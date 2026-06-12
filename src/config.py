"""全局配置：集中管理 API 密钥、模型名、可切换的 embedding 供应商。

所有可调项通过 .env 注入，代码里不写死任何密钥。
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Windows 控制台默认 stdout 编码为 GBK，打印中文会乱码（终端按 UTF-8 解读）。
# 此模块被所有入口导入，故在此统一把 stdout/stderr 切到 UTF-8，根治乱码。
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

load_dotenv()

# ---- 路径 ----
ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_RAW_DIR = ROOT_DIR / "data" / "raw"          # 原始法律文本（markdown）
DATA_PROCESSED_DIR = ROOT_DIR / "data" / "processed"  # 解析后的统一 schema json
VECTOR_STORE_DIR = ROOT_DIR / "vector_store"      # ChromaDB 持久化目录
COLLECTION_NAME = "chinese_laws"

# ---- LLM（ModelScope，OpenAI 兼容）----
MODELSCOPE_API_KEY = os.getenv("MODELSCOPE_API_KEY", "")
MODELSCOPE_BASE_URL = os.getenv("MODELSCOPE_BASE_URL", "https://api-inference.modelscope.cn/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-ai/DeepSeek-V3.2")

# ---- Embedding 供应商切换 ----
EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "modelscope").lower()

MODELSCOPE_EMBED_MODEL = os.getenv("MODELSCOPE_EMBED_MODEL", "Qwen/Qwen3-Embedding-0.6B")

SILICONFLOW_API_KEY = os.getenv("SILICONFLOW_API_KEY", "")
SILICONFLOW_BASE_URL = os.getenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1")
SILICONFLOW_EMBED_MODEL = os.getenv("SILICONFLOW_EMBED_MODEL", "BAAI/bge-m3")

# ---- 检索参数 ----
TOP_K = int(os.getenv("TOP_K", "5"))

# ---- Rerank（精排，默认关闭）----
# 实测：bge-m3 向量召回质量已很高，rerank（bge-reranker-v2-m3）对民法典短条文
# 场景反而损害排序精度（MRR），故默认关闭。保留实现作为可选项，可在 .env 开启对比。
# 召回阶段先取 RERANK_CANDIDATES 条，rerank 精排后取 TOP_K 条。
RERANK_ENABLED = os.getenv("RERANK_ENABLED", "false").lower() == "true"
RERANK_CANDIDATES = int(os.getenv("RERANK_CANDIDATES", "10"))
# rerank 供应商目前复用 SiliconFlow（与 embedding 同一 key，OpenAI 兼容外的独立 /rerank 接口）
SILICONFLOW_RERANK_MODEL = os.getenv("SILICONFLOW_RERANK_MODEL", "BAAI/bge-reranker-v2-m3")
# 相关性阈值：rerank 分数低于此值的条文视为不相关并丢弃（0~1，0 表示不过滤）
RELEVANCE_THRESHOLD = float(os.getenv("RELEVANCE_THRESHOLD", "0"))
# 向量距离阈值：若最相关条文的余弦距离仍大于此值，判定问题与民法典无关，
# 返回空（触发"未找到相关条文"），避免把无关条文喂给 LLM 诱发幻觉。
# 实测：真实法律问题 distance≈0.6~0.9，无关问题（天气/菜谱）≥1.2，故阈值取 1.0。
# 设为 0 可关闭该过滤。
MAX_DISTANCE = float(os.getenv("MAX_DISTANCE", "1.0"))

# ---- 混合检索（向量 + BM25 关键词，RRF 融合）----
# 向量擅长语义，BM25 擅长法律术语精确匹配，两路 RRF 融合提升召回。
HYBRID_ENABLED = os.getenv("HYBRID_ENABLED", "true").lower() == "true"
# 每一路召回的候选数（融合后再取 TOP_K）
HYBRID_CANDIDATES = int(os.getenv("HYBRID_CANDIDATES", "20"))
# RRF 融合常数，越小则排名靠前项权重越大
RRF_K = int(os.getenv("RRF_K", "10"))
# 两路权重：向量召回质量高，给更高权重，让 BM25 只补召回不主导 top 排名。
# 实测 vec=5/bm25=1 时混合检索相比纯向量净赚召回率（Hit 0.88→0.92）而 MRR 基本持平。
HYBRID_VECTOR_WEIGHT = float(os.getenv("HYBRID_VECTOR_WEIGHT", "5.0"))
HYBRID_BM25_WEIGHT = float(os.getenv("HYBRID_BM25_WEIGHT", "1.0"))


def embedding_config() -> dict:
    """返回当前生效的 embedding 供应商配置。"""
    if EMBEDDING_PROVIDER == "siliconflow":
        return {
            "provider": "siliconflow",
            "api_key": SILICONFLOW_API_KEY,
            "base_url": SILICONFLOW_BASE_URL,
            "model": SILICONFLOW_EMBED_MODEL,
        }
    # 默认 modelscope
    return {
        "provider": "modelscope",
        "api_key": MODELSCOPE_API_KEY,
        "base_url": MODELSCOPE_BASE_URL,
        "model": MODELSCOPE_EMBED_MODEL,
    }
