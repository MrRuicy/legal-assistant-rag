# 评估体系说明

本项目的评估分**两种正交口径**，分别由不同脚本产出，对应不同 JSON 结果文件。
理解这两种口径的区别，是读懂 `eval/` 下结果文件的关键。

---

## 口径 A：检索 Coverage（召回质量）

**测什么**：检索到的条文 vs 标注的 ground-truth 条文的覆盖率。只看「检索召回」，不看 LLM 答案。

- **脚本**：`eval_multihop.py`
- **题集**：`multihop_set.json`（20 道多跳题，每题标注 `expected` 跨法律条文号）
- **指标**：
  - `Coverage`：期望条文被召回的比例（核心指标）
  - `Hit`：至少命中一条的题目比例
  - `LawCoverage`：期望涉及的法律被触及的比例
  - `avg_hops/avg_rounds`：平均检索轮数

**用法**:
```bash
python -m eval.eval_multihop --mode single          # 单跳基线
python -m eval.eval_multihop --mode fixed           # Phase 1 固定多跳
python -m eval.eval_multihop --mode agent --save out.json  # Phase 2 Agent,保存结果
```

**历史成绩记录**:

| 阶段 | Coverage | LawCoverage | 平均轮数 |
|------|----------|-------------|----------|
| 单跳基线 | 0.597 | 0.950 | 1 |
| Phase 1 固定多跳（占位实现，固定 2 跳） | 0.666 | 0.983 | 2.0 |
| Phase 2 Agent v1（历史，MAX_CONTEXT=16，旧 Reflect） | 0.716 | 0.958 | 1.15 |
| Phase 2 Agent v2（历史，MAX_CONTEXT=24 + 新 Reflect） | 0.838 | 0.983 | 1.90 |
| **Phase 2 Agent（2026-06 修复后，含 #10 守卫 + 工具统计）** | **0.825** | **0.983** | 1.90 |

> ⚠️ 注意：这些数字测的是**检索 Coverage**（不是答案质量）。最新版本含 9+1 项 bug 修复
> （交叉引用方向/条号正则/AGENT_MAX_CONTEXT 截断/#10 工具短路守卫等）。
> v2 的 0.838 与 fixed 的 0.825 差异在小样本(20题)+LLM 非确定性下属噪声；fixed 版工具命中率从虚高的
> 0.55 降到合理的 0.25，且工具触发组 Coverage(0.927) 显著高于未触发组(0.791)——工具真正生效。
> 完整分析见 [EVAL_REPORT.md](EVAL_REPORT.md)。

**关键结论**：单跳调大 top_k（8→16）只到 0.688，而 Agent 多跳到 0.825——证明缺口是结构性的
（单 query 召不全跨法律条文簇），需要多跳规划而非单纯增大 top_k。

---

## 口径 B：答案质量（LLM-as-judge）

**测什么**：完整跑链路（检索 + 生成）后，用一个 LLM 裁判给最终答案按四维度打分（1~5）。

- **脚本**：`eval_answer.py`
- **题集**：`answer_set.json`（8 道题，带 `key_points` 供裁判核对，含 1 道负样本）
- **维度**：accuracy（准确性）/ grounding（忠于检索）/ citation（引用规范）/ clarity（清晰度）

**用法**:
```bash
python -m eval.eval_answer --mode single --save answer_single.json   # 单跳
python -m eval.eval_answer --mode agent  --save answer_agent.json    # 多跳 Agent
python -m eval.eval_answer --limit 3                                 # 只评前 3 题（省配额）
```

**历史成绩记录**:

| 模式 | accuracy | grounding | citation | clarity | 综合 |
|------|----------|-----------|----------|---------|------|
| 单跳 | 4.62 | 4.25 | 4.75 | 4.88 | 4.62 |
| 多跳 Agent | （部分跑过，见下） | | | | |

> Agent 版答案质量评估部分跑过，发现一个值得注意的现象：**多跳 Agent 不一定优于单跳**。
> 例如「危险驾驶罪和交通肇事罪区别」一题，Agent 跑 3 轮后反而以「检索缺失」为由拒答（acc 偏低）——
> 简单/对比题上 Agent 可能画蛇添足。这也是保留单跳模式 + 深度模式开关的依据。

---

## 其他文件

- `eval_set.json` / `evaluate.py`：早期单跳检索评估（100 题，Recall/Hit/MRR），第一版基线用。
- `_discover_articles.py`：Phase 0 造多跳题时的一次性辅助脚本（为子查询跑检索、人工 curate
  ground-truth），保留备查，非评估流程的一部分。
- `*.log`：运行日志，已在 `.gitignore` 忽略，不入库。

---

## 两种口径如何配合

- **Coverage（口径 A）** 回答「检索够不够全」——多跳的核心价值在这里（0.597→0.825）。
- **答案质量（口径 B）** 回答「最终答案好不好」——守住底线：Agent 不能在简单题上退化。

二者正交：高 Coverage 是好答案的必要条件，但不充分（条文召回了，LLM 也可能答偏）。
完整验收需要两个口径都看。
