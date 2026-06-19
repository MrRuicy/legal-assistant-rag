<script setup lang="ts">
import { ref, nextTick, watch } from 'vue'
import { ArrowUp, Square } from 'lucide-vue-next'

const props = defineProps<{ streaming: boolean }>()
const emit = defineEmits<{ send: [q: string]; stop: [] }>()

const text = ref('')
const textarea = ref<HTMLTextAreaElement | null>(null)

function autoGrow() {
  const el = textarea.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 180) + 'px'
}

watch(text, () => nextTick(autoGrow))

function submit() {
  if (props.streaming) {
    emit('stop')
    return
  }
  const q = text.value.trim()
  if (!q) return
  emit('send', q)
  text.value = ''
  nextTick(() => {
    autoGrow()
    textarea.value?.focus()
  })
}

function onKeydown(e: KeyboardEvent) {
  // Enter 发送，Shift+Enter 换行
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
    e.preventDefault()
    submit()
  }
}

defineExpose({
  setText: (v: string) => {
    text.value = v
    nextTick(() => textarea.value?.focus())
  },
})
</script>

<template>
  <div class="chat-input">
    <div class="input-box">
      <textarea
        ref="textarea"
        v-model="text"
        rows="1"
        placeholder="向法律助手提问，Enter 发送，Shift+Enter 换行"
        @keydown="onKeydown"
      />
      <button
        class="send-btn"
        :class="{ streaming }"
        :disabled="!streaming && !text.trim()"
        :title="streaming ? '停止生成' : '发送'"
        @click="submit"
      >
        <Square v-if="streaming" :size="16" fill="currentColor" />
        <ArrowUp v-else :size="18" />
      </button>
    </div>
    <p class="input-hint">AI 生成内容仅供参考，不构成法律意见</p>
  </div>
</template>

<style scoped>
.chat-input {
  padding: 14px 20px 18px;
}
.input-box {
  display: flex;
  align-items: flex-end;
  gap: 10px;
  max-width: 820px;
  margin: 0 auto;
  background: var(--bg-surface);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-lg);
  padding: 8px 8px 8px 16px;
  transition: border-color 0.15s;
}
.input-box:focus-within {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-soft);
}
textarea {
  flex: 1;
  resize: none;
  border: none;
  outline: none;
  background: transparent;
  color: var(--text-primary);
  font-size: 0.95rem;
  line-height: 1.6;
  max-height: 180px;
  padding: 6px 0;
}
textarea::placeholder {
  color: var(--text-tertiary);
}
.send-btn {
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  border-radius: 10px;
  border: none;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, var(--accent-grad-from), var(--accent-grad-to));
  color: #fff;
  transition: opacity 0.15s, transform 0.15s;
}
.send-btn:hover:not(:disabled) {
  transform: translateY(-1px);
}
.send-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.send-btn.streaming {
  background: var(--danger);
}
.input-hint {
  text-align: center;
  font-size: 0.72rem;
  color: var(--text-tertiary);
  margin-top: 8px;
}
</style>
