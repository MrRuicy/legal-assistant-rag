/* ============================================================
   api/chat.ts — 流式对话接口 + 示例/配置拉取
   统一走 /api 相对路径（dev 由 Vite proxy 转发，prod 由 Nginx/同源托管）
   ============================================================ */

import type { ChatRequest, ExamplesResponse, ClientConfig } from '@/types/api'
import type { Chunk, ChatMode } from '@/types/chat'

const ENDPOINTS: Record<ChatMode, string> = {
  single: '/api/chat',
  agent: '/api/chat/agent',
}

/**
 * 流式对话。返回一个异步生成器，逐个 yield 解析后的 chunk。
 * 调用方用 `for await (const chunk of streamChat(...))` 消费。
 *
 * @param req     请求体
 * @param mode    'single' | 'agent'
 * @param signal  AbortSignal，用于中断流
 */
export async function* streamChat(
  req: ChatRequest,
  mode: ChatMode,
  signal?: AbortSignal,
): AsyncGenerator<Chunk> {
  const resp = await fetch(ENDPOINTS[mode], {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
    signal,
  })

  if (!resp.ok) {
    const text = await resp.text().catch(() => '')
    throw new Error(`请求失败 (${resp.status}): ${text || resp.statusText}`)
  }
  if (!resp.body) {
    throw new Error('响应没有可读流（body 为空）')
  }

  const reader = resp.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })

      // SSE 事件以 \n\n 分隔；按完整事件切分，残段留在 buffer
      const events = buffer.split('\n\n')
      buffer = events.pop() ?? ''

      for (const evt of events) {
        const line = evt.trim()
        if (!line.startsWith('data:')) continue
        const payload = line.slice(5).trim()
        if (!payload) continue
        try {
          yield JSON.parse(payload) as Chunk
        } catch {
          // 跨 chunk 的不完整 JSON：理论上不会发生（已按 \n\n 切分），忽略
        }
      }
    }

    // 冲洗 buffer 中可能残留的最后一个事件
    const tail = buffer.trim()
    if (tail.startsWith('data:')) {
      const payload = tail.slice(5).trim()
      if (payload) {
        try {
          yield JSON.parse(payload) as Chunk
        } catch {
          /* 忽略残缺尾段 */
        }
      }
    }
  } finally {
    reader.releaseLock()
  }
}

/** 获取随机示例问题（空状态 chips） */
export async function getExamples(n = 6): Promise<string[]> {
  const resp = await fetch(`/api/examples?n=${n}`)
  if (!resp.ok) return []
  const data = (await resp.json()) as ExamplesResponse
  return data.examples ?? []
}

/** 获取前端配置（深度模式默认值、标题等） */
export async function getClientConfig(): Promise<ClientConfig | null> {
  try {
    const resp = await fetch('/api/config')
    if (!resp.ok) return null
    return (await resp.json()) as ClientConfig
  } catch {
    return null
  }
}
