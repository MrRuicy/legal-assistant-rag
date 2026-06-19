<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { Menu, Settings, Sparkles, Download } from 'lucide-vue-next'
import { useSettingsStore } from '@/stores/settings'
import { useSessionsStore } from '@/stores/sessions'

const props = defineProps<{ sidebarCollapsed: boolean }>()
const emit = defineEmits<{ openSidebar: []; openSettings: []; export: [] }>()

const settings = useSettingsStore()
const { agentMode } = storeToRefs(settings)
const sessions = useSessionsStore()
</script>

<template>
  <header class="app-header">
    <div class="header-left">
      <button
        v-if="props.sidebarCollapsed"
        class="icon-btn"
        title="展开侧栏"
        @click="emit('openSidebar')"
      >
        <Menu :size="18" />
      </button>
      <span class="app-title">⚖️ 法律助手 <span class="beta">beta</span></span>
    </div>

    <div class="header-right">
      <!-- 深度模式开关 -->
      <button
        class="agent-toggle"
        :class="{ on: agentMode }"
        :title="agentMode ? '深度模式：多跳检索推理' : '普通模式：单跳检索'"
        @click="settings.toggleAgentMode()"
      >
        <Sparkles :size="15" />
        <span>深度模式</span>
        <span class="switch" :class="{ on: agentMode }"><span class="knob" /></span>
      </button>

      <button
        class="icon-btn"
        title="导出当前会话"
        :disabled="!sessions.currentSession?.messages.length"
        @click="emit('export')"
      >
        <Download :size="18" />
      </button>
      <button class="icon-btn" title="设置" @click="emit('openSettings')">
        <Settings :size="18" />
      </button>
    </div>
  </header>
</template>

<style scoped>
.app-header {
  height: 56px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 16px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-surface);
}
.header-left,
.header-right {
  display: flex;
  align-items: center;
  gap: 10px;
}
.app-title {
  font-size: 1.05rem;
  font-weight: 600;
}
.beta {
  font-size: 0.65rem;
  color: var(--accent);
  background: var(--accent-soft);
  padding: 1px 6px;
  border-radius: 6px;
  vertical-align: middle;
  font-weight: 500;
}
.icon-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  background: transparent;
  border: none;
  border-radius: var(--radius-sm);
  color: var(--text-secondary);
}
.icon-btn:hover:not(:disabled) {
  background: var(--bg-elevated);
  color: var(--text-primary);
}
.icon-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.agent-toggle {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 6px 12px;
  background: var(--bg-surface-2);
  border: 1px solid var(--border);
  border-radius: 999px;
  color: var(--text-secondary);
  font-size: 0.82rem;
  font-weight: 500;
  transition: all 0.15s;
}
.agent-toggle.on {
  color: var(--accent);
  border-color: var(--accent);
  background: var(--accent-soft);
}
.switch {
  width: 30px;
  height: 16px;
  border-radius: 999px;
  background: var(--border-strong);
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
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: #fff;
  transition: transform 0.2s;
}
.switch.on .knob {
  transform: translateX(14px);
}
</style>
