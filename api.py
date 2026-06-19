"""FastAPI 后端 — RESTful + SSE 流式接口，并托管 Vue 前端（单端口部署）。

前端（web/，Vue 3）构建产物 web/dist 由本服务在 `/` 托管，API 在 `/api/*`。
启动: python api.py  或  uvicorn api:app --host 0.0.0.0 --port 8000
端口: 环境变量 PORT（默认 8000；ModelScope 创空间用 7860）
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Dict, Optional
import os
import json
import sys
from pathlib import Path

# 确保能导入 src 模块
sys.path.insert(0, str(Path(__file__).parent))

from src.rag import LegalRAG
from src.agent import LegalAgent
from src import config

# 向量库缺失则直接报错退出（不现场构建，避免误触发耗 embedding 配额）。
if not config.VECTOR_STORE_DIR.exists() or not any(config.VECTOR_STORE_DIR.iterdir()):
    sys.exit(
        f"ERROR - 向量库不存在 ({config.VECTOR_STORE_DIR})。\n"
        f"请先运行: python scripts/build_index.py"
    )

app = FastAPI(title="法律助手 API", version="2.0")

# CORS: 允许前端跨域调用(本地开发 + 生产都需要)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境改为具体域名
    allow_methods=["*"],
    allow_headers=["*"],
)

# 启动时实例化(共享向量库,避免每次请求重建)
rag = LegalRAG()
agent = LegalAgent(rag)


class ChatRequest(BaseModel):
    """聊天请求体"""
    question: str
    history: Optional[List[Dict]] = None  # [{"role": "user"/"assistant", "content": "..."}]
    top_k: Optional[int] = None


@app.get("/api/health")
async def health():
    """健康检查"""
    return {
        "service": "法律助手 API",
        "version": "2.0",
        "endpoints": {
            "单跳": "POST /api/chat",
            "深度模式": "POST /api/chat/agent",
        }
    }


@app.post("/api/chat")
async def chat_single(req: ChatRequest):
    """单跳 RAG 流式接口(Server-Sent Events)。

    Returns:
        StreamingResponse: SSE 流,每行格式 `data: {JSON}\n\n`
        chunk 类型: rewrite / references / answer / verify / disclaimer / error
    """
    if not req.question.strip():
        raise HTTPException(400, "question 不能为空")

    def event_stream():
        try:
            for chunk in rag.answer_stream(
                req.question,
                history=req.history,
                top_k=req.top_k
            ):
                # SSE 格式: data: {json}\n\n
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # 关闭 Nginx 缓冲
        }
    )


@app.post("/api/chat/agent")
async def chat_agent_mode(req: ChatRequest):
    """深度模式(多跳 Agent)流式接口。

    Returns:
        StreamingResponse: SSE 流
        chunk 类型: trace / references / answer / verify / disclaimer
    """
    if not req.question.strip():
        raise HTTPException(400, "question 不能为空")

    def event_stream():
        try:
            for chunk in agent.run_stream(
                req.question,
                history=req.history
            ):
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )


class FeedbackRequest(BaseModel):
    """用户反馈请求体"""
    question: str
    answer: str
    liked: bool
    rewrite: Optional[str] = None
    refs: Optional[List[Dict]] = None
    verify_status: Optional[str] = None


@app.get("/api/examples")
async def get_examples(n: int = 4):
    """随机抽取示例问题(空状态 chips 用)。"""
    import random
    pool = [
        "父母与成年子女之间有哪些法定义务？",
        "用人单位拖欠工资可以怎么维权？",
        "公司股东出资有哪些方式？",
        "诉讼时效期间一般是多少年？",
        "消费者发现假货可以要求几倍赔偿？",
        "离婚时夫妻共同财产怎么分割？",
        "签了合同后能不能反悔？",
        "试用期最长可以约定多久？",
        "房屋租赁合同到期后房东能随意涨租吗？",
        "遗嘱有哪几种法定形式？",
        "交通事故责任如何认定？",
        "未成年人能否独立签订合同？",
        "劳动合同到期不续签有没有补偿？",
        "网购商品七天无理由退货有哪些例外？",
        "被公司违法辞退能要求赔偿吗？",
        "个人信息被泄露可以怎么维权？",
    ]
    k = min(n, len(pool))
    return {"examples": random.sample(pool, k)}


@app.post("/api/feedback")
async def post_feedback(req: FeedbackRequest):
    """接收用户 👍/👎 反馈，追加到 feedback.jsonl。"""
    import time
    if not config.FEEDBACK_LOG_ENABLED:
        return {"ok": True, "msg": "feedback logging disabled"}
    try:
        record = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "liked": req.liked,
            "question": req.question,
            "rewrite": req.rewrite,
            "answer": (req.answer or "")[:2000],
            "refs": req.refs or [],
            "verify_status": req.verify_status,
        }
        config.FEEDBACK_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(config.FEEDBACK_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "msg": str(e)}


@app.get("/api/config")
async def get_client_config():
    """返回前端需要的配置(深度模式默认值等)。"""
    return {
        "agent_mode_default": config.AGENT_MODE,
        "app_title": config.APP_TITLE,
        "app_subtitle": config.APP_SUBTITLE,
    }


# 托管前端构建产物（必须放在所有 /api 路由注册之后，否则根挂载会吞掉 API）。
# html=True：未匹配的路径回退到 index.html（前端 hash 路由）。dist 不存在则跳过（纯 API 模式）。
_DIST_DIR = Path(__file__).parent / "web" / "dist"
if _DIST_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(_DIST_DIR), html=True), name="frontend")
else:
    print(f"WARN - 前端构建产物不存在 ({_DIST_DIR})，仅提供 API。"
          f" 构建: cd web && npm run build")


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    print(f"法律助手启动中... http://localhost:{port}  (API 文档 /docs)")
    uvicorn.run(app, host="0.0.0.0", port=port)
