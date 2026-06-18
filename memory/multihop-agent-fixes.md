---
name: multihop-agent-fixes
description: 2026-06-18 多跳 Agent 的 9+1 项 bug 修复(交叉引用/时效/截断/守卫等)
metadata:
  type: project
---

2026-06-18 检查「多跳检索 Agent 升级方案」(PLAN.md)落地后的问题,修复了一批 bug。涉及 src/agent.py、src/tools.py、eval/eval_multihop.py。

**已修复并验证(代码层)**:
1. 交叉引用工具 KeyError 'law' — tools.py 键名应为 law_name/article_no(实跑 KeyError → 正常)
2. 交叉引用逻辑方向反了 — 新增 LegalTools.get_article(),"缺第X条"返回该条原文本身(+其引用),而非它引用的条文
3. AGENT_MAX_CONTEXT 截断未接上 — agent.py Answer 节点现按 config.AGENT_MAX_CONTEXT 截断(实测 29→24)
4. Reflect 条号正则只认阿拉伯数字 — 扩展支持中文数字+空格("第 27 条")+法律名简称→库内全称解析(《民法典》→中华人民共和国民法典)
5. 时效计算 365 天近似忽略闰年 — tools.py 新增 _add_years() 按日历年加(2/29 回退 2/28)
6. 删死代码 decompose_query / _parse_str_list
7. 工具调用加 try/except 兜底,异常不冒泡打挂 run()
8. **(实际使用暴露的流式 bug)** 流式输出一段后报 "list index out of range" — rag.py:189 `chunk.choices[0]` 在 choices 为空列表时 IndexError。许多 OpenAI 兼容供应商(ModelScope/Qwen/GLM)流式收尾发只带 usage 的空 choices chunk,或中途发 role-only 空 chunk。因 produced=True 无法重试 → web 层显示"⚠️ LLM 调用失败"。修复: _stream_complete 先判 `if not choices: continue`,delta 也判空。已用真实流式调用验证通过。
10. **(Phase 3 评估暴露的新问题)** 交叉引用工具用 re.search 在整个 miss 找条号,导致长语义子问题(碰巧含条号)被短路掉本该走的语义检索 → 个人信息泄露题 Coverage 塌到 0.25。修复: agent.py 新增 _is_clean_article_ref() 守卫,仅当 miss 是"干净条号引用"才走工具。**此修复跑评估验证被中断(配额耗尽),待明天额度刷新后重跑确认。**

**#7 单跳降级偏差: 暂不改**(见 [[agent-planner-downgrade]])

**未做(需用户拍板/后续)**: #8 简单题回归测试、#9 LLM-judge 报告(已部分跑)、扩题集 20→30。

依赖: 验证用 .venv 缺 langgraph,已 pip install langgraph>=1.2.0(装了 1.2.5)。requirements.txt 已声明但 .venv 未装。
