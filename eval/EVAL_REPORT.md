# 法律助手 RAG 评估报告

> 生成日期：2026-06-19 · 评估对象：单跳 RAG vs 多跳 Agent
> 对应方案：[PLAN.md](PLAN.md) 多跳检索 Agent 升级

---

## 一、结论速览

| 维度 | 单跳 | 多跳 Agent | 判断 |
|---|---|---|---|
| 检索 Coverage（跨法律条文召回） | 0.597 | **0.825** | ✅ Agent 大幅领先(+38%) |
| 答案质量（LLM-judge，简单题集） | **4.75** | 4.44 | ⚠️ Agent 在简单题上退化 -0.31 |

**核心结论**：多跳 Agent 在**复杂跨法律问题**上召回显著更全（结构性优势，单跳调大 top_k 也补不上）；但在**简单题**上会画蛇添足、反而略差。**保留单跳 + 深度模式开关分流是正确设计**。

---

## 二、口径 A：检索 Coverage（多跳的核心价值）

题集：[multihop_set.json](eval/multihop_set.json) 20 道多跳题（答案需 ≥2 次检索才能召全，expected 跨多部法律）。

| 模式 | Coverage | Hit | LawCoverage | 平均轮数 | 工具 |
|------|----------|-----|-------------|----------|------|
| 单跳基线 | 0.597 | 1.0 | 0.950 | 1 | — |
| 固定多跳 (Phase1) | 0.666 | 1.0 | 0.983 | 2.0 | — |
| **Agent (修复后)** | **0.825** | 1.0 | 0.983 | 1.9 | 命中率 0.25 / 补 14 条 |

**关键证据**：单跳即便把 top_k 调到 16，Coverage 极限也只有 0.73（实测），仍有结构性缺口——单个 query 召不全跨法律的多个条文簇。**这正是多跳规划的价值所在**，不是单纯增大 top_k 能替代的。

**Agent vs 固定多跳**：固定两跳 0.666，Agent 自适应补跳到 0.825。Agent 的 Planner/Reflect 能按问题难度动态决定跳数（avg 1.9），比死板两跳更优。

---

## 三、口径 B：答案质量（LLM-as-judge）

题集：[answer_set.json](eval/answer_set.json) 8 道题（7 正样本简单题 + 1 负样本），**同一裁判 DeepSeek-V4-Flash** 打分，四维度 1~5。

| 模式 | accuracy | grounding | citation | clarity | 综合 |
|------|----------|-----------|----------|---------|------|
| 单跳 | 4.88 | 4.62 | 4.62 | 4.88 | **4.75** |
| 多跳 Agent | 4.62 | 4.50 | 3.88 | 4.75 | **4.44** |

**发现**：在简单题集上 Agent 综合分 **低于** 单跳（-0.31），主要拖累：
- **citation -0.74**：多跳召回更多条文，Answer 引用时更易出条号偏差。
- 个别对比题（「危险驾驶 vs 交通肇事」）Agent 跑 3 跳后反而以「检索缺失」拒答，acc 仅 3。

**这印证了 [PLAN.md](PLAN.md) 五的风险点**：「简单/对比题上 Agent 可能画蛇添足」。也是保留单跳模式 + Web 深度模式开关的依据——简单题走单跳，复杂题才开 Agent。

---

## 四、本轮修复对评估的影响

本次修了多跳 Agent 的一批 bug（详见提交记录），其中**评估直接验证了两项**：

### #10 交叉引用工具短路语义检索（评估暴露 + 验证修复）
- **问题**：工具用 `re.search` 在整个 missing 串里找条号，导致「碰巧含条号的长语义子问题」被误判为可用工具解决，**短路掉本该走的语义检索**。
- **症状**：个人信息泄露题 Coverage 塌到 0.25；工具命中率虚高 0.55，但触发组(0.789) vs 未触发组(0.785) Coverage 几乎无差——**工具白干**。
- **修复**：新增 `_is_clean_article_ref()` 守卫，仅当 missing 是「干净条号引用」才走工具。
- **修复后验证**：
  - 工具命中率 0.55 → **0.25**（拦掉了虚假触发）
  - 触发组 Coverage **0.927** vs 未触发组 0.791（修复前两组持平）——**工具真正帮上忙了**
  - 个人信息泄露题 0.25 → **0.5**（不再被短路）

### Phase 1 固定多跳脚本修复
- 之前 `eval_multihop --mode fixed` 因 `fixed_multihop_retrieve` 缺失直接 ImportError。
- 补全占位实现（固定两跳），结果 Coverage 0.666 / avg_hops 2.0，可复现。

---

## 五、评估方法与可复现

```bash
# 口径 A：检索 Coverage
python -m eval.eval_multihop --mode single  --save eval/baseline_singlehop.json
python -m eval.eval_multihop --mode fixed   --save eval/phase1_fixed_multihop.json
python -m eval.eval_multihop --mode agent   --save eval/phase2_agent_fixed.json

# 口径 B：答案质量（须用同一裁判才可比）
python -m eval.eval_answer --mode single --save eval/answer_single_v4judge.json
python -m eval.eval_answer --mode agent  --save eval/answer_agent_full.json
```

**注意**：
- 答案质量对比**必须用同一裁判模型**，否则不可比（旧 answer_single.json 用的是 DeepSeek-V3.2 裁判，已重跑 v4judge 版对齐）。
- 跑评估会改 `vector_store/chroma.sqlite3`（读副作用），跑完 `git checkout` 还原。

---

## 六、数据集合理性（已审查，无需重建）

- **multihop_set（20 题）**：单跳 top_k=16 极限仅 0.73 仍有缺口 → 证明多跳必要；expected 标注全部在向量库内；7 个法律领域分布均衡（劳动/消费/行政/刑民交叉等）。
- **样本量**：20 题偏小，Coverage 差值在小样本+LLM 非确定性下有 ±0.02~0.04 波动，趋势可信但精确值仅供参考。
- **后续可选**：从 eval_set.json（100 题）补标 10 道多跳题到 30 题，提高统计功效。

---

## 七、待办

- [ ] 简单题回归测试（PLAN 底线「Agent 不退化」的正式量化，目前只有 answer_set 8 题侧证）。
- [ ] multihop_set 扩到 30 题。
- [ ] Agent citation 维度优化（多跳召回多条文时的引用准确性）。
