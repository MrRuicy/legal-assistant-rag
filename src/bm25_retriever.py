"""BM25 关键词检索器（内存索引）。

向量检索擅长语义，但对法律术语的精确匹配（如"定金""居住权""第X条"）
不如关键词检索。BM25 基于词频，正好补足这一短板，与向量结果融合可提升召回。

接入 38 部法律后条文已 5000+，每次冷启动重新 jieba 分词会拖慢启动，
故支持把分词语料缓存到磁盘（pickle）：启动时若缓存比 JSON 新则直接加载，
免重复分词。
"""
import json
import pickle
import re
from pathlib import Path
from typing import List, Dict
import jieba
from rank_bm25 import BM25Okapi

from . import config

# 中文停用词（精简版，过滤对检索无意义的高频词）
_STOPWORDS = {
    "的", "了", "和", "是", "在", "有", "与", "或", "及", "等", "为", "对",
    "上", "下", "中", "其", "之", "以", "可以", "应当", "不", "什么", "如何",
    "怎么", "哪些", "吗", "呢", "啊", "请问", "我", "你", "他", "她", "它",
    "这", "那", "个", "条", "第",
}


def _tokenize(text: str) -> List[str]:
    """jieba 分词 + 去停用词 + 去标点，返回词列表。"""
    tokens = jieba.lcut(text)
    return [
        t.strip() for t in tokens
        if t.strip() and t not in _STOPWORDS and not re.fullmatch(r"[\W_]+", t)
    ]


class BM25Retriever:
    def __init__(self, articles: List[Dict], corpus: List[List[str]] = None):
        """articles: 条文 dict 列表（同 civil_code.json 的元素结构）。

        corpus 可传入预分词语料（来自磁盘缓存）以跳过 jieba 重建。
        """
        self.articles = articles
        if corpus is None:
            # 分词语料：法律名 + 编/章/节 + 条文正文，与向量库 embedding 文本保持一致
            corpus = [
                _tokenize(
                    f"{a.get('law_name','')} {a['part']} {a['chapter']} {a['section']} "
                    f"第{a['article_no']}条 {a['article_text']}"
                )
                for a in articles
            ]
        self.corpus = corpus
        self.bm25 = BM25Okapi(corpus)

    @classmethod
    def from_json(cls, json_path=None) -> "BM25Retriever":
        """从条文 JSON 构建；若磁盘有比 JSON 新的分词缓存则直接加载（免重新分词）。"""
        json_path = Path(json_path or (config.DATA_PROCESSED_DIR / "civil_code.json"))
        with open(json_path, encoding="utf-8") as f:
            articles = json.load(f)

        cache_path = cls._cache_path()
        if cache_path.exists() and cache_path.stat().st_mtime >= json_path.stat().st_mtime:
            try:
                with open(cache_path, "rb") as f:
                    cached = pickle.load(f)
                if cached.get("count") == len(articles):
                    return cls(articles, corpus=cached["corpus"])
            except Exception:
                pass  # 缓存损坏/不兼容则重建

        inst = cls(articles)
        inst._save_cache()
        return inst

    @staticmethod
    def _cache_path() -> Path:
        return config.VECTOR_STORE_DIR / "bm25_corpus.pkl"

    def _save_cache(self):
        try:
            self._cache_path().parent.mkdir(parents=True, exist_ok=True)
            with open(self._cache_path(), "wb") as f:
                pickle.dump({"count": len(self.articles), "corpus": self.corpus}, f)
        except Exception:
            pass  # 缓存写失败不影响功能

    def search(self, query: str, top_k: int) -> List[Dict]:
        """返回 top_k 条，每条带 bm25_score 与完整 metadata。"""
        tokens = _tokenize(query)
        if not tokens:
            return []

        scores = self.bm25.get_scores(tokens)
        # 取分数最高的 top_k 个下标
        ranked_idx = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]

        hits = []
        for idx in ranked_idx:
            if scores[idx] <= 0:
                continue  # BM25 分数为 0 表示无任何词匹配，跳过
            a = self.articles[idx]
            hits.append({
                "article_no": a["article_no"],
                "sub_no": a.get("sub_no", 0),
                "law_name": a["law_name"],
                "part": a["part"],
                "chapter": a["chapter"],
                "section": a["section"],
                "article_text": a["article_text"],
                "effective_date": a.get("effective_date", ""),
                "bm25_score": float(scores[idx]),
            })
        return hits
