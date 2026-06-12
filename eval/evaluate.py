"""检索质量评估脚本。

针对评估集 eval/eval_set.json，逐题调用 VectorStore.search，
计算检索指标，量化每次优化（阈值过滤 / rerank / 混合检索）的效果。

指标：
- Recall@K：期望条文中被召回的比例（平均）
- Hit@K：至少命中一条期望条文的题目比例
- MRR：首个命中条文排名的倒数（平均），衡量命中条文是否排在前面

用法：
    python -m eval.evaluate            # 用 config.TOP_K
    python -m eval.evaluate --top-k 10
"""
import sys
import json
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.vector_store import VectorStore

EVAL_SET_PATH = Path(__file__).resolve().parent / "eval_set.json"


def evaluate(top_k: int):
    with open(EVAL_SET_PATH, encoding="utf-8") as f:
        eval_set = json.load(f)

    vs = VectorStore()

    total_recall = 0.0
    total_hit = 0
    total_rr = 0.0
    misses = []

    for case in eval_set:
        question = case["question"]
        expected = set(case["expected_articles"])

        hits = vs.search(question, top_k=top_k)
        retrieved = [h["article_no"] for h in hits]
        retrieved_set = set(retrieved)

        # Recall@K
        matched = expected & retrieved_set
        recall = len(matched) / len(expected) if expected else 0.0
        total_recall += recall

        # Hit@K
        hit = 1 if matched else 0
        total_hit += hit

        # MRR：第一个命中期望条文的排名
        rr = 0.0
        for rank, art_no in enumerate(retrieved, 1):
            if art_no in expected:
                rr = 1.0 / rank
                break
        total_rr += rr

        if recall < 1.0:
            misses.append({
                "question": question,
                "expected": sorted(expected),
                "retrieved": retrieved,
                "missed": sorted(expected - retrieved_set),
                "note": case.get("note", ""),
            })

    n = len(eval_set)
    print(f"\n{'='*60}")
    print(f"检索评估结果  (题目数={n}, top_k={top_k})")
    print(f"{'='*60}")
    print(f"  Recall@{top_k}:  {total_recall / n:.3f}   (期望条文召回比例)")
    print(f"  Hit@{top_k}:     {total_hit / n:.3f}   (至少命中一条的题目比例)")
    print(f"  MRR:        {total_rr / n:.3f}   (首个命中条文的排名倒数)")
    print(f"{'='*60}")

    if misses:
        print(f"\n未完全召回的题目（{len(misses)}/{n}）：")
        for m in misses:
            print(f"\n  Q: {m['question']}  [{m['note']}]")
            print(f"     期望: {m['expected']}")
            print(f"     召回: {m['retrieved']}")
            print(f"     遗漏: {m['missed']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="检索质量评估")
    parser.add_argument("--top-k", type=int, default=None, help="检索条数，默认用 config.TOP_K")
    args = parser.parse_args()

    from src import config
    evaluate(args.top_k or config.TOP_K)
