<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { RefreshCw, Scale } from 'lucide-vue-next'
import { getExamples } from '@/api/chat'

const emit = defineEmits<{ pick: [q: string] }>()
const examples = ref<string[]>([])
const loading = ref(false)

async function load() {
  loading.value = true
  examples.value = await getExamples(6)
  loading.value = false
}

onMounted(load)
</script>

<template>
  <div class="empty-state">
    <div class="empty-icon"><Scale :size="40" /></div>
    <h2 class="empty-title">法律助手</h2>
    <p class="empty-sub">基于 RAG 检索 38 部法律条文，回答有出处、可追溯</p>

    <div class="chips-head">
      <span>试试这些问题</span>
      <button class="refresh-btn" :disabled="loading" @click="load">
        <RefreshCw :size="13" :class="{ spin: loading }" /> 换一换
      </button>
    </div>
    <div class="chips">
      <button
        v-for="(q, i) in examples"
        :key="i"
        class="chip"
        @click="emit('pick', q)"
      >
        {{ q }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  padding: 48px 20px;
  max-width: 640px;
  margin: 0 auto;
}
.empty-icon {
  width: 72px;
  height: 72px;
  border-radius: var(--radius-lg);
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, var(--accent-grad-from), var(--accent-grad-to));
  color: #fff;
  margin-bottom: 18px;
  box-shadow: var(--shadow-md);
}
.empty-title {
  font-size: 1.6rem;
  font-weight: 700;
  margin-bottom: 8px;
}
.empty-sub {
  color: var(--text-secondary);
  font-size: 0.92rem;
  margin-bottom: 32px;
}
.chips-head {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  justify-content: space-between;
  margin-bottom: 12px;
  font-size: 0.82rem;
  color: var(--text-secondary);
}
.refresh-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: transparent;
  border: none;
  color: var(--accent);
  font-size: 0.8rem;
}
.refresh-btn:hover {
  color: var(--accent-hover);
}
.spin {
  animation: spin 0.8s linear infinite;
}
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
.chips {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  width: 100%;
}
@media (max-width: 640px) {
  .chips {
    grid-template-columns: 1fr;
  }
}
.chip {
  text-align: left;
  padding: 12px 14px;
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  color: var(--text-primary);
  font-size: 0.88rem;
  line-height: 1.5;
  transition: all 0.15s;
}
.chip:hover {
  border-color: var(--accent);
  background: var(--bg-elevated);
  transform: translateY(-1px);
}
</style>
