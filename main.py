"""主入口脚本：构建向量库 + 启动 Web 服务。"""
import sys
from pathlib import Path

import gradio as gr

# 确保能导入 src
sys.path.insert(0, str(Path(__file__).parent))

from src import config
from src import law_catalog
from src.parser import (
    parse_all_civil_code,
    parse_law_markdown,
    save_to_json,
)
from src.vector_store import build_vector_store
from src.web import create_app, CUSTOM_CSS


def _collect_articles():
    """汇总要入库的条文：民法典（data/raw）+ 精选目录（本地 Laws/，存在才接入）。"""
    articles = []

    # 1. 民法典：优先用本地 Laws/民法典，回退到 data/raw
    civil_dir = law_catalog.civil_code_dir()
    if not civil_dir.exists():
        civil_dir = config.DATA_RAW_DIR
    civ = parse_all_civil_code(civil_dir)
    articles.extend(civ)
    print(f"OK - 民法典 {len(civ)} 条（来源 {civil_dir}）")

    # 2. 精选法律目录（需本地克隆 LawRefBook/Laws）
    resolved, missing = law_catalog.resolve_catalog()
    for path, eff in resolved:
        arts = parse_law_markdown(path, effective_date=eff)
        articles.extend(arts)
        name = arts[0].law_name if arts else path.stem
        print(f"OK - {name} {len(arts)} 条")
    if missing:
        print(f"WARN - 以下精选法律在本地 Laws/ 未找到，已跳过：")
        for m in missing:
            print(f"       - {m}")
        print("       （如需接入，请克隆 LawRefBook/Laws 到项目根的 Laws/ 目录）")

    return articles


def _warn_if_large():
    """构建后检查向量库体积，超阈值时给出护栏提示。"""
    total = 0
    if config.VECTOR_STORE_DIR.exists():
        for p in config.VECTOR_STORE_DIR.rglob("*"):
            if p.is_file():
                total += p.stat().st_size
    mb = total / (1024 * 1024)
    print(f"\n向量库体积：{mb:.1f} MB")
    if mb > config.VECTOR_STORE_WARN_MB:
        print(
            f"WARN - 向量库超过 {config.VECTOR_STORE_WARN_MB} MB。仓库会随之变大；"
            f"如需精简，可在 .env 设 EMBED/缩减 LAW_CATALOG，或改为启动时构建"
            f"（取消 .gitignore 对 vector_store/ 的放开，依赖 app.py 兜底构建）。"
        )


def setup():
    """初始化：解析法律文本 + 构建向量库（首次运行必须执行）。

    会接入民法典 + src/law_catalog.py 里在本地 Laws/ 能找到的精选法律。
    """
    print("=== Step 1: Parse markdown（民法典 + 精选目录）===")
    articles = _collect_articles()
    print(f"OK - 合计 {len(articles)} 条")

    print("\n=== Step 2: Save JSON ===")
    json_path = config.DATA_PROCESSED_DIR / "civil_code.json"
    save_to_json(articles, json_path)
    print(f"OK - Saved to {json_path}")

    print("\n=== Step 3: Build vector store ===")
    build_vector_store()
    print("OK - Vector store built")

    _warn_if_large()


def serve():
    """启动 Gradio Web 服务。"""
    # 检查向量库是否存在
    if not config.VECTOR_STORE_DIR.exists() or not list(config.VECTOR_STORE_DIR.iterdir()):
        print("ERROR - Vector store not initialized. Run: python main.py setup")
        sys.exit(1)

    print("=== Starting Gradio Web ===")
    app = create_app()
    app.launch(server_name="127.0.0.1", server_port=7860, share=False, inbrowser=True, theme=gr.themes.Soft(), css=CUSTOM_CSS)


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
