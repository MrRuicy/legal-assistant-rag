<script setup lang="ts">
import { computed } from 'vue'
import { Sparkles } from 'lucide-vue-next'
import type { Message } from '@/types/chat'
import { renderMarkdown } from '@/composables/useMarkdown'
import { scrollToRef, refAnchorId } from '@/composables/useScrollAnchor'
import { filterCitedRefs } from '@/utils/citation'
import TracePanel from './TracePanel.vue'
import StatusLine from './StatusLine.vue'
import AnswerFooter from './AnswerFooter.vue'

const props = defineProps<{ message: Message }>()

const html = computed(() => renderMarkdown(props.message.content))

const showStatus = computed(
  () => props.message.status === 'pending' && !props.message.content,
)

// trace 是否还在跑（消息未结束）
const traceLive = computed(
  () => props.message.status === 'pending' || props.message.status === 'streaming',
)

// 委托点击条号链接 → 滚动到引用卡片（仅在本条消息实际引用的条文里找）
function onContentClick(e: MouseEvent) {
  const target = (e.target as HTMLElement).closest('.law-ref') as HTMLElement | null
  if (!target) return
  const law = target.dataset.law ?? ''
  const noText = target.dataset.no ?? ''
  const refs = filterCitedRefs(props.message.refs, props.message.verify)
  const numMatch = noText.match(/\d+/)
  const no = numMatch?.[0] ?? ''
  let hit = refs.find(
    (r) => (!law || r.law_name.includes(law)) && String(r.article_no) === no,
  )
  if (!hit && no) {
    hit = refs.find((r) => String(r.article_no) === no)
  }
  if (hit) scrollToRef(refAnchorId(props.message.id, hit.law_name, hit.article_no))
}
</script>

<template>
  <div class="ai-message">
    <div class="ai-avatar"><Sparkles :size="16" /></div>
    <div class="ai-card">
      <!-- 改写提示 -->
      <p v-if="message.rewrite" class="rewrite-hint">
        已理解为：{{ message.rewrite }}
      </p>

      <!-- 多跳轨迹（Agent 模式） -->
      <TracePanel
        v-if="message.trace && message.trace.length"
        :trace="message.trace"
        :live="traceLive"
      />

      <!-- 等待状态行 -->
      <StatusLine v-if="showStatus" :label="message.statusLabel" />

      <!-- 正文 Markdown -->
      <div
        v-if="message.content"
        class="prose"
        :class="{ 'is-error': message.status === 'error' }"
        @click="onContentClick"
        v-html="html"
      />

      <!-- 页脚：校验徽章 + 引用 + 反馈 + 免责（消息完成后展示） -->
      <AnswerFooter
        v-if="message.status === 'done' && (message.verify || message.refs?.length)"
        :message="message"
      />
    </div>
  </div>
</template>

<style scoped>
.ai-message {
  display: flex;
  gap: 10px;
  max-width: 100%;
}
.ai-avatar {
  flex-shrink: 0;
  width: 30px;
  height: 30px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, var(--accent-grad-from), var(--accent-grad-to));
  color: white;
}
.ai-card {
  flex: 1;
  min-width: 0;
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 4px 18px 18px 18px;
  padding: 14px 16px;
  box-shadow: var(--shadow-sm);
}
.rewrite-hint {
  font-size: 0.78rem;
  color: var(--text-tertiary);
  margin-bottom: 10px;
  padding: 6px 10px;
  background: var(--bg-surface-2);
  border-radius: var(--radius-sm);
  border-left: 2px solid var(--accent);
}
.prose.is-error {
  color: var(--danger);
}
</style>
