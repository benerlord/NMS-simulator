<script setup lang="ts">
import { computed } from 'vue'
import { PlusOutlined, DeleteOutlined, ArrowUpOutlined, ArrowDownOutlined } from '@ant-design/icons-vue'
import type { AlarmSchemaFieldInput } from '@/api/alarmSchema'

const props = defineProps<{
  fields: AlarmSchemaFieldInput[]
}>()

const emit = defineEmits<{
  (e: 'update:fields', v: AlarmSchemaFieldInput[]): void
}>()

const FIELD_TYPES = [
  { value: 'text', label: '文本 (text)' },
  { value: 'number', label: '数字 (number)' },
  { value: 'select', label: '下拉 (select)' },
  { value: 'boolean', label: '布尔 (boolean)' },
] as const

function update(index: number, patch: Partial<AlarmSchemaFieldInput>) {
  const next = props.fields.map((f, i) => (i === index ? { ...f, ...patch } : f))
  emit('update:fields', next)
}

function addField() {
  const sortOrder = props.fields.length > 0 ? Math.max(...props.fields.map(f => f.sortOrder ?? 0)) + 1 : 0
  emit('update:fields', [
    ...props.fields,
    {
      fieldKey: '',
      fieldLabel: '',
      fieldType: 'text',
      maxLength: null,
      defaultValue: null,
      options: null,
      required: false,
      sortOrder,
    },
  ])
}

function removeField(index: number) {
  emit('update:fields', props.fields.filter((_, i) => i !== index))
}

function moveUp(index: number) {
  if (index === 0) return
  const next = [...props.fields]
  ;[next[index - 1], next[index]] = [next[index], next[index - 1]]
  emit('update:fields', next)
}

function moveDown(index: number) {
  if (index >= props.fields.length - 1) return
  const next = [...props.fields]
  ;[next[index], next[index + 1]] = [next[index + 1], next[index]]
  emit('update:fields', next)
}

function isText(f: AlarmSchemaFieldInput) {
  return f.fieldType === 'text'
}

function isSelect(f: AlarmSchemaFieldInput) {
  return f.fieldType === 'select'
}
</script>

<template>
  <div class="alarm-field-editor">
    <div class="field-editor-header">
      <span class="field-title">告警字段</span>
      <a-button type="dashed" size="small" @click="addField">
        <template #icon><PlusOutlined /></template>
        添加字段
      </a-button>
    </div>

    <div v-if="fields.length === 0" class="empty-tip">暂无字段，点击"添加字段"开始配置</div>

    <div v-for="(field, index) in fields" :key="index" class="field-row">
      <div class="field-row-header">
        <span class="field-index">字段 {{ index + 1 }}</span>
        <a-space size="small">
          <a-button type="text" size="small" :disabled="index === 0" @click="moveUp(index)">
            <template #icon><ArrowUpOutlined /></template>
          </a-button>
          <a-button type="text" size="small" :disabled="index === fields.length - 1" @click="moveDown(index)">
            <template #icon><ArrowDownOutlined /></template>
          </a-button>
          <a-button type="text" size="small" danger @click="removeField(index)">
            <template #icon><DeleteOutlined /></template>
          </a-button>
        </a-space>
      </div>

      <a-row :gutter="12">
        <a-col :span="8">
          <a-form-item label="字段标识" :colon="false" class="compact-form-item">
            <a-input
              :value="field.fieldKey"
              placeholder="如: severity"
              @update:value="(v: string) => update(index, { fieldKey: v })"
            />
          </a-form-item>
        </a-col>
        <a-col :span="8">
          <a-form-item label="显示名称" :colon="false" class="compact-form-item">
            <a-input
              :value="field.fieldLabel"
              placeholder="如: 告警级别"
              @update:value="(v: string) => update(index, { fieldLabel: v })"
            />
          </a-form-item>
        </a-col>
        <a-col :span="8">
          <a-form-item label="字段类型" :colon="false" class="compact-form-item">
            <a-select
              :value="field.fieldType"
              @update:value="(v: 'text' | 'number' | 'select' | 'boolean') => update(index, { fieldType: v, maxLength: null, options: null })"
            >
              <a-select-option v-for="ft in FIELD_TYPES" :key="ft.value" :value="ft.value">
                {{ ft.label }}
              </a-select-option>
            </a-select>
          </a-form-item>
        </a-col>
      </a-row>

      <a-row :gutter="12">
        <a-col v-if="isText(field)" :span="8">
          <a-form-item label="最大长度" :colon="false" class="compact-form-item">
            <a-input-number
              :value="field.maxLength ?? undefined"
              :min="1"
              :precision="0"
              placeholder="如: 200"
              style="width: 100%"
              @update:value="(v: number | null) => update(index, { maxLength: v })"
            />
          </a-form-item>
        </a-col>
        <a-col v-if="isSelect(field)" :span="12">
          <a-form-item label="选项列表" :colon="false" class="compact-form-item">
            <a-input
              :value="field.options ?? ''"
              placeholder="逗号分隔，如: 紧急,严重,一般"
              @update:value="(v: string) => update(index, { options: v || null })"
            />
          </a-form-item>
        </a-col>
        <a-col :span="8">
          <a-form-item label="默认值" :colon="false" class="compact-form-item">
            <a-input
              :value="field.defaultValue ?? ''"
              placeholder="可选"
              @update:value="(v: string) => update(index, { defaultValue: v || null })"
            />
          </a-form-item>
        </a-col>
        <a-col :span="4">
          <a-form-item label="排序" :colon="false" class="compact-form-item">
            <a-input-number
              :value="field.sortOrder ?? 0"
              :min="0"
              style="width: 100%"
              @update:value="(v: number | null) => update(index, { sortOrder: v ?? 0 })"
            />
          </a-form-item>
        </a-col>
        <a-col :span="4">
          <a-form-item label="必填" :colon="false" class="compact-form-item">
            <a-switch
              :checked="field.required ?? false"
              @update:checked="(v: boolean) => update(index, { required: v })"
            />
          </a-form-item>
        </a-col>
      </a-row>
    </div>
  </div>
</template>

<style scoped>
.alarm-field-editor {
  border: 1px solid #d9d9d9;
  border-radius: 6px;
  padding: 12px;
  background: #fafafa;
}

.field-editor-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.field-title {
  font-weight: 500;
  color: rgba(0, 0, 0, 0.85);
}

.empty-tip {
  text-align: center;
  color: rgba(0, 0, 0, 0.45);
  padding: 16px 0;
  font-size: 13px;
}

.field-row {
  border: 1px solid #e8e8e8;
  border-radius: 4px;
  padding: 12px 12px 0;
  margin-bottom: 10px;
  background: #fff;
}

.field-row-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.field-index {
  font-size: 12px;
  color: rgba(0, 0, 0, 0.45);
  font-weight: 500;
}

.compact-form-item {
  margin-bottom: 8px;
}
</style>
