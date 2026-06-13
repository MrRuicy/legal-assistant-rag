"""Gradio Web 界面（多轮对话 + 流式输出 + 引用校验 + 锚点跳转 + 反馈）。

UI 风格：简洁现代——大圆角、留白、灰阶、弱描边，去掉视觉噪声，
让对话与条文成为绝对主角。
"""
import json
import re
import time
from html import escape
from typing import Dict, List, Optional

import gradio as gr

from . import config
from .parser import chinese_to_arabic
from .rag import LegalRAG, _strip_law_prefix


# 简洁现代风：大留白、24px 圆角、单一灰阶、几乎无边框
CUSTOM_CSS = """
:root {
    --bg: #fafafa;
    --surface: #ffffff;
    --border: #ececec;
    --text: #1a1a1a;
    --muted: #6b6b6b;
    --accent: #2d2d2d;
    --ok: #16a34a;
    --warn: #dc2626;
    --info: #6b7280;
    --chip-bg: #f3f4f6;
    --chip-bg-hover: #e5e7eb;
    --link: #1f2937;
}
.gradio-container { max-width: 1180px !important; margin: 0 auto !important; padding: 18px 22px !important; }
body, .gradio-container { background: var(--bg) !important; color: var(--text) !important; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif !important; }

/* 顶栏：极简 */
#app-header { text-align: left; margin: 4px 0 14px 0; padding: 0; }
#app-header h1 { margin: 0; font-size: 1.35rem; font-weight: 600; letter-spacing: -0.01em; }
#app-header p { margin: 2px 0 0 0; color: var(--muted); font-size: 0.82rem; font-weight: 400; }

/* 对话区：大圆角卡片，弱描边 */
#chatbot { height: 64vh !important; border: 1px solid var(--border) !important; border-radius: 18px !important; background: var(--surface) !important; box-shadow: none !important; }
#chatbot .message { font-size: 0.95rem; line-height: 1.7; }
#chatbot .message.user { background: #f3f4f6 !important; border-radius: 14px !important; }
#chatbot .message.bot { background: transparent !important; }

/* 输入区:圆润、低存在感 */
#input-row { margin-top: 10px; gap: 8px !important; }
#input-row textarea { border-radius: 14px !important; border: 1px solid var(--border) !important; padding: 12px 14px !important; font-size: 0.95rem !important; background: var(--surface) !important; }
#input-row textarea:focus { border-color: #cbd5e1 !important; box-shadow: 0 0 0 3px rgba(203,213,225,0.25) !important; }
#input-row button { border-radius: 12px !important; font-weight: 500 !important; }

/* 右侧栏:留白 + 弱分组 */
#side-col { padding-left: 6px; }
#verify-slot { min-height: 8px; }

/* 检索条文卡片(原生 details/summary) */
#refs-box { max-height: 70vh; overflow-y: auto; padding-right: 4px; }
#refs-box .refs-empty { color: var(--muted); font-size: 0.9rem; padding: 18px 4px; text-align: center; }
#refs-box .refs-count { color: var(--muted); font-size: 0.8rem; margin: 2px 0 10px 0; letter-spacing: 0.02em; }
#refs-box details { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 0; margin-bottom: 8px; transition: border-color 0.15s; }
#refs-box details:hover { border-color: #d4d4d4; }
#refs-box details[open] { border-color: #d4d4d4; }
#refs-box details:target { border-color: #1f2937; box-shadow: 0 0 0 2px rgba(31,41,55,0.08); animation: anchor-flash 1.2s ease-out; }
@keyframes anchor-flash { 0% { background: #fef3c7; } 100% { background: var(--surface); } }
#refs-box summary { cursor: pointer; padding: 12px 14px; list-style: none; font-size: 0.92rem; line-height: 1.5; user-select: none; }
#refs-box summary::-webkit-details-marker { display: none; }
#refs-box summary .ref-title { font-weight: 600; color: var(--text); }
#refs-box summary .ref-meta { display: block; color: var(--muted); font-size: 0.78rem; margin-top: 3px; }
#refs-box summary .ref-arrow { float: right; color: var(--muted); transition: transform 0.15s; font-size: 0.8rem; }
#refs-box details[open] summary .ref-arrow { transform: rotate(90deg); }
#refs-box .ref-body { padding: 0 14px 14px 14px; color: #2d2d2d; font-size: 0.9rem; line-height: 1.75; border-top: 1px solid #f3f4f6; padding-top: 10px; margin-top: 4px; }

/* 答案中的条号锚点链接 */
.cite-link { color: var(--link); text-decoration: none; border-bottom: 1px dashed #9ca3af; padding: 0 1px; transition: all 0.12s; }
.cite-link:hover { color: #000; border-bottom-color: #1f2937; background: #f3f4f6; border-radius: 3px; }

/* 引用校验徽章:更克制 */
.verify-badge { border-radius: 12px; padding: 10px 14px; line-height: 1.55; font-size: 0.86rem; margin-bottom: 10px; border: 1px solid; }
.verify-badge.ok { background: #f0fdf4; border-color: #bbf7d0; color: #166534; }
.verify-badge.warn { background: #fef2f2; border-color: #fecaca; color: #991b1b; }
.verify-badge.none { background: #f9fafb; border-color: #e5e7eb; color: #4b5563; }
.verify-badge b { font-weight: 600; }

/* 示例问题 chips */
#examples-wrap { padding: 24px 8px; }
#examples-wrap .examples-title { color: var(--muted); font-size: 0.86rem; margin-bottom: 12px; }
#examples-wrap .gr-button { background: var(--chip-bg) !important; color: var(--text) !important; border: none !important; border-radius: 999px !important; padding: 7px 14px !important; font-size: 0.85rem !important; font-weight: 400 !important; min-width: 0 !important; }
#examples-wrap .gr-button:hover { background: var(--chip-bg-hover) !important; }

/* 节标题 */
.section-label { color: var(--muted); font-size: 0.78rem; font-weight: 500; letter-spacing: 0.06em; text-transform: uppercase; margin: 4px 0 8px 0; }

footer { display: none !important; }
"""


# 示例问题:覆盖几部主要法律,降低用户上手门槛
EXAMPLE_QUESTIONS = [
    "父母与成年子女之间有哪些法定义务？",
    "用人单位拖欠工资可以怎么维权？",
    "公司股东出资有哪些方式？",
    "诉讼时效期间一般是多少年？",
    "消费者发现假货可以要求几倍赔偿？",
]


def _verify_html(verify: dict) -> str:
    """引用校验徽章,简洁现代风。"""
    if not verify:
        return ""
    status = verify.get("status")
    msg = verify.get("message", "")
    if status == "ok":
        cls, icon, label = "ok", "✓", "引用校验通过"
    elif status == "warn":
        cls, icon, label = "warn", "!", "引用校验告警"
    else:
        cls, icon, label = "none", "i", "引用校验"
    return (
        f'<div class="verify-badge {cls}">'
        f'<b>{icon} {label}</b>'
        f'<div style="margin-top:3px;">{escape(msg)}</div>'
        f"</div>"
    )


def _ref_anchor_id(law_name: str, article_no: int, sub_no: int = 0) -> str:
    """条文锚点 id:法律名归一化 + 条号(+附加条号)。

    用 _strip_law_prefix 去掉「中华人民共和国」前缀,缩短锚点,跨答案/列表保持一致。
    最终形如 "ref-民法典-26",或 "ref-民法典-133-1"(第133条之一)。
    """
    base = _strip_law_prefix(law_name) or "law"
    suffix = f"-{sub_no}" if sub_no else ""
    return f"ref-{base}-{article_no}{suffix}"


def _format_refs_html(hits: List[Dict]) -> str:
    """检索条文 → 可折叠卡片 HTML(带锚点 id,供答案中条号链接跳转)。"""
    if not hits:
        return '<div id="refs-box"><div class="refs-empty">提问后,这里会显示检索到的法律条文</div></div>'

    parts = [f'<div id="refs-box"><div class="refs-count">本次命中 {len(hits)} 条</div>']
    for h in hits:
        law = h.get("law_name", "")
        no = h["article_no"]
        sub = h.get("sub_no", 0)
        anchor = _ref_anchor_id(law, no, sub)
        sub_label = f"之{sub}" if sub else ""
        meta = " · ".join(s for s in [h.get("part", ""), h.get("chapter", "")] if s)
        body = escape(h.get("article_text", "")).replace("\n", "<br>")
        parts.append(
            f'<details id="{escape(anchor)}">'
            f'<summary>'
            f'<span class="ref-arrow">▸</span>'
            f'<span class="ref-title">《{escape(law)}》第{no}条{sub_label}</span>'
            f'<span class="ref-meta">{escape(meta)}</span>'
            f"</summary>"
            f'<div class="ref-body">{body}</div>'
            f"</details>"
        )
    parts.append("</div>")
    return "".join(parts)


# 答案中「《X法》第N条」匹配:同时支持阿拉伯数字与中文数字
_CITE_RE = re.compile(
    r"《([^》]+)》\s*第\s*(\d+|[一二三四五六七八九十百千零]+)\s*条(之[一二三四五六七八九十]+)?"
)


def _linkify_citations(answer_md: str, hits: List[Dict]) -> str:
    """把答案 markdown 里的「《X法》第N条」替换为指向右侧条文卡片的锚点链接。

    只在该 (法律, 条号) 出现在 hits 中时才替换(防止给"伪引用"也加上链接,
    与引用校验语义保持一致)。流式中途不能调用此函数——会破坏 token 边界。
    """
    if not hits:
        return answer_md
    valid = {
        (_strip_law_prefix(h.get("law_name", "")), h["article_no"], h.get("sub_no", 0))
        for h in hits
    }
    # 法律名 → 原始 law_name(用于构造锚点 id)
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

    def chat_stream(question: str, history: list, refs_state: list):
        """流式回调。

        额外维护 refs_state(每条 assistant 消息对应的 hits 快照),用于:
        1. 流式结束后把答案里的条号转成锚点链接(需要 hits 才能判断是否有效引用);
        2. 用户点 👍/👎 时按消息索引回查上下文一并落盘。

        Yields:
            (history, refs_html, verify_html, refs_state)
        """
        if not question.strip():
            yield history, _format_refs_html([]), "", refs_state
            return

        # 截取本轮提问之前的历史(传给 RAG 做查询改写与上下文承接)
        prior_history = list(history)

        # 初始化本轮对话
        history.append({"role": "user", "content": question})
        history.append({"role": "assistant", "content": ""})
        refs_hits: List[Dict] = []
        answer_parts: List[str] = []
        last_verify: Optional[Dict] = None
        rewrite_used: Optional[str] = None

        for chunk in rag.answer_stream(question, history=prior_history):
            ctype = chunk["type"]
            content = chunk["content"]
            if ctype == "rewrite":
                rewrite_used = content if isinstance(content, str) else None
                continue
            elif ctype == "references":
                refs_hits = content if isinstance(content, list) else []
                yield history, _format_refs_html(refs_hits), "", refs_state
            elif ctype == "answer":
                if isinstance(content, str):
                    answer_parts.append(content)
                history[-1]["content"] = "".join(answer_parts)
                yield history, _format_refs_html(refs_hits), "", refs_state
            elif ctype == "verify":
                last_verify = content if isinstance(content, dict) else None
                # 流式结束(verify 在最后),把答案里的条号转锚点链接
                linked = _linkify_citations("".join(answer_parts), refs_hits)
                history[-1]["content"] = linked
                yield history, _format_refs_html(refs_hits), _verify_html(last_verify or {}), refs_state
            elif ctype == "disclaimer":
                # 免责声明追加到答案末尾(锚点替换已在 verify 时完成)
                cur = history[-1]["content"]
                history[-1]["content"] = cur + f"\n\n---\n\n{content}"
                yield history, _format_refs_html(refs_hits), _verify_html(last_verify or {}), refs_state
            elif ctype == "error":
                history[-1]["content"] = f"⚠️ {content}"
                yield history, _format_refs_html(refs_hits), "", refs_state
                # 错误也要记录占位,保持 refs_state 与 history assistant 消息一一对应
                refs_state = refs_state + [{"hits": [], "verify": None, "rewrite": rewrite_used}]
                return

        # 正常结束:为这条 assistant 消息记一份引用快照
        refs_state = refs_state + [{
            "hits": refs_hits,
            "verify": last_verify,
            "rewrite": rewrite_used,
            "question": question,
        }]
        yield history, _format_refs_html(refs_hits), _verify_html(last_verify or {}), refs_state

    def on_like(history: list, refs_state: list, evt: gr.LikeData):
        """用户对消息点 👍/👎,落 JSONL 攒难例集。"""
        try:
            idx = evt.index
            if isinstance(idx, (list, tuple)):
                idx = idx[0]
            msg = history[idx] if 0 <= idx < len(history) else {}
            # idx 是 history(平铺 user/assistant 交替)中的位置;
            # 第 k 条 assistant 消息对应 refs_state[k]
            assistant_idx = sum(
                1 for _, m in enumerate(history[: idx + 1]) if m.get("role") == "assistant"
            ) - 1
            ctx = refs_state[assistant_idx] if 0 <= assistant_idx < len(refs_state) else {}
            record = {
                "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "liked": bool(evt.liked),
                "question": ctx.get("question", ""),
                "rewrite": ctx.get("rewrite"),
                "answer": (msg.get("content") or "")[:2000],
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
        # 顶栏:极简
        with gr.Column(elem_id="app-header"):
            gr.HTML(
                f"<h1>⚖️ {escape(config.APP_TITLE)}</h1>"
                f"<p>{escape(config.APP_SUBTITLE)}</p>"
            )

        # 状态:每条 assistant 消息对应的引用快照,索引与 history 中的 assistant 消息对齐
        refs_state = gr.State([])

        with gr.Row(equal_height=False):
            # 左:对话区
            with gr.Column(scale=3):
                chatbot = gr.Chatbot(
                    label=None,
                    show_label=False,
                    elem_id="chatbot",
                    avatar_images=(None, None),
                    feedback_options=("有用", "需改进"),
                    placeholder=None,
                    sanitize_html=False,  # 我们要让答案里的 <a class=cite-link> 锚点生效
                )

                # 空状态示例问题(初次进入显示;有对话后隐藏)
                with gr.Column(elem_id="examples-wrap", visible=True) as examples_wrap:
                    gr.HTML('<div class="examples-title">试试这些问题 ↓</div>')
                    with gr.Row():
                        example_btns = [
                            gr.Button(q, size="sm") for q in EXAMPLE_QUESTIONS
                        ]

                with gr.Row(elem_id="input-row"):
                    question_input = gr.Textbox(
                        placeholder="向法律助手提问，例如「父母与成年子女之间有哪些法定义务？」",
                        lines=1,
                        scale=8,
                        show_label=False,
                        container=False,
                        autofocus=True,
                    )
                    submit_btn = gr.Button("发送", variant="primary", scale=1, min_width=72)
                    clear_btn = gr.Button("清空", scale=1, min_width=64)

            # 右:校验徽章 + 检索条文卡片
            with gr.Column(scale=2, elem_id="side-col"):
                gr.HTML('<div class="section-label">引用校验</div>')
                verify_output = gr.HTML(elem_id="verify-slot")
                gr.HTML('<div class="section-label" style="margin-top:18px;">检索到的条文</div>')
                refs_output = gr.HTML(_format_refs_html([]))

        # 提交后:隐藏空状态示例
        def _hide_examples():
            return gr.update(visible=False)

        # 主提交流程
        submit_btn.click(
            fn=chat_stream,
            inputs=[question_input, chatbot, refs_state],
            outputs=[chatbot, refs_output, verify_output, refs_state],
        ).then(lambda: "", outputs=question_input).then(
            _hide_examples, outputs=examples_wrap
        )

        question_input.submit(
            fn=chat_stream,
            inputs=[question_input, chatbot, refs_state],
            outputs=[chatbot, refs_output, verify_output, refs_state],
        ).then(lambda: "", outputs=question_input).then(
            _hide_examples, outputs=examples_wrap
        )

        # 示例按钮:塞入输入框 → 立即触发提交
        for btn, q in zip(example_btns, EXAMPLE_QUESTIONS):
            btn.click(lambda v=q: v, outputs=question_input).then(
                fn=chat_stream,
                inputs=[question_input, chatbot, refs_state],
                outputs=[chatbot, refs_output, verify_output, refs_state],
            ).then(lambda: "", outputs=question_input).then(
                _hide_examples, outputs=examples_wrap
            )

        # 清空:对话/引用/校验/状态 一并清掉,示例重新显示
        clear_btn.click(
            lambda: ([], _format_refs_html([]), "", [], gr.update(visible=True)),
            outputs=[chatbot, refs_output, verify_output, refs_state, examples_wrap],
        )

        # 反馈事件:Chatbot 内置 👍/👎 → JSONL
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
