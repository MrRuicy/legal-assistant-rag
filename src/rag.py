"""RAG 问答链：检索 + LLM 生成（强制条文引用与免责）。"""
import re
from typing import List, Dict
from openai import OpenAI

from . import config
from .vector_store import VectorStore
from .parser import chinese_to_arabic


class LegalRAG:
    def __init__(self):
        self.vector_store = VectorStore()
        self.llm_client = OpenAI(
            api_key=config.MODELSCOPE_API_KEY,
            base_url=config.MODELSCOPE_BASE_URL,
        )

    @staticmethod
    def _is_quota_error(e: Exception) -> bool:
        """判断异常是否为配额超限/限流（429），用于触发模型故障转移。"""
        if getattr(e, "status_code", None) == 429:
            return True
        msg = str(e).lower()
        return "429" in msg or "quota" in msg or "rate limit" in msg

    def _complete(self, messages: List[Dict], temperature: float = 0.1) -> str:
        """非流式调用，按 config.LLM_MODELS 优先级故障转移（配额超限自动换下一个）。

        所有模型都配额超限时抛出最后一个异常，交由调用方处理。
        """
        last_err = None
        for model in config.LLM_MODELS:
            try:
                resp = self.llm_client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    stream=False,
                )
                return resp.choices[0].message.content
            except Exception as e:
                if self._is_quota_error(e):
                    last_err = e
                    continue  # 配额超限，换下一个模型
                raise  # 其他错误（网络/参数等）直接抛出
        raise last_err if last_err else RuntimeError("无可用模型")

    def _stream_complete(self, messages: List[Dict], temperature: float = 0.1):
        """流式调用，按 config.LLM_MODELS 优先级故障转移。

        仅在「尚未产出任何 token」时才切换模型，避免向用户重复输出。
        一旦开始产出内容后再报错，则直接抛出（无法干净重试）。
        所有模型都配额超限时抛出最后一个异常。
        """
        last_err = None
        for model in config.LLM_MODELS:
            produced = False
            try:
                stream = self.llm_client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    stream=True,
                )
                for chunk in stream:
                    delta = chunk.choices[0].delta
                    if delta.content:
                        produced = True
                        yield delta.content
                return  # 正常流式完成
            except Exception as e:
                if produced:
                    raise  # 已输出部分内容，不能重试
                if self._is_quota_error(e):
                    last_err = e
                    continue  # 配额超限且尚未输出，换下一个模型
                raise
        raise last_err if last_err else RuntimeError("无可用模型")

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

        # 3. 调用 LLM（按优先级故障转移）
        answer_text = self._complete(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,  # 降低随机性，提高准确性
        )

        return {
            "answer": answer_text,
            "references": hits,
            "disclaimer": self._disclaimer(),
        }

    def answer_stream(self, question: str, history: List[Dict] = None, top_k: int = None):
        """流式回答法律问题（generator，逐 token yield）。

        Args:
            question: 用户当前问题
            history: 对话历史 [{"role": "user"/"assistant", "content": ...}, ...]，
                     用于把追问改写成独立问题并让回答连贯。
            top_k: 检索条数

        Yields:
            Dict，每个 chunk:
            {
                "type": "references" | "answer" | "disclaimer" | "error" | "rewrite",
                "content": ...
            }
        """
        # 0. 有历史时，把追问改写成独立完整的问题（解决指代/省略导致检索失败）
        search_query = self._rewrite_query(question, history)
        if search_query != question:
            yield {"type": "rewrite", "content": search_query}

        # 1. 用改写后的问题检索相关条文（embedding API 失败时友好降级）
        try:
            hits = self.vector_store.search(search_query, top_k=top_k)
        except Exception as e:
            yield {"type": "references", "content": []}
            yield {"type": "error", "content": f"检索服务暂时不可用：{str(e)}"}
            return

        # 先 yield 检索结果
        yield {"type": "references", "content": hits}

        if not hits:
            yield {
                "type": "answer",
                "content": "未找到相关法律条文，无法回答该问题。",
            }
            yield {"type": "disclaimer", "content": self._disclaimer()}
            return

        # 2. 构造 prompt
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

        # 把最近的历史对话纳入 messages，让追问的回答能承接上文
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(self._recent_history_messages(history))
        messages.append({"role": "user", "content": user_prompt})

        # 3. 流式调用 LLM（按优先级故障转移，用户无感知）
        answer_parts = []
        try:
            for piece in self._stream_complete(messages, temperature=0.1):
                answer_parts.append(piece)
                yield {"type": "answer", "content": piece}
        except Exception as e:
            if self._is_quota_error(e):
                yield {"type": "error", "content": "所有模型今日配额均已用尽，请稍后再试或明日重试。"}
            else:
                yield {"type": "error", "content": f"LLM 调用失败：{str(e)}"}
            return

        # 3.5 引用校验：检查回答引用的条号是否都在检索结果中（防编造）
        verify = self._verify_citations("".join(answer_parts), hits)
        yield {"type": "verify", "content": verify}

        # 4. 最后 yield 免责声明
        yield {"type": "disclaimer", "content": self._disclaimer()}

    def _verify_citations(self, answer_text: str, hits: List[Dict]) -> Dict:
        """校验回答中引用的条号是否都在检索到的条文里。

        返回结构化结果，供前端醒目展示：
            {
                "status": "ok" | "warn" | "none",
                "cited": [条号...],        # 回答中引用的条号
                "fabricated": [条号...],   # 疑似编造（不在检索结果中）的条号
                "message": str,            # 给用户看的提示文本
            }
        只做提示不阻断——LLM 偶尔会引用相关但未检索到的条文，标注出来交用户判断。
        """
        cited = sorted(self._extract_cited_articles(answer_text))
        if not cited:
            return {
                "status": "none",
                "cited": [],
                "fabricated": [],
                "message": "本回答未显式引用条文编号。",
            }

        retrieved = {h["article_no"] for h in hits}
        fabricated = sorted(set(cited) - retrieved)
        if fabricated:
            nos = "、".join(f"第{n}条" for n in fabricated)
            return {
                "status": "warn",
                "cited": cited,
                "fabricated": fabricated,
                "message": (
                    f"引用的 {nos} 不在本次检索到的条文范围内，可能存在偏差，"
                    f"请以《民法典》原文为准并核实。"
                ),
            }
        nos = "、".join(f"第{n}条" for n in cited)
        return {
            "status": "ok",
            "cited": cited,
            "fabricated": [],
            "message": f"回答引用的 {nos} 均来自本次检索到的条文，可追溯。",
        }

    @staticmethod
    def _extract_cited_articles(text: str) -> set:
        """从回答文本提取引用的条号（支持"第188条""第一百八十八条"两种写法）。"""
        cited = set()
        # 阿拉伯数字：第188条
        for m in re.findall(r"第\s*(\d+)\s*条", text):
            cited.add(int(m))
        # 中文数字：第一百八十八条
        for m in re.findall(r"第([一二三四五六七八九十百千零]+)条", text):
            try:
                cited.add(chinese_to_arabic(m))
            except Exception:
                pass
        return cited

    def _rewrite_query(self, question: str, history: List[Dict] = None) -> str:
        """把依赖上文的追问改写成独立、完整的问题（用于检索）。

        无历史时直接返回原问题（省一次 API 调用）。改写失败时降级为原问题。
        """
        if not history:
            return question

        # 取最近 3 轮，助手回答截断（去掉免责声明等噪声），保留主题信息
        convo_lines = []
        for m in history[-6:]:
            role = "用户" if m.get("role") == "user" else "助手"
            content = self._extract_text(m.get("content")).split("\n\n---")[0][:150]
            if content:
                convo_lines.append(f"{role}：{content}")
        convo_text = "\n".join(convo_lines)

        prompt = f"""下面是用户与法律助手的对话历史：
{convo_text}

用户最新的问题是：{question}

请把这个最新问题改写成一个独立、完整、不依赖上下文的问题，用于检索《民法典》条文。
只输出改写后的问题本身，不要任何解释、引号或前缀。若问题本身已完整，原样输出。"""

        try:
            rewritten = self._complete(
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
            )
            return rewritten.strip() or question
        except Exception:
            return question  # 改写失败则退回原问题，不阻断主流程

    def _recent_history_messages(self, history: List[Dict] = None) -> List[Dict]:
        """把最近的历史整理成干净的 messages（助手回答去掉免责声明）。"""
        if not history:
            return []
        msgs = []
        for m in history[-6:]:
            role = m.get("role")
            content = self._extract_text(m.get("content")).split("\n\n---")[0].strip()
            if role in ("user", "assistant") and content:
                msgs.append({"role": role, "content": content})
        return msgs

    @staticmethod
    def _extract_text(content) -> str:
        """安全提取消息文本。

        Gradio Chatbot 在 messages 格式下，content 可能是 str，也可能是
        list/tuple（富文本/文件等结构）。统一转成纯文本，避免对非字符串调用 split。
        """
        if content is None:
            return ""
        if isinstance(content, str):
            return content
        if isinstance(content, (list, tuple)):
            parts = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    # 常见结构如 {"text": ...} 或 gradio 的文件/组件字典
                    parts.append(str(item.get("text", "")))
            return " ".join(p for p in parts if p)
        if isinstance(content, dict):
            return str(content.get("text", ""))
        return str(content)

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
