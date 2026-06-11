"""全局配置：集中管理 API 密钥、模型名、可切换的 embedding 供应商。

所有可调项通过 .env 注入，代码里不写死任何密钥。
"""
import os
from pathlib import Path
from dotenv import load_dotenv

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
