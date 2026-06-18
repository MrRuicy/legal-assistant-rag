"""全局配置：集中管理 API 密钥、模型名、可切换的 embedding 供应商。

所有可调项通过 .env 注入，代码里不写死任何密钥。
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ---- 路径 ----
ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_RAW_DIR = ROOT_DIR / "data" / "raw"  # 原始法律文本（markdown）
DATA_PROCESSED_DIR = ROOT_DIR / "data" / "processed"  # 解析后的统一 schema json
VECTOR_STORE_DIR = ROOT_DIR / "vector_store"  # ChromaDB 持久化目录
COLLECTION_NAME = "chinese_laws"

# ---- 应用品牌 ----
# 多法律接入后，界面文案由这两个变量决定，不再写死「民法典」。
APP_TITLE = os.getenv("APP_TITLE", "中国法律助手")
APP_SUBTITLE = os.getenv(
    "APP_SUBTITLE", "基于 RAG 的中国法律法规智能问答 · 多轮对话 · 条文引用校验"
)

# ---- LLM（默认 ModelScope，OpenAI 兼容）----
# 主供应商 key / base_url；故障转移链里未单独指定 key/base_url 的档位都继承这两个值。
MODELSCOPE_API_KEY = os.getenv("MODELSCOPE_API_KEY", "")
MODELSCOPE_BASE_URL = os.getenv(
    "MODELSCOPE_BASE_URL", "https://api-inference.modelscope.cn/v1"
)
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-ai/DeepSeek-V3.2")

# 单次 LLM 调用的超时（秒）。OpenAI SDK 默认约 600s，一旦服务端接了连接却不回包，
# 会干等 10 分钟拖垮整条多跳链/前端体验。设显式短超时，让挂起的调用快速故障转移到下一档。
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "60"))

# 单次 embedding 调用的超时（秒）与重试次数。embedding 无故障转移链（仅一个供应商），
# 但仍需 timeout 防止服务端挂起时无限等待（多跳检索一题多次 embedding，更易踩到）。
# 超时/连接错误时重试，仍失败则抛出（由上层捕获，不阻断整轮评估）。
EMBED_TIMEOUT = float(os.getenv("EMBED_TIMEOUT", "30"))
EMBED_MAX_RETRY = int(os.getenv("EMBED_MAX_RETRY", "2"))

# ---- 故障转移断路器（配额感知）----
# 默认行为是每次都从首选模型依次撞，主力模型耗尽时每次调用都白撞一次 429（虽不耗配额但多一跳）。
# 断路器：某档撞限额后记下冷却截止时间，后续调用直接跳过它、从可用的档开始，冷却到期再恢复。
# 区分两类 429（靠响应头 model-requests-remaining）：
#   - 每日配额耗尽（remaining=0）→ 长冷却（今天不会恢复，避免反复重撞）
#   - 每分钟限速 RPM（remaining>0）→ 短冷却（过会儿自动恢复重试）
LLM_RPM_COOLDOWN_SEC = float(os.getenv("LLM_RPM_COOLDOWN_SEC", "90"))       # RPM 限速短冷却
LLM_EXHAUST_COOLDOWN_SEC = float(os.getenv("LLM_EXHAUST_COOLDOWN_SEC", "3600"))  # 每日耗尽长冷却

# ---- LLM 故障转移链（配额超限自动切换，可跨供应商）----
# ModelScope 免费配额按模型分别计算（实测：多数模型 50 次/天，Qwen3.5 系列 100 次/天）；
# 当首选模型 429 配额超限时，自动按顺序切到下一档，用户无感知（仅多等片刻）。
# 配合断路器（见上）：耗尽的档会被记冷却、后续调用直接跳过，不再每次白撞。
#
# 每一档可以是「纯模型名」或「带自有 API 的完整档位」，用 .env 的 LLM_FALLBACK_MODELS 配置：
#   - 纯模型名（如 ZhipuAI/GLM-5）       → 继承主供应商的 key 与 base_url
#   - 模型|key|base_url（| 分隔）          → 用自己的 API，可接任意 OpenAI 兼容供应商或中转
#   - 模型|key                            → 自带 key，base_url 继承主供应商
#   - 档位之间用英文逗号分隔
# 例：LLM_FALLBACK_MODELS=ZhipuAI/GLM-5,deepseek-chat|sk-xxx|https://api.deepseek.com/v1
#
# 默认链设计：① DeepSeek/Qwen 优先；② 大配额靠前（Qwen3.5 系列 100/天）；
# ③ 末尾挂异构厂商（GLM/Kimi/MiniMax）作真正兜底，避免「ModelScope 同源全部 429 一起熄火」。
# 总可用量约 550 次/天。（DeepSeek-V4-Pro 实测返回 choices=None 畸形响应且照扣配额，已排除。）
_DEFAULT_FALLBACKS = [
    "Qwen/Qwen3.5-397B-A17B",            # 100/天，最强 Qwen
    "deepseek-ai/DeepSeek-V4-Flash",     # 50/天，快
    "Qwen/Qwen3.5-122B-A10B",            # 100/天
    "Qwen/Qwen3-Next-80B-A3B-Instruct",  # 100/天
    "ZhipuAI/GLM-5.1",                   # 50/天，异构兜底
    "moonshotai/Kimi-K2.5",              # 50/天，异构兜底
    "MiniMax/MiniMax-M2.5",              # 50/天，异构兜底
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
_fallback_entries = [
    e.strip() for e in _fallback_env.split(",") if e.strip()
] or _DEFAULT_FALLBACKS
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
EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "siliconflow").lower()

MODELSCOPE_EMBED_MODEL = os.getenv(
    "MODELSCOPE_EMBED_MODEL", "Qwen/Qwen3-Embedding-0.6B"
)

SILICONFLOW_API_KEY = os.getenv("SILICONFLOW_API_KEY", "")
SILICONFLOW_BASE_URL = os.getenv(
    "SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1"
)
SILICONFLOW_EMBED_MODEL = os.getenv("SILICONFLOW_EMBED_MODEL", "BAAI/bge-m3")

# ---- 用户反馈日志 ----
# 用户对回答的 👍/👎 反馈落到本地 JSONL，攒成难例集后可回灌评估集。
# 每行一条：{ts, question, rewrite, liked, answer, refs:[{law,no}], verify_status}
FEEDBACK_LOG_ENABLED = os.getenv("FEEDBACK_LOG_ENABLED", "true").lower() == "true"
FEEDBACK_LOG_PATH = ROOT_DIR / "data" / "feedback.jsonl"

# ---- 向量库体积护栏 ----
# setup 构建后若向量库超过此 MB 数会提示（仓库会随之变大）。仅提示，不阻断。
VECTOR_STORE_WARN_MB = int(os.getenv("VECTOR_STORE_WARN_MB", "150"))

# ---- Query embedding 缓存 ----
# 每次提问都要对 query 求一次 embedding（消耗供应商配额、增加延迟）。
# 相同/重复问题很常见，故对 query 向量做磁盘缓存（key = provider+model+文本）。
# 缓存随模型/供应商变化自动隔离，换 embedding 模型不会读到旧向量。
EMBED_CACHE_ENABLED = os.getenv("EMBED_CACHE_ENABLED", "true").lower() == "true"
EMBED_CACHE_DIR = ROOT_DIR / "vector_store" / "_query_cache"
EMBED_CACHE_MAX = int(
    os.getenv("EMBED_CACHE_MAX", "2000")
)  # 最多缓存的 query 数（LRU 淘汰）

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
SILICONFLOW_RERANK_MODEL = os.getenv(
    "SILICONFLOW_RERANK_MODEL", "BAAI/bge-reranker-v2-m3"
)
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


# ---- 多跳检索 Agent ----
# 把单跳检索链升级为「会自己判断信息够不够、还要查什么」的多跳 Agent。
# AGENT_MODE 为 web 端「深度模式」的默认值；MAX_HOPS 是防死循环的硬上限。
AGENT_MODE = os.getenv("AGENT_MODE", "false").lower() == "true"
# 每跳之间去重后仍要查的子问题；跳数超过此值强制收敛去作答（防死循环/成本爆炸）。
MAX_HOPS = int(os.getenv("MAX_HOPS", "3"))
# 每个子问题检索的条数。与 TOP_K 对齐（=8），保证多跳每跳的召回预算与单跳一致，
# 三种模式（单跳/固定多跳/Agent）口径可比；合并去重后再受 AGENT_MAX_CONTEXT 截断。
AGENT_PER_HOP_TOP_K = int(os.getenv("AGENT_PER_HOP_TOP_K", "8"))
# 多跳合并去重后，喂给 Answer 节点的条文上限（控制最终上下文长度与成本）。
# 实测：多跳一题去重后候选常 17~20 条，16 偏紧会把相关条文截掉（如个保法#66 排19被切）。
# 提到 24 可救回这类「召回了却进不了上下文」的遗漏，代价仅是 Answer 多读几条条文的 token。
AGENT_MAX_CONTEXT = int(os.getenv("AGENT_MAX_CONTEXT", "24"))
# 规划/反思用的「便宜快」模型（留空则复用故障转移链首档）。Answer 仍用强模型。
# 语法同 LLM_FALLBACK_MODELS 单档：model | api_key | base_url（后两段可省，继承主供应商）。
AGENT_PLANNER_MODEL = os.getenv("AGENT_PLANNER_MODEL", "")


def planner_providers() -> list:
    """Planner/Reflect 用的 provider 链（便宜快的模型，压多跳成本）。

    AGENT_PLANNER_MODEL 留空时返回主故障转移链（与 Answer 同模型，零额外配置即可用）；
    配置后把该便宜模型置顶、主链兜底，既省钱又不牺牲可用性。
    语法同单档 LLM_FALLBACK_MODELS：model | api_key | base_url（后两段可省）。
    """
    if not AGENT_PLANNER_MODEL.strip():
        return LLM_PROVIDERS
    head = _parse_provider_entry(AGENT_PLANNER_MODEL)
    chain = [head]
    seen = {(head["model"], head["base_url"])}
    for p in LLM_PROVIDERS:
        k = (p["model"], p["base_url"])
        if k not in seen:
            seen.add(k)
            chain.append(p)
    return chain


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
