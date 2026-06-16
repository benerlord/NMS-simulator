<script setup lang="ts">
import { computed } from 'vue'
import { Input } from 'ant-design-vue'

const props = defineProps<{
  value: string
  placeholder?: string
}>()

const emit = defineEmits<{
  (e: 'update:value', v: string): void
}>()

const parseError = computed(() => {
  const v = props.value
  if (!v) return ''
  try {
    const parsed = JSON.parse(v)
    if (!Array.isArray(parsed)) return '必须是 JSON array（如 ["a","b"]）'
    return ''
  } catch {
    return 'JSON 语法错误'
  }
})

function handleInput(e: Event) {
  emit('update:value', (e.target as HTMLTextAreaElement).value)
}
</script>

<template>
  <div class="array-json-input">
    <Input.TextArea
      :value="value"
      :placeholder="placeholder"
      :auto-size="{ minRows: 2, maxRows: 6 }"
      :status="parseError ? 'error' : undefined"
      @input="handleInput"
    />
    <div v-if="parseError" class="error-hint">{{ parseError }}</div>
  </div>
</template>

<style scoped>
.array-json-input {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.error-hint {
  font-size: 12px;
  color: #ff4d4f;
}
</style>
