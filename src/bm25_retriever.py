"""BM25 关键词检索器（内存索引）。

向量检索擅长语义，但对法律术语的精确匹配（如"定金""居住权""第X条"）
不如关键词检索。BM25 基于词频，正好补足这一短板，与向量结果融合可提升召回。

民法典仅 1260 条，索引常驻内存即可，无需额外存储。jieba 分词。
"""
import json
import re
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
    def __init__(self, articles: List[Dict]):
        """articles: 条文 dict 列表（同 civil_code.json 的元素结构）。"""
        self.articles = articles
        # 分词语料：编/章/节 + 条文正文，与向量库的 embedding 文本保持一致
        corpus = [
            _tokenize(
                f"{a['part']} {a['chapter']} {a['section']} "
                f"第{a['article_no']}条 {a['article_text']}"
            )
            for a in articles
        ]
        self.bm25 = BM25Okapi(corpus)

    @classmethod
    def from_json(cls, json_path=None) -> "BM25Retriever":
        json_path = json_path or (config.DATA_PROCESSED_DIR / "civil_code.json")
        with open(json_path, encoding="utf-8") as f:
            articles = json.load(f)
        return cls(articles)

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
                "law_name": a["law_name"],
                "part": a["part"],
                "chapter": a["chapter"],
                "section": a["section"],
                "article_text": a["article_text"],
                "bm25_score": float(scores[idx]),
            })
        return hits
