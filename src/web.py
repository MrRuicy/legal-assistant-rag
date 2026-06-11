"""Gradio Web 界面。"""
import gradio as gr

from .rag import LegalRAG


def create_app():
    rag = LegalRAG()

    def chat(question: str, top_k: int) -> tuple[str, str]:
        """Gradio 回调：返回 (答案, 引用条文)。"""
        if not question.strip():
            return "请输入您的法律问题。", ""

        result = rag.answer(question, top_k=top_k)

        # 格式化引用条文
        refs_text = ""
        if result["references"]:
            refs_text = "**检索到的相关条文：**\n\n"
            for ref in result["references"]:
                refs_text += (
                    f"- **第{ref['article_no']}条**（{ref['part']} {ref['chapter']}）\n"
                    f"  {ref['article_text']}\n\n"
                )

        answer_full = f"{result['answer']}\n\n---\n\n{result['disclaimer']}"

        return answer_full, refs_text

    with gr.Blocks(title="民法典法律助手", theme=gr.themes.Soft()) as demo:
        gr.Markdown("# ⚖️ 民法典法律助手")
        gr.Markdown("基于 RAG 的《中华人民共和国民法典》智能问答系统")

        with gr.Row():
            with gr.Column(scale=2):
                question_input = gr.Textbox(
                    label="请输入您的法律问题",
                    placeholder="例如：父母与成年子女之间有哪些法定义务？",
                    lines=3,
                )
                top_k_slider = gr.Slider(
                    minimum=1, maximum=10, value=5, step=1,
                    label="检索条文数量（Top-K）",
                )
                submit_btn = gr.Button("提交问题", variant="primary")

            with gr.Column(scale=3):
                answer_output = gr.Markdown(label="回答")

        with gr.Accordion("📜 引用条文（详细）", open=False):
            refs_output = gr.Markdown()

        submit_btn.click(
            fn=chat,
            inputs=[question_input, top_k_slider],
            outputs=[answer_output, refs_output],
        )

        gr.Markdown("""
---
### 使用说明
- 本系统基于《中华人民共和国民法典》（2021年实施）构建
- 回答均基于实际法律条文，并在答案中标注引用来源
- 本系统仅供学习参考，不构成法律建议
- 若需专业法律意见，请咨询执业律师
        """)

    return demo


if __name__ == "__main__":
    app = create_app()
    app.launch(server_name="127.0.0.1", server_port=7860, share=False, inbrowser=True)
