<script setup lang="ts">
import { ref, computed } from 'vue'
import { PlusOutlined, DeleteOutlined, EditOutlined } from '@ant-design/icons-vue'
import type { EdgeTypeFieldItem, EdgeTypeFieldCreate, EdgeTypeFieldUpdate } from '@/api/types'

const props = defineProps<{
  fields: EdgeTypeFieldItem[]
  loading?: boolean
}>()

const emit = defineEmits<{
  create: [data: EdgeTypeFieldCreate]
  update: [fieldId: number, data: EdgeTypeFieldUpdate]
  delete: [fieldId: number]
}>()

const FIELD_TYPES = [
  { value: 'text', label: '文本 (text)' },
  { value: 'number', label: '数字 (number)' },
  { value: 'select', label: '下拉 (select)' },
  { value: 'boolean', label: '布尔 (boolean)' },
] as const

interface FieldForm {
  fieldKey: string
  fieldLabel: string
  fieldType: 'text' | 'number' | 'select' | 'boolean'
  defaultValue: string
  options: string
  required: boolean
  sortOrder: number
}

const editingId = ref<number | null>(null)
const formData = ref<FieldForm>({
  fieldKey: '',
  fieldLabel: '',
  fieldType: 'text',
  defaultValue: '',
  options: '',
  required: false,
  sortOrder: 0,
})
const showForm = ref(false)

const isSelect = computed(() => formData.value.fieldType === 'select')

function openCreate() {
  editingId.value = null
  formData.value = {
    fieldKey: '',
    fieldLabel: '',
    fieldType: 'text',
    defaultValue: '',
    options: '',
    required: false,
    sortOrder: 0,
  }
  showForm.value = true
}

function openEdit(field: EdgeTypeFieldItem) {
  editingId.value = field.id
  formData.value = {
    fieldKey: field.fieldKey,
    fieldLabel: field.fieldLabel,
    fieldType: field.fieldType,
    defaultValue: field.defaultValue ?? '',
    options: field.options ?? '',
    required: field.required,
    sortOrder: field.sortOrder,
  }
  showForm.value = true
}

function cancelEdit() {
  showForm.value = false
  editingId.value = null
}

function submitForm() {
  if (editingId.value) {
    emit('update', editingId.value, {
      fieldLabel: formData.value.fieldLabel,
      fieldType: formData.value.fieldType,
      defaultValue: formData.value.defaultValue || null,
      options: formData.value.options || null,
      required: formData.value.required,
      sortOrder: formData.value.sortOrder,
    })
  } else {
    emit('create', {
      fieldKey: formData.value.fieldKey,
      fieldLabel: formData.value.fieldLabel,
      fieldType: formData.value.fieldType,
      defaultValue: formData.value.defaultValue || null,
      options: formData.value.options || null,
      required: formData.value.required,
      sortOrder: formData.value.sortOrder,
    })
  }
  cancelEdit()
}
</script>

<template>
  <div class="field-editor">
    <div class="field-header">
      <span class="field-title">字段配置</span>
      <a-button type="dashed" size="small" :loading="loading" @click="openCreate">
        <template #icon><PlusOutlined /></template>
        添加字段
      </a-button>
    </div>

    <a-table
      :dataSource="fields"
      :pagination="false"
      size="small"
      :loading="loading"
      rowKey="id"
    >
      <a-table-column title="字段标识" dataIndex="fieldKey" width="120" />
      <a-table-column title="显示名称" dataIndex="fieldLabel" width="140" />
      <a-table-column title="类型" dataIndex="fieldType" width="100">
        <template #default="{ text }">
          <a-tag>{{ text }}</a-tag>
        </template>
      </a-table-column>
      <a-table-column title="必填" dataIndex="required" width="60">
        <template #default="{ text }">
          <a-tag :color="text ? 'red' : 'default'">{{ text ? '是' : '否' }}</a-tag>
        </template>
      </a-table-column>
      <a-table-column title="默认值" dataIndex="defaultValue" width="100">
        <template #default="{ text }">
          <span class="field-default">{{ text ?? '-' }}</span>
        </template>
      </a-table-column>
      <a-table-column title="选项" dataIndex="options" width="120">
        <template #default="{ text }">
          <span class="field-options">{{ text ?? '-' }}</span>
        </template>
      </a-table-column>
      <a-table-column title="排序" dataIndex="sortOrder" width="60" />
      <a-table-column title="操作" width="100" fixed="right">
        <template #default="{ record }">
          <a-space>
            <a-button type="link" size="small" @click="openEdit(record)">
              <template #icon><EditOutlined /></template>
            </a-button>
            <a-popconfirm
              title="确定删除该字段？"
              ok-text="确定"
              cancel-text="取消"
              @confirm="emit('delete', record.id)"
            >
              <a-button type="link" size="small" danger :loading="loading">
                <template #icon><DeleteOutlined /></template>
              </a-button>
            </a-popconfirm>
          </a-space>
        </template>
      </a-table-column>
    </a-table>

    <a-modal
      v-model:open="showForm"
      :title="editingId ? '编辑字段' : '添加字段'"
      @ok="submitForm"
      ok-text="确定"
      cancel-text="取消"
      width="480px"
    >
      <a-form layout="vertical">
        <a-form-item v-if="!editingId" label="字段标识" required>
          <a-input v-model:value="formData.fieldKey" placeholder="如: bandwidth" />
        </a-form-item>
        <a-form-item label="显示名称" required>
          <a-input v-model:value="formData.fieldLabel" placeholder="如: 带宽" />
        </a-form-item>
        <a-form-item label="字段类型" required>
          <a-select v-model:value="formData.fieldType">
            <a-select-option v-for="ft in FIELD_TYPES" :key="ft.value" :value="ft.value">
              {{ ft.label }}
            </a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item v-if="isSelect" label="选项列表">
          <a-input v-model:value="formData.options" placeholder="用逗号分隔，如: 100M,1G,10G" />
        </a-form-item>
        <a-form-item label="默认值">
          <a-input v-model:value="formData.defaultValue" placeholder="可选" />
        </a-form-item>
        <a-form-item label="排序">
          <a-input-number v-model:value="formData.sortOrder" :min="0" style="width: 100%" />
        </a-form-item>
        <a-form-item label="必填">
          <a-switch v-model:checked="formData.required" />
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<style scoped>
.field-editor {
  margin-top: 16px;
}

.field-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.field-title {
  font-weight: 500;
  color: rgba(0, 0, 0, 0.85);
}

.field-default,
.field-options {
  max-width: 100px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  display: block;
  font-size: 12px;
  color: rgba(0, 0, 0, 0.45);
}
</style>
