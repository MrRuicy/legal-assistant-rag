# RAG 系统完整学习总结

> 基于「中国法律助手 RAG 系统」项目的技术实践

---

## 目录

1. [RAG 系统概述](#1-rag-系统概述)
2. [核心技术组件](#2-核心技术组件)
3. [数据处理流程](#3-数据处理流程)
4. [检索技术详解](#4-检索技术详解)
5. [生成与优化](#5-生成与优化)
6. [工程化实践](#6-工程化实践)
7. [评估与迭代](#7-评估与迭代)
8. [总结与思考](#8-总结与思考)

---

## 1. RAG 系统概述

### 1.1 什么是 RAG

**RAG（Retrieval-Augmented Generation，检索增强生成）** 是一种结合了**信息检索**和**语言生成**的 AI 架构模式。

**核心思想**：
- 大语言模型（LLM）虽然强大，但存在**知识截止日期**、**幻觉问题**、**领域知识不足**等局限
- RAG 通过在生成前先**检索相关知识**，让 LLM 基于检索到的真实文档回答，从而：
  - ✅ 提供**可追溯的答案**（每个回答都能指向具体来源）
  - ✅ 解决**幻觉问题**（基于真实文档，而非模型参数记忆）
  - ✅ 支持**动态知识更新**（更新知识库即可，无需重新训练模型）
  - ✅ 降低**成本**（无需为特定领域微调大模型）

### 1.2 RAG 的基本流程

```
用户提问
    ↓
【检索阶段】从知识库检索相关文档
    ↓
【增强阶段】将检索结果作为上下文注入 Prompt
    ↓
【生成阶段】LLM 基于上下文生成答案
    ↓
返回答案 + 引用来源
```

### 1.3 本项目的 RAG 架构

本项目是一个**生产级的法律领域 RAG 系统**，具有以下特点：

- **知识库**：38 部中国法律法规，5165 条条文
- **混合检索**：向量检索 + BM25 关键词检索
- **多轮对话**：支持上下文追问
- **引用校验**：自动验证 LLM 引用的条文是否存在
- **故障转移**：多档模型自动切换，保证服务可用性

**技术栈**：
- 文档解析：自研通用 LawRefBook Markdown 解析器
- Embedding：SiliconFlow API (bge-m3) / ModelScope API
- 向量库：ChromaDB（本地持久化）
- 关键词检索：jieba + BM25Okapi
- LLM：DeepSeek-V3.2 / Qwen3 / GLM-5（多模型故障转移）
- Web 框架：Gradio

---

## 2. 核心技术组件

### 2.1 文档解析（Parser）

#### 为什么需要文档解析

原始法律文本是 Markdown 格式，包含层级结构（编、章、节、条），需要解析成结构化数据才能入库。

#### 统一数据模型

```python
@dataclass
class LawArticle:
    law_name: str         # 法律名称，如"中华人民共和国公司法"
    part: str             # 编（仅民法典等有）
    chapter: str          # 章，如"第一章 总则"
    section: str          # 节
    article_no: int       # 条号（数字）
    sub_no: int           # "第X条之一"→1，普通条为0
    article_text: str     # 条文正文
    effective_date: str   # 生效日期
```

**设计要点**：
- 以**条文**为最小单元（法律问答通常引用到条）
- `sub_no` 解决"第133条之一"与"第133条"的唯一性问题
- 保留层级信息（part/chapter/section）用于增强 embedding 语义

#### 解析难点

1. **多段条文识别**：一条法律条文可能跨多个自然段，需要正确累积
2. **中文数字转换**：支持"第一百八十八条"与"第188条"两种写法
3. **通用性**：同一解析器适用于所有 LawRefBook 格式的法律

**核心正则**：
```python
_ARTICLE_HEAD_RE = re.compile(
    r'^第([一二三四五六七八九十百千零\d]+)条(之[一二三四五六七八九十]+)?[\s　]+(.*)$'
)
```

**解析逻辑**（状态机）：
```python
for line in lines:
    if line.startswith("# "):      # 法律名 / 编
    if line.startswith("## "):     # 章
    if line.startswith("### "):    # 节
    if _ARTICLE_HEAD_RE.match(line):  # 条文起始
        flush_previous_article()
        create_new_article()
    else:                          # 条文续段
        append_to_current_article()
```

### 2.2 Embedding 技术

#### 什么是 Embedding

**Embedding（嵌入）** 是将文本转换为高维向量（通常 768 或 1024 维）的技术，使得**语义相似的文本在向量空间中距离更近**。

**示例**：
```
"诉讼时效是多久" → [0.23, -0.15, 0.87, ..., 0.42]  (768维)
"诉讼时效一般是几年" → [0.21, -0.14, 0.89, ..., 0.40]  (相近)
"如何注册公司" → [-0.62, 0.78, -0.33, ..., 0.11]  (距离远)
```

#### 本项目的 Embedding 方案

**可切换的供应商架构**：
```python
class EmbeddingClient:
    def __init__(self):
        cfg = config.embedding_config()  # 从 .env 读取供应商配置
        self.provider = cfg["provider"]  # siliconflow / modelscope
        self.model = cfg["model"]
        self.client = OpenAI(api_key=cfg["api_key"], base_url=cfg["base_url"])
```

**支持的供应商**：
- **SiliconFlow**（推荐）：bge-m3 模型，免费额度充足
- **ModelScope**（备选）：Qwen3-Embedding-0.6B

**为什么设计成可切换**：
1. 不同供应商的免费额度、速度、质量各异
2. 避免单点依赖（某个供应商故障时可快速切换）
3. 未来可能需要本地部署模型

#### Embedding 的两种场景

**场景1：批量构建向量库**（setup 阶段）
```python
def embed(self, texts: List[str], batch_size: int = 16) -> List[List[float]]:
    """对一批文本求向量，自动分批避免单次请求过大"""
    vectors = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        resp = self.client.embeddings.create(model=self.model, input=batch)
        vectors.extend([item.embedding for item in resp.data])
    return vectors
```

**场景2：单条查询 Embedding**（每次提问时）
```python
def embed_query(self, text: str) -> List[float]:
    """对单条 query 求向量，带磁盘缓存（命中则零 API 调用）"""
    cached = self._cache.get(self.provider, self.model, text)
    if cached is not None:
        return cached
    vec = self.embed([text])[0]
    self._cache.set(self.provider, self.model, text, vec)
    return vec
```

#### Query Embedding 缓存

**问题**：每次提问都要调用 embedding API，消耗配额且增加延迟。

**解决方案**：磁盘 LRU 缓存
```python
class QueryEmbedCache:
    def _key(self, provider: str, model: str, text: str) -> str:
        # 缓存键 = sha1(供应商 + 模型 + 文本)
        return hashlib.sha1(f"{provider}\x00{model}\x00{text}".encode()).hexdigest()
    
    def get(self, provider, model, text):
        path = self.dir / f"{self._key(provider, model, text)}.json"
        if path.exists():
            return json.load(open(path))["vector"]
        return None
```

**优点**：
- 相同问题**零 API 调用**，节省配额
- 降低**首字延迟**（无需等待 embedding 接口）
- 换模型/供应商**自动隔离**（缓存键包含 provider+model）

**淘汰策略**：
- 最多缓存 2000 条 query（可配置）
- 超过上限时按文件 mtime 淘汰最旧的 10%

---

### 2.3 向量数据库（Vector Store）

#### 为什么需要向量数据库

传统数据库基于**精确匹配**（WHERE column = 'value'），无法做**语义搜索**。向量数据库支持：
- **相似度搜索**：找出与 query 向量最接近的 Top-K 个文档向量
- **高效索引**：HNSW、IVF 等算法加速高维向量检索

#### 本项目的选型：ChromaDB

**特点**：
- **本地持久化**：数据存储在本地文件，无需额外服务器
- **轻量零配置**：`pip install chromadb` 即可使用
- **嵌入式运行**：直接在 Python 进程中运行，适合中小规模数据

**初始化**：
```python
self.chroma_client = chromadb.PersistentClient(
    path=str(config.VECTOR_STORE_DIR)  # 本地持久化目录
)
self.collection = self.chroma_client.get_or_create_collection(
    name="chinese_laws",
    metadata={"description": "中国法律条文向量库"}
)
```

#### 构建向量库

**数据准备**：
```python
for art in articles:
    # ID：跨法律唯一（法律名 + 条号 + sub_no）
    ids.append(f"{art.law_name}#{art.article_no}_{art.sub_no}")
    
    # 文本：含层级信息增强语义
    texts.append(
        f"{art.law_name} {art.part} {art.chapter} {art.section} "
        f"第{art.article_no}条 {art.article_text}"
    )
    
    # Metadata：结构化信息（检索时返回）
    metadatas.append({
        "law_name": art.law_name,
        "article_no": art.article_no,
        "article_text": art.article_text,
        # ...
    })
```

**分批入库**：
```python
for i in range(0, len(texts), batch_size):
    batch_texts = texts[i:i+batch_size]
    embeddings = self.embed_client.embed(batch_texts)
    self.collection.add(
        ids=batch_ids,
        embeddings=embeddings,
        documents=batch_texts,
        metadatas=batch_metas,
    )
```

**设计要点**：
1. **ID 唯一性**：`法律名#条号_sub_no` 避免跨法律冲突
2. **文本增强**：embedding 文本包含法律名和层级，消除跨法律歧义
3. **Metadata 存储**：结构化信息单独存储，检索时一并返回

#### 向量检索

```python
def _vector_search(self, query: str, n_results: int) -> List[Dict]:
    query_vec = self.embed_client.embed_query(query)  # query embedding
    results = self.collection.query(
        query_embeddings=[query_vec],
        n_results=n_results,  # Top-K
    )
    # 返回 metadata + distance
    return hits
```

**距离度量**：余弦相似度（Cosine Similarity）
- 向量夹角越小，语义越相近
- ChromaDB 返回的 distance 是余弦距离（1 - 余弦相似度）

---


### 2.4 BM25 关键词检索

#### 为什么需要 BM25

**向量检索的局限**：
- 擅长**语义理解**（"诉讼时效"能匹配"时效期限"）
- 但对**精确术语匹配**不够敏感（"定金" vs "订金"、"居住权"等法律专有名词）

**BM25 的优势**：
- 基于**词频统计**，精确匹配关键词
- 对法律术语、条号（"第188条"）等精确检索效果好

#### BM25 算法原理

**核心思想**：词频越高、文档越短、该词在语料库中越稀有，则相关性越高。

**公式**：
```
BM25(D, Q) = Σ IDF(qi) * (f(qi, D) * (k1 + 1)) / (f(qi, D) + k1 * (1 - b + b * |D| / avgdl))
```

- `IDF(qi)`：词 qi 的逆文档频率（越稀有权重越高）
- `f(qi, D)`：词 qi 在文档 D 中的词频
- `|D|`：文档长度
- `k1, b`：调节参数（BM25Okapi 默认 k1=1.5, b=0.75）

#### 本项目的实现

**分词**：
```python
def _tokenize(text: str) -> List[str]:
    """jieba 分词 + 去停用词 + 去标点"""
    tokens = jieba.lcut(text)
    return [
        t.strip() for t in tokens
        if t.strip() and t not in _STOPWORDS and not re.fullmatch(r"[\W_]+", t)
    ]
```

**停用词表**（精简版）：
```python
_STOPWORDS = {
    "的", "了", "和", "是", "在", "有", "与", "或", "及", "等", "为", "对",
    "上", "下", "中", "其", "之", "以", "可以", "应当", "不", "什么", "如何",
    "怎么", "哪些", "吗", "呢", "啊", "请问", "我", "你", "他", "她", "它",
    "这", "那", "个", "条", "第",
}
```

**构建索引**：
```python
class BM25Retriever:
    def __init__(self, articles: List[Dict]):
        # 分词语料：与向量库 embedding 文本保持一致
        corpus = [
            _tokenize(
                f"{a['law_name']} {a['part']} {a['chapter']} "
                f"第{a['article_no']}条 {a['article_text']}"
            )
            for a in articles
        ]
        self.bm25 = BM25Okapi(corpus)
```

**检索**：
```python
def search(self, query: str, top_k: int) -> List[Dict]:
    tokens = _tokenize(query)
    scores = self.bm25.get_scores(tokens)
    # 取分数最高的 top_k 个（分数 > 0 才有匹配）
    ranked_idx = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
    return [hits with bm25_score]
```

#### 分词语料缓存

**问题**：接入 38 部法律后，5000+ 条文每次冷启动都重新分词，拖慢启动速度。

**解决方案**：分词结果缓存到磁盘（pickle）
```python
@classmethod
def from_json(cls, json_path):
    cache_path = config.VECTOR_STORE_DIR / "bm25_corpus.pkl"
    # 若缓存比 JSON 新，直接加载
    if cache_path.exists() and cache_path.stat().st_mtime >= json_path.stat().st_mtime:
        cached = pickle.load(open(cache_path, "rb"))
        if cached.get("count") == len(articles):
            return cls(articles, corpus=cached["corpus"])
    # 否则重新分词并缓存
    inst = cls(articles)
    inst._save_cache()
    return inst
```

---

## 3. 数据处理流程

### 3.1 数据准备阶段（Setup）

```
原始数据（Markdown）
    ↓
【解析】parse_law_markdown() → LawArticle 对象
    ↓
【保存】save_to_json() → civil_code.json
    ↓
【Embedding】embed() → 向量
    ↓
【入库】ChromaDB.add() → 向量库
    ↓
【BM25索引】BM25Retriever() → 分词语料缓存
```

**执行命令**：
```bash
python main.py setup
```

**输出**：
- `data/processed/civil_code.json`：所有法律条文的结构化数据
- `vector_store/`：ChromaDB 向量库
- `vector_store/bm25_corpus.pkl`：BM25 分词语料缓存

### 3.2 向量库构建细节

```python
def build_from_articles(self, articles: List[LawArticle], batch_size: int = 32):
    ids, texts, metadatas = [], [], []
    
    for art in articles:
        # 1. 跨法律唯一 ID
        ids.append(f"{art.law_name}#{art.article_no}_{art.sub_no}")
        
        # 2. Embedding 文本（含层级信息增强语义）
        texts.append(
            f"{art.law_name} {art.part} {art.chapter} {art.section} "
            f"第{art.article_no}条 {art.article_text}"
        )
        
        # 3. Metadata（检索时返回）
        metadatas.append({
            "law_name": art.law_name,
            "article_no": art.article_no,
            "article_text": art.article_text,
            # ...
        })
    
    # 分批 embed + 入库
    for i in tqdm(range(0, len(texts), batch_size)):
        batch_texts = texts[i:i+batch_size]
        embeddings = self.embed_client.embed(batch_texts)
        self.collection.add(ids=batch_ids, embeddings=embeddings, ...)
```

**关键设计**：
1. **ID 设计**：`法律名#条号_sub_no` 保证跨法律唯一性
2. **文本增强**：embedding 时加入法律名和层级，消除歧义（不同法律的"第1条"语义不同）
3. **批量处理**：减少 API 调用次数

---


## 4. 检索技术详解

### 4.1 混合检索（Hybrid Search）

#### 为什么需要混合检索

**单一检索方式的局限**：
- **纯向量检索**：语义理解强，但对精确术语（"定金"、"第188条"）不够敏感
- **纯 BM25**：精确匹配强，但无法理解同义词、语义变体

**混合检索优势**：取长补短，提升召回率
- 向量召回：语义相关的条文
- BM25 召回：包含关键词的条文
- 两路结果融合：兼顾语义和精确匹配

#### RRF 融合算法

**RRF（Reciprocal Rank Fusion）** 是一种简单有效的结果融合算法。

**核心思想**：根据文档在各路结果中的**排名**（而非分数）计算融合分数。

**公式**：
```
RRF_score(d) = Σ weight_i / (k + rank_i(d))
```

- `rank_i(d)`：文档 d 在第 i 路结果中的排名（从 0 开始）
- `k`：常数（通常取 60，本项目取 10 因为候选数较小）
- `weight_i`：第 i 路的权重

**优点**：
- **无需归一化**：不同检索器的分数量纲不同（向量距离 vs BM25 分数），RRF 只看排名
- **鲁棒性好**：对异常分数不敏感
- **简单高效**：无需训练，易于实现

#### 本项目的实现

```python
def _hybrid_search(self, query: str, top_k: int) -> List[Dict]:
    # 1. 两路召回（各取 40 条候选）
    vec_hits = self._vector_search(query, n=40)
    bm25_hits = self.bm25.search(query, n=40)

    # 2. 合并：以 (法律名, 条号, sub_no) 为键去重
    merged = {}
    rrf = {}

    # 向量路加权
    for rank, h in enumerate(vec_hits):
        key = (h['law_name'], h['article_no'], h['sub_no'])
        merged[key] = h
        rrf[key] = HYBRID_VECTOR_WEIGHT / (RRF_K + rank)

    # BM25 路加权
    for rank, h in enumerate(bm25_hits):
        key = (h['law_name'], h['article_no'], h['sub_no'])
        if key in merged:
            merged[key]['bm25_score'] = h['bm25_score']
        else:
            merged[key] = h
        rrf[key] += HYBRID_BM25_WEIGHT / (RRF_K + rank)

    # 3. 按 RRF 分数降序排序，取 top_k
    ordered = sorted(merged.values(), key=lambda h: rrf[...], reverse=True)
    return ordered[:top_k]
```

**参数配置**：
- `HYBRID_VECTOR_WEIGHT = 5.0`：向量路权重
- `HYBRID_BM25_WEIGHT = 1.0`：BM25 路权重
- `RRF_K = 10`：RRF 常数

**权重设计理由**：
- 向量召回质量高，给更高权重（5:1）
- 让 BM25 只补召回，不主导排序
- 实测：混合检索相比纯向量，Recall 提升 5%，MRR 基本持平

### 4.2 相关性闸门（Relevance Gating）

#### 问题场景

用户可能问与法律无关的问题：
- "今天天气怎么样？"
- "红烧肉怎么做？"

如果直接把**最相近**的法律条文喂给 LLM，会诱发**幻觉**（强行解释无关条文）。

#### 解决方案：距离阈值过滤

```python
# 相关性闸门：若所有候选的向量距离都超过阈值，返回空
if config.MAX_DISTANCE > 0:
    dists = [c["distance"] for c in candidates if c.get("distance") is not None]
    if dists and min(dists) > config.MAX_DISTANCE:
        return []  # 触发"未找到相关条文"
```

**阈值设定**（`MAX_DISTANCE = 1.0`）：
- 真实法律问题：distance ≈ 0.6 ~ 0.9
- 无关问题：distance ≥ 1.2
- 阈值取 1.0，在两者之间划界

**效果**：
- 无关问题返回"未找到相关条文"
- 避免 LLM 基于无关条文生成误导性答案

### 4.3 Rerank 精排（可选）

#### 什么是 Rerank

**Rerank（重排序）** 是在粗排（向量/BM25）之后的精排阶段，用专门的**交叉编码器**（Cross-Encoder）对 `(query, doc)` 对打分。

**与 Embedding 的区别**：
- **Embedding**（双塔模型）：query 和 doc 独立编码，通过向量相似度匹配
- **Rerank**（交叉编码器）：query 和 doc 一起输入模型，直接输出相关性分数

**优势**：精度更高（能捕捉 query-doc 之间的细粒度交互）
**劣势**：计算量大（需要对每个候选 doc 都与 query 一起推理）

#### 为什么本项目默认关闭

**实测结论**：bge-m3 向量召回质量已很高，rerank 对本项目的短条文场景**反而损害排序精度**（MRR 下降）。

**原因分析**：
- 法律条文较短（平均 50-100 字），语义明确
- 向量检索已能准确召回相关条文
- Rerank 对长文档、多候选场景收益更大

**保留原因**：作为可选特性，可在 `.env` 中开启对比效果。

---

## 5. 生成与优化

### 5.1 RAG 问答链完整流程

```
用户提问
    ↓
0. 查询改写（多轮场景：用历史把追问补全成独立问题）
    ↓
1. 混合检索：向量召回 + BM25 召回 → 加权 RRF 融合
    ↓
2. 相关性闸门：最佳距离 > 阈值则判定无关，返回"未找到相关条文"
    ↓
3. 构造 Prompt（Top-K 条文 + 问题 + 强制引用指令）+ 历史对话
    ↓
4. LLM 流式生成（配额超限自动故障转移）
    ↓
5. 引用校验：按「《法律名》第X条」核对引用是否都在检索结果中
    ↓
6. 返回（流式答案 + 引用条文 + 校验徽章 + 免责声明）
```

### 5.2 查询改写（Query Rewriting）

#### 为什么需要查询改写

**多轮对话中的追问问题**：
- 用户："诉讼时效一般是多少年？"
- 助手："根据《民法典》第188条，诉讼时效为三年..."
- 用户："**有无例外？**" ← 这个问题依赖上文，无法独立检索

**直接检索的问题**：
- Query = "有无例外？" → embedding 后语义模糊，无法召回相关条文

#### 解决方案

用 LLM 把依赖上文的追问**改写成独立、完整的问题**：
```
"有无例外？" → "诉讼时效的例外情况有哪些？"
```

#### 实现代码

```python
def _rewrite_query(self, question: str, history: List[Dict] = None) -> str:
    if not history:
        return question  # 无历史，直接返回原问题

    # 取最近 3 轮对话（去掉免责声明等噪声）
    convo_lines = []
    for m in history[-6:]:
        role = "用户" if m["role"] == "user" else "助手"
        content = m["content"].split("\n\n---")[0][:150]
        convo_lines.append(f"{role}：{content}")

    prompt = "对话历史 + 最新问题，请改写成独立完整的问题用于检索。只输出改写后的问题。"

    try:
        rewritten = self._complete([{"role": "user", "content": prompt}])
        return rewritten.strip() or question
    except Exception:
        return question  # 改写失败则退回原问题
```

**设计要点**：
1. **只在有历史时调用**：首轮问题无需改写，省一次 API 调用
2. **历史截断**：只取最近 3 轮（6 条消息），避免上下文过长
3. **降级处理**：改写失败时用原问题，不阻断主流程

### 5.3 Prompt 工程

#### System Prompt 设计

```python
def _system_prompt(self, hits: List[Dict] = None) -> str:
    laws = ""
    if hits:
        names = list(dict.fromkeys(h["law_name"] for h in hits))
        laws = "本次检索涉及：" + "、".join(f"《{n}》" for n in names) + "。\n"

    return f"""你是一个严谨的中国法律助手，依据检索到的现行法律法规条文回答用户问题。
{laws}
**严格要求：**
1. 答案必须基于检索到的条文，引用时写明法律名与条号，格式为"《法律名》第X条"。
2. 如果检索结果与问题无关，明确回答"未找到相关条文"。
3. 不得编造、推测或引用检索结果外的条文；不要把某部法律的条号安到另一部法律上。
4. 用通俗易懂的语言解释法律条文，但保持准确性。
5. 回答结尾必须包含"以上内容仅供参考，不构成法律建议"。"""
```

**关键设计点**：
1. **强制引用格式**：`《法律名》第X条`，避免张冠李戴
2. **禁止幻觉**：明确"不得编造、推测"
3. **跨法律提示**：动态列出本次检索涉及的法律，提醒 LLM 区分
4. **通俗解释**：既要准确，也要易懂
5. **免责声明**：强制加入，符合合规要求

#### Context 构造

```python
def _build_context(self, hits: List[Dict]) -> str:
    lines = []
    for i, h in enumerate(hits, 1):
        lines.append(
            f"{i}. 《{h['law_name']}》第{h['article_no']}条"
            f"（{h['part']} {h['chapter']}）\n"
            f"   {h['article_text']}"
        )
    return "\n\n".join(lines)
```

**格式设计**：
- 编号（1, 2, 3...）方便 LLM 引用
- 包含法律名、条号、层级信息（章节）
- 格式清晰，易于 LLM 解析

### 5.4 引用校验（Citation Verification）

#### 为什么需要引用校验

**LLM 可能出现的问题**：
- 引用检索结果外的条文（记忆中的条文，可能已失效）
- 把甲法律的条号安到乙法律上（"《公司法》第188条" 实际是民法典的条号）

**解决方案**：自动校验回答中的引用是否都在检索结果中。

#### 实现逻辑

```python
def _verify_citations(self, answer_text: str, hits: List[Dict]) -> Dict:
    # 1. 提取回答中的引用 {(法律名, 条号), ...}
    cited = self._extract_citations(answer_text)

    # 2. 构建检索结果索引
    retrieved_pairs = {(_strip_law_prefix(h["law_name"]), h["article_no"]) for h in hits}
    retrieved_nos = {h["article_no"] for h in hits}

    # 3. 校验：精确匹配 (法律名, 条号) 对
    fabricated = []
    for law, no in cited:
        if law:  # 已知法律名：必须精确命中
            if (_strip_law_prefix(law), no) not in retrieved_pairs:
                fabricated.append(f"《{law}》第{no}条")
        else:    # 法律名未知：只比对条号
            if no not in retrieved_nos:
                fabricated.append(f"第{no}条")

    # 4. 返回结构化结果（warn / ok）
    if fabricated:
        return {"status": "warn", "fabricated": fabricated,
                "message": f"引用的 {fabricated} 不在检索结果中，请核实"}
    return {"status": "ok", "message": "回答引用的条文均来自检索结果，可追溯"}
```

#### 引用提取

```python
@staticmethod
def _extract_citations(text: str) -> set:
    """从回答提取 (法律名, 条号) 引用"""
    cited = set()
    token_re = re.compile(r"《([^》]+)》|第\s*(\d+)\s*条")
    current_law = ""
    for m in token_re.finditer(text):
        law, article_no = m.groups()
        if law:
            current_law = law  # 记录当前法律名
        elif article_no:
            cited.add((current_law, int(article_no)))
    return cited
```

**设计要点**：
1. **跟踪法律名**：扫描时记录最近出现的《法律名》，后续条号归属到该法律
2. **支持简写**：允许首次引用后省略法律名（"第X条"）
3. **宽松匹配**：法律名归一化（去掉"中华人民共和国"前缀），提升容错性

### 5.5 异构故障转移（Heterogeneous Fallback）

#### 问题背景

免费 API 都有**配额限制**（如 ModelScope 每模型约 20 次/天），用完就 429 错误。

**常见方案的局限**：
- 单一供应商多模型：同一家的模型可能共享总配额或同时 429，无法真正兜底

#### 解决方案：异构故障转移链

支持**跨供应商**的多档模型自动切换：
```
第1档：DeepSeek-V3.2 (ModelScope)
第2档：Qwen3-235B   (ModelScope)
第3档：GLM-5        (ModelScope)
第4档：deepseek-chat (自有 API key, api.deepseek.com) ← 异构兜底
```

#### 配置格式

`.env` 中配置：
```ini
LLM_MODEL=deepseek-ai/DeepSeek-V3.2
LLM_FALLBACK_MODELS=Qwen/Qwen3-235B,deepseek-chat|sk-xxx|https://api.deepseek.com/v1
```

**语法**：
- `模型名`：继承主供应商的 key 和 base_url
- `模型|key|base_url`：自带 API，完全独立的供应商

#### 实现逻辑

```python
def _stream_complete(self, messages, temperature=0.1):
    last_err = None
    for provider in self.providers:
        produced = False
        try:
            stream = self._client_for(provider).chat.completions.create(...)
            for chunk in stream:
                produced = True
                yield chunk.choices[0].delta.content
            return  # 成功完成
        except Exception as e:
            if produced:
                raise  # 已输出部分内容，不能重试
            if self._is_quota_error(e):  # 429 错误
                last_err = e
                continue  # 换下一档
            raise  # 其他错误直接抛出
    raise last_err  # 所有档位都失败
```

**关键设计**：
1. **只在未产出时切换**：已开始输出后不能重试（避免重复内容）
2. **只处理配额错误**：网络、参数等其他错误直接抛出
3. **用户无感知**：切换过程对用户透明，只是稍慢几秒

---

## 6. 工程化实践

### 6.1 流式输出（Streaming）

#### 为什么需要流式

LLM 生成完整回答可能需要数秒到十几秒，若等全部生成完再返回，体验很差。
**流式输出**逐 token 返回，用户能看到答案"逐字呈现"，大幅降低**感知延迟**。

#### 实现：Generator 模式

```python
def answer_stream(self, question, history=None, top_k=None):
    """流式回答（generator，逐 token yield）。每个 chunk 带 type 标识。"""
    yield {"type": "rewrite", "content": search_query}    # 改写后的查询
    yield {"type": "references", "content": hits}         # 检索结果
    for piece in self._stream_complete(messages):
        yield {"type": "answer", "content": piece}        # 答案片段
    yield {"type": "verify", "content": verify}           # 引用校验
    yield {"type": "disclaimer", "content": disclaimer}   # 免责声明
```

**设计要点**：
- 用 `type` 字段区分不同类型内容，前端分别渲染
- 检索结果先返回，让用户立即看到"找到了哪些条文"

### 6.2 配置管理

#### 集中式配置（config.py）

**所有可调项通过 `.env` 注入，代码中不写死任何密钥**：

```python
from dotenv import load_dotenv
load_dotenv()

MODELSCOPE_API_KEY = os.getenv("MODELSCOPE_API_KEY", "")
TOP_K = int(os.getenv("TOP_K", "8"))
MAX_DISTANCE = float(os.getenv("MAX_DISTANCE", "1.0"))
HYBRID_ENABLED = os.getenv("HYBRID_ENABLED", "true").lower() == "true"
```

**优点**：安全（密钥不进代码/git）、灵活（调参不改代码）、环境隔离。

#### 关键参数及调优经验

| 参数 | 默认值 | 说明 | 调优经验 |
|------|--------|------|----------|
| `TOP_K` | 8 | 最终送入 LLM 的条文数 | 5→8 使 Recall 0.75→0.90，再大边际递减 |
| `MAX_DISTANCE` | 1.0 | 相关性闸门阈值 | 真实问题 0.6-0.9，无关问题≥1.2 |
| `HYBRID_CANDIDATES` | 40 | 每路召回候选数 | 20→40 使 Recall 微升 |
| `HYBRID_VECTOR_WEIGHT` | 5.0 | 向量路权重 | vec:bm25=5:1 净赚召回率 |
| `RRF_K` | 10 | RRF 融合常数 | 候选数小，取小值让排名差异更敏感 |
| `RERANK_ENABLED` | false | 是否开启精排 | 短条文场景反而损害 MRR |

### 6.3 缓存策略

本项目有**两层缓存**，都为节省 API 配额和降低延迟：

**Query Embedding 缓存**（`vector_store/_query_cache/{sha1}.json`）
- 相同问题零 API 调用，LRU 淘汰（最多 2000 条）

**BM25 分词语料缓存**（`vector_store/bm25_corpus.pkl`）
- 避免每次启动重新 jieba 分词，基于 mtime 判断是否过期

### 6.4 部署适配

**双入口设计**：
- `main.py`：本地开发入口（`setup` / `serve`）
- `app.py`：云平台（创空间）部署入口（绑定 `0.0.0.0`，向量库缺失时兜底构建）

**预构建索引随仓库提交**：把 `vector_store/` 和 `data/processed/` 一并提交，云平台冷启动**无需重建索引**，不消耗 embedding 配额。

---

## 7. 评估与迭代

### 7.1 为什么需要评估

RAG 系统涉及多环节（检索、生成），需要**量化指标**来判断调参效果、定位问题、避免凭感觉优化。本项目设计了**双重评估体系**：检索评估 + 答案质量评估。

### 7.2 检索评估（Retrieval Evaluation）

#### 评估指标

| 指标 | 含义 | 解读 |
|------|------|------|
| **Recall@K** | 期望条文被召回的比例 | 检索的**完整性** |
| **Hit@K** | 至少命中一条期望条文的题目比例 | 检索的**有效性** |
| **MRR** | 首个命中条文排名的倒数 | 检索的**精度**（是否靠前） |

#### 评估集设计

```json
{
    "question": "诉讼时效一般是多少年？",
    "expected_articles": [
        {"law_name": "中华人民共和国民法典", "article_no": 188}
    ]
}
```
- 100 题，覆盖 37 部法律，每题标注期望召回的条文

#### 本项目当前指标

```
Recall@8 ≈ 0.975   （97.5% 的期望条文被召回）
Hit@8    = 1.000   （每道题都至少召回一条正确条文）
MRR      ≈ 0.866   （正确条文平均排在第 1-2 位）
```

### 7.3 答案质量评估（LLM-as-judge）

#### 为什么检索好不等于答得好

检索召回了正确条文，但 LLM 可能理解错误、引用不规范、答非所问，需单独评估**答案质量**。

#### LLM-as-judge 方法

用一个**裁判模型**对生成答案打分（1-5 分），四个维度：

| 维度 | 含义 |
|------|------|
| **准确性** | 答案是否符合法律规定 |
| **忠于检索** | 是否基于检索结果，无幻觉 |
| **引用规范** | 是否正确引用《法律名》第X条 |
| **表达清晰** | 是否通俗易懂 |

#### 负样本测试

评估集含**无关问题**（如"今天天气"），考察系统是否**正确拒答**，而非强行编造。

#### 执行命令

```bash
python -m eval.eval_answer              # 评估全部题目
python -m eval.eval_answer --limit 3    # 只评前3题（省配额）
python -m eval.eval_answer --save out.json  # 落盘明细
```

### 7.4 反馈难例闭环

```
用户提问 → AI 回答 → 用户点 👍/👎
                          ↓
              落盘到 data/feedback.jsonl
                          ↓
        筛选 👎 / 引用告警的题目作为难例
                          ↓
        回灌到 eval_set.json / answer_set.json
                          ↓
              定向修补检索/生成质量
```

**反馈日志格式**：
```json
{
    "ts": "2026-06-15T10:30:00",
    "question": "用户问题",
    "rewrite": "改写后的查询",
    "liked": false,
    "answer": "AI 回答",
    "refs": [{"law": "民法典", "no": 188}],
    "verify_status": "warn"
}
```

**价值**：持续收集真实难例，数据驱动改进，形成"上线→反馈→优化"正向循环。

---

## 8. 总结与思考

### 8.1 RAG 系统的核心要点

```
┌─────────────────────────────────────────────────┐
│                   RAG 系统全景                      │
├─────────────────────────────────────────────────┤
│  数据层：文档解析 → 结构化 → 分块（Chunking）        │
│  索引层：Embedding + 向量库 + BM25 索引             │
│  检索层：混合检索 + RRF 融合 + 相关性闸门 + Rerank   │
│  生成层：查询改写 + Prompt 工程 + LLM + 故障转移      │
│  校验层：引用校验 + 免责声明                          │
│  评估层：检索评估 + 答案评估 + 反馈闭环               │
└─────────────────────────────────────────────────┘
```

### 8.2 本项目的设计亮点

1. **混合检索 + RRF 融合**：向量（语义）+ BM25（精确）取长补短，RRF 无需归一化
2. **相关性闸门**：用距离阈值拦截无关问题，从源头避免幻觉
3. **引用校验**：自动验证 LLM 引用的真实性，跨法律不串号
4. **异构故障转移**：跨供应商多档兜底，解决免费 API 配额限制
5. **多层缓存**：Query embedding 缓存省配额，BM25 分词缓存加速启动
6. **双重评估 + 反馈闭环**：检索和生成分别量化，数据驱动持续优化

### 8.3 RAG 的通用优化方向

**检索质量优化**：
| 方向 | 方法 |
|------|------|
| 分块策略 | 按语义/结构分块，控制块大小，重叠分块 |
| 检索方式 | 混合检索、多路召回、查询扩展 |
| 重排序 | Cross-Encoder 精排（长文档场景） |
| 元数据过滤 | 按时间、类别等结构化字段过滤 |

**生成质量优化**：
| 方向 | 方法 |
|------|------|
| Prompt 工程 | 明确指令、Few-shot 示例、思维链 |
| 上下文管理 | 控制 Top-K、去重、排序 |
| 幻觉抑制 | 引用校验、相关性闸门、低 temperature |
| 多轮对话 | 查询改写、历史管理 |

**工程优化**：
| 方向 | 方法 |
|------|------|
| 性能 | 流式输出、缓存、批处理 |
| 可用性 | 故障转移、降级处理、超时控制 |
| 可观测 | 评估指标、日志、反馈收集 |
| 成本 | 缓存复用、合理 Top-K、模型选型 |

### 8.4 RAG vs 微调（Fine-tuning）

| 对比维度 | RAG | 微调 |
|----------|-----|------|
| 知识更新 | 更新知识库即可 | 需重新训练 |
| 可追溯性 | 强（能指向来源） | 弱（黑盒） |
| 幻觉控制 | 强（基于真实文档） | 较弱 |
| 成本 | 低（无需训练） | 高（GPU + 数据） |
| 适用场景 | 知识密集型问答 | 风格/格式定制 |

**结论**：对于**法律、医疗、金融**等知识密集、需要可追溯的领域，RAG 是更优选择。两者也可结合（微调模型 + RAG 检索）。

### 8.5 学习建议

1. **理解核心概念**：Embedding、向量检索、相似度度量是基础
2. **动手实践**：从最简单的"向量检索 + LLM"开始，逐步加入混合检索、Rerank、评估
3. **重视评估**：没有量化指标的优化是盲目的
4. **关注工程**：生产级 RAG 不只是算法，还有缓存、故障转移、流式等工程细节
5. **数据闭环**：收集真实反馈，持续迭代

---

## 附录：本项目文件结构对照

| 模块 | 文件 | 核心职责 |
|------|------|----------|
| 配置 | `src/config.py` | 集中管理参数、密钥、故障转移链 |
| 解析 | `src/parser.py` | Markdown → 结构化 LawArticle |
| 目录 | `src/law_catalog.py` | 定义接入哪些法律 |
| Embedding | `src/embedding.py` | 可切换的向量化客户端 |
| 缓存 | `src/embed_cache.py` | Query embedding 磁盘缓存 |
| 关键词检索 | `src/bm25_retriever.py` | jieba + BM25 检索 |
| 精排 | `src/reranker.py` | Cross-Encoder 重排序（可选） |
| 向量库 | `src/vector_store.py` | ChromaDB + 混合检索 + RRF |
| 问答链 | `src/rag.py` | 检索 + 改写 + 生成 + 校验 |
| Web | `src/web.py` | Gradio 界面 |
| 入口 | `main.py` / `app.py` | 本地 / 云部署入口 |
| 评估 | `eval/` | 检索评估 + 答案评估 |

---

> 本文档基于「中国法律助手 RAG 系统」项目整理，旨在系统梳理 RAG 技术的完整知识体系。
>
> 文档完成时间：2026-06-15
