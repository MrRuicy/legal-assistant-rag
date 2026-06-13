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

# ---- 应用品牌 / 适用范围 ----
# 多法律接入后，界面与 prompt 不再写死「民法典」。APP_LAW_SCOPE 用于 prompt 里
# 说明助手覆盖哪些法律（由 setup 实际接入的法律决定，可在 .env 覆盖文案）。
APP_TITLE = os.getenv("APP_TITLE", "中国法律助手")
APP_SUBTITLE = os.getenv("APP_SUBTITLE", "基于 RAG 的中国法律法规智能问答 · 多轮对话 · 条文引用校验")
APP_LAW_SCOPE = os.getenv("APP_LAW_SCOPE", "中国现行法律法规")

# ---- LLM（默认 ModelScope，OpenAI 兼容）----
# 主供应商 key / base_url；故障转移链里未单独指定 key/base_url 的档位都继承这两个值。
MODELSCOPE_API_KEY = os.getenv("MODELSCOPE_API_KEY", "")
MODELSCOPE_BASE_URL = os.getenv("MODELSCOPE_BASE_URL", "https://api-inference.modelscope.cn/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-ai/DeepSeek-V3.2")

# ---- LLM 故障转移链（配额超限自动切换，可跨供应商）----
# ModelScope 免费配额按模型分别计算（每模型约 20 次/天）；当首选模型 429 配额超限时，
# 自动按顺序切到下一档，用户无感知（仅多等片刻）。
#
# 每一档可以是「纯模型名」或「带自有 API 的完整档位」，用 .env 的 LLM_FALLBACK_MODELS 配置：
#   - 纯模型名（如 ZhipuAI/GLM-5）       → 继承主供应商的 key 与 base_url
#   - 模型|key|base_url（| 分隔）          → 用自己的 API，可接任意 OpenAI 兼容供应商或中转
#   - 模型|key                            → 自带 key，base_url 继承主供应商
#   - 档位之间用英文逗号分隔
# 例：LLM_FALLBACK_MODELS=ZhipuAI/GLM-5,deepseek-chat|sk-xxx|https://api.deepseek.com/v1
#
# 这样最后一档可挂一个异构供应商作真正兜底，避免「同一家全部 429 一起熄火」。
_DEFAULT_FALLBACKS = [
    "Qwen/Qwen3-235B-A22B-Instruct-2507",
    "ZhipuAI/GLM-5",
    "deepseek-ai/DeepSeek-V4-Flash",
    "MiniMax/MiniMax-M2.5",
    "deepseek-ai/DeepSeek-V3.2",
]


def _parse_provider_entry(entry: str) -> dict:
    """把一条故障转移配置解析成 {model, api_key, base_url}。

    语法：model | api_key | base_url（后两段可省，省略则继承主供应商）。
    """
    parts = [p.strip() for p in entry.split("|")]
    model = parts[0]
    api_key = parts[1] if len(parts) > 1 and parts[1] else MODELSCOPE_API_KEY
    base_url = parts[2] if len(parts) > 2 and parts[2] else MODELSCOPE_BASE_URL
    return {"model": model, "api_key": api_key, "base_url": base_url}


_fallback_env = os.getenv("LLM_FALLBACK_MODELS", "")
_fallback_entries = [e.strip() for e in _fallback_env.split(",") if e.strip()] or _DEFAULT_FALLBACKS
# 首选模型（继承主供应商）置顶，其后接故障转移链；按 (model, base_url) 去重并保持顺序。
LLM_PROVIDERS = []
_seen = set()
for _entry in [LLM_MODEL] + _fallback_entries:
    _p = _parse_provider_entry(_entry)
    _dedup_key = (_p["model"], _p["base_url"])
    if _dedup_key not in _seen:
        _seen.add(_dedup_key)
        LLM_PROVIDERS.append(_p)

# ---- Embedding 供应商切换 ----
EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "modelscope").lower()

MODELSCOPE_EMBED_MODEL = os.getenv("MODELSCOPE_EMBED_MODEL", "Qwen/Qwen3-Embedding-0.6B")

SILICONFLOW_API_KEY = os.getenv("SILICONFLOW_API_KEY", "")
SILICONFLOW_BASE_URL = os.getenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1")
SILICONFLOW_EMBED_MODEL = os.getenv("SILICONFLOW_EMBED_MODEL", "BAAI/bge-m3")

# ---- 用户反馈日志 ----
# 用户对回答的 👍/👎 反馈落到本地 JSONL，攒成难例集后可回灌评估集。
# 每行一条：{ts, question, rewrite, liked, answer, refs:[{law,no}], verify_status}
FEEDBACK_LOG_ENABLED = os.getenv("FEEDBACK_LOG_ENABLED", "true").lower() == "true"
FEEDBACK_LOG_PATH = ROOT_DIR / "data" / "feedback.jsonl"

# ---- Query embedding 缓存 ----
# 每次提问都要对 query 求一次 embedding（消耗供应商配额、增加延迟）。
# 相同/重复问题很常见，故对 query 向量做磁盘缓存（key = provider+model+文本）。
# 缓存随模型/供应商变化自动隔离，换 embedding 模型不会读到旧向量。
EMBED_CACHE_ENABLED = os.getenv("EMBED_CACHE_ENABLED", "true").lower() == "true"
EMBED_CACHE_DIR = ROOT_DIR / "vector_store" / "_query_cache"
EMBED_CACHE_MAX = int(os.getenv("EMBED_CACHE_MAX", "2000"))  # 最多缓存的 query 数（LRU 淘汰）

# ---- 检索参数 ----
# 默认 8：实测常见法律问题常涉及相邻条文，top_k=5→8 使 Recall 0.75→0.90、Hit 0.92→0.96，
# 且 MRR 不降（首个命中排名不受多召回影响）。再大边际收益递减且徒增 LLM 上下文。
TOP_K = int(os.getenv("TOP_K", "8"))

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
# 向量距离阈值：若最相关条文的余弦距离仍大于此值，判定问题与已接入法律无关，
# 返回空（触发"未找到相关条文"），避免把无关条文喂给 LLM 诱发幻觉。
# 实测：真实法律问题 distance≈0.6~0.9，无关问题（天气/菜谱）≥1.2，故阈值取 1.0。
# 设为 0 可关闭该过滤。
MAX_DISTANCE = float(os.getenv("MAX_DISTANCE", "1.0"))

# ---- 混合检索（向量 + BM25 关键词，RRF 融合）----
# 向量擅长语义，BM25 擅长法律术语精确匹配，两路 RRF 融合提升召回。
HYBRID_ENABLED = os.getenv("HYBRID_ENABLED", "true").lower() == "true"
# 每一路召回的候选数（融合后再取 TOP_K）。候选只影响融合质量、不进 LLM 上下文，
# 故可适当放大：100 题评估集上 20→40 使 Recall 0.965→0.970、MRR 微升。
HYBRID_CANDIDATES = int(os.getenv("HYBRID_CANDIDATES", "40"))
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
