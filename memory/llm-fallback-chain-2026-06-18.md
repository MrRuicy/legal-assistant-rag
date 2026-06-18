---
name: llm-fallback-chain-2026-06-18
description: 2026-06-18 根据实时配额优化 LLM 故障转移链(DeepSeek-V3.2 耗尽 → Qwen3.5 系列前置)
metadata:
  type: project
---

**背景**: 2026-06-18 晚,跑评估前探测配额。先是发现 deepseek-ai/DeepSeek-V3.2 当日 429 耗尽,改 Qwen3.5-397B 首选;但**实测 397B 会 read timeout 挂起**(>60s 不回包,正是评估卡死根因)。随后多档快模型(Flash/Qwen3-Next/Kimi)也被评估跑到 429。

**最终链**(.env 实测后定稿):
- `LLM_MODEL`: `Qwen/Qwen3.5-122B-A10B` (~10s,稳定可用)
- `LLM_FALLBACK_MODELS`: `ZhipuAI/GLM-5.1`(~14s) → `DeepSeek-V4-Flash` → `Qwen3-Next-80B` → `Kimi-K2.5` → `MiniMax-M2.5` → `DeepSeek-V3.2`(殿后,明日恢复)
- **Qwen3.5-397B 已剔除**(会挂起)。

**断路器机制**(rag.py): 撞 429 立即(毫秒级)切下一档并记冷却,非等超时;429 区分每日耗尽(长冷却 3600s)与 RPM 限速(短冷却 90s)。**但冷却表是实例级、进程内**——每次重跑 `python -m eval.*` 是新进程,冷却表清空,耗尽档需重撞一次(这是跨进程重跑评估开头略慢的原因)。

**How to apply**: 明日额度刷新后,可把快模型(DeepSeek-V4-Flash 0.2s / Qwen3-Next 1.1s)提回首选以加速。生产/评估自动按链故障转移。相关 [[multihop-agent-fixes]] [[eval-status-2026-06-18]]
