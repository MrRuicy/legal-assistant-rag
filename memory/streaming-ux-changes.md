---
name: streaming-ux-changes
description: 2026-06-18 三处交互流式优化(即时气泡/实时轨迹/呼吸状态行)
metadata:
  type: project
---

2026-06-18 修了三个交互体验问题,涉及 src/agent.py、src/web.py、src/rag.py。

**问题1 — 问题气泡延迟**: 回车后用户气泡迟迟不现(第一次 yield 要等后端跑完)。
修复: web.py 事件链在 _stash 与 chat_stream 之间插入 `_show_pending`,即时 append [user, assistant=""] 并返回,气泡秒现。chat_stream 改为复用末尾预追加的空气泡(prior_history = history[:-2]),不再自己 append。

**问题2 — 多跳轨迹非实时**: 原 run_stream 调 self.run() 整图跑完才一次性吐 trace。
修复: agent.py run_stream **改用 graph.stream(stream_mode='updates')** 逐节点 yield,每个节点(planner/retrieve/reflect)跑完即 yield 累积 trace,前端实时重绘。trace 在 LangGraph 状态里是全量累积的,直接取最新值即可。异常时退回 graph.invoke 兜底。

**问题3 — 等待指示位置怪**: 用呼吸状态行替代。
修复: web.py 新增 .status-line CSS(墨蓝呼吸圆点 status-pulse 动画) + _status_html()。_compose() 重构: 轨迹在最前(Agent思考过程实时展示),正文未到时显示状态行("正在检索相关条文…"/"正在生成回答…"/"正在检索并推理…"),有正文即替换。单跳在 rewrite/references chunk 处也 yield 状态行。

**Why**: 对标 DeepSeek 的实时思考过程体验。
**验证**: app.py 启动 HTTP 200,run_stream 实测逐节点输出(planner→retrieve→answer 三次 trace 而非一次)。
相关 [[multihop-agent-fixes]] [[ui-redesign-light]]
