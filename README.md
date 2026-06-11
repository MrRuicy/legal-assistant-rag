# 民法典法律助手 RAG 系统

基于 RAG（检索增强生成）的《中华人民共和国民法典》智能问答系统。

## 特性

- ✅ **准确引用**：答案强制引用具体条文（《民法典》第X条），避免幻觉
- ✅ **结构化数据**：按"编/章/节/条"解析民法典，保留完整层级信息
- ✅ **可切换 Embedding**：支持 ModelScope API 和 SiliconFlow API 两种供应商
- ✅ **本地向量库**：ChromaDB 本地持久化，无需额外服务器
- ✅ **Web 界面**：Gradio 驱动，支持本地/局域网/临时公网访问
- ✅ **合规设计**：内置免责声明，明确不构成法律建议

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
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
│   ├── config.py      # 配置管理（API key、模型名、可切换 embedding）
│   ├── parser.py      # Markdown 解析器（按条切分 + 通用 schema）
│   ├── embedding.py   # 可切换的 embedding 客户端（ModelScope/SiliconFlow）
│   ├── vector_store.py  # 向量库构建与检索（ChromaDB）
│   ├── rag.py         # RAG 问答链（检索 + LLM + 强制引用）
│   └── web.py         # Gradio Web 界面
├── main.py            # 主入口（setup / serve）
├── requirements.txt
├── .env.example       # 配置模板
└── README.md
```

## 架构设计

```
用户提问
    ↓
1. 向量检索（Top-K 相关条文）
    ↓
2. 构造 Prompt（条文 + 问题 + 强制引用指令）
    ↓
3. LLM 生成答案（ModelScope API）
    ↓
4. 返回（答案 + 引用条文 + 免责声明）
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
- **向量库**：ChromaDB（本地文件型）
- **LLM**：ModelScope API（DeepSeek-V3.2 等中文模型）
- **Web 框架**：Gradio

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
