/* ============================================================
   api/feedback.ts — 用户 👍/👎 反馈上报
   ============================================================ */

import type { FeedbackRequest } from '@/types/api'

/** 提交反馈，落盘到后端 feedback.jsonl。失败静默（不阻断用户） */
export async function submitFeedback(req: FeedbackRequest): Promise<boolean> {
  try {
    const resp = await fetch('/api/feedback', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    })
    if (!resp.ok) return false
    const data = (await resp.json()) as { ok?: boolean }
    return data.ok ?? false
  } catch {
    return false
  }
}
