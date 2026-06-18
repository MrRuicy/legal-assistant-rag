---
name: eval-status-2026-06-18
description: 2026-06-18 评估进度快照(Phase 0-3 部分完成,待明天额度刷新续跑)
metadata:
  type: project
---

2026-06-18 晚的评估执行进度(ModelScope 免费配额跑到大面积 429,暂停等次日刷新)。

**评估体系**: 两种正交口径 —— 口径A 检索Coverage(eval_multihop.py + multihop_set.json 20题), 口径B 答案质量LLM-judge(eval_answer.py + answer_set.json 8题)。数据集已审查过,**合理无需重建**(单跳top_k=16极限仅0.73仍有缺口,证明多跳必要;expected标注全在库内;7领域分布合理)。

**已完成**:
- Phase 0: 补全 src/tools.py 的 fixed_multihop_retrieve(之前 eval_multihop --mode fixed 会 ImportError)。占位实现固定2跳,重跑结果 Coverage 0.666/avg_hops 2.00(旧版3跳是0.771,已被覆盖)。
- Phase 1: 答案质量对比(**同裁判 DeepSeek-V4-Flash 公平对比, 8题**):
  - 单跳 overall 4.75 (acc4.88/grd4.62/cite4.62/clr4.88) — eval/answer_single_v4judge.json
  - Agent overall 4.44 (acc4.62/grd4.50/cite3.88/clr4.75) — eval/answer_agent_full.json
  - **结论: 简单题集上 Agent 退化 -0.31, 主要拖累 citation(-0.74) + 那道"危险驾驶vs交通肇事"对比题跑3跳还acc=3**。实证了 PLAN 风险点"简单/对比题 Agent 画蛇添足"。
- Phase 3(工具可观测): 扩展 eval_multihop.py 捕获 tool_resolved/tool_added_hits 统计,入 row 和 summary。

**待续跑(明天)**:
- Phase 2: eval_multihop --mode agent 验证修复后Coverage。修复前(v2)0.838→修复后波动 0.787~0.822(LLM非确定性,小样本)。avg_rounds 1.90→1.50~1.75(降了)。**关键: #10 守卫修复后的重跑被中断,需重跑确认个人信息泄露题Coverage从0.25回升**。
- 汇总 EVAL_REPORT.md(还没写)。
- README.md 表格数字需更新(phase1 0.771→0.666; 补 Agent答案质量行)。

**注意**: 跑评估会改 vector_store/chroma.sqlite3(读副作用),每次跑完 git checkout 还原。相关 [[multihop-agent-fixes]] [[llm-fallback-chain-2026-06-18]]

---

## 2026-06-19 更新: 评估全部完成 ✅

额度刷新后跑完收尾,全部三项 done:
- **Phase 2 重跑完成**: phase2_agent_fixed.json，Coverage 0.825 / LawCov 0.983 / avg_rounds 1.9。
  **#10 守卫修复验证成功**: 工具命中率 0.55→0.25(拦掉虚假触发); 触发组 Coverage 0.927 vs 未触发 0.791(修复前两组持平~0.79,工具白干); 个人信息泄露题 0.25→0.5。
- **EVAL_REPORT.md 已写**: 根目录,含双口径对比 + #10 修复验证 + 数据集审查 + 复现命令。
- **README.md / eval/README.md 数字已更新**: phase1 0.771→0.666, phase2 0.838→0.825(fixed), 答案质量 单跳4.75 vs Agent4.44(同裁判)。

**最终结论**: Agent 在复杂跨法律题召回 0.597→0.825(+38%); 简单题答案质量 4.44<单跳4.75(citation -0.74 拖累),保留单跳+深度模式开关分流正确。
**待办(后续)**: 简单题回归正式量化; multihop_set 扩到30题; Agent citation 优化。
