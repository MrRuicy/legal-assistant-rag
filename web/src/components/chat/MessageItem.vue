<script setup lang="ts">
import type { Message } from '@/types/chat'
import AiMessage from './AiMessage.vue'

defineProps<{ message: Message }>()
</script>

<template>
  <div class="message-item anim-slide-in" :class="message.role">
    <!-- 用户气泡 -->
    <div v-if="message.role === 'user'" class="user-bubble">
      {{ message.content }}
    </div>
    <!-- AI 消息 -->
    <AiMessage v-else :message="message" />
  </div>
</template>

<style scoped>
.message-item {
  display: flex;
  margin-bottom: 20px;
}
.message-item.user {
  justify-content: flex-end;
}
.user-bubble {
  max-width: 75%;
  padding: 11px 16px;
  background: linear-gradient(135deg, var(--accent-grad-from), var(--accent-grad-to));
  color: #fff;
  border-radius: 18px 18px 4px 18px;
  line-height: 1.6;
  font-size: 0.95rem;
  word-break: break-word;
  box-shadow: var(--shadow-sm);
}
</style>
