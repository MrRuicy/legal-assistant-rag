"""RAG 问答链：检索 + LLM 生成（强制条文引用与免责）。"""
from typing import List, Dict
from openai import OpenAI

from . import config
from .vector_store import VectorStore


class LegalRAG:
    def __init__(self):
        self.vector_store = VectorStore()
        self.llm_client = OpenAI(
            api_key=config.MODELSCOPE_API_KEY,
            base_url=config.MODELSCOPE_BASE_URL,
        )

    def answer(self, question: str, top_k: int = None) -> Dict:
        """回答法律问题：检索相关条文 → LLM 生成答案（必须引用条文）。"""
        # 1. 检索相关条文
        hits = self.vector_store.search(question, top_k=top_k)

        if not hits:
            return {
                "answer": "未找到相关法律条文，无法回答该问题。",
                "references": [],
                "disclaimer": self._disclaimer(),
            }

        # 2. 构造 prompt（强制引用、禁止幻觉）
        context = self._build_context(hits)
        system_prompt = """你是一个严谨的法律助手，专门解答《中华人民共和国民法典》相关问题。

**严格要求：**
1. 答案必须基于检索到的条文，逐条引用"《民法典》第X条"。
2. 如果检索结果与问题无关，明确回答"未找到相关条文"。
3. 不得编造、推测或引用检索结果外的条文。
4. 用通俗易懂的语言解释法律条文，但保持准确性。
5. 回答结尾必须包含"以上内容仅供参考，不构成法律建议"。"""

        user_prompt = f"""问题：{question}

检索到的相关条文：
{context}

请根据上述条文回答问题，逐条引用条文编号。"""

        # 3. 调用 LLM
        response = self.llm_client.chat.completions.create(
            model=config.LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,  # 降低随机性，提高准确性
        )

        answer_text = response.choices[0].message.content

        return {
            "answer": answer_text,
            "references": hits,
            "disclaimer": self._disclaimer(),
        }

    def _build_context(self, hits: List[Dict]) -> str:
        """将检索结果格式化为 prompt 上下文。"""
        lines = []
        for i, h in enumerate(hits, 1):
            lines.append(
                f"{i}. 《民法典》第{h['article_no']}条（{h['part']} {h['chapter']}）\n"
                f"   {h['article_text']}"
            )
        return "\n\n".join(lines)

    def _disclaimer(self) -> str:
        return (
            "⚠️ 免责声明：本回答由 AI 根据《中华人民共和国民法典》条文生成，"
            "仅供参考，不构成法律建议。如需专业法律意见，请咨询执业律师。"
        )


if __name__ == "__main__":
    # 测试
    rag = LegalRAG()
    result = rag.answer("父母是否有义务赡养成年子女？")
    print("问题:", "父母是否有义务赡养成年子女？")
    print("\n答案:\n", result["answer"])
    print("\n引用条文:")
    for ref in result["references"]:
        print(f"  - 第{ref['article_no']}条: {ref['article_text'][:50]}...")
    print("\n", result["disclaimer"])
