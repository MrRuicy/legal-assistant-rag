"""答案质量评估（item 2：LLM-as-judge）。

现有 eval/evaluate.py 只量化「检索」(Recall/Hit/MRR)，但 LLM 生成的「答案」质量
没有评估闭环——调 prompt / 换模型时无据可依。本脚本补上这一环：

对 eval/answer_set.json 的每道题，跑完整 RAG（检索 + 生成），再用一个 LLM 裁判
按四个维度打分（1~5）：
  - accuracy   法律准确性：是否符合 key_points、有无错引/曲解
  - grounding  忠于检索：结论是否有引用条文支撑、有无脱离条文的编造
  - citation   引用规范：是否按"《法律名》第X条"写明且条号正确
  - clarity    表达清晰：通俗、有条理

裁判默认复用 RAG 的故障转移链（config.LLM_PROVIDERS 第一档）。负样本（无关问题）
单独判：期望模型拒答 / 回未找到，accuracy 以"是否正确拒答"为准。

用法：
    python -m eval.eval_answer                  # 评估全部题目
    python -m eval.eval_answer --limit 3        # 只评前 3 题（省配额）
    python -m eval.eval_answer --save out.json  # 同时落盘逐题明细
"""
import sys
import json
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import config
from src.rag import LegalRAG

ANSWER_SET_PATH = Path(__file__).resolve().parent / "answer_set.json"

DIMENSIONS = ["accuracy", "grounding", "citation", "clarity"]

JUDGE_SYSTEM = """你是严格的法律问答质检员。针对给定问题、参考要点与 AI 回答，按四个维度各打 1~5 分（整数）：
- accuracy（法律准确性）：是否覆盖参考要点、有无错误或曲解。
- grounding（忠于检索）：结论是否基于检索条文、有无脱离条文的编造。
- citation（引用规范）：是否写明"《法律名》第X条"且条号正确。
- clarity（表达清晰）：是否通俗、有条理。
只输出 JSON：{"accuracy":int,"grounding":int,"citation":int,"clarity":int,"comment":"一句话点评"}。"""

NEGATIVE_SYSTEM = """这是一个与法律无关的问题（负样本）。正确做法是 AI 应拒答或回复"未找到相关条文"，且不编造任何法律条文。
请判断 AI 回答是否正确处理，按四个维度打 1~5 分（整数）：
- accuracy：是否正确识别为无关并拒答（正确=5，编造条文=1）。
- grounding：有无编造条文（无编造=5）。
- citation：不该有具体条文引用（无引用=5，乱引=1）。
- clarity：回复是否清楚。
只输出 JSON：{"accuracy":int,"grounding":int,"citation":int,"clarity":int,"comment":"一句话点评"}。"""


def _judge(rag: LegalRAG, case: dict, answer_text: str) -> dict:
    is_negative = not case.get("law")
    sys_prompt = NEGATIVE_SYSTEM if is_negative else JUDGE_SYSTEM
    points = "\n".join(f"- {p}" for p in case.get("key_points", []))
    user = f"""问题：{case['question']}
适用法律：{case.get('law') or '（无 / 与法律无关）'}
参考要点：
{points or '（无）'}

AI 回答：
{answer_text}

请打分并只输出 JSON。"""
    raw = rag._complete(
        messages=[
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user},
        ],
        temperature=0,
    )
    return _parse_scores(raw)


def _parse_scores(raw: str) -> dict:
    """从裁判输出里抠出 JSON 分数；解析失败则记 0 分并附原文。"""
    text = raw.strip()
    # 去掉可能的 ```json 围栏
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{"):]
    try:
        start, end = text.index("{"), text.rindex("}") + 1
        obj = json.loads(text[start:end])
        return {d: int(obj.get(d, 0)) for d in DIMENSIONS} | {"comment": obj.get("comment", "")}
    except Exception:
        return {d: 0 for d in DIMENSIONS} | {"comment": f"[解析失败] {raw[:80]}"}


def evaluate(limit: int = None, save: str = None):
    with open(ANSWER_SET_PATH, encoding="utf-8") as f:
        cases = json.load(f)
    if limit:
        cases = cases[:limit]

    rag = LegalRAG()
    rows = []
    totals = {d: 0.0 for d in DIMENSIONS}

    for i, case in enumerate(cases, 1):
        print(f"[{i}/{len(cases)}] {case['question']}")
        # 跑完整 RAG（非流式，便于评估）
        result = rag.answer(case["question"])
        answer_text = result["answer"]
        scores = _judge(rag, case, answer_text)
        for d in DIMENSIONS:
            totals[d] += scores[d]
        avg = sum(scores[d] for d in DIMENSIONS) / len(DIMENSIONS)
        print(f"     acc={scores['accuracy']} ground={scores['grounding']} "
              f"cite={scores['citation']} clarity={scores['clarity']}  ▸ {scores['comment']}")
        rows.append({
            "question": case["question"],
            "law": case.get("law", ""),
            "scores": scores,
            "avg": round(avg, 2),
            "answer": answer_text,
            "references": [
                {"law": r.get("law_name"), "article_no": r["article_no"], "sub_no": r.get("sub_no", 0)}
                for r in result["references"]
            ],
        })

    n = len(cases)
    print(f"\n{'='*60}")
    print(f"答案质量评估  (题目数={n}, 裁判={config.LLM_PROVIDERS[0]['model']})")
    print(f"{'='*60}")
    for d in DIMENSIONS:
        print(f"  {d:10s}: {totals[d]/n:.2f} / 5")
    overall = sum(totals.values()) / (len(DIMENSIONS) * n)
    print(f"  {'综合':10s}: {overall:.2f} / 5")
    print(f"{'='*60}")

    if save:
        out = Path(save)
        with open(out, "w", encoding="utf-8") as f:
            json.dump({"summary": {d: round(totals[d]/n, 2) for d in DIMENSIONS},
                       "overall": round(overall, 2), "rows": rows},
                      f, ensure_ascii=False, indent=2)
        print(f"逐题明细已保存到 {out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="答案质量评估（LLM-as-judge）")
    ap.add_argument("--limit", type=int, default=None, help="只评前 N 题（省配额）")
    ap.add_argument("--save", type=str, default=None, help="逐题明细落盘路径")
    args = ap.parse_args()
    evaluate(args.limit, args.save)
