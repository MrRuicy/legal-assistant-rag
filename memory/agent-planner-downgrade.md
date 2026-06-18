---
name: agent-planner-downgrade
description: 多跳 Agent 的「简单题降级」(#7) 影响面有限，已决定暂不改
metadata:
  type: project
---

多跳 Agent (src/agent.py) 的「简单题降级」偏差 (#7)：Planner 判 is_complex=False 时仍走
`Planner → Retrieve → Answer`，比 PLAN 设想的「直接甩回 rag.py 单跳快路径」多付一次 Planner LLM 调用。

**Why:** 影响面比初判要小——只在「用户在 web 界面手动勾了深度模式 (agent_mode=True)、但又问了个简单题」这一交叉场景下才浪费一次便宜模型调用。用户没勾深度模式时直接走 rag.answer_stream 纯单跳，根本不碰 Planner。深度模式开关 (web.py:471/517) 与 Planner 降级是两个不同层级的开关：前者用户手动决定走不走 Agent，后者是 Agent 内部进图后 LLM 自动判简单/复杂。

**How to apply:** 暂不改。改动收益小（低频场景省一次便宜调用），且会牺牲一致性（深度模式下简单题会丢失 trace 轨迹，用户勾了深度模式却看不到 Agent 轨迹会困惑）。日期：2026-06-18 决定。相关 [[multihop-agent-fixes]]
