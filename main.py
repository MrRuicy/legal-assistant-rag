"""主入口脚本：构建向量库 + 启动 Web 服务。"""
import sys
from pathlib import Path

import gradio as gr

# 确保能导入 src
sys.path.insert(0, str(Path(__file__).parent))

from src import config
from src.parser import parse_all_civil_code, save_to_json
from src.vector_store import build_vector_store
from src.web import create_app


def setup():
    """初始化：解析法律文本 + 构建向量库（首次运行必须执行）。"""
    print("=== Step 1: Parse markdown ===")
    articles = parse_all_civil_code(config.DATA_RAW_DIR)
    print(f"OK - Parsed {len(articles)} articles")

    print("\n=== Step 2: Save JSON ===")
    save_to_json(articles, config.DATA_PROCESSED_DIR / "civil_code.json")
    print(f"OK - Saved to {config.DATA_PROCESSED_DIR / 'civil_code.json'}")

    print("\n=== Step 3: Build vector store ===")
    build_vector_store()
    print("OK - Vector store built")


def serve():
    """启动 Gradio Web 服务。"""
    # 检查向量库是否存在
    if not config.VECTOR_STORE_DIR.exists() or not list(config.VECTOR_STORE_DIR.iterdir()):
        print("ERROR - Vector store not initialized. Run: python main.py setup")
        sys.exit(1)

    print("=== Starting Gradio Web ===")
    app = create_app()
    app.launch(server_name="127.0.0.1", server_port=7860, share=False, inbrowser=True, theme=gr.themes.Soft())


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "serve"

    if cmd == "setup":
        setup()
    elif cmd == "serve":
        serve()
    else:
        print("Usage: python main.py [setup|serve]")
        print("  setup: 初始化（解析法律文本 + 构建向量库）")
        print("  serve: 启动 Web 服务（默认）")
