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
from .parser import LawArticle


class VectorStore:
    def __init__(self):
        self.embed_client = EmbeddingClient()
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
            # ID: 唯一标识，格式 "law_part_articleNo"
            ids.append(f"civil_{art.article_no}")
            # 文本：用于 embedding（包含层级信息增强语义）
            texts.append(f"{art.part} {art.chapter} {art.section} 第{art.article_no}条 {art.article_text}")
            # Metadata：存储结构化信息（检索时返回）
            metadatas.append({
                "law_name": art.law_name,
                "part": art.part,
                "chapter": art.chapter,
                "section": art.section,
                "article_no": art.article_no,
                "article_text": art.article_text,
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
        """检索：返回 top_k 条最相关的法律条文（带 metadata）。"""
        top_k = top_k or config.TOP_K
        query_vec = self.embed_client.embed_query(query)

        results = self.collection.query(
            query_embeddings=[query_vec],
            n_results=top_k,
        )

        # 整理返回格式
        hits = []
        for i in range(len(results['ids'][0])):
            hits.append({
                "article_no": results['metadatas'][0][i]['article_no'],
                "law_name": results['metadatas'][0][i]['law_name'],
                "part": results['metadatas'][0][i]['part'],
                "chapter": results['metadatas'][0][i]['chapter'],
                "section": results['metadatas'][0][i]['section'],
                "article_text": results['metadatas'][0][i]['article_text'],
                "distance": results['distances'][0][i] if 'distances' in results else None,
            })
        return hits


def build_vector_store():
    """从已解析的 JSON 构建向量库（独立脚本入口）。"""
    json_path = config.DATA_PROCESSED_DIR / "civil_code.json"
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
