<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import type { EdgeTypeCreate, EdgeTypeUpdate, EdgeTypeDetail } from '@/api/types'

const SEMANTICS = [
  { value: 'connect', label: '连接 (connect)' },
  { value: 'contain', label: '包含 (contain)' },
]

const LINE_STYLES = [
  { value: 'solid', label: '实线' },
  { value: 'dashed', label: '虚线' },
  { value: 'dotted', label: '点线' },
]

interface EdgeTypeForm {
  code: string
  name: string
  semantic: string
  directed: boolean
  exclusiveTarget: boolean
  allowSourceTypeCodes: string
  allowTargetTypeCodes: string
  lineStyle: string
  color: string
  description: string
}

const props = defineProps<{
  open: boolean
  editing?: EdgeTypeDetail | null
  loading?: boolean
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
  create: [data: EdgeTypeCreate]
  update: [id: string, data: EdgeTypeUpdate]
}>()

const isEdit = computed(() => !!props.editing)

const defaultForm = (): EdgeTypeForm => ({
  code: '',
  name: '',
  semantic: 'connect',
  directed: true,
  exclusiveTarget: false,
  allowSourceTypeCodes: '',
  allowTargetTypeCodes: '',
  lineStyle: '',
  color: '',
  description: '',
})

const form = ref<EdgeTypeForm>(defaultForm())

watch(() => props.open, (open) => {
  if (open) {
    if (props.editing) {
      form.value = {
        code: props.editing.code,
        name: props.editing.name,
        semantic: props.editing.semantic,
        directed: props.editing.directed,
        exclusiveTarget: props.editing.exclusiveTarget,
        allowSourceTypeCodes: props.editing.allowSourceTypeCodes ?? '',
        allowTargetTypeCodes: props.editing.allowTargetTypeCodes ?? '',
        lineStyle: props.editing.lineStyle ?? '',
        color: props.editing.color ?? '',
        description: props.editing.description ?? '',
      }
    } else {
      form.value = defaultForm()
    }
  }
})

function close() {
  emit('update:open', false)
}

function submit() {
  if (isEdit.value && props.editing) {
    emit('update', props.editing.id, {
      name: form.value.name,
      semantic: form.value.semantic,
      directed: form.value.directed,
      exclusiveTarget: form.value.exclusiveTarget,
      allowSourceTypeCodes: form.value.allowSourceTypeCodes || null,
      allowTargetTypeCodes: form.value.allowTargetTypeCodes || null,
      lineStyle: form.value.lineStyle || null,
      color: form.value.color || null,
      description: form.value.description || null,
    })
  } else {
    emit('create', {
      code: form.value.code,
      name: form.value.name,
      semantic: form.value.semantic,
      directed: form.value.directed,
      exclusiveTarget: form.value.exclusiveTarget,
      allowSourceTypeCodes: form.value.allowSourceTypeCodes || null,
      allowTargetTypeCodes: form.value.allowTargetTypeCodes || null,
      lineStyle: form.value.lineStyle || null,
      color: form.value.color || null,
      description: form.value.description || null,
    })
  }
}
</script>

<template>
  <a-modal
    :open="open"
    :title="isEdit ? '编辑边类型' : '新建边类型'"
    :confirm-loading="loading"
    @ok="submit"
    @cancel="close"
    ok-text="确定"
    cancel-text="取消"
    width="600px"
  >
    <a-form layout="vertical">
      <a-row :gutter="16">
        <a-col :span="12">
          <a-form-item label="类型代码" required>
            <a-input
              v-model:value="form.code"
              placeholder="如: physical_link"
              :disabled="isEdit"
            />
          </a-form-item>
        </a-col>
        <a-col :span="12">
          <a-form-item label="类型名称" required>
            <a-input v-model:value="form.name" placeholder="如: 物理链路" />
          </a-form-item>
        </a-col>
      </a-row>

      <a-row :gutter="16">
        <a-col :span="12">
          <a-form-item label="语义">
            <a-select v-model:value="form.semantic">
              <a-select-option v-for="s in SEMANTICS" :key="s.value" :value="s.value">
                {{ s.label }}
              </a-select-option>
            </a-select>
          </a-form-item>
        </a-col>
        <a-col :span="12">
          <a-form-item label="线条样式">
            <a-select v-model:value="form.lineStyle" allowClear placeholder="可选">
              <a-select-option v-for="ls in LINE_STYLES" :key="ls.value" :value="ls.value">
                {{ ls.label }}
              </a-select-option>
            </a-select>
          </a-form-item>
        </a-col>
      </a-row>

      <a-row :gutter="16">
        <a-col :span="12">
          <a-form-item label="颜色">
            <a-input v-model:value="form.color" placeholder="如: #1890ff" />
          </a-form-item>
        </a-col>
        <a-col :span="12">
          <a-form-item label="允许源类型">
            <a-input v-model:value="form.allowSourceTypeCodes" placeholder="逗号分隔，如: switch,router" />
          </a-form-item>
        </a-col>
      </a-row>

      <a-row :gutter="16">
        <a-col :span="12">
          <a-form-item label="允许目标类型">
            <a-input v-model:value="form.allowTargetTypeCodes" placeholder="逗号分隔，如: switch,router" />
          </a-form-item>
        </a-col>
        <a-col :span="12">
          <a-form-item label="属性">
            <a-space direction="vertical" :size="4">
              <a-checkbox v-model:checked="form.directed">有向边</a-checkbox>
              <a-checkbox v-model:checked="form.exclusiveTarget">目标唯一 (exclusive_target)</a-checkbox>
            </a-space>
          </a-form-item>
        </a-col>
      </a-row>

      <a-form-item label="描述">
        <a-textarea v-model:value="form.description" :rows="2" placeholder="可选" />
      </a-form-item>
    </a-form>
  </a-modal>
</template>
