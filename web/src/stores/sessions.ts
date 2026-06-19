/* ============================================================
   stores/sessions.ts — 会话列表 / 当前会话 / 持久化
   存储策略：refs、trace 仅存摘要不存完整原文，避免 localStorage 超配额。
   ============================================================ */

import { defineStore } from 'pinia'
import { ref, computed, watch } from 'vue'
import type { Message, Session } from '@/types/chat'
import { filterCitedRefs } from '@/utils/citation'

const LS_KEY = 'legal-assistant:sessions'
const TITLE_MAX = 15

function uid(): string {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
}

/** 持久化前裁剪：条文原文 / trace 只留摘要，控制体积 */
function trimForStorage(s: Session): Session {
  return {
    ...s,
    messages: s.messages.map((m) => ({
      ...m,
      refs: m.refs?.map((r) => ({
        article_no: r.article_no,
        sub_no: r.sub_no,
        law_name: r.law_name,
        chapter: r.chapter,
        // 原文截断到 120 字，完整内容只在内存
        article_text: (r.article_text ?? '').slice(0, 120),
      })),
    })),
  }
}

function loadSessions(): Session[] {
  try {
    const raw = localStorage.getItem(LS_KEY)
    if (raw) return JSON.parse(raw) as Session[]
  } catch {
    /* ignore */
  }
  return []
}

export const useSessionsStore = defineStore('sessions', () => {
  const sessions = ref<Session[]>(loadSessions())
  const currentSessionId = ref<string>('')

  const currentSession = computed(
    () => sessions.value.find((s) => s.id === currentSessionId.value) ?? null,
  )

  const messages = computed<Message[]>(() => currentSession.value?.messages ?? [])

  // 初始化：无会话则建一个；否则选最近的
  function init() {
    if (sessions.value.length === 0) {
      createSession()
    } else {
      currentSessionId.value = sessions.value[0].id
    }
  }

  function createSession(): string {
    const now = Date.now()
    const s: Session = {
      id: uid(),
      title: '新对话',
      messages: [],
      createdAt: now,
      updatedAt: now,
    }
    sessions.value.unshift(s)
    currentSessionId.value = s.id
    return s.id
  }

  function selectSession(id: string) {
    currentSessionId.value = id
  }

  function deleteSession(id: string) {
    const idx = sessions.value.findIndex((s) => s.id === id)
    if (idx === -1) return
    sessions.value.splice(idx, 1)
    if (currentSessionId.value === id) {
      if (sessions.value.length === 0) createSession()
      else currentSessionId.value = sessions.value[0].id
    }
  }

  function renameSession(id: string, title: string) {
    const s = sessions.value.find((x) => x.id === id)
    if (s) s.title = title.trim() || '未命名对话'
  }

  function clearAllSessions() {
    sessions.value = []
    createSession()
  }

  /** 追加消息到当前会话，返回该消息引用（便于流式更新） */
  function appendMessage(msg: Message): Message {
    const s = currentSession.value
    if (!s) return msg
    s.messages.push(msg)
    s.updatedAt = Date.now()
    // 首条用户消息确定标题
    if (msg.role === 'user' && (s.title === '新对话' || !s.title)) {
      s.title = msg.content.slice(0, TITLE_MAX) || '新对话'
    }
    return s.messages[s.messages.length - 1]
  }

  function touch() {
    const s = currentSession.value
    if (s) s.updatedAt = Date.now()
  }

  /** 导出会话为 Markdown 文本 */
  function exportSessionMarkdown(id: string): string {
    const s = sessions.value.find((x) => x.id === id)
    if (!s) return ''
    const lines: string[] = [`# ${s.title}`, '']
    for (const m of s.messages) {
      if (m.role === 'user') {
        lines.push(`## 🙋 提问`, '', m.content, '')
      } else {
        lines.push(`## ⚖️ 法律助手`, '', m.content, '')
        const cited = filterCitedRefs(m.refs, m.verify)
        if (cited.length) {
          lines.push('**引用条文：**', '')
          for (const r of cited) {
            lines.push(`- 《${r.law_name}》第${r.article_no}条`)
          }
          lines.push('')
        }
        if (m.verify?.message) {
          lines.push(`> 校验：${m.verify.message}`, '')
        }
      }
    }
    return lines.join('\n')
  }

  // 持久化（裁剪后写入）
  watch(
    sessions,
    (val) => {
      try {
        const slim = val.map(trimForStorage)
        localStorage.setItem(LS_KEY, JSON.stringify(slim))
      } catch {
        /* 超配额等：静默 */
      }
    },
    { deep: true },
  )

  return {
    sessions,
    currentSessionId,
    currentSession,
    messages,
    init,
    createSession,
    selectSession,
    deleteSession,
    renameSession,
    clearAllSessions,
    appendMessage,
    touch,
    exportSessionMarkdown,
  }
})
