"""多跳检索 Agent（LangGraph 状态机）。

把单跳检索链升级为「会自己判断信息够不够、还要查什么」的多跳 Agent。
复用现有检索栈（vector_store + bm25 + rrf）与 LegalRAG 的 prompt / 引用校验 / 故障转移，
只在外层加规划（Planner）、反思（Reflect）、跳数控制（max_hops）。

图结构（见 PLAN.md 二）：

    Planner ──简单──────────────────────────► Answer ──► END
       │                                          ▲
       └──复杂──► Retrieve ──► Reflect ──够了──────┘
                     ▲            │
                     └───不够─────┘ （受 max_hops 硬上限约束，防死循环）

设计取舍：
- 模型分级：Planner / Reflect 用便宜模型（config.planner_providers），Answer 用强模型。
- 可降级：Planner 判断是简单问题 → 直接走单跳检索 + Answer，不为难简单题（守住回归底线）。
- 去重：每跳生成的新子问题先去掉「已查过的」，避免反复查同一点。
- 可观测：每个节点往 state['trace'] 追加一条记录（查了啥、Reflect 怎么判断），便于调试与前端展示。
"""
import json
import re
from typing import List, Dict, TypedDict, Optional

from langgraph.graph import StateGraph, END

from . import config
from .rag import LegalRAG
from .tools import (
    RetrieveTool,
    merge_dedup_hits,
    format_articles_context,
    _normalize_article_no,
)


class AgentState(TypedDict, total=False):
    """多跳 Agent 的流转状态。"""
    question: str                 # 用户原问题（已经过查询改写）
    history: List[Dict]           # 对话历史（供 Answer 承接上文）
    pending: List[str]            # 待检索的子问题队列
    asked: List[str]              # 已检索过的子问题（去重用）
    hits: List[Dict]              # 累积召回、合并去重后的条文
    hop: int                      # 当前跳数（每次 Retrieve +1）
    is_complex: bool              # Planner 判断：是否需要多跳
    answer: str                   # 最终答案
    verify: Dict                  # 引用校验结果
    trace: List[Dict]             # 可观测日志（逐节点）


# ---- Planner ----

_PLANNER_SYSTEM = """你是中国法律问答的规划助手。判断回答用户问题需要查几个法律点。

- 若问题只需单一法条/单一法律点即可完整回答（如"诉讼时效几年""试用期最长多久"），判为简单。
- 若问题涉及多个法律点、跨多部法律、或含"怎么办/如何维权/还要承担什么责任/区别"等需要
  组合多方面（定性、责任、计算、程序、时效等）才能答全的，判为复杂，并拆成 2~4 个彼此独立、
  各指向一个法律点的检索子问题。

只输出 JSON：
- 简单：{"complex": false, "subs": ["<可直接检索的问题>"]}
- 复杂：{"complex": true, "subs": ["子问题1","子问题2","子问题3"]}
子问题要含具体法律术语，彼此不重复。不要任何解释或前后缀。"""


def _planner_node(rag: LegalRAG):
    def node(state: AgentState) -> AgentState:
        q = state["question"]
        providers = config.planner_providers()
        try:
            raw = rag._complete(
                messages=[
                    {"role": "system", "content": _PLANNER_SYSTEM},
                    {"role": "user", "content": f"问题：{q}\n请判断并只输出 JSON。"},
                ],
                temperature=0,
                providers=providers,
            )
            obj = _parse_obj(raw)
            is_complex = bool(obj.get("complex", False))
            subs = [s.strip() for s in obj.get("subs", []) if isinstance(s, str) and s.strip()]
        except Exception:
            is_complex, subs = False, []

        # 降级：解析失败或没给子问题 → 退回用原问题单跳
        if not subs:
            subs = [q]
            is_complex = False
        subs = subs[:config.MAX_HOPS]

        trace = state.get("trace", [])
        trace.append({
            "node": "planner",
            "is_complex": is_complex,
            "subs": subs,
        })
        return {
            "pending": subs,
            "asked": [],
            "hits": [],
            "hop": 0,
            "is_complex": is_complex,
            "trace": trace,
        }
    return node


# ---- Retrieve ----

def _retrieve_node(tool: RetrieveTool):
    def node(state: AgentState) -> AgentState:
        pending = state.get("pending", [])
        asked = state.get("asked", [])
        prev_hits = state.get("hits", [])

        # 逐个检索本轮待查子问题（去掉已查过的，防重复）
        fresh = [s for s in pending if s not in asked]
        new_hit_lists = [tool.search(s, top_k=config.AGENT_PER_HOP_TOP_K) for s in fresh]

        # 合并去重：把历史召回与本轮召回一起去重（保留先到的）
        merged = merge_dedup_hits([prev_hits] + new_hit_lists)

        hop = state.get("hop", 0) + 1
        asked = asked + fresh

        trace = state.get("trace", [])
        trace.append({
            "node": "retrieve",
            "hop": hop,
            "queried": fresh,
            "n_hits_total": len(merged),
        })
        return {
            "hits": merged,
            "asked": asked,
            "pending": [],     # 本轮已消费，等 Reflect 决定下一轮查什么
            "hop": hop,
            "trace": trace,
        }
    return node


# ---- Reflect ----

_REFLECT_SYSTEM = """你是中国法律问答的反思助手。已检索到一批法律条文，请核查它们是否足以
**完整**回答用户问题——重点是"完整"，法律问题常含多个诉求点，漏掉任一点都会让回答残缺。

【重要·工具使用规则】
当发现缺失条文时，优先判断能否用工具直接补全（比检索更快更准）：
1. **交叉引用工具**：如果已召回的条文里提到"依照本法第X条""适用第Y条"等，但引用的条文不在
   上下文，在 missing 里写 "第X条" 或 "《XX法》第Y条"（必须包含具体条号），系统会自动调用
   交叉引用工具补全该条文原文。
2. **时效计算工具**：如果用户问题涉及"能否仲裁/起诉""是否过时效"，且已知事件日期，可在 missing
   里写 "时效计算：<案件类型>，事件日期<YYYY-MM-DD>"（如"时效计算：劳动争议，事件日期2020-06-15"），
   系统会自动计算时效并给出判断。

工具无法处理的（如宽泛的法律概念查询、跨领域衔接），再用普通检索子问题。

判断步骤（在心里做，不要输出过程）：
1. 先拆出用户问题包含的**所有诉求点**。例如"被违法辞退能不能告、怎么告"含两点：①能否主张赔偿
   ②如何维权（仲裁程序/时效）；"买到假货赔几倍、还要担什么责"含两点：①赔偿倍数 ②其他责任。
2. 逐一核对：每个诉求点是否都有对应条文支撑？常见易漏的方面——
   责任后果、赔偿计算标准、救济程序（仲裁/诉讼/复议）、时效期限、跨部门法的衔接（如刑民交叉）。
3. 检查已召回条文的**条文内交叉引用**：若条文正文里出现"依照XX条""适用XX法第Y条"，而被引用
   的条文不在当前上下文，立即在 missing 里补上该条号（触发工具补全）。
4. 只要有**任一诉求点缺乏条文支撑**，就判 sufficient=false，并给出 1~2 个精准的补充子问题。

输出格式（只输出 JSON，不要解释）：
- 已覆盖所有诉求点：{"sufficient": true, "missing": []}
- 仍缺某方面：{"sufficient": false, "missing": ["<针对缺失点的检索子问题或工具调用>", ...]}
  子问题要含具体法律术语（如"劳动争议仲裁时效""惩罚性赔偿计算"），且不与已查过的重复。
  优先用工具格式（"第X条""时效计算：..."），工具解决不了的再用语义检索子问题。

判断尺度：宁可补全也别留缺口。但若所有诉求点确已覆盖，不要为了凑数而补无关的跳。"""


def _reflect_node(rag: LegalRAG, tools):
    """Reflect 节点：判断已召回的条文是否足够完整，决定是否补跳。

    Phase 3 工具集成：先尝试用工具（交叉引用）直接补全，工具解决不了的再走检索。
    """
    def node(state: AgentState) -> AgentState:
        hop = state.get("hop", 0)
        asked = state.get("asked", [])
        hits = state.get("hits", [])

        # 到达跳数硬上限：强制收敛，不再反思（防死循环 / 成本爆炸）
        if hop >= config.MAX_HOPS:
            trace = state.get("trace", [])
            trace.append({"node": "reflect", "hop": hop, "decision": "stop_max_hops"})
            return {"pending": [], "trace": trace}

        # 已召回条文摘要（只给法律名+条号+首句，省 token）
        summary = _hits_summary(hits)
        asked_text = "\n".join(f"- {a}" for a in asked)
        providers = config.planner_providers()
        try:
            raw = rag._complete(
                messages=[
                    {"role": "system", "content": _REFLECT_SYSTEM},
                    {"role": "user", "content": (
                        f"用户问题：{state['question']}\n\n"
                        f"已检索的子问题：\n{asked_text}\n\n"
                        f"已召回的条文（摘要）：\n{summary}\n\n"
                        f"请先在心里拆出问题的所有诉求点，逐一核对是否都有条文支撑，"
                        f"再判断是否足够并只输出 JSON。"
                    )},
                ],
                temperature=0,
                providers=providers,
            )
            obj = _parse_obj(raw)
            sufficient = bool(obj.get("sufficient", True))
            missing = [s.strip() for s in obj.get("missing", []) if isinstance(s, str) and s.strip()]
        except Exception:
            sufficient, missing = True, []  # 反思失败 → 当作够了，去作答（不阻断）

        # 去掉已查过的，避免重复
        missing = [m for m in missing if m not in asked]

        # Phase 3: 工具补全（交叉引用 + 时效计算）——能用工具直接解决的就不走检索。
        # 每个工具调用都包 try/except：工具内部异常绝不能冒泡打挂整条 Agent 链，
        # 失败时该 miss 退回普通检索（below），不阻断作答。
        tool_resolved_missing = []
        tool_added_hits = []
        for miss in missing:
            try:
                # 工具1：交叉引用 - 仅当 miss 本身是「干净条号引用」时才走工具。
                # 长语义子问题（碰巧含条号）走普通检索，避免短路语义召回（Phase 3 评估教训）。
                if _is_clean_article_ref(miss):
                    # 匹配 "《XX法》第Y条" / "第X条"（阿拉伯或中文数字），容忍空格。
                    match = re.search(
                        r'《([^》]+)》\s*第\s*([0-9一二三四五六七八九十百千零两]+)\s*条'
                        r'|第\s*([0-9一二三四五六七八九十百千零两]+)\s*条',
                        miss,
                    )
                else:
                    match = None
                if match:
                    law = match.group(1) or ""
                    article_raw = match.group(2) or match.group(3)
                    article = _normalize_article_no(article_raw)
                    # 如果没明确法律名，从已有 hits 推断（取第一个 hit 的法律名）
                    if not law and hits:
                        law = hits[0].get("law_name", "")
                    if law and article:
                        article_id = f"{law}#{article}"
                        # 正解：Reflect 说"缺第X条"是要第X条的原文本身（连带其引用），
                        # 而非它引用的条文。get_article 返回该条本身 + 直接引用。
                        added = tools.get_article(article_id, with_references=True)
                        if added:
                            tool_resolved_missing.append(miss)
                            tool_added_hits.extend(added)
                            continue  # 已处理，跳过后续检查

                # 工具2：时效计算 - 匹配 "时效计算：<类型>，事件日期<YYYY-MM-DD>"
                time_match = re.search(r'时效计算[：:]\s*([^，,]+)[，,]\s*事件日期\s*(\d{4}-\d{2}-\d{2})', miss)
                if time_match:
                    case_type_raw = time_match.group(1).strip()
                    incident_date = time_match.group(2)
                    # 映射中文类型到工具参数
                    case_type_map = {
                        "劳动争议": "labor", "劳动": "labor", "劳动仲裁": "labor",
                        "民事": "civil", "民事诉讼": "civil",
                        "刑事": "criminal", "刑事案件": "criminal"
                    }
                    case_type = case_type_map.get(case_type_raw, "civil")  # 默认民事
                    result = tools.calculate_statute_of_limitations(case_type, incident_date)
                    if "error" not in result:
                        # 将时效计算结果转成虚拟"条文"格式，注入上下文
                        virtual_hit = {
                            "law_name": "时效计算结果",
                            "article_no": "自动计算",
                            "article_text": (
                                f"案件类型：{case_type_raw}\n"
                                f"时效期限：{result['limitation_years']}年\n"
                                f"诉讼时效截止日期：{result['deadline']}\n"
                                f"是否已过期：{'是' if result['is_expired'] else '否'}\n"
                                f"剩余天数：{result['days_remaining']}天\n"
                                f"法律依据：{result['legal_basis']}\n"
                                f"注意：{result['note']}"
                            )
                        }
                        tool_resolved_missing.append(miss)
                        tool_added_hits.append(virtual_hit)
            except Exception:
                # 工具失败：不解决该 miss，留给下方普通检索兜底
                continue

        # 工具补全的 hits 合并到状态（去重）
        if tool_added_hits:
            hits = merge_dedup_hits([hits, tool_added_hits])

        # 移除工具已解决的 missing，剩下的才需要检索
        missing = [m for m in missing if m not in tool_resolved_missing]

        decision = "answer" if (sufficient or not missing) else "continue"
        trace = state.get("trace", [])
        trace.append({
            "node": "reflect",
            "hop": hop,
            "decision": decision,
            "missing": missing if decision == "continue" else [],
            "tool_resolved": tool_resolved_missing,  # 记录工具解决了哪些
            "tool_added_hits": len(tool_added_hits),  # 工具补全了几条
        })
        return {
            "pending": missing if decision == "continue" else [],
            "hits": hits if tool_added_hits else state.get("hits", []),  # 工具补全时更新 hits
            "trace": trace,
        }
    return node


# ---- Answer ----

def _answer_node(rag: LegalRAG):
    def node(state: AgentState) -> AgentState:
        hits = state.get("hits", [])
        question = state["question"]

        if not hits:
            return {
                "answer": "未找到相关法律条文，无法回答该问题。",
                "verify": {"status": "none", "cited": [], "fabricated": [], "message": "无检索结果。"},
            }

        # 多跳累积的条文去重后可能很多 → 截断到 AGENT_MAX_CONTEXT，控制上下文长度与成本。
        # hits 已按召回先后去重，靠前的更相关，故直接取前 N 条。
        if len(hits) > config.AGENT_MAX_CONTEXT:
            hits = hits[:config.AGENT_MAX_CONTEXT]

        # 复用 LegalRAG 的 system prompt 与上下文格式（含法律名、强制引用、免责）
        context = format_articles_context(hits)
        system_prompt = rag._system_prompt(hits)
        user_prompt = (
            f"问题：{question}\n\n"
            f"检索到的相关条文：\n{context}\n\n"
            f'请根据上述条文回答问题，引用时写明"《法律名》第X条"。'
        )
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(rag._recent_history_messages(state.get("history")))
        messages.append({"role": "user", "content": user_prompt})

        # Answer 用强模型（默认故障转移链，不传 providers）
        answer_text = rag._complete(messages=messages, temperature=0.1)
        verify = rag._verify_citations(answer_text, hits)

        trace = state.get("trace", [])
        trace.append({"node": "answer", "n_context": len(hits)})
        return {"answer": answer_text, "verify": verify, "hits": hits, "trace": trace}
    return node


# ---- 路由 ----

def _route_after_retrieve(state: AgentState) -> str:
    # 简单题：检索一次即作答（等价单跳，守住回归底线，不为难简单题）。
    # 复杂题：进 Reflect 判断够不够、要不要补跳。
    return "reflect" if state.get("is_complex") else "answer"


def _route_after_reflect(state: AgentState) -> str:
    # Reflect 给了新的待查子问题 → 继续检索；否则去作答
    return "retrieve" if state.get("pending") else "answer"


# ---- 辅助 ----

def _is_clean_article_ref(miss: str) -> bool:
    """判断 miss 是否是「干净的条号引用」（应走交叉引用工具），而非长语义子问题。

    背景（Phase 3 评估暴露的问题）：交叉引用工具用 re.search 在整个 miss 里找「第X条」，
    导致 Reflect 输出的长语义子问题（只是碰巧提到条号，如「第1038条提及的赔偿责任如何
    结合第1182条计算」）被误判为可用条号工具解决，短路掉本该走的语义检索 → Coverage 塌方。

    判据：去掉法律名《…》、条号「第X条(之N)(第Y款)」、标点空格后，剩余实质字符 ≤ 3。
    即 miss 通篇就是在指一条/几条具体条文，没有额外的语义查询意图。
    """
    s = miss.strip()
    if not s:
        return False
    # 去掉书名号法律名
    s = re.sub(r'《[^》]+》', '', s)
    # 去掉条号引用：第X条、第X条之一、第X条第Y款/项
    s = re.sub(r'第\s*[0-9一二三四五六七八九十百千零两]+\s*条'
               r'(之[一二三四五六七八九十]+)?'
               r'(第?\s*[0-9一二三四五六七八九十]+\s*[款项])?', '', s)
    # 去掉常见连接词与标点
    s = re.sub(r'[、，,。；;：:\s和与及关于的（）()]', '', s)
    return len(s) <= 3


def _parse_obj(raw: str) -> Dict:
    """从 LLM 输出抠出 JSON 对象（容忍 ```json 围栏与前后噪声）。"""
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        nl = text.find("\n")
        if nl != -1:
            text = text[nl + 1:]
    try:
        start, end = text.index("{"), text.rindex("}") + 1
        return json.loads(text[start:end])
    except Exception:
        return {}


def _hits_summary(hits: List[Dict], max_chars: int = 40) -> str:
    lines = []
    for h in hits:
        short = h.get("law_name", "").replace("中华人民共和国", "")
        txt = h["article_text"][:max_chars].replace("\n", " ")
        lines.append(f"- 《{short}》第{h['article_no']}条：{txt}…")
    return "\n".join(lines)


class LegalAgent:
    """多跳检索 Agent 的对外封装。

    用法：
        agent = LegalAgent()
        result = agent.run("被公司违法辞退没补偿能不能告？怎么告？")
        # result = {answer, references, verify, trace, hops, disclaimer}
    """

    def __init__(self, rag: LegalRAG = None):
        self.rag = rag or LegalRAG()
        self.tool = RetrieveTool(self.rag.vector_store)  # 复用同一 VectorStore
        # Phase 3: 初始化工具集（交叉引用 / 时效计算）
        from .tools import get_legal_tools
        self.tools = get_legal_tools(self.rag.vector_store)
        self.graph = self._build_graph()

    def _build_graph(self):
        g = StateGraph(AgentState)
        g.add_node("planner", _planner_node(self.rag))
        g.add_node("retrieve", _retrieve_node(self.tool))
        g.add_node("reflect", _reflect_node(self.rag, self.tools))  # 传入工具集
        g.add_node("answer", _answer_node(self.rag))

        g.set_entry_point("planner")
        # Planner 永远先走 Retrieve（简单题也要召回一次，否则无条文可答）。
        g.add_edge("planner", "retrieve")
        # Retrieve 后：简单题直接作答；复杂题进 Reflect 判断是否补跳。
        g.add_conditional_edges("retrieve", _route_after_retrieve,
                                {"reflect": "reflect", "answer": "answer"})
        g.add_conditional_edges("reflect", _route_after_reflect,
                                {"retrieve": "retrieve", "answer": "answer"})
        g.add_edge("answer", END)
        return g.compile()

    def run(self, question: str, history: List[Dict] = None) -> Dict:
        """跑完整多跳流程，返回答案 + 引用 + 轨迹（非流式，用于评估）。"""
        final = self.graph.invoke({
            "question": question,
            "history": history or [],
        })
        return {
            "answer": final.get("answer", ""),
            "references": final.get("hits", []),
            "verify": final.get("verify", {}),
            "trace": final.get("trace", []),
            "hops": final.get("hop", 0),
            "disclaimer": self.rag._disclaimer(),
        }

    def run_stream(self, question: str, history: List[Dict] = None):
        """流式包装器：用 graph.stream 逐节点实时 yield，让多跳轨迹像「思考过程」
        一样边跑边冒出来（而非整图跑完才一次性出现）。

        Yields:
            Dict，每个 chunk:
            {
                "type": "trace" | "references" | "answer" | "verify" | "disclaimer",
                "content": ...
            }
        - 每个节点（planner/retrieve/reflect）跑完即 yield 一次累积 trace，前端实时重绘轨迹。
        - answer 节点跑完再 yield references / answer / verify / disclaimer。
        与单跳 answer_stream 口径对齐，便于 web.py 统一处理。
        """
        trace_acc: List[Dict] = []      # 累积轨迹（增量拼接）
        final_state: Dict = {}          # 最后一个节点的完整状态
        try:
            for chunk in self.graph.stream(
                {"question": question, "history": history or []},
                stream_mode="updates",
            ):
                # updates 模式：{node_name: 该节点返回的状态增量}
                for node_name, delta in chunk.items():
                    if not isinstance(delta, dict):
                        continue
                    final_state.update(delta)
                    # 该节点若产出了新 trace 记录，累积并实时 yield
                    node_trace = delta.get("trace")
                    if node_trace:
                        trace_acc = node_trace  # trace 在状态里是全量累积的，直接用最新值
                        yield {"type": "trace", "content": list(trace_acc)}
        except Exception:
            # 图执行异常：退回非流式，至少给出已有结果（不阻断作答）
            final_state = self.graph.invoke(
                {"question": question, "history": history or []}
            )
            if final_state.get("trace"):
                yield {"type": "trace", "content": list(final_state["trace"])}

        # 节点跑完后，yield references / answer / verify / disclaimer
        yield {"type": "references", "content": final_state.get("hits", [])}
        yield {"type": "answer", "content": final_state.get("answer", "")}
        yield {"type": "verify", "content": final_state.get("verify", {})}
        yield {"type": "disclaimer", "content": self.rag._disclaimer()}


if __name__ == "__main__":
    # 烟雾测试：跑一道典型多跳题，打印轨迹 + 答案 + 引用校验
    agent = LegalAgent()
    q = "被公司违法辞退又没给经济补偿，能不能告？该怎么维权？"
    print(f"问题：{q}\n")
    result = agent.run(q)

    print("=== 检索轨迹 ===")
    for t in result["trace"]:
        print(" ", t)

    print(f"\n=== 答案（{result['hops']} 跳，引用 {len(result['references'])} 条）===")
    print(result["answer"])
    print(f"\n引用校验：{result['verify'].get('status')} — {result['verify'].get('message')}")
