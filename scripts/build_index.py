"""向量库构建脚本。

首次部署 / 接入新法律后运行,解析法律 markdown 并构建向量索引。
数据源是本地克隆的 LawRefBook/Laws（项目根 `Laws/` 目录，不随仓库提交）。
启动服务请用 `python api.py`（FastAPI 后端）。

用法：python scripts/build_index.py
"""
import sys
from pathlib import Path

# scripts/ 在项目根下一层，回到根目录以导入 src
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import config
from src import law_catalog
from src.parser import (
    parse_all_civil_code,
    parse_law_markdown,
    save_to_json,
)
from src.vector_store import build_vector_store


def _collect_articles():
    """汇总要入库的条文：民法典 + 精选目录（均来自本地 Laws/，存在才接入）。"""
    articles = []

    # 1. 民法典（Laws/民法典，按编拆分的多个 md）
    civil_dir = law_catalog.civil_code_dir()
    if civil_dir.exists():
        civ = parse_all_civil_code(civil_dir)
        articles.extend(civ)
        print(f"OK - 民法典 {len(civ)} 条（来源 {civil_dir}）")
    else:
        print(f"WARN - 未找到 {civil_dir}，跳过民法典。")
        print("       （请克隆 LawRefBook/Laws 到项目根的 Laws/ 目录）")

    # 2. 精选法律目录
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
            f"如需精简，可缩减 LAW_CATALOG，或在 .gitignore 忽略 vector_store/ 改为运行时构建。"
        )


def main():
    """解析法律文本 + 构建向量库。"""
    print("=== Step 1: Parse markdown（民法典 + 精选目录）===")
    articles = _collect_articles()
    if not articles:
        print("ERROR - 没有解析到任何条文。请先克隆 Laws/ 到项目根。")
        sys.exit(1)
    print(f"OK - 合计 {len(articles)} 条")

    print("\n=== Step 2: Save JSON ===")
    json_path = config.DATA_PROCESSED_DIR / "articles.json"
    save_to_json(articles, json_path)
    print(f"OK - Saved to {json_path}")

    print("\n=== Step 3: Build vector store ===")
    build_vector_store()
    print("OK - Vector store built")

    _warn_if_large()


if __name__ == "__main__":
    main()
