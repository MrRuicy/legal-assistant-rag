/* ============================================================
   composables/useChat.ts — 核心流式对话逻辑
   统一单跳 / Agent 入口，消费 streamChat 的 chunk 并更新消息状态。
   ============================================================ */

import { ref } from 'vue'
import { storeToRefs } from 'pinia'
import { streamChat } from '@/api/chat'
import type {
  Message,
  Reference,
  TraceStep,
  VerifyResult,
  ChatMode,
} from '@/types/chat'
import { useSessionsStore } from '@/stores/sessions'
import { useSettingsStore } from '@/stores/settings'

function uid(): string {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
}

/** 模式对应的等待状态文案 */
const STATUS_LABELS: Record<ChatMode, string> = {
  single: '正在检索条文…',
  agent: '正在规划检索路径…',
}

export function useChat() {
  const sessions = useSessionsStore()
  const settings = useSettingsStore()
  const { agentMode, topK } = storeToRefs(settings)

  const isStreaming = ref(false)
  let controller: AbortController | null = null

  /** 中断当前流 */
  function stop() {
    controller?.abort()
    controller = null
    isStreaming.value = false
  }

  /**
   * 发送一条消息并流式接收回答。
   * 立即插入 [用户消息 + 空 AI 消息(pending)]，随 chunk 更新 AI 消息。
   */
  async function sendMessage(question: string) {
    const q = question.trim()
    if (!q || isStreaming.value) return

    const mode: ChatMode = agentMode.value ? 'agent' : 'single'

    // 构造历史（只取已完成的消息，role+content）
    const history = sessions.messages
      .filter((m) => m.status !== 'error')
      .map((m) => ({ role: m.role, content: m.content }))

    // 1. 插入用户消息
    sessions.appendMessage({
      id: uid(),
      role: 'user',
      content: q,
      status: 'done',
    })

    // 2. 插入空 AI 消息
    const ai = sessions.appendMessage({
      id: uid(),
      role: 'assistant',
      content: '',
      status: 'pending',
      mode,
      refs: [],
      trace: [],
      statusLabel: STATUS_LABELS[mode],
    })

    isStreaming.value = true
    controller = new AbortController()
    let firstAnswerChunk = true

    try {
      for await (const chunk of streamChat(
        { question: q, history, top_k: topK.value ?? undefined },
        mode,
        controller.signal,
      )) {
        applyChunk(ai, chunk, () => {
          if (firstAnswerChunk) {
            ai.status = 'streaming'
            ai.statusLabel = undefined
            firstAnswerChunk = false
          }
        })
        sessions.touch()
      }
      ai.status = ai.status === 'error' ? 'error' : 'done'
    } catch (err) {
      if ((err as Error).name === 'AbortError') {
        ai.status = 'done'
        ai.statusLabel = undefined
        if (!ai.content) ai.content = '_（已停止生成）_'
      } else {
        ai.status = 'error'
        ai.statusLabel = undefined
        ai.content = ai.content || `连接失败：${(err as Error).message}`
      }
    } finally {
      isStreaming.value = false
      controller = null
      sessions.touch()
    }
  }

  return { isStreaming, sendMessage, stop }
}

/** 把单个 chunk 应用到 AI 消息上 */
function applyChunk(ai: Message, chunk: { type: string; content: unknown }, onAnswer: () => void) {
  switch (chunk.type) {
    case 'rewrite':
      ai.rewrite = chunk.content as string
      break
    case 'references':
      ai.refs = chunk.content as Reference[]
      // Agent 模式 references 出现时更新状态文案
      if (ai.status === 'pending') ai.statusLabel = '正在生成答案…'
      break
    case 'answer':
      onAnswer()
      // 单跳：逐 token 追加；Agent：整段（一次性给）也兼容
      ai.content += chunk.content as string
      break
    case 'trace':
      ai.trace = chunk.content as TraceStep[]
      ai.statusLabel = traceStatusLabel(ai.trace)
      break
    case 'verify':
      ai.verify = chunk.content as VerifyResult
      break
    case 'disclaimer':
      ai.disclaimer = chunk.content as string
      break
    case 'error':
      ai.status = 'error'
      ai.statusLabel = undefined
      ai.content = ai.content || (chunk.content as string)
      break
  }
}

/** 根据最新 trace 节点推导状态文案 */
function traceStatusLabel(trace: TraceStep[]): string {
  const last = trace[trace.length - 1]
  if (!last) return '正在推理…'
  switch (last.node) {
    case 'planner':
      return last.is_complex
        ? `已拆解为 ${last.subs?.length ?? 0} 个子问题，开始检索…`
        : '正在检索条文…'
    case 'retrieve':
      return `已累积 ${last.n_hits_total ?? 0} 条，正在反思…`
    case 'reflect':
      return last.decision === 'continue' ? '需补充检索，继续…' : '正在生成答案…'
    case 'answer':
      return '正在生成答案…'
    default:
      return '正在推理…'
  }
}
