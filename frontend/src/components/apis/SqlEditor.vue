<script setup lang="ts">
import { shallowRef } from 'vue'
import { Codemirror } from 'vue-codemirror'
import { sql } from '@codemirror/lang-sql'
import { EditorView } from '@codemirror/view'

interface Props {
  modelValue: string
  placeholder?: string
  minHeight?: string
  disabled?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  placeholder: '-- 示例：SELECT * FROM nodes WHERE topology_id = :topology_id',
  minHeight: '140px',
  disabled: false,
})

const emit = defineEmits<{
  (e: 'update:modelValue', v: string): void
}>()

const extensions = [sql(), EditorView.lineWrapping]

const view = shallowRef<EditorView | null>(null)

function onReady(payload: { view: EditorView }) {
  view.value = payload.view
}

function onChange(v: string) {
  emit('update:modelValue', v)
}

function insertAtCursor(text: string) {
  const v = view.value
  if (!v) {
    emit('update:modelValue', (props.modelValue ?? '') + text)
    return
  }
  const { from, to } = v.state.selection.main
  v.dispatch({
    changes: { from, to, insert: text },
    selection: { anchor: from + text.length },
  })
  v.focus()
}

function focus() {
  view.value?.focus()
}

defineExpose({ insertAtCursor, focus })
</script>

<template>
  <div class="sql-editor" :style="{ minHeight: props.minHeight }">
    <Codemirror
      :model-value="props.modelValue"
      :placeholder="props.placeholder"
      :extensions="extensions"
      :disabled="props.disabled"
      :style="{ minHeight: props.minHeight }"
      :indent-with-tab="true"
      :tab-size="2"
      @ready="onReady"
      @update:model-value="onChange"
    />
  </div>
</template>

<style scoped>
.sql-editor {
  border: 1px solid #d9d9d9;
  border-radius: 6px;
  overflow: hidden;
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 13px;
}

.sql-editor:focus-within {
  border-color: #4096ff;
  box-shadow: 0 0 0 2px rgba(5, 145, 255, 0.1);
}

.sql-editor :deep(.cm-editor) {
  outline: none;
}

.sql-editor :deep(.cm-scroller) {
  font-family: 'Consolas', 'Monaco', monospace;
}
</style>
