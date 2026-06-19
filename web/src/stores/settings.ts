/* ============================================================
   stores/settings.ts — 用户偏好（深度模式、主题、top-k）
   持久化到 localStorage
   ============================================================ */

import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

type Theme = 'dark' | 'light'

const LS_KEY = 'legal-assistant:settings'

interface PersistedSettings {
  agentMode: boolean
  theme: Theme
  topK: number | null
}

function loadSettings(): PersistedSettings {
  try {
    const raw = localStorage.getItem(LS_KEY)
    if (raw) return { ...defaults(), ...JSON.parse(raw) }
  } catch {
    /* ignore */
  }
  return defaults()
}

function defaults(): PersistedSettings {
  return { agentMode: false, theme: 'dark', topK: null }
}

export const useSettingsStore = defineStore('settings', () => {
  const persisted = loadSettings()

  const agentMode = ref(persisted.agentMode)
  const theme = ref<Theme>(persisted.theme)
  const topK = ref<number | null>(persisted.topK)

  function applyTheme() {
    document.documentElement.setAttribute('data-theme', theme.value)
  }

  function toggleTheme() {
    theme.value = theme.value === 'dark' ? 'light' : 'dark'
    applyTheme()
  }

  function toggleAgentMode() {
    agentMode.value = !agentMode.value
  }

  // 任意偏好变化即持久化
  watch(
    [agentMode, theme, topK],
    () => {
      const data: PersistedSettings = {
        agentMode: agentMode.value,
        theme: theme.value,
        topK: topK.value,
      }
      localStorage.setItem(LS_KEY, JSON.stringify(data))
    },
    { deep: true },
  )

  return { agentMode, theme, topK, applyTheme, toggleTheme, toggleAgentMode }
})
