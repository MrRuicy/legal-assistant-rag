---
name: ui-redesign-light
description: 2026-06-18 UI 改版为「浅色清雅」(暖白底 + 墨蓝点缀 + 书卷气)
metadata:
  type: project
---

2026-06-18 把 Web 界面从「灰阶极简」改为「浅色清雅、优雅大气」。改动集中在 src/web.py 的 CUSTOM_CSS 常量(app.py 和 main.py 两入口都用 launch(theme=Soft, css=CUSTOM_CSS),改常量即全局生效),业务逻辑零改动。

**风格(用户确认)**: 浅色清雅 + 视觉/布局双优化。
**配色令牌**: 背景暖米白渐变 #f7f5f1→#efece6;主点缀墨蓝 --accent #1e3a5f(用户气泡/按钮/链接/标题/强调);金色 --gold #b08d57 极克制点缀;暖描边 #e7e3da。标题/欢迎语用衬线体 "Noto Serif SC"。

**九区改动**: 顶栏(衬线墨蓝+渐变分隔线)、AI气泡(透明→白"纸面"卡片+暖描边)、用户气泡(墨蓝)、空状态chips(墨蓝左边框+hover上浮)、输入区(focus-within墨蓝光晕+发送按钮墨蓝渐变)、深度模式(accent-color墨蓝)、校验徽章(调柔)、引用卡片(墨蓝竖条+锚点黄闪改墨蓝渐隐)、多跳轨迹(节点墨蓝圆点)。

**回滚**: git checkout src/web.py 即可。相关 [[streaming-ux-changes]]
