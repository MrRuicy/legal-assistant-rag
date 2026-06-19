<script setup lang="ts">
import { onMounted } from 'vue'
import { RouterView } from 'vue-router'
import { useSettingsStore } from '@/stores/settings'

const settings = useSettingsStore()

// 启动时应用持久化的主题
onMounted(() => {
  settings.applyTheme()
})
</script>

<template>
  <RouterView />
</template>
