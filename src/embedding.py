"""可切换的 embedding 客户端。

ModelScope 与 SiliconFlow 都兼容 OpenAI 的 /v1/embeddings 协议，
因此用同一个 OpenAI SDK 客户端，仅 base_url / key / model 不同。
通过 config.EMBEDDING_PROVIDER 切换，对上层完全透明。
"""
from typing import List
from openai import OpenAI

from . import config


class EmbeddingClient:
    def __init__(self):
        cfg = config.embedding_config()
        self.provider = cfg["provider"]
        self.model = cfg["model"]
        if not cfg["api_key"]:
            raise ValueError(
                f"embedding 供应商 {self.provider} 缺少 API key，请在 .env 中配置。"
            )
        self.client = OpenAI(api_key=cfg["api_key"], base_url=cfg["base_url"])

    def embed(self, texts: List[str], batch_size: int = 16) -> List[List[float]]:
        """对一批文本求向量。自动分批，避免单次请求过大。"""
        if isinstance(texts, str):
            texts = [texts]
        vectors: List[List[float]] = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            resp = self.client.embeddings.create(model=self.model, input=batch)
            # 按 index 排序，保证顺序与输入一致
            items = sorted(resp.data, key=lambda d: d.index)
            vectors.extend([item.embedding for item in items])
        return vectors

    def embed_query(self, text: str) -> List[float]:
        return self.embed([text])[0]
