<script setup lang="ts">
import { ref, computed, watch, h } from 'vue'
import { Modal } from 'ant-design-vue'
import EdgeTypeFieldEditor from './EdgeTypeFieldEditor.vue'
import { edgeTypeApi } from '@/api/types'
import type {
  EdgeTypeCreate, EdgeTypeUpdate, EdgeTypeDetail, EdgeTypeFieldInput,
} from '@/api/types'

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
  fields: EdgeTypeFieldInput[]
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
  fields: [],
})

const form = ref<EdgeTypeForm>(defaultForm())
const originalFieldKeys = ref<Set<string>>(new Set())

watch(() => props.open, (open) => {
  if (!open) return
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
      fields: (props.editing.fields ?? []).map(f => ({
        fieldKey: f.fieldKey,
        fieldLabel: f.fieldLabel,
        fieldType: f.fieldType,
        maxLength: f.maxLength,
        defaultValue: f.defaultValue,
        options: f.options,
        required: f.required,
        sortOrder: f.sortOrder,
      })),
    }
    originalFieldKeys.value = new Set(form.value.fields.map(f => f.fieldKey))
  } else {
    form.value = defaultForm()
    originalFieldKeys.value = new Set()
  }
})

function close() {
  emit('update:open', false)
}

function buildImpactContent(items: Array<{ fieldKey: string; affectedNodeCount: number }>) {
  return h('div', { style: { lineHeight: '1.8' } }, [
    h('div', { style: { marginBottom: '8px' } }, '以下字段将被删除，相关边的属性值会被清除：'),
    ...items.map(it =>
      h('div', { style: { paddingLeft: '12px', color: '#fa541c' } },
        `• ${it.fieldKey}：清除 ${it.affectedNodeCount} 条边的数据`),
    ),
    h('div', { style: { marginTop: '8px', color: '#999' } }, '此操作不可撤销，确定继续？'),
  ])
}

async function confirmDeleteImpactIfAny(): Promise<boolean> {
  if (!props.editing) return true
  const currentKeys = new Set(form.value.fields.map(f => f.fieldKey))
  const deletedKeys = [...originalFieldKeys.value].filter(k => !currentKeys.has(k))
  if (deletedKeys.length === 0) return true

  try {
    const resp = await edgeTypeApi.getFieldDeleteImpact(props.editing.id, deletedKeys)
    const nonEmpty = resp.items.filter(it => it.affectedNodeCount > 0)
    if (nonEmpty.length === 0) return true

    return await new Promise<boolean>((resolve) => {
      Modal.confirm({
        title: '确认删除字段',
        content: buildImpactContent(nonEmpty),
        okText: '确认删除',
        cancelText: '取消',
        okType: 'danger',
        width: 480,
        onOk: () => resolve(true),
        onCancel: () => resolve(false),
      })
    })
  } catch {
    return false
  }
}

async function submit() {
  const ok = await confirmDeleteImpactIfAny()
  if (!ok) return

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
      fields: form.value.fields,
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
      fields: form.value.fields,
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
    width="880px"
    :styles="{ body: { maxHeight: 'calc(100vh - 200px)', overflowY: 'auto' } }"
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

    <a-divider style="margin: 16px 0">字段配置</a-divider>

    <EdgeTypeFieldEditor v-model:fields="form.fields" />
  </a-modal>
</template>
