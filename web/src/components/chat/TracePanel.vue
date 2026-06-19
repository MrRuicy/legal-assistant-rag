<script setup lang="ts">
import { computed } from 'vue'
import type { TraceStep } from '@/types/chat'

const props = defineProps<{ trace: TraceStep[]; live?: boolean }>()

interface Row {
  label: string
  detail: string
  running: boolean
  done: boolean
}

const NODE_LABEL: Record<string, string> = {
  planner: '规划',
  retrieve: '检索',
  reflect: '反思',
  answer: '作答',
}

const rows = computed<Row[]>(() => {
  const list = props.trace ?? []
  return list.map((step, i) => {
    const isLast = i === list.length - 1
    return {
      label: NODE_LABEL[step.node] ?? step.node,
      detail: describe(step),
      // 仅最后一个节点在流式进行中标 running，且非 answer 完成态
      running: props.live === true && isLast && step.node !== 'answer',
      done: !(props.live === true && isLast) || step.node === 'answer',
    }
  })
})

function describe(s: TraceStep): string {
  switch (s.node) {
    case 'planner':
      return s.is_complex
        ? `判定为复杂问题 → ${s.subs?.length ?? 0} 个子问题`
        : '判定为简单问题，直接检索'
    case 'retrieve':
      return `${(s.queried ?? []).map((q) => `“${q}”`).join('、')} → 累积 ${s.n_hits_total ?? 0} 条`
    case 'reflect':
      if (s.decision === 'continue') {
        const m = (s.missing ?? []).join('、')
        return m ? `信息不足，补充检索：${m}` : '信息不足，继续检索'
      }
      return s.tool_added_hits
        ? `工具补全 ${s.tool_added_hits} 条，信息充分`
        : '信息充分，开始作答'
    case 'answer':
      return `基于 ${s.n_context ?? 0} 条法律条文生成答案`
    default:
      return ''
  }
}
</script>

<template>
  <div v-if="rows.length" class="trace-panel">
    <div v-for="(row, i) in rows" :key="i" class="trace-row anim-fade-in">
      <span class="trace-dot" :class="{ running: row.running, done: row.done && !row.running }">
        <span v-if="row.done && !row.running" class="check">✓</span>
        <span v-else class="status-dot" :class="{ running: row.running }" />
      </span>
      <span class="trace-label">{{ row.label }}</span>
      <span class="trace-detail">{{ row.detail }}</span>
    </div>
  </div>
</template>

<style scoped>
.trace-panel {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 10px 12px;
  margin-bottom: 12px;
  background: var(--bg-surface-2);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
}
.trace-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.82rem;
}
.trace-dot {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  flex-shrink: 0;
}
.trace-dot .check {
  color: var(--accent);
  font-size: 0.85rem;
  font-weight: 700;
}
.trace-label {
  color: var(--text-primary);
  font-weight: 600;
  flex-shrink: 0;
}
.trace-detail {
  color: var(--text-secondary);
}
</style>
