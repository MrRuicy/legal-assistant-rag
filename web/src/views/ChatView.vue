<script setup lang="ts">
import { ref, onMounted } from 'vue'
import AppSidebar from '@/components/layout/AppSidebar.vue'
import AppHeader from '@/components/layout/AppHeader.vue'
import ChatPanel from '@/components/chat/ChatPanel.vue'
import ChatInput from '@/components/input/ChatInput.vue'
import SettingsModal from '@/components/settings/SettingsModal.vue'
import { useSessionsStore } from '@/stores/sessions'
import { useChat } from '@/composables/useChat'

const sessions = useSessionsStore()
const { isStreaming, sendMessage, stop } = useChat()

const sidebarCollapsed = ref(false)
const settingsOpen = ref(false)
const inputRef = ref<InstanceType<typeof ChatInput> | null>(null)

onMounted(() => {
  sessions.init()
  if (window.innerWidth <= 768) sidebarCollapsed.value = true
})

function onPickExample(q: string) {
  inputRef.value?.setText(q)
}

function onExport() {
  const id = sessions.currentSessionId
  const md = sessions.exportSessionMarkdown(id)
  if (!md) return
  const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${sessions.currentSession?.title || '会话'}.md`
  a.click()
  URL.revokeObjectURL(url)
}
</script>

<template>
  <div class="app-shell">
    <Transition name="sidebar">
      <AppSidebar v-if="!sidebarCollapsed" @collapse="sidebarCollapsed = true" />
    </Transition>

    <div class="main-col">
      <AppHeader
        :sidebar-collapsed="sidebarCollapsed"
        @open-sidebar="sidebarCollapsed = false"
        @open-settings="settingsOpen = true"
        @export="onExport"
      />
      <ChatPanel :messages="sessions.messages" @pick="onPickExample" />
      <ChatInput
        ref="inputRef"
        :streaming="isStreaming"
        @send="sendMessage"
        @stop="stop"
      />
    </div>

    <SettingsModal :open="settingsOpen" @close="settingsOpen = false" />
  </div>
</template>

<style scoped>
.app-shell {
  display: flex;
  height: 100%;
  overflow: hidden;
}
.main-col {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  height: 100%;
}
.sidebar-enter-active,
.sidebar-leave-active {
  transition: margin-left 0.2s ease, opacity 0.2s ease;
}
.sidebar-enter-from,
.sidebar-leave-to {
  margin-left: -260px;
  opacity: 0;
}
</style>
