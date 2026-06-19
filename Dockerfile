# 多阶段构建：阶段一用 Node 构建 Vue 前端，阶段二 Python 运行后端 + 托管 dist。
# 这样无论本地是否预构建 dist，创空间从仓库构建都能产出完整前端。

# ---- 阶段一：构建前端 ----
FROM node:20-slim AS frontend
WORKDIR /web
COPY web/package*.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

# ---- 阶段二：Python 后端 ----
FROM python:3.10-slim
WORKDIR /app

# 仅装运行依赖（利用缓存：requirements 不变则不重装）
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 拷贝后端代码与预构建向量库（vector_store/ 和 data/processed 随仓库提交）
COPY api.py ./
COPY src/ ./src/
COPY scripts/ ./scripts/
COPY data/ ./data/
COPY vector_store/ ./vector_store/

# 从阶段一拷入前端构建产物
COPY --from=frontend /web/dist ./web/dist

# 创空间约定端口 7860
ENV PORT=7860
EXPOSE 7860

CMD ["python", "api.py"]
