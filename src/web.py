"""Gradio Web 界面（单栏对话 + 流式输出 + 答案内联校验/引用 + 锚点跳转 + 反馈）。

UI 风格：简洁现代——大圆角、留白、灰阶、弱描边，去掉视觉噪声。
布局：单栏、自适应视口。引用校验徽章 + 引用条文（整体可折叠）作为页脚
附在每条回答末尾，让对话流成为绝对主角。
"""
import json
import random
import re
import time
from html import escape
from typing import Dict, List, Optional

import gradio as gr

from . import config
from .parser import chinese_to_arabic
from .rag import LegalRAG, _strip_law_prefix
from .agent import LegalAgent


# 简洁现代风：大留白、大圆角、单一灰阶、几乎无边框
CUSTOM_CSS = """
:root {
    --bg: #f7f7f8;
    --surface: #ffffff;
    --border: #ebebed;
    --text: #18181b;
    --muted: #71717a;
    --accent: #18181b;
    --chip-bg: #ffffff;
    --chip-border: #e4e4e7;
    --chip-bg-hover: #f4f4f5;
    --link: #1f2937;
}

/* 自适应视口：宽度按比例 + 上限，避免写死；高度按视口 95% 留出底部余量 */
body { margin: 0; padding: 0; overflow-x: hidden; overflow-y: auto; }
.gradio-container {
    width: 94% !important;
    max-width: 1080px !important;
    margin: 0 auto !important;
    padding: 10px 0 12px 0 !important;
    min-height: 100vh;
}
body, .gradio-container {
    background: var(--bg) !important;
    color: var(--text) !important;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif !important;
}

/* 顶栏：极简，压缩上下边距 */
#app-header { text-align: left; margin: 0 2px 10px 2px; padding: 0; }
#app-header h1 { margin: 0; font-size: 1.35rem; font-weight: 650; letter-spacing: -0.015em; }
#app-header p { margin: 2px 0 0 0; color: var(--muted); font-size: 0.82rem; font-weight: 400; }

/* ── 对话外壳：相对定位容器，输入区/示例 chips 悬浮其内；高度按视口比例，确保输入框不被遮挡 ── */
#chat-shell {
    position: relative;
    height: calc(95vh - 80px) !important;
    min-height: 420px;
}

/* 对话区：填满外壳，大圆角弱描边 */
#chatbot {
    position: absolute !important;
    inset: 0 !important;
    height: 100% !important;
    border: 1px solid var(--border) !important;
    border-radius: 20px !important;
    background: var(--surface) !important;
    box-shadow: 0 1px 2px rgba(0,0,0,0.03) !important;
}
/* 给消息列表底部留白，避免最后一条被悬浮输入框遮住 */
#chatbot .message-wrap, #chatbot .bubble-wrap { padding-bottom: 96px !important; gap: 16px !important; }
#chatbot .message { font-size: 0.95rem; line-height: 1.72; border: none !important; }
#chatbot .message.user, #chatbot .message.user * {
    background: #1f2937 !important;
    color: #ffffff !important;
}
#chatbot .message.user {
    border-radius: 16px 16px 4px 16px !important;
    padding: 10px 14px !important;
}
#chatbot .message.bot {
    background: transparent !important;
    border-radius: 4px 16px 16px 16px !important;
}
#chatbot .message.bot a { color: var(--link) !important; }

/* ── 悬浮输入区：贴外壳底部（而非对话框底部），毛玻璃卡片，居中且左右对齐对话框 ── */
#input-row {
    position: absolute !important;
    left: 50%;
    bottom: 8px;
    transform: translateX(-50%);
    width: calc(100% - 2px) !important;  /* 比对话框窄 2px，视觉上内嵌 */
    max-width: calc(100% - 2px);
    z-index: 6;
    gap: 8px !important;
    align-items: center !important;
    background: rgba(255,255,255,0.95) !important;
    backdrop-filter: blur(14px);
    -webkit-backdrop-filter: blur(14px);
    border: 1px solid var(--chip-border) !important;
    border-radius: 17px !important;
    padding: 6px 6px 6px 6px !important;
    box-shadow: 0 4px 18px rgba(0,0,0,0.07) !important;
}
#input-row textarea {
    border: none !important;
    box-shadow: none !important;
    background: transparent !important;
    border-radius: 11px !important;
    padding: 9px 12px !important;
    font-size: 0.95rem !important;
}
#input-row textarea:focus { border: none !important; box-shadow: none !important; outline: none !important; }
#send-btn {
    border-radius: 12px !important;
    font-weight: 600 !important;
    background: #18181b !important;
    border: none !important;
    color: #fff !important;
    padding: 0 16px !important;
    height: 38px !important;
}
#send-btn:hover { background: #000 !important; }
#clear-btn {
    border-radius: 12px !important;
    background: #f4f4f5 !important;
    border: 1px solid var(--chip-border) !important;
    color: var(--muted) !important;
    font-weight: 500 !important;
    padding: 0 14px !important;
    height: 38px !important;
}
#clear-btn:hover { background: #e9e9eb !important; }

/* ── 深度模式开关：紧凑行，小字灰调 ── */
#agent-mode-row {
    position: absolute !important;
    left: 50%;
    bottom: 54px;  /* 在输入框上方，留足间距 */
    transform: translateX(-50%);
    width: calc(100% - 2px) !important;
    max-width: calc(100% - 2px);
    z-index: 5;
    gap: 0 !important;
    padding: 0 12px !important;
}
#agent-mode-checkbox label {
    font-size: 0.82rem !important;
    color: var(--muted) !important;
    font-weight: 400 !important;
    display: flex !important;
    align-items: center !important;
    gap: 6px !important;
}
#agent-mode-checkbox input[type="checkbox"] {
    margin: 0 !important;
    cursor: pointer !important;
}

/* ── 空状态：欢迎 + 示例 chips，悬浮于对话框中部（不占文档流高度）── */
#examples-wrap {
    position: absolute !important;
    left: 50%;
    top: 50%;
    transform: translate(-50%, -50%);
    width: min(680px, 86%);
    z-index: 4;
    padding: 0 !important;
    text-align: center;
}
#examples-head { display: flex; align-items: center; justify-content: center; gap: 10px; margin-bottom: 16px; }
#examples-head .examples-title { color: var(--muted); font-size: 0.92rem; font-weight: 500; }
#shuffle-btn {
    background: transparent !important;
    border: none !important;
    color: var(--muted) !important;
    font-size: 0.82rem !important;
    font-weight: 500 !important;
    padding: 4px 8px !important;
    min-width: 0 !important;
    width: auto !important;
    flex: 0 0 auto !important;
    border-radius: 8px !important;
}
#shuffle-btn:hover { background: var(--chip-bg-hover) !important; color: var(--text) !important; }

/* chips 容器：居中、单行自动换行，chip 等高、宽度随内容、不被拉伸 */
#chips-row { display: flex !important; flex-wrap: wrap !important; justify-content: center !important; gap: 9px !important; }
#chips-row > * { flex: 0 0 auto !important; width: auto !important; min-width: 0 !important; }
#chips-row button {
    background: var(--chip-bg) !important;
    color: var(--text) !important;
    border: 1px solid var(--chip-border) !important;
    border-radius: 999px !important;
    padding: 9px 16px !important;
    height: auto !important;
    font-size: 0.875rem !important;
    font-weight: 400 !important;
    line-height: 1.4 !important;
    white-space: nowrap !important;
    box-shadow: 0 1px 2px rgba(0,0,0,0.04) !important;
    transition: all 0.13s ease !important;
}
#chips-row button:hover {
    background: var(--chip-bg-hover) !important;
    border-color: #d4d4d8 !important;
    transform: translateY(-1px);
    box-shadow: 0 2px 8px rgba(0,0,0,0.07) !important;
}

/* ── 答案页脚：校验徽章 + 引用条文（整体可折叠），内联在每条回答末尾 ── */
.answer-footer { margin-top: 16px; }

/* 引用校验徽章：克制 */
.verify-badge { border-radius: 12px; padding: 9px 13px; line-height: 1.5; font-size: 0.84rem; margin-bottom: 9px; border: 1px solid; }
.verify-badge.ok { background: #f0fdf4; border-color: #bbf7d0; color: #15803d; }
.verify-badge.warn { background: #fffbeb; border-color: #fde68a; color: #b45309; }
.verify-badge.none { background: #f9fafb; border-color: #e5e7eb; color: #52525b; }
.verify-badge b { font-weight: 650; }

/* 引用条文整体折叠块 */
.refs-block { background: #fbfbfc; border: 1px solid var(--border); border-radius: 14px; padding: 0; overflow: hidden; }
.refs-block > summary { cursor: pointer; padding: 11px 15px; list-style: none; font-size: 0.86rem; font-weight: 600; color: var(--text); user-select: none; }
.refs-block > summary::-webkit-details-marker { display: none; }
.refs-block > summary .blk-arrow { color: var(--muted); font-size: 0.72rem; margin-right: 7px; display: inline-block; transition: transform 0.15s; }
.refs-block[open] > summary .blk-arrow { transform: rotate(90deg); }
.refs-block[open] > summary { border-bottom: 1px solid var(--border); }
.refs-block > summary .blk-count { color: var(--muted); font-weight: 400; margin-left: 5px; font-size: 0.8rem; }
.refs-block .refs-inner { padding: 9px 10px 10px 10px; }

/* 单条条文卡片（嵌套 details/summary） */
.ref-item { background: var(--surface); border: 1px solid #f0f0f1; border-radius: 11px; margin-bottom: 7px; transition: border-color 0.15s; }
.ref-item:last-child { margin-bottom: 0; }
.ref-item:hover { border-color: #e0e0e3; }
.ref-item:target { border-color: #1f2937; box-shadow: 0 0 0 2px rgba(31,41,55,0.1); animation: anchor-flash 1.3s ease-out; }
@keyframes anchor-flash { 0% { background: #fef9c3; } 100% { background: var(--surface); } }
.ref-item > summary { cursor: pointer; padding: 10px 13px; list-style: none; font-size: 0.875rem; line-height: 1.45; user-select: none; }
.ref-item > summary::-webkit-details-marker { display: none; }
.ref-item > summary .ref-title { font-weight: 600; color: var(--text); }
.ref-item > summary .ref-meta { display: block; color: var(--muted); font-size: 0.76rem; margin-top: 3px; }
.ref-item > summary .ref-arrow { float: right; color: var(--muted); transition: transform 0.15s; font-size: 0.72rem; margin-top: 3px; }
.ref-item[open] > summary .ref-arrow { transform: rotate(90deg); }
.ref-item .ref-body { padding: 9px 13px 11px 13px; color: #3f3f46; font-size: 0.875rem; line-height: 1.72; border-top: 1px solid #f4f4f5; margin: 2px 0 0 0; }

/* 答案中的条号锚点链接 */
.cite-link { color: var(--link); text-decoration: none; border-bottom: 1px dashed #a1a1aa; padding: 0 1px; transition: all 0.12s; }
.cite-link:hover { color: #000; border-bottom-color: #1f2937; background: #f4f4f5; border-radius: 3px; }

footer { display: none !important; }
"""


# 示例问题池：覆盖多部主要法律。空状态随机抽取 N 条作为 chips，「换一换」重抽。
EXAMPLE_POOL = [
    "父母与成年子女之间有哪些法定义务？",
    "用人单位拖欠工资可以怎么维权？",
    "公司股东出资有哪些方式？",
    "诉讼时效期间一般是多少年？",
    "消费者发现假货可以要求几倍赔偿？",
    "离婚时夫妻共同财产怎么分割？",
    "签了合同后能不能反悔？",
    "试用期最长可以约定多久？",
    "房屋租赁合同到期后房东能随意涨租吗？",
    "遗嘱有哪几种法定形式？",
    "交通事故责任如何认定？",
    "未成年人能否独立签订合同？",
    "劳动合同到期不续签有没有补偿？",
    "网购商品七天无理由退货有哪些例外？",
]
N_CHIPS = 4


def _sample_questions() -> List[str]:
    """随机抽取 N_CHIPS 个示例问题。"""
    k = min(N_CHIPS, len(EXAMPLE_POOL))
    return random.sample(EXAMPLE_POOL, k)


def _verify_html(verify: Optional[dict]) -> str:
    """引用校验徽章，简洁现代风。通过时显示完整确认句，异常时展开详情。"""
    if not verify:
        return ""
    status = verify.get("status")
    msg = verify.get("message", "")
    if status == "ok":
        # 通过：显示确认句，不展开技术细节
        cls, icon = "ok", "✓"
        return f'<div class="verify-badge {cls}"><b>{icon} 回答所引用的法律条文均已通过校验</b></div>'
    elif status == "warn":
        cls, icon, label = "warn", "!", "引用校验告警"
    else:
        cls, icon, label = "none", "i", "引用校验"
    # 告警/异常：展开详情
    return (
        f'<div class="verify-badge {cls}">'
        f"<b>{icon} {label}</b>"
        f'<div style="margin-top:3px;">{escape(msg)}</div>'
        f"</div>"
    )


def _ref_anchor_id(law_name: str, article_no: int, sub_no: int = 0) -> str:
    """条文锚点 id：法律名归一化 + 条号(+附加条号)。

    用 _strip_law_prefix 去掉「中华人民共和国」前缀，缩短锚点。
    形如 "ref-民法典-26"，或 "ref-民法典-133-1"(第133条之一)。
    """
    base = _strip_law_prefix(law_name) or "law"
    suffix = f"-{sub_no}" if sub_no else ""
    return f"ref-{base}-{article_no}{suffix}"


def _refs_block_html(hits: List[Dict]) -> str:
    """检索条文 → 整体可折叠块（内含每条可单独展开的卡片，带锚点 id）。"""
    if not hits:
        return ""
    items = []
    for h in hits:
        law = h.get("law_name", "")
        no = h["article_no"]
        sub = h.get("sub_no", 0)
        anchor = _ref_anchor_id(law, no, sub)
        sub_label = f"之{sub}" if sub else ""
        meta = " · ".join(s for s in [h.get("part", ""), h.get("chapter", "")] if s)
        body = escape(h.get("article_text", "")).replace("\n", "<br>")
        items.append(
            f'<details class="ref-item" id="{escape(anchor)}">'
            f"<summary>"
            f'<span class="ref-arrow">▸</span>'
            f'<span class="ref-title">《{escape(law)}》第{no}条{sub_label}</span>'
            f'<span class="ref-meta">{escape(meta)}</span>'
            f"</summary>"
            f'<div class="ref-body">{body}</div>'
            f"</details>"
        )
    return (
        '<details class="refs-block">'
        "<summary>"
        '<span class="blk-arrow">▸</span>引用条文'
        f'<span class="blk-count">{len(hits)} 条</span>'
        "</summary>"
        f'<div class="refs-inner">{"".join(items)}</div>'
        "</details>"
    )


def _answer_footer_html(verify: Optional[dict], hits: List[Dict]) -> str:
    """组装回答页脚：校验徽章 + 引用条文折叠块。两者皆空则返回空串。"""
    badge = _verify_html(verify)
    refs = _refs_block_html(hits)
    if not badge and not refs:
        return ""
    return f'<div class="answer-footer">{badge}{refs}</div>'


def _trace_block_html(trace: List[Dict]) -> str:
    """Agent 多跳轨迹 → 折叠块（每个节点一行，展示规划/检索/反思决策）。

    单跳模式下 trace 为空，不渲染此块。多跳模式展示每轮查了什么、Reflect 判断。
    """
    if not trace:
        return ""
    lines = []
    for i, t in enumerate(trace, 1):
        node = t.get("node", "")
        if node == "planner":
            is_complex = "复杂" if t.get("is_complex") else "简单"
            subs = t.get("subs", [])
            subs_text = "、".join(f'"{s}"' for s in subs[:3])
            if len(subs) > 3:
                subs_text += f" 等 {len(subs)} 个"
            lines.append(f"<b>规划</b>：判定为{is_complex}问题 → {subs_text}")
        elif node == "retrieve":
            hop = t.get("hop", "?")
            queried = t.get("queried", [])
            n = t.get("n_hits_total", 0)
            q_text = "、".join(f'"{q}"' for q in queried[:2])
            if len(queried) > 2:
                q_text += f" 等 {len(queried)} 个"
            lines.append(f"<b>检索 #{hop}</b>：{q_text} → 累积 {n} 条")
        elif node == "reflect":
            hop = t.get("hop", "?")
            decision = t.get("decision", "")
            dec_label = {"answer": "✓ 信息充分，开始作答", "continue": "⟳ 需补充", "stop_max_hops": "⊗ 达到跳数上限，强制收敛"}.get(decision, decision)
            missing = t.get("missing", [])
            if missing:
                miss_text = "、".join(f'"{m}"' for m in missing[:2])
                if len(missing) > 2:
                    miss_text += f" 等 {len(missing)} 个"
                dec_label += f" → {miss_text}"
            lines.append(f"<b>反思 #{hop}</b>：{dec_label}")
        elif node == "answer":
            n = t.get("n_context", 0)
            lines.append(f"<b>作答</b>：基于 {n} 条法律条文生成答案")
    body = "<br>".join(f'<div style="padding:3px 0;font-size:0.84rem;line-height:1.6;">{ln}</div>' for ln in lines)
    return (
        '<details class="refs-block" style="margin-bottom:9px;">'
        "<summary>"
        '<span class="blk-arrow">▸</span>多跳轨迹'
        f'<span class="blk-count">{len(trace)} 步</span>'
        "</summary>"
        f'<div class="refs-inner" style="color:#52525b;">{body}</div>'
        "</details>"
    )


# 答案中「《X法》第N条」匹配：同时支持阿拉伯数字与中文数字
_CITE_RE = re.compile(
    r"《([^》]+)》\s*第\s*(\d+|[一二三四五六七八九十百千零]+)\s*条(之[一二三四五六七八九十]+)?"
)


def _linkify_citations(answer_md: str, hits: List[Dict]) -> str:
    """把答案 markdown 里的「《X法》第N条」替换为指向页脚条文卡片的锚点链接。

    只在该 (法律, 条号) 出现在 hits 中时才替换(防止给"伪引用"也加链接,
    与引用校验语义保持一致)。流式中途不能调用此函数——会破坏 token 边界。
    """
    if not hits:
        return answer_md
    valid = {
        (_strip_law_prefix(h.get("law_name", "")), h["article_no"], h.get("sub_no", 0))
        for h in hits
    }
    law_lookup = {_strip_law_prefix(h.get("law_name", "")): h.get("law_name", "") for h in hits}

    def repl(m: re.Match) -> str:
        law = m.group(1).strip()
        num_raw = m.group(2)
        sub_raw = m.group(3)
        try:
            no = int(num_raw) if num_raw.isdigit() else chinese_to_arabic(num_raw)
        except Exception:
            return m.group(0)
        sub = 0
        if sub_raw:
            try:
                sub = chinese_to_arabic(sub_raw[1:])
            except Exception:
                sub = 0
        key = (_strip_law_prefix(law), no, sub)
        if key not in valid:
            return m.group(0)
        anchor = _ref_anchor_id(law_lookup.get(_strip_law_prefix(law), law), no, sub)
        return f'<a class="cite-link" href="#{anchor}">{m.group(0)}</a>'

    return _CITE_RE.sub(repl, answer_md)


def _append_feedback(record: Dict) -> None:
    """反馈追加到 JSONL(失败静默,不影响用户)。"""
    if not config.FEEDBACK_LOG_ENABLED:
        return
    try:
        config.FEEDBACK_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(config.FEEDBACK_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"WARN - feedback log write failed: {e}")


def create_app():
    rag = LegalRAG()
    agent = LegalAgent(rag)  # 复用同一 RAG 实例（共享 VectorStore）

    def chat_stream(question: str, history: list, refs_state: list, agent_mode: bool = False):
        """流式回调（单栏）。

        agent_mode=False（默认）：单跳，调用 rag.answer_stream 流式输出。
        agent_mode=True：多跳 Agent，调用 agent.run_stream（分阶段 yield）。

        校验徽章与引用条文不再走独立侧栏，而是在流式结束后作为页脚 HTML
        追加进当前 assistant 消息内容里。Agent 模式额外在页脚前插入轨迹折叠块。
        refs_state 仍维护每条回答的快照，供 👍/👎 反馈按消息索引回查上下文落盘。

        Yields:
            (history, refs_state)
        """
        if not question.strip():
            yield history, refs_state
            return

        prior_history = list(history)

        history.append({"role": "user", "content": question})
        history.append({"role": "assistant", "content": ""})
        refs_hits: List[Dict] = []
        answer_parts: List[str] = []
        last_verify: Optional[Dict] = None
        disclaimer_md: str = ""
        rewrite_used: Optional[str] = None
        trace_list: List[Dict] = []  # Agent 模式独有

        def _compose(linkify: bool) -> str:
            """把答案正文 + 免责声明 + 轨迹(Agent) + 页脚拼成消息内容。"""
            ans = "".join(answer_parts)
            if linkify:
                ans = _linkify_citations(ans, refs_hits)
            body = ans
            if disclaimer_md:
                body += f"\n\n---\n\n{disclaimer_md}"
            # Agent 模式：在页脚前先插入轨迹折叠块
            if agent_mode:
                trace_html = _trace_block_html(trace_list)
                if trace_html:
                    body += f"\n\n{trace_html}"
            footer = _answer_footer_html(last_verify, refs_hits)
            if footer:
                body += f"\n\n{footer}"
            return body

        if agent_mode:
            # 多跳 Agent：非逐 token 流式，分阶段 yield（trace → refs → answer → verify → disclaimer）
            for chunk in agent.run_stream(question, history=prior_history):
                chunk_type = chunk.get("type")
                if chunk_type == "trace":
                    trace_list = chunk.get("content", [])
                    # trace 到齐后先 yield 一次（让前端尽早展示轨迹），正文暂空
                    history[-1]["content"] = _compose(linkify=False)
                    yield history, refs_state
                elif chunk_type == "references":
                    refs_hits = chunk.get("content", [])
                elif chunk_type == "answer":
                    answer_parts.append(chunk.get("content", ""))
                    history[-1]["content"] = _compose(linkify=False)
                    yield history, refs_state
                elif chunk_type == "verify":
                    last_verify = chunk.get("content", {})
                elif chunk_type == "disclaimer":
                    disclaimer_md = chunk.get("content", "")
            # 最终 linkify
            history[-1]["content"] = _compose(linkify=True)
            refs_state.append({"hits": refs_hits, "verify": last_verify})
            yield history, refs_state
        else:
            # 单跳：原流式逻辑（逐 token）
            for chunk in rag.answer_stream(question, history=prior_history):
                ctype = chunk["type"]
                content = chunk["content"]
                if ctype == "rewrite":
                    rewrite_used = content if isinstance(content, str) else None
                    continue
                elif ctype == "references":
                    refs_hits = content if isinstance(content, list) else []
                    continue
                elif ctype == "answer":
                    if isinstance(content, str):
                        answer_parts.append(content)
                    history[-1]["content"] = "".join(answer_parts)
                    yield history, refs_state
                elif ctype == "verify":
                    last_verify = content if isinstance(content, dict) else None
                    history[-1]["content"] = _compose(linkify=True)
                    yield history, refs_state
                elif ctype == "disclaimer":
                    disclaimer_md = content if isinstance(content, str) else ""
                    history[-1]["content"] = _compose(linkify=True)
                    yield history, refs_state
                elif ctype == "error":
                    history[-1]["content"] = f"⚠️ {content}"
                    yield history, refs_state
                    refs_state = refs_state + [{"hits": [], "verify": None, "rewrite": rewrite_used, "question": question, "answer": f"⚠️ {content}"}]
                    return

            history[-1]["content"] = _compose(linkify=True)
            refs_state = refs_state + [{
                "hits": refs_hits,
                "verify": last_verify,
                "rewrite": rewrite_used,
                "question": question,
                "answer": "".join(answer_parts),
            }]
            yield history, refs_state

    def on_like(history: list, refs_state: list, evt: gr.LikeData):
        """用户对消息点 👍/👎，落 JSONL 攒难例集。"""
        try:
            idx = evt.index
            if isinstance(idx, (list, tuple)):
                idx = idx[0]
            assistant_idx = sum(
                1 for m in history[: idx + 1] if m.get("role") == "assistant"
            ) - 1
            ctx = refs_state[assistant_idx] if 0 <= assistant_idx < len(refs_state) else {}
            record = {
                "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "liked": bool(evt.liked),
                "question": ctx.get("question", ""),
                "rewrite": ctx.get("rewrite"),
                "answer": (ctx.get("answer") or "")[:2000],
                "refs": [
                    {"law": h.get("law_name", ""), "no": h.get("article_no"), "sub": h.get("sub_no", 0)}
                    for h in ctx.get("hits") or []
                ],
                "verify_status": (ctx.get("verify") or {}).get("status"),
            }
            _append_feedback(record)
        except Exception as e:
            print(f"WARN - on_like failed: {e}")
        return gr.update()

    with gr.Blocks(title=config.APP_TITLE) as demo:
        # 顶栏：极简
        with gr.Column(elem_id="app-header"):
            gr.HTML(
                f"<h1>⚖️ {escape(config.APP_TITLE)}</h1>"
                f"<p>{escape(config.APP_SUBTITLE)}</p>"
            )

        # 状态：每条 assistant 消息对应的引用快照（与 history assistant 消息对齐）
        refs_state = gr.State([])
        # 暂存本轮问题：回车先清空输入框，再把问题喂给 chat_stream
        question_store = gr.State("")

        # 对话外壳：相对定位容器，输入区与示例 chips 悬浮其内
        with gr.Column(elem_id="chat-shell"):
            # 单栏：对话流（填满外壳）
            chatbot = gr.Chatbot(
                label=None,
                show_label=False,
                elem_id="chatbot",
                avatar_images=(None, None),
                feedback_options=("有用", "需改进"),
                placeholder=None,
                sanitize_html=False,  # 让答案/页脚里的 HTML（锚点链接、折叠块）生效
            )

            # 空状态：欢迎 + 示例 chips + 换一换（悬浮居中；有对话后隐藏）
            init_qs = _sample_questions()
            with gr.Column(elem_id="examples-wrap", visible=True) as examples_wrap:
                with gr.Row(elem_id="examples-head"):
                    gr.HTML('<div class="examples-title">💡 试试这些问题</div>')
                    shuffle_btn = gr.Button("🔄 换一换", elem_id="shuffle-btn", size="sm")
                with gr.Row(elem_id="chips-row"):
                    example_btns = [
                        gr.Button(q, size="sm", elem_classes="chip") for q in init_qs
                    ]

            # 悬浮输入区：贴对话框底部
            with gr.Row(elem_id="input-row"):
                question_input = gr.Textbox(
                    placeholder="向法律助手提问，例如「父母与成年子女之间有哪些法定义务？」",
                    lines=1,
                    max_lines=4,
                    scale=8,
                    show_label=False,
                    container=False,
                    autofocus=True,
                )
                submit_btn = gr.Button("发送", variant="primary", scale=1, min_width=72, elem_id="send-btn")
                clear_btn = gr.Button("清空", scale=1, min_width=64, elem_id="clear-btn")

            # 深度模式开关：悬浮在输入区下方（小字说明 + Checkbox）
            with gr.Row(elem_id="agent-mode-row", elem_classes="compact-row"):
                agent_mode_cb = gr.Checkbox(
                    label="深度模式（多跳检索 Agent，自动规划+反思，适合复杂问题）",
                    value=config.AGENT_MODE,
                    scale=1,
                    elem_id="agent-mode-checkbox",
                )

        # 状态：深度模式当前值（初始从 config 读，用户切换后更新）
        agent_mode_state = gr.State(config.AGENT_MODE)

        def _stash(q: str):
            """把输入框内容转存到 state，并立即清空输入框。"""
            return q, "", gr.update(visible=False)

        def _shuffle():
            """重抽示例问题，更新各 chip 的文案。"""
            qs = _sample_questions()
            return [gr.update(value=q) for q in qs]

        # 提交链：先清空输入框 → 再流式回答（回车/点击后问题立即消失）
        for trigger in (submit_btn.click, question_input.submit):
            trigger(
                _stash, inputs=[question_input], outputs=[question_store, question_input, examples_wrap]
            ).then(
                chat_stream,
                inputs=[question_store, chatbot, refs_state, agent_mode_state],
                outputs=[chatbot, refs_state],
            )

        # 示例 chip：点击把自身文案转存 → 清空输入框 → 流式回答
        for btn in example_btns:
            btn.click(
                _stash, inputs=[btn], outputs=[question_store, question_input, examples_wrap]
            ).then(
                chat_stream,
                inputs=[question_store, chatbot, refs_state, agent_mode_state],
                outputs=[chatbot, refs_state],
            )

        # 深度模式 Checkbox：切换时同步到 state
        agent_mode_cb.change(
            lambda x: x,
            inputs=[agent_mode_cb],
            outputs=[agent_mode_state],
        )

        # 换一换：重抽 chips
        shuffle_btn.click(_shuffle, outputs=example_btns)

        # 清空：对话/状态清掉，示例重新显示并重抽
        def _clear():
            return [], [], "", gr.update(visible=True), *[gr.update(value=q) for q in _sample_questions()]

        clear_btn.click(
            _clear,
            outputs=[chatbot, refs_state, question_store, examples_wrap, *example_btns],
        )

        # 反馈事件：Chatbot 内置 👍/👎 → JSONL
        chatbot.like(on_like, inputs=[chatbot, refs_state], outputs=None)

    return demo


if __name__ == "__main__":
    app = create_app()
    app.launch(
        server_name="127.0.0.1",
        server_port=7860,
        share=False,
        inbrowser=True,
        theme=gr.themes.Soft(),
        css=CUSTOM_CSS,
    )
