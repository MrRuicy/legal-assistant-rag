# 民法典法律助手 RAG 系统

基于 RAG（检索增强生成）的《中华人民共和国民法典》智能问答系统。

## 特性

- ✅ **混合检索**：向量召回 + BM25 关键词召回，加权 RRF 融合，兼顾语义与法律术语精确匹配
- ✅ **引用校验**：自动核对回答引用的条号是否来自检索结果，醒目徽章标注（通过/告警），降低幻觉风险
- ✅ **准确引用**：答案强制引用具体条文（《民法典》第X条）
- ✅ **多轮对话**：支持追问，自动改写依赖上下文的问题（如"有无例外"→"诉讼时效的例外"）再检索
- ✅ **流式输出**：回答逐字呈现，无需等待整段生成
- ✅ **多模型故障转移**：某模型配额超限（429）时按优先级自动切换下一个模型，用户无感知
- ✅ **相关性闸门**：距离阈值拦截无关问题（如天气、菜谱），返回"未找到相关条文"
- ✅ **检索评估集**：内置 25 题评估集与脚本（`eval/`），量化每次优化的 Recall/Hit/MRR
- ✅ **可切换 Embedding**：支持 ModelScope API 和 SiliconFlow API 两种供应商
- ✅ **本地向量库**：ChromaDB 本地持久化，无需额外服务器
- ✅ **合规设计**：内置免责声明，明确不构成法律建议

## 快速开始

### 1. 安装依赖

建议使用虚拟环境，并用清华镜像源加速：

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 2. 配置 API 密钥

复制 `.env.example` 为 `.env`，填入你的 API 密钥：

```bash
cp .env.example .env
```

编辑 `.env`：
```ini
# ModelScope（必填，用于 LLM）
MODELSCOPE_API_KEY=your_modelscope_token_here
LLM_MODEL=deepseek-ai/DeepSeek-V3.2

# 模型故障转移链（可选，逗号分隔）：首选模型配额超限时按序自动切换
# 留空则用内置默认链。ModelScope 免费配额按模型分别计算（每模型约 20 次/天）
# LLM_FALLBACK_MODELS=Qwen/Qwen3-235B-A22B-Instruct-2507,ZhipuAI/GLM-5

# Embedding 供应商选择（推荐 siliconflow，ModelScope 免费额度较严）
EMBEDDING_PROVIDER=siliconflow

# SiliconFlow（embedding 推荐，免费额度充足）
SILICONFLOW_API_KEY=your_siliconflow_token_here
```

**获取 API 密钥：**
- ModelScope: [modelscope.cn](https://modelscope.cn) → 访问令牌
- SiliconFlow: [cloud.siliconflow.cn](https://cloud.siliconflow.cn) → API 密钥

### 3. 初始化（首次运行）

```bash
python main.py setup
```

这会：
1. 解析 `data/raw/` 下的民法典 markdown 文件
2. 生成统一的 JSON 数据（`data/processed/civil_code.json`）
3. 调用 embedding API 构建向量库（存储在 `vector_store/`）

### 4. 启动 Web 服务

```bash
python main.py serve
```

默认访问地址：`http://localhost:7860`

## 目录结构

```
legal-assistant-rag/
├── data/
│   ├── raw/           # 民法典原始 markdown（从 LawRefBook 下载）
│   └── processed/     # 解析后的统一 JSON
├── src/
│   ├── config.py        # 配置管理（API key、模型优先级链、检索参数）
│   ├── parser.py        # Markdown 解析器（按条切分 + 通用 schema）
│   ├── embedding.py     # 可切换的 embedding 客户端（ModelScope/SiliconFlow）
│   ├── bm25_retriever.py  # BM25 关键词检索（jieba 分词，内存索引）
│   ├── reranker.py      # rerank 精排客户端（可选，默认关闭）
│   ├── vector_store.py  # 向量库 + 混合检索 + RRF 融合 + 距离闸门
│   ├── rag.py           # RAG 问答链（检索 + 改写 + 故障转移 + 引用校验）
│   └── web.py           # Gradio Web 界面（流式 + 多轮）
├── eval/
│   ├── eval_set.json    # 检索评估集（25 题，覆盖 7 编）
│   └── evaluate.py      # 评估脚本（Recall@K / Hit@K / MRR）
├── main.py            # 主入口（setup / serve）
├── requirements.txt
├── .env.example       # 配置模板
└── README.md
```

## 架构设计

```
用户提问
    ↓
0. 查询改写（多轮场景：用历史把追问补全成独立问题）
    ↓
1. 混合检索：向量召回 + BM25 召回 → 加权 RRF 融合（向量权重 5 : BM25 权重 1）
    ↓
2. 相关性闸门：最佳距离 > 阈值则判定无关，返回"未找到相关条文"
    ↓
3. 构造 Prompt（Top-K 条文 + 问题 + 强制引用指令）+ 历史对话
    ↓
4. LLM 流式生成（模型配额超限自动故障转移）
    ↓
5. 引用校验：核对引用条号是否都在检索结果中
    ↓
6. 返回（流式答案 + 引用条文 + 校验徽章 + 免责声明）
```

**数据流通用 Schema：**
```python
LawArticle {
  law_name: "中华人民共和国民法典"
  part: "总则"
  chapter: "第一章 基本规定"
  section: ""
  article_no: 1
  article_text: "为了保护民事主体的合法权益..."
  effective_date: "2021-01-01"
}
```

## 技术栈

- **数据源**：[LawRefBook/Laws](https://github.com/LawRefBook/Laws) 民法典 markdown
- **Embedding**：SiliconFlow API（推荐，bge-m3）/ ModelScope API（备选）
- **关键词检索**：jieba 分词 + rank_bm25（BM25Okapi）
- **向量库**：ChromaDB（本地文件型）
- **检索融合**：加权 Reciprocal Rank Fusion（RRF）
- **LLM**：ModelScope API（DeepSeek-V3.2 / Qwen3 / GLM-5 等中文模型，支持多模型故障转移）
- **Web 框架**：Gradio

## 检索评估

内置评估集量化检索质量，每次调参后可对比效果：

```bash
python -m eval.evaluate            # 用默认 Top-K
python -m eval.evaluate --top-k 10
```

指标说明：
- **Recall@K**：期望条文被召回的比例
- **Hit@K**：至少命中一条期望条文的题目比例
- **MRR**：首个命中条文排名的倒数（衡量命中条文是否靠前）

当前混合检索在 25 题评估集上：Recall@8 ≈ 0.90，Hit@8 ≈ 0.96。

## 扩展其他法律

当前只接入民法典。要添加其他法律（刑法、公司法等）：

1. 下载对应的 markdown 文件到 `data/raw/`
2. 在 `parser.py` 中添加对应的解析函数（或复用 `parse_civil_code_markdown`，如果格式相同）
3. 修改 `parse_all_civil_code` 或新增函数合并多部法律
4. 重新运行 `python main.py setup`

**数据结构已通用化**（`law_name` 字段区分不同法律），检索/RAG/Web 模块无需改动。

## 部署到 ModelScope 创空间

1. 在 [ModelScope 创空间](https://modelscope.cn/studios) 创建新应用
2. 上传整个项目
3. 设置启动命令：`python main.py serve`
4. 在创空间环境变量中配置 `.env` 的密钥
5. 发布即可获得永久公网 URL

## 注意事项

- **法律时效性**：本系统基于民法典 2021 年版本，不包含后续司法解释
- **免责声明**：所有答案仅供参考，不构成法律建议
- **API 限额**：免费 API 有调用次数限制，生产环境建议升级付费或本地部署模型
- **数据准确性**：虽已尽力确保，但法律条文解析可能存在误差，使用前请核对原文

## License

本项目代码采用 MIT 协议。

法律数据来源于 [LawRefBook/Laws](https://github.com/LawRefBook/Laws)，为公开法律文本。
