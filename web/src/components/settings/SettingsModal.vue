<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { Sun, Moon } from 'lucide-vue-next'
import Modal from '@/components/ui/Modal.vue'
import { useSettingsStore } from '@/stores/settings'
import { useSessionsStore } from '@/stores/sessions'

defineProps<{ open: boolean }>()
const emit = defineEmits<{ close: [] }>()

const settings = useSettingsStore()
const { theme, agentMode } = storeToRefs(settings)
const sessions = useSessionsStore()

function clearAll() {
  if (confirm('确定清除全部本地会话？此操作不可撤销。')) {
    sessions.clearAllSessions()
    emit('close')
  }
}
</script>

<template>
  <Modal :open="open" title="设置" @close="emit('close')">
    <div class="settings">
      <!-- 主题 -->
      <div class="row">
        <div class="row-info">
          <span class="row-title">外观主题</span>
          <span class="row-desc">深色玻璃态 / 浅色清雅</span>
        </div>
        <button class="theme-switch" @click="settings.toggleTheme()">
          <Moon v-if="theme === 'dark'" :size="15" />
          <Sun v-else :size="15" />
          {{ theme === 'dark' ? '深色' : '浅色' }}
        </button>
      </div>

      <!-- 深度模式 -->
      <div class="row">
        <div class="row-info">
          <span class="row-title">深度模式（默认）</span>
          <span class="row-desc">多跳检索推理，回答更全面但更慢</span>
        </div>
        <button
          class="switch"
          :class="{ on: agentMode }"
          @click="settings.toggleAgentMode()"
        >
          <span class="knob" />
        </button>
      </div>

      <!-- 反馈说明 -->
      <div class="row">
        <div class="row-info">
          <span class="row-title">使用反馈</span>
          <span class="row-desc">👍/👎 会记录到后端日志，用于改进检索质量</span>
        </div>
      </div>

      <!-- 清除数据 -->
      <div class="row danger-row">
        <div class="row-info">
          <span class="row-title">清除本地会话</span>
          <span class="row-desc">删除浏览器中保存的全部对话历史</span>
        </div>
        <button class="danger-btn" @click="clearAll">清除</button>
      </div>
    </div>
  </Modal>
</template>

<style scoped>
.settings {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 14px 0;
  border-bottom: 1px solid var(--border);
}
.row:last-child {
  border-bottom: none;
}
.row-info {
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.row-title {
  font-size: 0.9rem;
  font-weight: 500;
  color: var(--text-primary);
}
.row-desc {
  font-size: 0.76rem;
  color: var(--text-tertiary);
  line-height: 1.5;
}
.theme-switch {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 14px;
  background: var(--bg-surface-2);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  color: var(--text-primary);
  font-size: 0.82rem;
}
.theme-switch:hover {
  border-color: var(--accent);
}
.switch {
  flex-shrink: 0;
  width: 40px;
  height: 22px;
  border-radius: 999px;
  background: var(--border-strong);
  border: none;
  position: relative;
  transition: background 0.2s;
}
.switch.on {
  background: var(--accent);
}
.knob {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: #fff;
  transition: transform 0.2s;
}
.switch.on .knob {
  transform: translateX(18px);
}
.danger-btn {
  flex-shrink: 0;
  padding: 7px 16px;
  background: var(--danger-soft);
  border: 1px solid var(--danger);
  border-radius: var(--radius-sm);
  color: var(--danger);
  font-size: 0.82rem;
  font-weight: 500;
}
.danger-btn:hover {
  background: var(--danger);
  color: #fff;
}
</style>
