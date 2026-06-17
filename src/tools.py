"""Agent 工具集：法条交叉引用、时效计算等专用工具，让 Agent 会用工具而非只会检索。

Phase 3 扩展：这些工具在 Reflect 节点判断需要时被调用，补全缺失的关联信息。
同时包含 Agent 节点需要的辅助函数（RetrieveTool、merge_dedup_hits 等）。
"""
import re
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from .vector_store import VectorStore


# ---- Agent 节点辅助工具（检索、去重、格式化）----

class RetrieveTool:
    """检索工具：封装 VectorStore 的混合检索，供 Retrieve 节点调用。"""

    def __init__(self, vector_store: VectorStore):
        self.vector_store = vector_store

    def search(self, query: str, top_k: int = 8) -> List[Dict]:
        """执行混合检索（向量 + BM25 + RRF），返回条文列表。

        Returns:
            [{"law": "劳动合同法", "article": "47", "content": "...", ...}]
        """
        return self.vector_store._hybrid_search(query, top_k=top_k)


def merge_dedup_hits(hit_lists: List[List[Dict]]) -> List[Dict]:
    """合并多次检索结果并去重（按 law_name#article_no 去重，保留首次出现）。

    Args:
        hit_lists: 多次检索的结果列表，如 [[hit1, hit2], [hit3, hit1], ...]

    Returns:
        去重后的 hits，保持首次出现顺序
    """
    seen = set()
    merged = []
    for hits in hit_lists:
        for h in hits:
            key = f"{h.get('law_name', '')}#{h.get('article_no', '')}"
            if key not in seen:
                seen.add(key)
                merged.append(h)
    return merged


def format_articles_context(hits: List[Dict]) -> str:
    """将条文列表格式化为 LLM 上下文（Answer 节点用）。

    格式：《法律名》第X条：【条文全文】
    """
    if not hits:
        return ""
    lines = []
    for h in hits:
        law = h.get("law_name", "未知法律")
        article = h.get("article_no", "?")
        content = h.get("article_text", "")
        lines.append(f"《{law}》第{article}条：\n{content}\n")
    return "\n".join(lines)


def decompose_query(question: str) -> List[str]:
    """查询分解：将复杂问题拆成子问题（Planner 节点的简化版占位实现）。

    实际由 Planner 节点用 LLM 完成，这里只是占位（万一需要规则兜底）。
    """
    # 占位实现：按"、"/"？"切分，或返回原问题
    parts = [p.strip() for p in re.split(r'[、？?]', question) if p.strip()]
    return parts if len(parts) > 1 else [question]


def _parse_str_list(text: str) -> List[str]:
    """从 LLM 输出解析字符串列表（Planner/Reflect 节点用，容忍各种格式）。

    支持格式：
    - JSON 数组: ["sub1", "sub2"]
    - 换行列表: "- sub1\n- sub2"
    - 逗号分隔: "sub1, sub2, sub3"
    """
    text = text.strip()
    # 尝试 JSON
    if text.startswith("["):
        try:
            import json
            return [s.strip() for s in json.loads(text) if isinstance(s, str) and s.strip()]
        except Exception:
            pass
    # 尝试换行列表（"- xxx" 或 "1. xxx"）
    if "\n" in text:
        lines = text.split("\n")
        result = []
        for line in lines:
            line = line.strip()
            # 去掉列表标记
            line = re.sub(r'^[-*•]\s*', '', line)
            line = re.sub(r'^\d+[.)]\s*', '', line)
            if line:
                result.append(line)
        if result:
            return result
    # 尝试逗号分隔
    if "," in text or "，" in text:
        return [s.strip() for s in re.split(r'[,，]', text) if s.strip()]
    # 兜底：返回原文（单个子问题）
    return [text] if text else []


# ---- Phase 3 专用工具（交叉引用 / 时效计算）----

class LegalTools:
    """法律问答专用工具集，供 Agent 调用。"""

    def __init__(self, vector_store: VectorStore):
        self.vector_store = vector_store
        # 懒加载：首次调用交叉引用工具时才构建引用图（避免启动慢）
        self._reference_graph: Optional[Dict[str, List[Dict]]] = None

    def lookup_referenced_articles(self, article_id: str, max_depth: int = 1) -> List[Dict]:
        """法条交叉引用查询：给定一条法条，返回它直接引用的其他条文。

        用例：Agent 看到"依照本法第47条"但第47条不在上下文 → 调此工具补全。

        Args:
            article_id: 法条 ID，格式 "法律名#条号"（如 "劳动合同法#47"）
            max_depth: 引用深度（1=仅直接引用，2=引用的引用，...）默认1避免爆炸

        Returns:
            被引用条文列表 [{"law":"劳动合同法", "article":"47", "content":"..."}]
            空列表表示该条文不引用其他条文或引用图未建立。
        """
        if self._reference_graph is None:
            self._build_reference_graph()

        result = []
        visited = set()
        queue = [(article_id, 0)]  # (id, 当前深度)

        while queue:
            current_id, depth = queue.pop(0)
            if current_id in visited or depth >= max_depth:
                continue
            visited.add(current_id)

            refs = self._reference_graph.get(current_id, [])
            for ref in refs:
                ref_id = f"{ref['law']}#{ref['article']}"
                if ref_id not in visited:
                    result.append(ref)
                    if depth + 1 < max_depth:
                        queue.append((ref_id, depth + 1))

        return result

    def _build_reference_graph(self) -> None:
        """构建法条引用图：解析每条法条内容，提取"第X条"/"本法第Y条"等引用模式。

        引用模式示例：
        - "依照本法第四十七条" → 同法第47条
        - "适用《民法典》第一千零三十四条" → 民法典#1034
        - "按照第二百零三条执行" → 同法第203条（需上下文推断法律名）

        存入 self._reference_graph = {"劳动合同法#48": [{"law":"劳动合同法","article":"47","content":"..."}]}
        """
        self._reference_graph = {}
        all_articles = self.vector_store.collection.get(include=["metadatas", "documents"])
        if not all_articles or not all_articles.get("ids"):
            return

        # 构建 ID → 文档映射，用于反查被引用条文的内容
        id_to_doc = {}
        for i, doc_id in enumerate(all_articles["ids"]):
            meta = all_articles["metadatas"][i]
            content = all_articles["documents"][i]
            id_to_doc[doc_id] = {
                "law_name": meta.get("law_name", ""),
                "article_no": meta.get("article_no", ""),
                "article_text": content
            }

        # 解析每条法条，提取引用
        for doc_id, doc in id_to_doc.items():
            content = doc["article_text"]
            law = doc["law_name"]
            refs = []

            # 模式1：同法引用 "第X条"（中文数字）
            for match in re.finditer(r"第([一二三四五六七八九十百千零]+)条", content):
                article_cn = match.group(1)
                try:
                    from .parser import chinese_to_arabic
                    article_num = str(chinese_to_arabic(article_cn))
                    ref_id = f"{law}#{article_num}"
                    if ref_id in id_to_doc and ref_id != doc_id:
                        refs.append(id_to_doc[ref_id])
                except Exception:
                    pass  # 解析失败忽略

            # 模式2：跨法引用 "《XXX》第Y条"（简化：只匹配书名号+第X条，实际可更复杂）
            for match in re.finditer(r"《([^》]+)》第([一二三四五六七八九十百千零]+)条", content):
                ref_law = match.group(1)
                article_cn = match.group(2)
                try:
                    from .parser import chinese_to_arabic
                    article_num = str(chinese_to_arabic(article_cn))
                    ref_id = f"{ref_law}#{article_num}"
                    if ref_id in id_to_doc:
                        refs.append(id_to_doc[ref_id])
                except Exception:
                    pass

            if refs:
                self._reference_graph[doc_id] = refs

    def calculate_statute_of_limitations(
        self, case_type: str, incident_date: str, query_date: Optional[str] = None
    ) -> Dict:
        """诉讼/仲裁时效计算工具：判断某事件是否已过时效。

        用例：用户问"2020年被辞退现在还能仲裁吗" → Agent 调此工具获取时效判断。

        Args:
            case_type: 案件类型，可选值 "labor"(劳动争议)/"civil"(民事)/"criminal"(刑事)
            incident_date: 权利被侵害日期，格式 "YYYY-MM-DD"（如 "2020-03-15"）
            query_date: 查询日期（默认今天），格式同上

        Returns:
            {
                "limitation_years": 时效年限（如 1 / 3 / 20）,
                "deadline": 时效截止日 "YYYY-MM-DD",
                "is_expired": 是否已过期 (bool),
                "days_remaining": 剩余天数（负数=已过期N天）,
                "legal_basis": 依据条文（如 "《劳动争议调解仲裁法》第27条"）,
                "note": 补充说明（如"从知道或应当知道权利被侵害之日起算"）
            }
        """
        # 时效规则表（实际应从法条库提取，这里硬编码常见规则作演示）
        rules = {
            "labor": {
                "years": 1,
                "basis": "《劳动争议调解仲裁法》第27条",
                "note": "劳动争议申请仲裁的时效期间为一年，从当事人知道或者应当知道其权利被侵害之日起计算。",
            },
            "civil": {
                "years": 3,
                "basis": "《民法典》第188条",
                "note": "向人民法院请求保护民事权利的诉讼时效期间为三年。",
            },
            "criminal": {
                "years": 20,
                "basis": "《刑法》第87条",
                "note": "犯罪经过下列期限不再追诉：法定最高刑为无期徒刑、死刑的，经过二十年（此处简化为最长追诉期）。",
            },
        }

        rule = rules.get(case_type.lower())
        if not rule:
            return {
                "error": f"不支持的案件类型: {case_type}，可选值: labor/civil/criminal",
            }

        try:
            incident_dt = datetime.strptime(incident_date, "%Y-%m-%d")
            query_dt = datetime.strptime(query_date, "%Y-%m-%d") if query_date else datetime.now()
            deadline_dt = incident_dt + timedelta(days=rule["years"] * 365)
            days_remaining = (deadline_dt - query_dt).days

            return {
                "limitation_years": rule["years"],
                "deadline": deadline_dt.strftime("%Y-%m-%d"),
                "is_expired": days_remaining < 0,
                "days_remaining": days_remaining,
                "legal_basis": rule["basis"],
                "note": rule["note"],
            }
        except ValueError as e:
            return {"error": f"日期格式错误: {e}，请使用 YYYY-MM-DD 格式"}


# 全局单例（避免重复构建引用图）
_tools_instance: Optional[LegalTools] = None


def get_legal_tools(vector_store: VectorStore) -> LegalTools:
    """获取工具集单例（Web 服务端复用，避免重复构建引用图）。"""
    global _tools_instance
    if _tools_instance is None:
        _tools_instance = LegalTools(vector_store)
    return _tools_instance
