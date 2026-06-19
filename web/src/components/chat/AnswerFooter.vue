<script setup lang="ts">
import { ref, computed } from 'vue'
import { ThumbsUp, ThumbsDown } from 'lucide-vue-next'
import type { Message } from '@/types/chat'
import Collapsible from '@/components/ui/Collapsible.vue'
import VerifyBadge from '@/components/ui/VerifyBadge.vue'
import RefCard from './RefCard.vue'
import { submitFeedback } from '@/api/feedback'
import { filterCitedRefs, missingCitedLabels } from '@/utils/citation'

const props = defineProps<{ message: Message }>()

// 只展示回答中实际引用到的条文
const citedRefs = computed(() =>
  filterCitedRefs(props.message.refs, props.message.verify),
)

// 「被回答引用、但检索库里没有」的条文（模型用了自身知识，无对应卡片）
const missingLabels = computed(() =>
  missingCitedLabels(props.message.refs, props.message.verify),
)

const localFeedback = ref<'up' | 'down' | null>(props.message.feedback ?? null)

async function vote(liked: boolean) {
  const val = liked ? 'up' : 'down'
  // 再次点击同按钮取消
  localFeedback.value = localFeedback.value === val ? null : val
  props.message.feedback = localFeedback.value
  if (localFeedback.value === null) return

  await submitFeedback({
    question: '', // 由调用上下文不易拿到对应 user 问题，留空（后端可选）
    answer: props.message.content,
    liked,
    rewrite: props.message.rewrite,
    refs: props.message.refs,
    verify_status: props.message.verify?.status,
  })
}
</script>

<template>
  <div class="answer-footer">
    <!-- 校验徽章 + 免责 + 反馈 同一行 -->
    <div class="footer-bar">
      <VerifyBadge v-if="message.verify" :verify="message.verify" />
      <div class="spacer" />
      <div class="feedback">
        <button
          class="fb-btn"
          :class="{ active: localFeedback === 'up' }"
          title="有帮助"
          @click="vote(true)"
        >
          <ThumbsUp :size="15" />
        </button>
        <button
          class="fb-btn"
          :class="{ active: localFeedback === 'down' }"
          title="待改进"
          @click="vote(false)"
        >
          <ThumbsDown :size="15" />
        </button>
      </div>
    </div>

    <!-- 校验存疑时的提示 -->
    <p v-if="message.verify?.status === 'warn'" class="verify-warn">
      ⚠ {{ message.verify.message }}
    </p>

    <!-- 引用条文折叠块（仅回答实际引用到的；含未命中提示） -->
    <Collapsible v-if="citedRefs.length || missingLabels.length" accent>
      <template #title>
        引用条文 {{ citedRefs.length }} 条<template v-if="missingLabels.length">（另 {{ missingLabels.length }} 条未命中）</template>
      </template>
      <div class="ref-list">
        <RefCard
          v-for="(r, i) in citedRefs"
          :key="i"
          :reference="r"
          :scope="message.id"
        />
        <!-- 被引用但未检索到：诚实暴露模型知识泄漏 -->
        <div v-if="missingLabels.length" class="missing-note">
          <span class="missing-head">⚠ 以下条文为模型引用，未在检索库中命中：</span>
          <span class="missing-list">{{ missingLabels.join('、') }}</span>
          <span class="missing-tail">无法提供原文，请以官方法律文本为准并核实。</span>
        </div>
      </div>
    </Collapsible>

    <!-- 免责声明 -->
    <p v-if="message.disclaimer" class="disclaimer">{{ message.disclaimer }}</p>
  </div>
</template>

<style scoped>
.answer-footer {
  margin-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.footer-bar {
  display: flex;
  align-items: center;
  gap: 8px;
}
.spacer {
  flex: 1;
}
.feedback {
  display: flex;
  gap: 4px;
}
.fb-btn {
  display: flex;
  padding: 5px;
  background: transparent;
  border: 1px solid transparent;
  border-radius: 6px;
  color: var(--text-tertiary);
  transition: all 0.15s;
}
.fb-btn:hover {
  color: var(--text-primary);
  background: var(--bg-elevated);
}
.fb-btn.active {
  color: var(--accent);
  background: var(--accent-soft);
  border-color: var(--accent);
}
.verify-warn {
  font-size: 0.8rem;
  color: var(--warning);
  background: var(--warning-soft);
  padding: 8px 10px;
  border-radius: var(--radius-sm);
  line-height: 1.6;
}
.ref-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.missing-note {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 8px 10px;
  font-size: 0.78rem;
  line-height: 1.6;
  color: var(--text-secondary);
  background: var(--warning-soft);
  border: 1px dashed var(--warning);
  border-radius: var(--radius-sm);
}
.missing-head {
  color: var(--warning);
  font-weight: 500;
}
.missing-list {
  color: var(--text-primary);
}
.missing-tail {
  color: var(--text-tertiary);
}
.disclaimer {
  font-size: 0.74rem;
  color: var(--text-tertiary);
  line-height: 1.6;
  padding-top: 6px;
  border-top: 1px dashed var(--border);
}
</style>
