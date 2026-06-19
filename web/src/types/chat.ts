/* ============================================================
   chat.ts — 对话领域类型，严格对齐后端 SSE chunk 契约
   ============================================================ */

/** 检索到的单条法律条文（对齐 vector_store hits 字段） */
export interface Reference {
  article_no: number | string
  sub_no?: number
  law_name: string
  part?: string
  chapter?: string
  section?: string
  article_text: string
  effective_date?: string
  distance?: number | null
  rerank_score?: number | null
}

/** 引用校验结果 */
export interface VerifyResult {
  status: 'ok' | 'warn' | 'none'
  cited: string[]
  fabricated: string[]
  message: string
}

/** 多跳轨迹节点（不同 node 字段不同，用可选并集表达） */
export interface TraceStep {
  node: 'planner' | 'retrieve' | 'reflect' | 'answer'
  // planner
  is_complex?: boolean
  subs?: string[]
  // retrieve
  hop?: number
  queried?: string[]
  n_hits_total?: number
  // reflect
  decision?: string
  missing?: string[]
  tool_resolved?: string[]
  tool_added_hits?: number
  // answer
  n_context?: number
}

/** SSE chunk 类型（单跳 + Agent 两个接口的并集） */
export type ChunkType =
  | 'rewrite'
  | 'references'
  | 'answer'
  | 'trace'
  | 'verify'
  | 'disclaimer'
  | 'error'

/** 单个 SSE chunk */
export interface Chunk {
  type: ChunkType
  content: string | Reference[] | TraceStep[] | VerifyResult
}

/** 对话模式 */
export type ChatMode = 'single' | 'agent'

/** 消息状态 */
export type MessageStatus = 'pending' | 'streaming' | 'done' | 'error'

/** 一条消息（用户或 AI） */
export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  status?: MessageStatus
  mode?: ChatMode
  // AI 消息专属
  rewrite?: string
  refs?: Reference[]
  trace?: TraceStep[]
  verify?: VerifyResult
  disclaimer?: string
  statusLabel?: string // 等待状态文案：「正在检索条文…」
  feedback?: 'up' | 'down' | null
}

/** 一个会话 */
export interface Session {
  id: string
  title: string
  messages: Message[]
  createdAt: number
  updatedAt: number
}
