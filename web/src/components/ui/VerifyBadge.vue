<script setup lang="ts">
import { computed } from 'vue'
import { ShieldCheck, ShieldAlert, Shield } from 'lucide-vue-next'
import type { VerifyResult } from '@/types/chat'

const props = defineProps<{ verify: VerifyResult }>()

const meta = computed(() => {
  switch (props.verify.status) {
    case 'ok':
      return { icon: ShieldCheck, label: '引用可追溯', cls: 'ok' }
    case 'warn':
      return { icon: ShieldAlert, label: '引用存疑', cls: 'warn' }
    default:
      return { icon: Shield, label: '未显式引用', cls: 'none' }
  }
})
</script>

<template>
  <span class="verify-badge" :class="meta.cls" :title="verify.message">
    <component :is="meta.icon" :size="14" />
    {{ meta.label }}
  </span>
</template>

<style scoped>
.verify-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 10px;
  border-radius: 999px;
  font-size: 0.75rem;
  font-weight: 500;
  border: 1px solid transparent;
  cursor: help;
}
.verify-badge.ok {
  background: var(--success-soft);
  color: var(--success);
  border-color: var(--success);
}
.verify-badge.warn {
  background: var(--warning-soft);
  color: var(--warning);
  border-color: var(--warning);
}
.verify-badge.none {
  background: var(--bg-surface-2);
  color: var(--text-tertiary);
  border-color: var(--border);
}
</style>
