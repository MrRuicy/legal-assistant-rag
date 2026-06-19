<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { ChevronRight } from 'lucide-vue-next'

withDefaults(
  defineProps<{
    title?: string
    defaultOpen?: boolean
    accent?: boolean // 左侧天蓝竖条
  }>(),
  { defaultOpen: false, accent: false },
)

const open = ref(false)
const initialized = ref(false)
const root = ref<HTMLElement | null>(null)

function toggle() {
  open.value = !open.value
  initialized.value = true
}

// 内部 RefCard 触发锚点跳转时，冒泡事件让本折叠块自动展开
function onAnchorExpand() {
  open.value = true
}
onMounted(() => root.value?.addEventListener('anchor-expand', onAnchorExpand))
onBeforeUnmount(() => root.value?.removeEventListener('anchor-expand', onAnchorExpand))
</script>

<template>
  <div ref="root" class="collapsible" :class="{ accent }">
    <button class="collapsible-head" type="button" @click="toggle">
      <ChevronRight class="chevron" :class="{ rotated: open }" :size="16" />
      <span class="collapsible-title">
        <slot name="title">{{ title }}</slot>
      </span>
    </button>
    <div v-show="open" class="collapsible-body anim-fade-in">
      <slot />
    </div>
  </div>
</template>

<style scoped>
.collapsible {
  border-radius: var(--radius-sm);
  overflow: hidden;
}
.collapsible.accent {
  border-left: 2px solid var(--accent);
  background: var(--bg-surface-2);
}
.collapsible-head {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding: 8px 12px;
  background: transparent;
  border: none;
  color: var(--text-secondary);
  font-size: 0.85rem;
  font-weight: 500;
  text-align: left;
  transition: color 0.15s;
}
.collapsible-head:hover {
  color: var(--text-primary);
}
.chevron {
  flex-shrink: 0;
  transition: transform 0.2s ease;
  color: var(--accent);
}
.chevron.rotated {
  transform: rotate(90deg);
}
.collapsible-title {
  flex: 1;
}
.collapsible-body {
  padding: 4px 12px 12px;
}
</style>
