<script setup lang="ts">
import { computed } from 'vue'
import {
  Table, Input, InputNumber, Select, Switch, Button, Tooltip, Affix, message,
} from 'ant-design-vue'
import {
  PlusOutlined, DeleteOutlined, ArrowUpOutlined, ArrowDownOutlined,
} from '@ant-design/icons-vue'
import type { EdgeTypeFieldInput } from '@/api/types'

const props = defineProps<{
  fields: EdgeTypeFieldInput[]
}>()

const emit = defineEmits<{
  (e: 'update:fields', v: EdgeTypeFieldInput[]): void
}>()

const localFields = computed({
  get: () => props.fields,
  set: (v) => emit('update:fields', v),
})

function addField() {
  const newField: EdgeTypeFieldInput = {
    fieldKey: '',
    fieldLabel: '',
    fieldType: 'text',
    maxLength: 50,
    defaultValue: undefined,
    options: undefined,
    required: false,
    sortOrder: localFields.value.length,
  }
  emit('update:fields', [...localFields.value, newField])
}

function removeField(index: number) {
  emit('update:fields', localFields.value.filter((_, i) => i !== index))
}

function moveUp(index: number) {
  if (index === 0) return
  const next = [...localFields.value]
  ;[next[index - 1], next[index]] = [next[index], next[index - 1]]
  emit('update:fields', next)
}

function moveDown(index: number) {
  if (index === localFields.value.length - 1) return
  const next = [...localFields.value]
  ;[next[index], next[index + 1]] = [next[index + 1], next[index]]
  emit('update:fields', next)
}

function updateField(index: number, key: keyof EdgeTypeFieldInput, value: any) {
  const next = [...localFields.value]
  next[index] = { ...next[index], [key]: value }
  emit('update:fields', next)
}

function validateArrayDefault(field: EdgeTypeFieldInput) {
  if (field.fieldType !== 'array' || !field.defaultValue) return
  try {
    const v = JSON.parse(field.defaultValue)
    if (!Array.isArray(v)) {
      message.warning('默认值必须是 JSON array')
    }
  } catch {
    message.warning('默认值 JSON 语法错误')
  }
}

// field_key 已填则禁止编辑（不可变约束 — rename 需"删旧+加新"）
function isFieldKeyLocked(field: EdgeTypeFieldInput): boolean {
  return !!field.fieldKey && field.fieldKey.length > 0
}

const columns = [
  { title: 'Key', dataIndex: 'fieldKey', key: 'fieldKey', width: 120 },
  { title: 'Label', dataIndex: 'fieldLabel', key: 'fieldLabel', width: 140 },
  { title: 'Type', dataIndex: 'fieldType', key: 'fieldType', width: 100 },
  { title: 'MaxLen', dataIndex: 'maxLength', key: 'maxLength', width: 80 },
  { title: 'Default', dataIndex: 'defaultValue', key: 'defaultValue', width: 100 },
  { title: 'Options', dataIndex: 'options', key: 'options', width: 120 },
  { title: 'Required', dataIndex: 'required', key: 'required', width: 70 },
  { title: '操作', key: 'actions', width: 100, fixed: 'right' as const },
]
</script>

<template>
  <div class="edge-type-field-editor">
    <Affix :offset-top="0">
      <div class="toolbar toolbar-top">
        <Button type="primary" size="small" @click="addField">
          <PlusOutlined /> 新增字段
        </Button>
        <span class="hint">{{ localFields.length }} 个字段</span>
      </div>
    </Affix>

    <Table
      :columns="columns"
      :data-source="localFields"
      :pagination="false"
      :row-key="(_record: EdgeTypeFieldInput, index?: number) => `row-${index}`"
      size="small"
      :scroll="{ x: 900 }"
    >
      <template #bodyCell="{ column, index, record }">
        <template v-if="column.key === 'fieldKey'">
          <Input
            :value="record.fieldKey"
            size="small"
            placeholder="key"
            :disabled="isFieldKeyLocked(record)"
            @update:value="(v: string) => updateField(index, 'fieldKey', v)"
          />
        </template>
        <template v-else-if="column.key === 'fieldLabel'">
          <Input
            :value="record.fieldLabel"
            size="small"
            placeholder="标签"
            @update:value="(v: string) => updateField(index, 'fieldLabel', v)"
          />
        </template>
        <template v-else-if="column.key === 'fieldType'">
          <Select
            :value="record.fieldType"
            size="small"
            style="width: 100%"
            @change="(v: any) => updateField(index, 'fieldType', v)"
          >
            <Select.Option value="text">text</Select.Option>
            <Select.Option value="number">number</Select.Option>
            <Select.Option value="select">select</Select.Option>
            <Select.Option value="boolean">boolean</Select.Option>
            <Select.Option value="array">array</Select.Option>
          </Select>
        </template>
        <template v-else-if="column.key === 'maxLength'">
          <InputNumber
            :value="record.maxLength"
            size="small"
            :min="1"
            :disabled="record.fieldType !== 'text'"
            style="width: 100%"
            @change="(v: any) => updateField(index, 'maxLength', v)"
          />
        </template>
        <template v-else-if="column.key === 'defaultValue'">
          <Input
            :value="record.defaultValue || ''"
            size="small"
            :placeholder="record.fieldType === 'array' ? 'JSON: [&quot;a&quot;,&quot;b&quot;]' : '默认值'"
            @update:value="(v: string) => updateField(index, 'defaultValue', v || null)"
            @blur="() => validateArrayDefault(record)"
          />
        </template>
        <template v-else-if="column.key === 'options'">
          <Tooltip :title="record.options">
            <Input
              :value="record.options || ''"
              size="small"
              placeholder="opt1,opt2"
              :disabled="record.fieldType !== 'select'"
              @update:value="(v: string) => updateField(index, 'options', v || null)"
            />
          </Tooltip>
        </template>
        <template v-else-if="column.key === 'required'">
          <Switch
            :checked="!!record.required"
            size="small"
            @change="(v: any) => updateField(index, 'required', v)"
          />
        </template>
        <template v-else-if="column.key === 'actions'">
          <div class="action-buttons">
            <Button type="text" size="small" :disabled="index === 0" @click="moveUp(index)">
              <ArrowUpOutlined />
            </Button>
            <Button type="text" size="small" :disabled="index === localFields.length - 1" @click="moveDown(index)">
              <ArrowDownOutlined />
            </Button>
            <Button type="text" size="small" danger @click="removeField(index)">
              <DeleteOutlined />
            </Button>
          </div>
        </template>
      </template>
    </Table>

    <div class="toolbar toolbar-bottom">
      <Button type="primary" size="small" @click="addField">
        <PlusOutlined /> 新增字段
      </Button>
    </div>
  </div>
</template>

<style scoped>
.edge-type-field-editor { display: flex; flex-direction: column; }
.toolbar { display: flex; align-items: center; gap: 12px; padding: 8px 0; background: #fff; z-index: 10; }
.toolbar-top { border-bottom: 1px solid #f0f0f0; }
.toolbar-bottom { border-top: 1px solid #f0f0f0; margin-top: 8px; }
.hint { color: #999; font-size: 12px; }
.action-buttons { display: flex; gap: 2px; }
</style>
