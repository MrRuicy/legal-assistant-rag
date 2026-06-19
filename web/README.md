# 法律助手 Web 前端（Vue 3）

Vue 3 前端，对接 FastAPI 后端（`api.py`）。

## 技术栈

Vue 3 (Composition API) · Vite 6 · TypeScript 5 · Tailwind CSS v4 · Pinia · Vue Router 4 · markdown-it + highlight.js · Headless UI · Lucide

## 本地开发

```bash
# 终端 1：后端
cd ..            # 回到仓库根
python api.py    # FastAPI :8000

# 终端 2：前端
cd web
npm install
npm run dev      # Vite :5173，/api/* 自动代理到 :8000
```

打开 http://localhost:5173

## 生产构建

```bash
npm run build    # 输出 dist/
npm run preview  # 本地预览构建产物
```

### 部署选项

- **Nginx 反代（推荐）**：`location /` → `dist/`；`location /api/` → `proxy_pass http://localhost:8000`
- **FastAPI 托管**：在 `api.py` 末尾 `app.mount("/", StaticFiles(directory="web/dist", html=True))`，单端口部署
- **分离部署**：前端 CDN + 后端 Docker

## 目录结构

```
src/
├── types/         接口契约类型（chat.ts / api.ts）
├── api/           接口层（chat.ts 流式解析 / feedback.ts）
├── stores/        Pinia（sessions 会话持久化 / settings 偏好）
├── composables/   useChat 对话核心 / useMarkdown / useScrollAnchor
├── components/
│   ├── layout/    AppSidebar / AppHeader
│   ├── chat/      ChatPanel / MessageItem / AiMessage / TracePanel / RefCard / AnswerFooter / StatusLine
│   ├── input/     ChatInput / ExampleChips
│   ├── ui/        VerifyBadge / Collapsible / Modal
│   └── settings/  SettingsModal
├── views/         ChatView（主页面）
└── styles/        tokens.css（主题变量）/ prose.css / animations.css
```

## 功能

- 流式对话（SSE）：单跳 RAG + 深度模式（多跳 Agent 实时轨迹）
- Markdown 渲染 + 条号引用点击跳转高亮
- 引用条文折叠卡片 + 引用校验徽章（可追溯 / 存疑 / 未引用）
- 会话管理：多会话、重命名、删除、导出 Markdown，localStorage 持久化
- 深色玻璃态 / 浅色清雅 双主题
- 示例问题 chips、👍/👎 反馈、设置面板

## 后端契约

SSE chunk 类型对齐 `src/rag.py` / `src/agent.py`：
`rewrite` · `references` · `answer` · `trace`(Agent) · `verify` · `disclaimer` · `error`
