"""向量库：构建与检索。

使用 ChromaDB（本地持久化、轻量、零配置）。
embedding 通过 src.embedding.EmbeddingClient 获取（供应商可切换）。
"""
import json
from typing import List, Dict
import chromadb
from tqdm import tqdm

from . import config
from .embedding import EmbeddingClient
from .reranker import Reranker
from .bm25_retriever import BM25Retriever
from .parser import LawArticle


def _article_id(law_name: str, article_no: int, sub_no: int = 0) -> str:
    """跨法律唯一的条文 ID。sub_no 区分"第X条之一/之二"，避免互相覆盖。"""
    suffix = f"_{sub_no}" if sub_no else ""
    return f"{law_name}#{article_no}{suffix}"


def _article_key(hit: Dict):
    """合并/去重用的组合键：(法律名, 条号, 附加条序号)。"""
    return (hit.get("law_name", ""), hit["article_no"], hit.get("sub_no", 0))


class VectorStore:
    def __init__(self):
        self.embed_client = EmbeddingClient()
        self.reranker = Reranker() if config.RERANK_ENABLED else None
        self.bm25 = BM25Retriever.from_json() if config.HYBRID_ENABLED else None
        self.chroma_client = chromadb.PersistentClient(
            path=str(config.VECTOR_STORE_DIR)
        )
        self.collection = self.chroma_client.get_or_create_collection(
            name=config.COLLECTION_NAME,
            metadata={"description": "中国法律条文向量库"}
        )

    def build_from_articles(self, articles: List[LawArticle], batch_size: int = 32):
        """从解析好的条文列表构建向量库（embedding + 存储）。"""
        if self.collection.count() > 0:
            print(f"向量库已有 {self.collection.count()} 条，清空重建...")
            self.chroma_client.delete_collection(config.COLLECTION_NAME)
            self.collection = self.chroma_client.get_or_create_collection(config.COLLECTION_NAME)

        print(f"正在为 {len(articles)} 条法律条文生成 embedding...")

        ids, texts, metadatas = [], [], []
        for i, art in enumerate(articles):
            # ID：跨法律唯一。仅用 article_no 会冲突（每部法律都有"第一条"，
            # 同一法律还有"第X条之一"），故以 (law_name, article_no, sub_no) 组合作键。
            ids.append(_article_id(art.law_name, art.article_no, art.sub_no))
            # 文本：用于 embedding（含法律名 + 层级信息增强语义、消除跨法律歧义）
            texts.append(
                f"{art.law_name} {art.part} {art.chapter} {art.section} "
                f"{art.article_label} {art.article_text}"
            )
            # Metadata：存储结构化信息（检索时返回）
            metadatas.append({
                "law_name": art.law_name,
                "part": art.part,
                "chapter": art.chapter,
                "section": art.section,
                "article_no": art.article_no,
                "sub_no": art.sub_no,
                "article_text": art.article_text,
                "effective_date": art.effective_date,
            })

        # 分批 embed + 入库
        for i in tqdm(range(0, len(texts), batch_size), desc="Building vector store"):
            batch_ids = ids[i:i+batch_size]
            batch_texts = texts[i:i+batch_size]
            batch_metas = metadatas[i:i+batch_size]

            embeddings = self.embed_client.embed(batch_texts, batch_size=batch_size)

            self.collection.add(
                ids=batch_ids,
                embeddings=embeddings,
                documents=batch_texts,
                metadatas=batch_metas,
            )

        print(f"OK - Vector store built: {self.collection.count()} articles")

    def search(self, query: str, top_k: int = None) -> List[Dict]:
        """检索：混合召回（向量 + BM25，RRF 融合）→（可选）rerank → 阈值过滤。

        流程：
        1. 召回候选：向量一路；开启混合时再加 BM25 一路，两路 RRF 融合。
        2. （可选）rerank 精排。默认关闭——实测对民法典短条文场景无正向价值。
        3. 阈值过滤（基于 rerank 分数，仅在 rerank 开启且阈值>0 时生效）。
        """
        top_k = top_k or config.TOP_K

        # rerank 开启时需要更多候选供精排；否则按融合所需候选数
        n_final = config.RERANK_CANDIDATES if self.reranker else top_k

        # 1. 召回 + 融合
        if self.bm25:
            candidates = self._hybrid_search(query, n_final)
        else:
            candidates = self._vector_search(query, n_final)
        if not candidates:
            return []

        # 1.5 相关性闸门：若所有候选的向量距离都超过阈值，判定问题与已接入法律无关，
        # 返回空（交由上层回"未找到相关条文"），避免把无关条文喂给 LLM 诱发幻觉。
        if config.MAX_DISTANCE > 0:
            dists = [c["distance"] for c in candidates if c.get("distance") is not None]
            if dists and min(dists) > config.MAX_DISTANCE:
                return []

        # 2. rerank 精排（默认关闭）
        if self.reranker:
            candidates = self._apply_rerank(query, candidates, top_k)
        else:
            candidates = candidates[:top_k]

        # 3. 阈值过滤（仅当有 rerank 分数时生效）
        if config.RELEVANCE_THRESHOLD > 0:
            candidates = [
                c for c in candidates
                if c.get("rerank_score") is None
                or c["rerank_score"] >= config.RELEVANCE_THRESHOLD
            ]

        return candidates

    def _hybrid_search(self, query: str, top_k: int) -> List[Dict]:
        """向量 + BM25 两路召回，RRF 融合后取 top_k 条。

        RRF：score = Σ 1/(RRF_K + rank)，rank 为该条在各路结果中的名次（从0起）。
        只出现在一路的条文也参与排序，从而兼顾语义召回与关键词召回。
        """
        n = config.HYBRID_CANDIDATES
        vec_hits = self._vector_search(query, n)
        bm25_hits = self.bm25.search(query, n)

        # 以 (law_name, article_no) 为键合并两路；保留各自分数字段便于调试/展示
        merged: Dict[tuple, Dict] = {}
        rrf: Dict[tuple, float] = {}

        for rank, h in enumerate(vec_hits):
            key = _article_key(h)
            merged.setdefault(key, h)
            rrf[key] = rrf.get(key, 0.0) + config.HYBRID_VECTOR_WEIGHT / (config.RRF_K + rank)

        for rank, h in enumerate(bm25_hits):
            key = _article_key(h)
            if key in merged:
                merged[key]["bm25_score"] = h.get("bm25_score")
            else:
                merged[key] = h
            rrf[key] = rrf.get(key, 0.0) + config.HYBRID_BM25_WEIGHT / (config.RRF_K + rank)

        # 按 RRF 分数降序
        ordered = sorted(merged.values(), key=lambda h: rrf[_article_key(h)], reverse=True)
        for h in ordered:
            h.setdefault("distance", None)
            h.setdefault("bm25_score", None)
            h.setdefault("rerank_score", None)
        return ordered[:top_k]

    def _vector_search(self, query: str, n_results: int) -> List[Dict]:
        """纯向量检索，返回 n_results 条候选（带 distance）。"""
        query_vec = self.embed_client.embed_query(query)
        results = self.collection.query(
            query_embeddings=[query_vec],
            n_results=n_results,
        )

        hits = []
        for i in range(len(results['ids'][0])):
            meta = results['metadatas'][0][i]
            hits.append({
                "article_no": meta['article_no'],
                "sub_no": meta.get('sub_no', 0),
                "law_name": meta['law_name'],
                "part": meta['part'],
                "chapter": meta['chapter'],
                "section": meta['section'],
                "article_text": meta['article_text'],
                "effective_date": meta.get('effective_date', ''),
                "distance": results['distances'][0][i] if 'distances' in results else None,
                "rerank_score": None,
            })
        return hits

    def _apply_rerank(self, query: str, candidates: List[Dict], top_k: int) -> List[Dict]:
        """融合向量排名与 rerank 排名（RRF），取 top_k 条。

        实测纯 rerank 排序虽提升召回广度，但会把向量排第一的正确条文挪后、
        损害 MRR。故用 Reciprocal Rank Fusion 融合两路排名，兼顾召回与精度：
        score = 1/(k+vec_rank) + 1/(k+rerank_rank)。
        rerank 失败时降级为原向量顺序，保证可用性。
        """
        docs = [
            f"《{c.get('law_name','')}》第{c['article_no']}条 {c['article_text']}"
            for c in candidates
        ]
        try:
            ranked = self.reranker.rerank(query, docs, top_n=len(candidates))
        except Exception as e:
            print(f"WARN - rerank 失败，降级为向量检索顺序：{e}")
            return candidates[:top_k]

        # 向量排名（候选已按向量相似度降序）与 rerank 分数
        RRF_K = 10  # RRF 常数：候选数小，取小值让排名差异更敏感
        rerank_rank = {r["index"]: rank for rank, r in enumerate(ranked)}
        rerank_score = {r["index"]: r["score"] for r in ranked}

        fused = []
        for vec_rank, c in enumerate(candidates):
            rr = rerank_rank.get(vec_rank, len(candidates))
            rrf = 1.0 / (RRF_K + vec_rank) + 1.0 / (RRF_K + rr)
            hit = dict(c)
            hit["rerank_score"] = rerank_score.get(vec_rank)
            hit["_rrf"] = rrf
            fused.append(hit)

        fused.sort(key=lambda h: h["_rrf"], reverse=True)
        for h in fused:
            del h["_rrf"]
        return fused[:top_k]


def build_vector_store():
    """从已解析的 JSON 构建向量库（独立脚本入口）。"""
    json_path = config.DATA_PROCESSED_DIR / "articles.json"
    if not json_path.exists():
        print(f"ERROR - {json_path} not found. Run parser.py first.")
        return

    with open(json_path, encoding='utf-8') as f:
        data = json.load(f)
    articles = [LawArticle(**d) for d in data]

    vs = VectorStore()
    vs.build_from_articles(articles)


if __name__ == "__main__":
    build_vector_store()
