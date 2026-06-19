<script setup lang="ts">
import {
  Dialog,
  DialogPanel,
  DialogTitle,
  TransitionRoot,
  TransitionChild,
} from '@headlessui/vue'
import { X } from 'lucide-vue-next'

defineProps<{ open: boolean; title?: string }>()
const emit = defineEmits<{ close: [] }>()
</script>

<template>
  <TransitionRoot :show="open" as="template">
    <Dialog class="modal-root" @close="emit('close')">
      <TransitionChild
        as="template"
        enter="transition-opacity duration-200"
        enter-from="opacity-0"
        enter-to="opacity-100"
        leave="transition-opacity duration-150"
        leave-from="opacity-100"
        leave-to="opacity-0"
      >
        <div class="modal-overlay" aria-hidden="true" />
      </TransitionChild>

      <div class="modal-wrap">
        <TransitionChild
          as="template"
          enter="transition duration-200"
          enter-from="opacity-0 scale-95"
          enter-to="opacity-100 scale-100"
          leave="transition duration-150"
          leave-from="opacity-100 scale-100"
          leave-to="opacity-0 scale-95"
        >
          <DialogPanel class="modal-panel">
            <div class="modal-head">
              <DialogTitle class="modal-title">{{ title }}</DialogTitle>
              <button class="modal-close" type="button" @click="emit('close')">
                <X :size="18" />
              </button>
            </div>
            <div class="modal-body">
              <slot />
            </div>
          </DialogPanel>
        </TransitionChild>
      </div>
    </Dialog>
  </TransitionRoot>
</template>

<style scoped>
.modal-root {
  position: relative;
  z-index: 50;
}
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.55);
  backdrop-filter: blur(2px);
}
.modal-wrap {
  position: fixed;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
}
.modal-panel {
  width: 100%;
  max-width: 460px;
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
  overflow: hidden;
}
.modal-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 20px;
  border-bottom: 1px solid var(--border);
}
.modal-title {
  font-size: 1.05rem;
  font-weight: 600;
  color: var(--text-primary);
}
.modal-close {
  display: flex;
  background: transparent;
  border: none;
  color: var(--text-secondary);
  padding: 4px;
  border-radius: 6px;
}
.modal-close:hover {
  background: var(--bg-elevated);
  color: var(--text-primary);
}
.modal-body {
  padding: 20px;
}
</style>
