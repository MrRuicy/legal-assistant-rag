"""Gradio Web 界面（多轮对话 + 流式输出 + 引用校验）。"""
import gradio as gr

from . import config
from .rag import LegalRAG

# 自定义 CSS：整体适配浏览器视口，尽量一页不翻页
CUSTOM_CSS = """
.gradio-container { max-width: 100% !important; padding: 8px 16px !important; }
#app-header { text-align: center; margin: 0 0 6px 0; }
#app-header h1 { margin: 2px 0; font-size: 1.4rem; }
#app-header p { margin: 0; color: #666; font-size: 0.85rem; }
#chatbot { height: 58vh !important; }
#refs-box { height: 42vh; overflow-y: auto; padding-right: 6px; }
footer { display: none !important; }
"""


def _verify_html(verify: dict) -> str:
    """把引用校验结果渲染成醒目的彩色徽章 HTML。"""
    if not verify:
        return ""
    status = verify.get("status")
    msg = verify.get("message", "")
    if status == "ok":
        bg, border, icon, label = "#e6f4ea", "#34a853", "✅", "引用校验通过"
    elif status == "warn":
        bg, border, icon, label = "#fdecea", "#ea4335", "⚠️", "引用校验告警"
    else:  # none
        bg, border, icon, label = "#f1f3f4", "#9aa0a6", "ℹ️", "引用校验"
    return (
        f'<div style="background:{bg};border-left:5px solid {border};'
        f'padding:10px 14px;border-radius:6px;line-height:1.5;">'
        f'<b style="font-size:0.95rem;">{icon} {label}</b>'
        f'<div style="margin-top:4px;color:#333;font-size:0.88rem;">{msg}</div>'
        f"</div>"
    )


def _format_refs(hits) -> str:
    """格式化检索到的条文为 Markdown。"""
    if not hits:
        return "_暂无检索结果_"
    lines = [f"**本次检索到 {len(hits)} 条相关条文：**\n"]
    for h in hits:
        law = h.get("law_name", "")
        lines.append(
            f"- **《{law}》第{h['article_no']}条**（{h['part']} {h['chapter']}）\n"
            f"  {h['article_text']}\n"
        )
    return "\n".join(lines)


def create_app():
    rag = LegalRAG()

    def chat_stream(question: str, history: list):
        """Gradio 流式回调：generator。

        检索条数由 config.TOP_K 设定（已用评估集调优为 8），不暴露给终端用户。

        Yields:
            (history, refs_md, verify_html): 对话历史、引用条文、引用校验徽章
        """
        if not question.strip():
            history.append({"role": "user", "content": question})
            history.append({"role": "assistant", "content": "请输入您的法律问题。"})
            yield history, "_暂无检索结果_", ""
            return

        # 截取本轮提问之前的历史（传给 RAG 做查询改写与上下文承接）
        prior_history = list(history)

        # 初始化本轮对话
        history.append({"role": "user", "content": question})
        history.append({"role": "assistant", "content": ""})
        refs_hits = []
        answer_parts = []

        for chunk in rag.answer_stream(question, history=prior_history):
            ctype = chunk["type"]
            if ctype == "rewrite":
                continue  # 查询改写仅影响检索，不在对话框展示
            elif ctype == "references":
                refs_hits = chunk["content"]
                yield history, _format_refs(refs_hits), ""
            elif ctype == "answer":
                answer_parts.append(chunk["content"])
                history[-1]["content"] = "".join(answer_parts)
                yield history, _format_refs(refs_hits), ""
            elif ctype == "verify":
                # 引用校验：渲染到独立的醒目徽章区
                history[-1]["content"] = "".join(answer_parts)
                yield history, _format_refs(refs_hits), _verify_html(chunk["content"])
            elif ctype == "disclaimer":
                answer_parts.append(f"\n\n---\n\n{chunk['content']}")
                history[-1]["content"] = "".join(answer_parts)
                yield history, _format_refs(refs_hits), gr.skip()
            elif ctype == "error":
                history[-1]["content"] = f"⚠️ {chunk['content']}"
                yield history, _format_refs(refs_hits), ""
                return

    with gr.Blocks(title=config.APP_TITLE) as demo:
        with gr.Column(elem_id="app-header"):
            gr.HTML(
                f"<h1>⚖️ {config.APP_TITLE}</h1>"
                f"<p>{config.APP_SUBTITLE}</p>"
            )

        with gr.Row(equal_height=True):
            # 左侧：对话区
            with gr.Column(scale=3):
                chatbot = gr.Chatbot(
                    label="对话",
                    elem_id="chatbot",
                )
                with gr.Row():
                    question_input = gr.Textbox(
                        placeholder="例如：父母与成年子女之间有哪些法定义务？（回车发送）",
                        lines=1,
                        scale=8,
                        show_label=False,
                        container=False,
                    )
                    submit_btn = gr.Button("发送", variant="primary", scale=1, min_width=70)
                    clear_btn = gr.Button("清空", scale=1, min_width=60)

            # 右侧：引用校验徽章（固定在顶）+ 检索条文（固定高度滚动）
            with gr.Column(scale=2):
                verify_output = gr.HTML(label="引用校验")
                gr.Markdown("#### 📜 检索到的条文")
                with gr.Column(elem_id="refs-box"):
                    refs_output = gr.Markdown("_暂无检索结果_")

        # 事件绑定
        submit_event = submit_btn.click(
            fn=chat_stream,
            inputs=[question_input, chatbot],
            outputs=[chatbot, refs_output, verify_output],
        ).then(lambda: "", outputs=question_input)

        question_input.submit(
            fn=chat_stream,
            inputs=[question_input, chatbot],
            outputs=[chatbot, refs_output, verify_output],
        ).then(lambda: "", outputs=question_input)

        clear_btn.click(
            lambda: ([], "_暂无检索结果_", ""),
            outputs=[chatbot, refs_output, verify_output],
        )

    return demo


if __name__ == "__main__":
    app = create_app()
    app.launch(server_name="127.0.0.1", server_port=7860, share=False, inbrowser=True, theme=gr.themes.Soft(), css=CUSTOM_CSS)
