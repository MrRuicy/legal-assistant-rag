"""Agent 工具集：法条交叉引用、时效计算等专用工具，让 Agent 会用工具而非只会检索。

Phase 3 扩展：这些工具在 Reflect 节点判断需要时被调用，补全缺失的关联信息。
同时包含 Agent 节点需要的辅助函数（RetrieveTool、merge_dedup_hits 等）。
"""
import re
from typing import List, Dict, Optional
from datetime import datetime
from .vector_store import VectorStore


def _add_years(dt: datetime, years: int) -> datetime:
    """日期加 N 年（按日历年，非 365 天）。

    2/29 起算且目标年非闰年时回退到 2/28（法律时效边界以日历年计，闰年不另算一天）。
    """
    try:
        return dt.replace(year=dt.year + years)
    except ValueError:
        # 2 月 29 日 → 目标年无该日，落到 2 月 28 日
        return dt.replace(year=dt.year + years, day=28)


# ---- Agent 节点辅助工具（检索、去重、格式化）----

class RetrieveTool:
    """检索工具：封装 VectorStore 的混合检索，供 Retrieve 节点调用。"""

    def __init__(self, vector_store: VectorStore):
        self.vector_store = vector_store

    def search(self, query: str, top_k: int = 8) -> List[Dict]:
        """执行混合检索（向量 + BM25 + RRF），返回条文列表。

        Returns:
            [{"law": "劳动合同法", "article": "47", "content": "...", ...}]
        """
        return self.vector_store._hybrid_search(query, top_k=top_k)


def merge_dedup_hits(hit_lists: List[List[Dict]]) -> List[Dict]:
    """合并多次检索结果并去重（按 law_name#article_no 去重，保留首次出现）。

    Args:
        hit_lists: 多次检索的结果列表，如 [[hit1, hit2], [hit3, hit1], ...]

    Returns:
        去重后的 hits，保持首次出现顺序
    """
    seen = set()
    merged = []
    for hits in hit_lists:
        for h in hits:
            key = f"{h.get('law_name', '')}#{h.get('article_no', '')}"
            if key not in seen:
                seen.add(key)
                merged.append(h)
    return merged


def format_articles_context(hits: List[Dict]) -> str:
    """将条文列表格式化为 LLM 上下文（Answer 节点用）。

    格式：《法律名》第X条：【条文全文】
    """
    if not hits:
        return ""
    lines = []
    for h in hits:
        law = h.get("law_name", "未知法律")
        article = h.get("article_no", "?")
        content = h.get("article_text", "")
        lines.append(f"《{law}》第{article}条：\n{content}\n")
    return "\n".join(lines)


def _normalize_article_no(raw: str) -> Optional[str]:
    """把条号文本规整成阿拉伯数字字符串。

    接受阿拉伯数字（"47"）或中文数字（"四十七"），返回 "47"；无法解析返回 None。
    Reflect/正则抓到的条号可能是任一种，统一规整后才能拼 article_id 命中条文。
    """
    raw = raw.strip()
    if not raw:
        return None
    if raw.isdigit():
        return str(int(raw))
    try:
        from .parser import chinese_to_arabic
        return str(chinese_to_arabic(raw))
    except Exception:
        return None


# ---- Phase 3 专用工具（交叉引用 / 时效计算）----

class LegalTools:
    """法律问答专用工具集，供 Agent 调用。"""

    def __init__(self, vector_store: VectorStore):
        self.vector_store = vector_store
        # 懒加载：首次调用交叉引用工具时才构建引用图（避免启动慢）
        self._reference_graph: Optional[Dict[str, List[Dict]]] = None
        # id -> 条文 dict（{law_name, article_no, article_text}），建图时一并缓存，
        # 供 get_article 直接按条号取条文原文（Reflect 补全缺失条文用）。
        self._id_to_doc: Optional[Dict[str, Dict]] = None
        # 库内全部法律全称集合，用于把 LLM 给的简称（《民法典》）解析成库内全称
        # （中华人民共和国民法典），否则精确拼 id 永远命中不了。
        self._law_names: Optional[set] = None

    def _ensure_graph(self) -> None:
        if self._reference_graph is None or self._id_to_doc is None:
            self._build_reference_graph()

    def _resolve_law_name(self, law: str) -> Optional[str]:
        """把 LLM 给的法律名（常为简称）解析成库内全称。

        匹配顺序：精确 → 补"中华人民共和国"前缀 → 去前缀后相等 → 互相包含（取最短）。
        无法匹配返回 None。
        """
        if not law or not self._law_names:
            return None
        if law in self._law_names:
            return law
        prefixed = f"中华人民共和国{law}"
        if prefixed in self._law_names:
            return prefixed
        stripped = law.replace("中华人民共和国", "")
        same = [n for n in self._law_names if n.replace("中华人民共和国", "") == stripped]
        if same:
            return same[0]
        # 兜底：互相包含（如"民法典" ⊂ "中华人民共和国民法典"），取最短全称
        contains = [n for n in self._law_names if stripped in n or n in stripped]
        return min(contains, key=len) if contains else None

    def _resolve_article_id(self, article_id: str) -> Optional[str]:
        """把 "简称#条号" 规整成库内 "全称#条号"；无法解析返回 None。"""
        if "#" not in article_id:
            return None
        law, _, no = article_id.partition("#")
        full = self._resolve_law_name(law)
        return f"{full}#{no}" if full else None

    def get_article(self, article_id: str, with_references: bool = True) -> List[Dict]:
        """按条号取条文原文本身（可选连带它直接引用的条文）。

        这是 Reflect「缺第X条」场景的正解：Reflect 说"缺第47条"意思是要第47条的
        原文，所以先返回该条本身；with_references=True 时再附上它引用的条文，顺藤摸瓜。

        Args:
            article_id: 法条 ID，格式 "法律名#条号"（法律名可为简称，会自动解析为库内全称）
            with_references: 是否连带返回该条直接引用的其他条文

        Returns:
            条文 dict 列表 [{"law_name","article_no","article_text"}]；该条不存在则返回 []。
        """
        self._ensure_graph()
        resolved_id = self._resolve_article_id(article_id) or article_id
        doc = self._id_to_doc.get(resolved_id)
        if not doc:
            return []
        result = [doc]
        if with_references:
            for ref in self.lookup_referenced_articles(resolved_id, max_depth=1):
                result.append(ref)
        return result

    def lookup_referenced_articles(self, article_id: str, max_depth: int = 1) -> List[Dict]:
        """法条交叉引用查询：给定一条法条，返回它直接引用的其他条文。

        用例：补全某条文正文里"依照本法第X条"所指向、但不在上下文的关联条文。

        Args:
            article_id: 法条 ID，格式 "法律名#条号"（如 "中华人民共和国劳动合同法#47"）
            max_depth: 引用深度（1=仅直接引用，2=引用的引用，...）默认1避免爆炸

        Returns:
            被引用条文列表 [{"law_name","article_no","article_text"}]
            空列表表示该条文不引用其他条文或引用图未建立。
        """
        self._ensure_graph()

        result = []
        visited = set()
        queue = [(article_id, 0)]  # (id, 当前深度)

        while queue:
            current_id, depth = queue.pop(0)
            if current_id in visited or depth >= max_depth:
                continue
            visited.add(current_id)

            refs = self._reference_graph.get(current_id, [])
            for ref in refs:
                # 引用图存的是 id_to_doc 的条文 dict，键为 law_name / article_no。
                ref_id = f"{ref['law_name']}#{ref['article_no']}"
                if ref_id not in visited:
                    result.append(ref)
                    if depth + 1 < max_depth:
                        queue.append((ref_id, depth + 1))

        return result

    def _build_reference_graph(self) -> None:
        """构建法条引用图：解析每条法条内容，提取"第X条"/"本法第Y条"等引用模式。

        引用模式示例：
        - "依照本法第四十七条" → 同法第47条
        - "适用《民法典》第一千零三十四条" → 民法典#1034
        - "按照第二百零三条执行" → 同法第203条（需上下文推断法律名）

        存入 self._reference_graph = {"劳动合同法#48": [{"law_name":"劳动合同法","article_no":"47","article_text":"..."}]}
        同时缓存 self._id_to_doc 供 get_article 按条号直接取条文原文。
        """
        self._reference_graph = {}
        self._id_to_doc = {}
        self._law_names = set()
        all_articles = self.vector_store.collection.get(include=["metadatas", "documents"])
        if not all_articles or not all_articles.get("ids"):
            return

        # 构建 ID → 文档映射，用于反查被引用条文的内容
        id_to_doc = self._id_to_doc
        for i, doc_id in enumerate(all_articles["ids"]):
            meta = all_articles["metadatas"][i]
            content = all_articles["documents"][i]
            law_name = meta.get("law_name", "")
            id_to_doc[doc_id] = {
                "law_name": law_name,
                "article_no": meta.get("article_no", ""),
                "article_text": content
            }
            if law_name:
                self._law_names.add(law_name)

        # 解析每条法条，提取引用
        for doc_id, doc in id_to_doc.items():
            content = doc["article_text"]
            law = doc["law_name"]
            refs = []

            # 模式1：同法引用 "第X条"（中文数字）
            for match in re.finditer(r"第([一二三四五六七八九十百千零]+)条", content):
                article_cn = match.group(1)
                try:
                    from .parser import chinese_to_arabic
                    article_num = str(chinese_to_arabic(article_cn))
                    ref_id = f"{law}#{article_num}"
                    if ref_id in id_to_doc and ref_id != doc_id:
                        refs.append(id_to_doc[ref_id])
                except Exception:
                    pass  # 解析失败忽略

            # 模式2：跨法引用 "《XXX》第Y条"（简化：只匹配书名号+第X条，实际可更复杂）
            for match in re.finditer(r"《([^》]+)》第([一二三四五六七八九十百千零]+)条", content):
                ref_law = match.group(1)
                article_cn = match.group(2)
                try:
                    from .parser import chinese_to_arabic
                    article_num = str(chinese_to_arabic(article_cn))
                    ref_id = f"{ref_law}#{article_num}"
                    if ref_id in id_to_doc:
                        refs.append(id_to_doc[ref_id])
                except Exception:
                    pass

            if refs:
                self._reference_graph[doc_id] = refs

    def calculate_statute_of_limitations(
        self, case_type: str, incident_date: str, query_date: Optional[str] = None
    ) -> Dict:
        """诉讼/仲裁时效计算工具：判断某事件是否已过时效。

        用例：用户问"2020年被辞退现在还能仲裁吗" → Agent 调此工具获取时效判断。

        Args:
            case_type: 案件类型，可选值 "labor"(劳动争议)/"civil"(民事)/"criminal"(刑事)
            incident_date: 权利被侵害日期，格式 "YYYY-MM-DD"（如 "2020-03-15"）
            query_date: 查询日期（默认今天），格式同上

        Returns:
            {
                "limitation_years": 时效年限（如 1 / 3 / 20）,
                "deadline": 时效截止日 "YYYY-MM-DD",
                "is_expired": 是否已过期 (bool),
                "days_remaining": 剩余天数（负数=已过期N天）,
                "legal_basis": 依据条文（如 "《劳动争议调解仲裁法》第27条"）,
                "note": 补充说明（如"从知道或应当知道权利被侵害之日起算"）
            }
        """
        # 时效规则表（实际应从法条库提取，这里硬编码常见规则作演示）
        rules = {
            "labor": {
                "years": 1,
                "basis": "《劳动争议调解仲裁法》第27条",
                "note": "劳动争议申请仲裁的时效期间为一年，从当事人知道或者应当知道其权利被侵害之日起计算。",
            },
            "civil": {
                "years": 3,
                "basis": "《民法典》第188条",
                "note": "向人民法院请求保护民事权利的诉讼时效期间为三年。",
            },
            "criminal": {
                "years": 20,
                "basis": "《刑法》第87条",
                "note": "犯罪经过下列期限不再追诉：法定最高刑为无期徒刑、死刑的，经过二十年（此处简化为最长追诉期）。",
            },
        }

        rule = rules.get(case_type.lower())
        if not rule:
            return {
                "error": f"不支持的案件类型: {case_type}，可选值: labor/civil/criminal",
            }

        try:
            incident_dt = datetime.strptime(incident_date, "%Y-%m-%d")
            query_dt = datetime.strptime(query_date, "%Y-%m-%d") if query_date else datetime.now()
            # 按"年"加而非 365 天/年，避免闰年累计误差影响"是否刚好过期"的边界判断。
            deadline_dt = _add_years(incident_dt, rule["years"])
            days_remaining = (deadline_dt - query_dt).days

            return {
                "limitation_years": rule["years"],
                "deadline": deadline_dt.strftime("%Y-%m-%d"),
                "is_expired": days_remaining < 0,
                "days_remaining": days_remaining,
                "legal_basis": rule["basis"],
                "note": rule["note"],
            }
        except ValueError as e:
            return {"error": f"日期格式错误: {e}，请使用 YYYY-MM-DD 格式"}


# ---- Phase 1 固定多跳检索（评估用占位实现）----

def fixed_multihop_retrieve(llm_complete, tool: RetrieveTool, question: str,
                            per_hop_top_k: int) -> Dict:
    """Phase 1 固定多跳检索占位实现(eval_multihop.py --mode fixed 用)。

    固定策略: LLM 拆成 2 个子问题 → 两跳检索 → 去重合并。
    足够复现 phase1_fixed_multihop.json 结果,不求完美(Agent 已超过它)。

    Args:
        llm_complete: LegalRAG._complete 方法(用于调 LLM 拆子问题)
        tool: RetrieveTool 实例(用于检索)
        question: 原问题
        per_hop_top_k: 每跳检索条数

    Returns:
        {"merged": 合并去重后的 hits, "hops": 跳数, "subs": 子问题列表}
    """
    # 简化版拆解 prompt:固定拆 2 个子问题
    subs_prompt = (
        f"把下面这个法律问题拆解成 2 个具体的子问题,每行一个,直接输出子问题不要编号:\n"
        f"{question}"
    )
    try:
        subs_raw = llm_complete(
            messages=[{"role": "user", "content": subs_prompt}],
            temperature=0,
        )
        # 解析子问题(去掉编号、空行)
        import re
        lines = subs_raw.strip().split('\n')
        subs = []
        for line in lines:
            line = re.sub(r'^[-*•\d+.)\s]+', '', line).strip()  # 去编号
            if line and len(line) > 3:
                subs.append(line)
        # 容错:拆解失败则用原问题 + 简化版
        if not subs:
            subs = [question]
        elif len(subs) == 1:
            subs.append(question)  # 只拆出 1 个,补原问题作第二跳
        subs = subs[:2]  # 固定两跳
    except Exception:
        # LLM 调用失败:降级为单跳
        subs = [question]

    # 逐跳检索 → 累积
    all_hits = []
    for sub in subs:
        hits = tool.search(sub, top_k=per_hop_top_k)
        all_hits.extend(hits)

    # 去重合并(按 law_name + article_no)
    merged = merge_dedup_hits([all_hits])

    return {
        "merged": merged,
        "hops": len(subs),
        "subs": subs,
    }


# 全局单例（避免重复构建引用图）
_tools_instance: Optional[LegalTools] = None


def get_legal_tools(vector_store: VectorStore) -> LegalTools:
    """获取工具集单例（Web 服务端复用，避免重复构建引用图）。"""
    global _tools_instance
    if _tools_instance is None:
        _tools_instance = LegalTools(vector_store)
    return _tools_instance
