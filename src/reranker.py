"""可切换的 rerank（精排）客户端。

向量召回擅长语义但排序不够精；rerank 模型对 (query, doc) 对直接打分，
能把最相关的条文排到前面。这里复用 SiliconFlow 的 /rerank 接口
（与 embedding 同一 API key，独立于 OpenAI SDK，故用 httpx 直接请求）。

通过 config.RERANK_ENABLED 开关，对上层透明。
"""
from typing import List, Dict
import httpx

from . import config


class Reranker:
    def __init__(self):
        self.model = config.SILICONFLOW_RERANK_MODEL
        self.api_key = config.SILICONFLOW_API_KEY
        self.base_url = config.SILICONFLOW_BASE_URL.rstrip("/")
        if not self.api_key:
            raise ValueError("rerank 需要 SILICONFLOW_API_KEY，请在 .env 中配置。")

    def rerank(self, query: str, documents: List[str], top_n: int) -> List[Dict]:
        """对候选文档按与 query 的相关性精排。

        返回 [{"index": 原始下标, "score": 相关性分数(0~1)}, ...]，按分数降序，
        最多 top_n 条。index 用于映射回调用方的原始候选列表。
        """
        if not documents:
            return []

        resp = httpx.post(
            f"{self.base_url}/rerank",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model,
                "query": query,
                "documents": documents,
                "top_n": top_n,
                "return_documents": False,
            },
            timeout=30.0,
        )
        resp.raise_for_status()
        data = resp.json()

        return [
            {"index": r["index"], "score": r["relevance_score"]}
            for r in data["results"]
        ]
