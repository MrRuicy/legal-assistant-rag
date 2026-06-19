<script setup lang="ts">
import { ref } from 'vue'
import { Plus, MessageSquare, Trash2, Pencil, Check, PanelLeftClose } from 'lucide-vue-next'
import { useSessionsStore } from '@/stores/sessions'

const emit = defineEmits<{ collapse: [] }>()
const store = useSessionsStore()

const editingId = ref('')
const editTitle = ref('')

function startEdit(id: string, title: string) {
  editingId.value = id
  editTitle.value = title
}
function commitEdit() {
  if (editingId.value) store.renameSession(editingId.value, editTitle.value)
  editingId.value = ''
}
</script>

<template>
  <aside class="sidebar">
    <div class="sidebar-top">
      <button class="new-chat" @click="store.createSession()">
        <Plus :size="16" /> 新对话
      </button>
      <button class="collapse-btn" title="收起侧栏" @click="emit('collapse')">
        <PanelLeftClose :size="18" />
      </button>
    </div>

    <nav class="session-list">
      <div
        v-for="s in store.sessions"
        :key="s.id"
        class="session-item"
        :class="{ active: s.id === store.currentSessionId }"
        @click="store.selectSession(s.id)"
      >
        <MessageSquare :size="15" class="sess-icon" />
        <template v-if="editingId === s.id">
          <input
            v-model="editTitle"
            class="rename-input"
            @keydown.enter="commitEdit"
            @blur="commitEdit"
            @click.stop
          />
          <button class="row-act" @click.stop="commitEdit"><Check :size="14" /></button>
        </template>
        <template v-else>
          <span class="sess-title">{{ s.title }}</span>
          <span class="row-actions">
            <button class="row-act" title="重命名" @click.stop="startEdit(s.id, s.title)">
              <Pencil :size="13" />
            </button>
            <button class="row-act" title="删除" @click.stop="store.deleteSession(s.id)">
              <Trash2 :size="13" />
            </button>
          </span>
        </template>
      </div>
    </nav>

    <div class="sidebar-foot">
      <span class="foot-text">⚖️ 法律助手 v2.0</span>
    </div>
  </aside>
</template>

<style scoped>
.sidebar {
  width: 260px;
  flex-shrink: 0;
  background: var(--bg-sidebar);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  height: 100%;
}
.sidebar-top {
  display: flex;
  gap: 8px;
  padding: 12px;
}
.new-chat {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 10px;
  background: var(--accent-soft);
  border: 1px solid var(--accent);
  border-radius: var(--radius-md);
  color: var(--accent);
  font-weight: 500;
  font-size: 0.9rem;
  transition: all 0.15s;
}
.new-chat:hover {
  background: var(--accent);
  color: #fff;
}
.collapse-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  background: transparent;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  color: var(--text-secondary);
}
.collapse-btn:hover {
  color: var(--text-primary);
  background: var(--bg-elevated);
}
.session-list {
  flex: 1;
  overflow-y: auto;
  padding: 0 8px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.session-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 9px 10px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  color: var(--text-secondary);
  font-size: 0.86rem;
  transition: background 0.12s;
}
.session-item:hover {
  background: var(--bg-elevated);
  color: var(--text-primary);
}
.session-item.active {
  background: var(--bg-elevated);
  color: var(--text-primary);
}
.sess-icon {
  flex-shrink: 0;
  opacity: 0.7;
}
.sess-title {
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.row-actions {
  display: none;
  gap: 2px;
}
.session-item:hover .row-actions {
  display: flex;
}
.row-act {
  display: flex;
  padding: 3px;
  background: transparent;
  border: none;
  color: var(--text-tertiary);
  border-radius: 4px;
}
.row-act:hover {
  color: var(--text-primary);
  background: var(--bg-surface);
}
.rename-input {
  flex: 1;
  background: var(--bg-base);
  border: 1px solid var(--accent);
  border-radius: 4px;
  color: var(--text-primary);
  font-size: 0.84rem;
  padding: 3px 6px;
  outline: none;
}
.sidebar-foot {
  padding: 12px;
  border-top: 1px solid var(--border);
}
.foot-text {
  font-size: 0.74rem;
  color: var(--text-tertiary);
}
</style>
