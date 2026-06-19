<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { ChevronRight } from 'lucide-vue-next'
import type { Reference } from '@/types/chat'
import { refAnchorId } from '@/composables/useScrollAnchor'

const props = defineProps<{ reference: Reference; scope: string }>()
const open = ref(false)
const root = ref<HTMLElement | null>(null)
const anchorId = refAnchorId(props.scope, props.reference.law_name, props.reference.article_no)

// 条号锚点跳转时自动展开本卡片
function onExpand() {
  open.value = true
}
onMounted(() => root.value?.addEventListener('anchor-expand', onExpand))
onBeforeUnmount(() => root.value?.removeEventListener('anchor-expand', onExpand))
</script>

<template>
  <div :id="anchorId" ref="root" class="ref-card">
    <button class="ref-head" type="button" @click="open = !open">
      <ChevronRight class="chevron" :class="{ rotated: open }" :size="14" />
      <span class="ref-title">
        《{{ reference.law_name }}》第{{ reference.article_no }}条
      </span>
      <span v-if="reference.chapter" class="ref-chapter">{{ reference.chapter }}</span>
    </button>
    <div v-show="open" class="ref-text anim-fade-in">
      {{ reference.article_text }}
      <div v-if="reference.effective_date" class="ref-meta">
        施行日期：{{ reference.effective_date }}
      </div>
    </div>
  </div>
</template>

<style scoped>
.ref-card {
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--bg-base);
  overflow: hidden;
}
.ref-head {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding: 8px 10px;
  background: transparent;
  border: none;
  text-align: left;
  color: var(--text-primary);
  font-size: 0.85rem;
}
.ref-head:hover {
  background: var(--bg-surface-2);
}
.chevron {
  flex-shrink: 0;
  color: var(--accent);
  transition: transform 0.2s;
}
.chevron.rotated {
  transform: rotate(90deg);
}
.ref-title {
  font-weight: 500;
  color: var(--accent);
}
.ref-chapter {
  margin-left: auto;
  font-size: 0.72rem;
  color: var(--text-tertiary);
}
.ref-text {
  padding: 8px 12px 10px 30px;
  font-size: 0.85rem;
  line-height: 1.7;
  color: var(--text-secondary);
  border-top: 1px solid var(--border);
}
.ref-meta {
  margin-top: 6px;
  font-size: 0.72rem;
  color: var(--text-tertiary);
}
</style>
