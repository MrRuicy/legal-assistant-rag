/* ============================================================
   api.ts — 请求体 / 响应体类型，对齐 api.py 的 Pydantic 模型
   ============================================================ */

import type { Reference } from './chat'

/** POST /api/chat | /api/chat/agent 请求体 */
export interface ChatRequest {
  question: string
  history?: { role: string; content: string }[]
  top_k?: number
}

/** POST /api/feedback 请求体 */
export interface FeedbackRequest {
  question: string
  answer: string
  liked: boolean
  rewrite?: string
  refs?: Reference[]
  verify_status?: string
}

/** GET /api/examples 响应体 */
export interface ExamplesResponse {
  examples: string[]
}

/** GET /api/config 响应体 */
export interface ClientConfig {
  agent_mode_default: boolean
  app_title: string
  app_subtitle: string
}
