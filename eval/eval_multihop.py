"""多跳检索评估（Phase 0 基线 + 后续 Agent 对比的统一打分器）。

针对 eval/multihop_set.json（每题答案需 ≥2 次不同检索才能完整召回，
expected 跨多部法律），量化「单次检索 vs 多跳」的召回差距。

指标（按题平均）：
- Coverage：期望条文（跨所有法律去重后）被召回的比例 —— 多跳的核心指标。
  单跳一次 top_k 往往装不下跨法律的多个条文簇，Coverage 会明显低于 1。
- Hit：至少命中一条期望条文的题目比例。
- LawCoverage：期望涉及的「法律部数」被触及的比例（命中≥1条即算触及该法）。
  衡量单次检索是否会整部法律漏掉（多跳最该补的短板）。

用法：
    python -m eval.eval_multihop                       # 单跳基线（config.TOP_K）
    python -m eval.eval_multihop --top-k 12            # 调大 top_k 观察单跳能否逼近
    python -m eval.eval_multihop --mode fixed          # Phase 1 固定多跳（拆解→逐跳检索→合并）
    python -m eval.eval_multihop --mode agent          # Phase 2 LangGraph Agent（Planner/Reflect 自适应）
    python -m eval.eval_multihop --mode agent --save agent.json
"""
import sys
import json
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.vector_store import VectorStore

MULTIHOP_SET_PATH = Path(__file__).resolve().parent / "multihop_set.json"


def _short(law: str) -> str:
    return law.replace("中华人民共和国", "")


def _expected_pairs(case: dict) -> set:
    """把 case 的 expected（[{law, articles}]）摊平成 {(law, no)} 集合。"""
    pairs = set()
    for grp in case["expected"]:
        for no in grp["articles"]:
            pairs.add((grp["law"], no))
    return pairs


def _expected_laws(case: dict) -> set:
    return {grp["law"] for grp in case["expected"]}


def _retrieve_single(vs, question, top_k):
    """单跳：一次检索。返回 (召回 {(law,no)}, 召回法律集, 轨迹信息)。"""
    hits = vs.search(question, top_k=top_k)
    retrieved = {(h.get("law_name", ""), h["article_no"]) for h in hits}
    laws = {h.get("law_name", "") for h in hits}
    return retrieved, laws, {"hops": 1, "n_hits": len(hits)}


def _retrieve_fixed_multihop(question, top_k):
    """Phase 1 固定多跳：LLM 拆子问题 → 逐跳检索 → 合并去重。

    复用 LegalRAG._complete 作拆解 LLM、RetrieveTool 作检索（共享同一 VectorStore），
    核心逻辑统一走 src.tools.fixed_multihop_retrieve（与生产代码同源，避免评估与实现漂移）。
    """
    from src.rag import LegalRAG
    from src.tools import RetrieveTool, fixed_multihop_retrieve

    rag = _retrieve_fixed_multihop._rag
    if rag is None:
        rag = _retrieve_fixed_multihop._rag = LegalRAG()
    tool = RetrieveTool(rag.vector_store)

    result = fixed_multihop_retrieve(rag._complete, tool, question, per_hop_top_k=top_k)
    merged = result["merged"]
    retrieved = {(h.get("law_name", ""), h["article_no"]) for h in merged}
    laws = {h.get("law_name", "") for h in merged}
    return retrieved, laws, {"hops": result["hops"], "subs": result["subs"], "n_hits": len(merged)}


_retrieve_fixed_multihop._rag = None


def _retrieve_agent(question, top_k):
    """Phase 2 LangGraph Agent：Planner 判难易 → Retrieve → Reflect 自适应补跳。

    评估只看 Agent 最终喂给 Answer 的条文（state['hits']）的召回，与单跳/固定多跳口径一致。
    """
    from src.agent import LegalAgent

    agent = _retrieve_agent._agent
    if agent is None:
        agent = _retrieve_agent._agent = LegalAgent()

    final = agent.graph.invoke({"question": question, "history": []})
    hits = final.get("hits", [])
    retrieved = {(h.get("law_name", ""), h["article_no"]) for h in hits}
    laws = {h.get("law_name", "") for h in hits}
    # 轨迹里数 retrieve 节点的次数作为「实际检索轮数」
    rounds = sum(1 for t in final.get("trace", []) if t.get("node") == "retrieve")
    subs = []
    for t in final.get("trace", []):
        if t.get("node") == "planner":
            subs = t.get("subs", [])
    return retrieved, laws, {"hops": rounds, "subs": subs, "n_hits": len(hits),
                             "is_complex": final.get("is_complex")}


_retrieve_agent._agent = None


def evaluate(top_k: int, mode: str = "single", save: str = None):
    with open(MULTIHOP_SET_PATH, encoding="utf-8") as f:
        cases = json.load(f)

    vs = VectorStore() if mode == "single" else None

    tot_cov = 0.0
    tot_hit = 0
    tot_lawcov = 0.0
    tot_hops = 0
    rows = []

    for case in cases:
        q = case["question"]
        expected = _expected_pairs(case)
        exp_laws = _expected_laws(case)

        try:
            if mode == "fixed":
                retrieved, retrieved_laws, trace = _retrieve_fixed_multihop(q, top_k)
            elif mode == "agent":
                retrieved, retrieved_laws, trace = _retrieve_agent(q, top_k)
            else:
                retrieved, retrieved_laws, trace = _retrieve_single(vs, q, top_k)
        except Exception as e:
            # 单题失败（多为瞬时 API 错误）不应拖垮整轮评估：记 0 分并标注，继续下一题。
            print(f"[{mode}] !! 跳过（出错）: {q}\n   {type(e).__name__}: {e}", flush=True)
            rows.append({
                "question": q, "coverage": 0.0, "law_coverage": 0.0,
                "expected": sorted(f"{_short(l)}#{n}" for l, n in expected),
                "missed": sorted(f"{_short(l)}#{n}" for l, n in expected),
                "note": case.get("note", ""), "error": f"{type(e).__name__}: {e}",
            })
            continue

        matched = expected & retrieved
        coverage = len(matched) / len(expected) if expected else 0.0
        law_cov = len(exp_laws & retrieved_laws) / len(exp_laws) if exp_laws else 0.0

        tot_cov += coverage
        tot_hit += 1 if matched else 0
        tot_lawcov += law_cov
        tot_hops += trace["hops"]

        missed = sorted(f"{_short(l)}#{n}" for l, n in (expected - retrieved))
        row = {
            "question": q,
            "coverage": round(coverage, 3),
            "law_coverage": round(law_cov, 3),
            "expected": sorted(f"{_short(l)}#{n}" for l, n in expected),
            "missed": missed,
            "note": case.get("note", ""),
        }
        if mode in ("fixed", "agent"):
            row["subs"] = trace.get("subs", [])
            row["rounds"] = trace["hops"]
            extra = f" complex={trace.get('is_complex')}" if mode == "agent" else ""
            print(f"[{mode}] {q}\n   轮数={trace['hops']}{extra} 子问题={trace.get('subs')}\n"
                  f"   覆盖率={row['coverage']} 遗漏={missed}")
        rows.append(row)

    n = len(cases)
    label = {"single": "单跳基线", "fixed": "固定多跳(Phase1)", "agent": "LangGraph Agent(Phase2)"}.get(mode, mode)
    print(f"\n{'='*64}")
    print(f"多跳检索评估 · {label}  题目数={n}, per_hop_top_k={top_k}")
    print(f"{'='*64}")
    print(f"  Coverage:     {tot_cov / n:.3f}   (跨法律期望条文召回比例)")
    print(f"  Hit:          {tot_hit / n:.3f}   (至少命中一条的题目比例)")
    print(f"  LawCoverage:  {tot_lawcov / n:.3f}   (期望涉及法律被触及比例)")
    print(f"  平均轮数:      {tot_hops / n:.2f}")
    print(f"{'='*64}")

    if mode == "single":
        print(f"\n各题召回缺口（Coverage<1）：")
        for r in rows:
            if r["coverage"] < 1.0:
                print(f"\n  Q: {r['question']}")
                print(f"     覆盖率={r['coverage']}  期望={r['expected']}")
                print(f"     遗漏={r['missed']}")

    if save:
        summary = {
            "mode": mode,
            "top_k": top_k,
            "coverage": round(tot_cov / n, 3),
            "hit": round(tot_hit / n, 3),
            "law_coverage": round(tot_lawcov / n, 3),
            "avg_rounds": round(tot_hops / n, 2),
        }
        with open(save, "w", encoding="utf-8") as f:
            json.dump({"summary": summary, "rows": rows}, f, ensure_ascii=False, indent=2)
        print(f"\n明细已保存到 {save}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="多跳检索评估（单跳基线 / 固定多跳 / Agent）")
    ap.add_argument("--top-k", type=int, default=None, help="每跳检索条数，默认用 config.TOP_K")
    ap.add_argument("--mode", choices=["single", "fixed", "agent"], default="single",
                    help="single=单跳基线；fixed=Phase1 固定多跳；agent=Phase2 LangGraph Agent")
    ap.add_argument("--save", type=str, default=None, help="逐题明细落盘路径")
    args = ap.parse_args()

    from src import config
    evaluate(args.top_k or config.TOP_K, args.mode, args.save)
