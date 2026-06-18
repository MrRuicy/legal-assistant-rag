"""可切换的 embedding 客户端。

ModelScope 与 SiliconFlow 都兼容 OpenAI 的 /v1/embeddings 协议，
因此用同一个 OpenAI SDK 客户端，仅 base_url / key / model 不同。
通过 config.EMBEDDING_PROVIDER 切换，对上层完全透明。
"""
import time
from typing import List
from openai import OpenAI

from . import config
from .embed_cache import QueryEmbedCache


class EmbeddingClient:
    def __init__(self):
        cfg = config.embedding_config()
        self.provider = cfg["provider"]
        self.model = cfg["model"]
        if not cfg["api_key"]:
            raise ValueError(
                f"embedding 供应商 {self.provider} 缺少 API key，请在 .env 中配置。"
            )
        # 显式 timeout：防止服务端挂起时无限等待（多跳检索一题多次 embedding 更易踩到）。
        self.client = OpenAI(
            api_key=cfg["api_key"], base_url=cfg["base_url"], timeout=config.EMBED_TIMEOUT
        )
        self._cache = QueryEmbedCache()

    def embed(self, texts: List[str], batch_size: int = 16) -> List[List[float]]:
        """对一批文本求向量。自动分批，避免单次请求过大。

        批量构建向量库不走 query 缓存（一次性、文本各异），只有 embed_query 走缓存。
        每批超时/连接错误时重试（config.EMBED_MAX_RETRY），仍失败则抛出。
        """
        if isinstance(texts, str):
            texts = [texts]
        vectors: List[List[float]] = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            resp = self._embed_batch_with_retry(batch)
            # 按 index 排序，保证顺序与输入一致
            items = sorted(resp.data, key=lambda d: d.index)
            vectors.extend([item.embedding for item in items])
        return vectors

    def _embed_batch_with_retry(self, batch: List[str]):
        """对单批文本求向量，超时/连接错误时重试（指数退避）。"""
        last_err = None
        for attempt in range(config.EMBED_MAX_RETRY + 1):
            try:
                return self.client.embeddings.create(model=self.model, input=batch)
            except Exception as e:
                name = type(e).__name__.lower()
                transient = "timeout" in name or "connection" in name or "apiconnection" in name
                if transient and attempt < config.EMBED_MAX_RETRY:
                    last_err = e
                    time.sleep(1.5 * (attempt + 1))  # 退避后重试
                    continue
                raise
        raise last_err if last_err else RuntimeError("embedding 调用失败")

    def embed_query(self, text: str) -> List[float]:
        """对单条 query 求向量，带磁盘缓存（命中则零 API 调用）。"""
        cached = self._cache.get(self.provider, self.model, text)
        if cached is not None:
            return cached
        vec = self.embed([text])[0]
        self._cache.set(self.provider, self.model, text, vec)
        return vec
