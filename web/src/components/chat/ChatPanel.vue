<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'
import type { Message } from '@/types/chat'
import MessageItem from './MessageItem.vue'
import ExampleChips from '@/components/input/ExampleChips.vue'

const props = defineProps<{ messages: Message[] }>()
const emit = defineEmits<{ pick: [q: string] }>()

const scroller = ref<HTMLElement | null>(null)

function scrollToBottom() {
  const el = scroller.value
  if (!el) return
  el.scrollTop = el.scrollHeight
}

// 消息变化（新增/流式追加）时贴底
watch(
  () => props.messages.map((m) => m.content).join('|') + props.messages.length,
  () => nextTick(scrollToBottom),
)
</script>

<template>
  <div ref="scroller" class="chat-panel">
    <div class="panel-inner">
      <ExampleChips v-if="messages.length === 0" @pick="emit('pick', $event)" />
      <template v-else>
        <MessageItem v-for="m in messages" :key="m.id" :message="m" />
      </template>
    </div>
  </div>
</template>

<style scoped>
.chat-panel {
  flex: 1;
  overflow-y: auto;
  padding: 24px 20px;
}
.panel-inner {
  max-width: 820px;
  margin: 0 auto;
}
</style>
