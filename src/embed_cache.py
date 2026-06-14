"""Query embedding 磁盘缓存：省 embedding 配额、降首字延迟。

每次提问都要对 query 求一次 embedding，消耗供应商配额并增加首字延迟。
相同/重复问题很常见，故把 query 向量缓存到磁盘：
- key = sha1(provider + model + 文本)，换模型/供应商自动隔离，不会读到旧向量；
- 简单的 LRU：超过上限按文件 mtime 淘汰最旧的；
- 纯本地文件，无需额外服务；构建向量库（批量 embed）不走此缓存，只缓存单条 query。
"""
import hashlib
import json
from pathlib import Path
from typing import List, Optional

from . import config


class QueryEmbedCache:
    def __init__(self, cache_dir: Path = None, max_entries: int = None):
        self.enabled = config.EMBED_CACHE_ENABLED
        self.dir = cache_dir or config.EMBED_CACHE_DIR
        self.max_entries = max_entries or config.EMBED_CACHE_MAX
        if self.enabled:
            self.dir.mkdir(parents=True, exist_ok=True)

    def _key(self, provider: str, model: str, text: str) -> str:
        h = hashlib.sha1(f"{provider}\x00{model}\x00{text}".encode("utf-8"))
        return h.hexdigest()

    def get(self, provider: str, model: str, text: str) -> Optional[List[float]]:
        if not self.enabled:
            return None
        path = self.dir / f"{self._key(provider, model, text)}.json"
        if not path.exists():
            return None
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)["vector"]
        except Exception:
            return None  # 缓存损坏则当未命中，由上层重新求向量

    def set(self, provider: str, model: str, text: str, vector: List[float]):
        if not self.enabled:
            return
        path = self.dir / f"{self._key(provider, model, text)}.json"
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"text": text, "vector": vector}, f)
        except Exception:
            return  # 写缓存失败不应影响主流程
        self._evict_if_needed()

    def _evict_if_needed(self):
        """超过上限时按 mtime 淘汰最旧的 10%（批量淘汰减少频繁扫描）。"""
        files = list(self.dir.glob("*.json"))
        if len(files) <= self.max_entries:
            return
        files.sort(key=lambda p: p.stat().st_mtime)
        drop = len(files) - self.max_entries + max(1, self.max_entries // 10)
        for p in files[:drop]:
            try:
                p.unlink()
            except Exception:
                pass
