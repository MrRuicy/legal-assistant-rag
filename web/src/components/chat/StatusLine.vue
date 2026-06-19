<script setup lang="ts">
defineProps<{ label?: string }>()
</script>

<template>
  <div class="status-line">
    <span class="loading-dots">
      <span></span><span></span><span></span>
    </span>
    <span class="status-text">{{ label ?? '正在处理…' }}</span>
  </div>
</template>

<style scoped>
.status-line {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 4px 0;
}
.status-text {
  color: var(--text-secondary);
  font-size: 0.88rem;
}
</style>
