/* ============================================================
   composables/useScrollAnchor.ts — 条号链接 → 引用卡片平滑滚动 + 高亮
   锚点 id 带 messageId 作用域，避免多轮对话中相同条文 id 冲突
   （否则 getElementById 永远命中第一条，跳到旧回答）。
   ============================================================ */

/** 生成引用卡片锚点 id（scope 用 message.id 隔离每轮回答） */
export function refAnchorId(
  scope: string,
  lawName: string,
  articleNo: number | string,
): string {
  const safe = `${lawName}-${articleNo}`.replace(/[^\w一-龥-]/g, '')
  return `ref-${scope}-${safe}`
}

/**
 * 滚动到指定引用卡片并高亮。先派发 expand 事件让卡片展开，
 * 等下一帧 DOM 高度稳定后再滚动居中（解决「折叠时跳过去看不到」）。
 */
export function scrollToRef(anchorId: string) {
  const el = document.getElementById(anchorId)
  if (!el) return
  // 通知卡片及其上级折叠块展开（冒泡：RefCard 自身 + 祖先 Collapsible 都收到）
  el.dispatchEvent(new CustomEvent('anchor-expand', { bubbles: true }))
  requestAnimationFrame(() => {
    el.scrollIntoView({ behavior: 'smooth', block: 'center' })
    el.classList.remove('anchor-flash')
    void el.offsetWidth // 强制重排以重启动画
    el.classList.add('anchor-flash')
  })
}

export function useScrollAnchor() {
  return { refAnchorId, scrollToRef }
}
