"""ModelScope 创空间入口。

创空间默认运行 app.py。与本地 main.py serve 的区别：
- server_name 用 0.0.0.0（对外可访问），端口 7860
- 不自动打开浏览器（服务器无 GUI）
- 向量库缺失时自动构建作兜底（正常情况下向量库已随仓库提交）

运行时仍需在创空间「环境变量」中配置：
- MODELSCOPE_API_KEY    （LLM 生成）
- SILICONFLOW_API_KEY   （每次提问的 query embedding）
- EMBEDDING_PROVIDER=siliconflow
- 可选 LLM_MODEL / LLM_FALLBACK_MODELS
"""
import sys
from pathlib import Path

import gradio as gr

sys.path.insert(0, str(Path(__file__).parent))

from src import config
from src.web import create_app, CUSTOM_CSS


def _ensure_vector_store():
    """确保向量库就绪：缺失则现场构建（兜底，正常应已随仓库提交）。"""
    if config.VECTOR_STORE_DIR.exists() and list(config.VECTOR_STORE_DIR.iterdir()):
        return
    print("WARN - 向量库不存在，开始现场构建（需 embedding API，耗时较长）...")
    from src.parser import parse_all_civil_code, save_to_json
    from src.vector_store import build_vector_store

    json_path = config.DATA_PROCESSED_DIR / "civil_code.json"
    if not json_path.exists():
        articles = parse_all_civil_code(config.DATA_RAW_DIR)
        save_to_json(articles, json_path)
    build_vector_store()
    print("OK - 向量库构建完成")


_ensure_vector_store()
demo = create_app()

if __name__ == "__main__":
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
        theme=gr.themes.Soft(),
        css=CUSTOM_CSS,
    )
