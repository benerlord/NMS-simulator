<script setup lang="ts">
import { ref, computed, watch, h } from 'vue'
import { Modal } from 'ant-design-vue'
import NodeTypeFieldEditor from './NodeTypeFieldEditor.vue'
import { nodeTypeApi } from '@/api/types'
import type {
  NodeTypeCreate, NodeTypeUpdate, NodeTypeDetail, NodeTypeFieldInput,
} from '@/api/types'

const CATEGORIES = ['physical', 'virtual', 'cloud', 'application']
const RENDER_MODES = [
  { value: 'none', label: '无' },
  { value: 'flat', label: '扁平' },
]
const SHAPES = [
  { value: 'rect', label: '矩形' },
  { value: 'circle', label: '圆形' },
  { value: 'ellipse', label: '椭圆' },
  { value: 'polygon', label: '多边形' },
]

interface NodeTypeForm {
  code: string
  name: string
  category: string
  icon: string
  color: string
  shape: string
  renderMode: string
  dnTemplate: string
  description: string
  fields: NodeTypeFieldInput[]
}

const props = defineProps<{
  open: boolean
  editing?: NodeTypeDetail | null
  loading?: boolean
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
  create: [data: NodeTypeCreate]
  update: [id: string, data: NodeTypeUpdate]
}>()

const isEdit = computed(() => !!props.editing)

const defaultForm = (): NodeTypeForm => ({
  code: '',
  name: '',
  category: 'physical',
  icon: '',
  color: '',
  shape: '',
  renderMode: 'none',
  dnTemplate: '',
  description: '',
  fields: [],
})

const form = ref<NodeTypeForm>(defaultForm())
const originalFieldKeys = ref<Set<string>>(new Set())

watch(() => props.open, (open) => {
  if (!open) return
  if (props.editing) {
    form.value = {
      code: props.editing.code,
      name: props.editing.name,
      category: props.editing.category,
      icon: props.editing.icon ?? '',
      color: props.editing.color ?? '',
      shape: props.editing.shape ?? '',
      renderMode: props.editing.renderMode,
      dnTemplate: props.editing.dnTemplate ?? '',
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
    h('div', { style: { marginBottom: '8px' } }, '以下字段将被删除，相关节点的属性值会被清除：'),
    ...items.map(it =>
      h('div', { style: { paddingLeft: '12px', color: '#fa541c' } },
        `• ${it.fieldKey}：清除 ${it.affectedNodeCount} 个节点的数据`),
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
    const resp = await nodeTypeApi.getFieldDeleteImpact(props.editing.id, deletedKeys)
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
      icon: form.value.icon || null,
      color: form.value.color || null,
      shape: form.value.shape || null,
      renderMode: form.value.renderMode,
      dnTemplate: form.value.dnTemplate || null,
      description: form.value.description || null,
      fields: form.value.fields,
    })
  } else {
    emit('create', {
      code: form.value.code,
      name: form.value.name,
      category: form.value.category,
      icon: form.value.icon || null,
      color: form.value.color || null,
      shape: form.value.shape || null,
      renderMode: form.value.renderMode,
      dnTemplate: form.value.dnTemplate || null,
      description: form.value.description || null,
      fields: form.value.fields,
    })
  }
}
</script>

<template>
  <a-modal
    :open="open"
    :title="isEdit ? '编辑节点类型' : '新建节点类型'"
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
              placeholder="如: switch"
              :disabled="isEdit"
            />
          </a-form-item>
        </a-col>
        <a-col :span="12">
          <a-form-item label="类型名称" required>
            <a-input v-model:value="form.name" placeholder="如: 交换机" />
          </a-form-item>
        </a-col>
      </a-row>

      <a-row :gutter="16">
        <a-col :span="12">
          <a-form-item label="分类">
            <a-select v-model:value="form.category">
              <a-select-option v-for="cat in CATEGORIES" :key="cat" :value="cat">
                {{ cat }}
              </a-select-option>
            </a-select>
          </a-form-item>
        </a-col>
        <a-col :span="12">
          <a-form-item label="渲染模式">
            <a-select v-model:value="form.renderMode">
              <a-select-option v-for="m in RENDER_MODES" :key="m.value" :value="m.value">
                {{ m.label }}
              </a-select-option>
            </a-select>
          </a-form-item>
        </a-col>
      </a-row>

      <a-row :gutter="16">
        <a-col :span="12">
          <a-form-item label="图标">
            <a-input v-model:value="form.icon" placeholder="可选" />
          </a-form-item>
        </a-col>
        <a-col :span="12">
          <a-form-item label="颜色">
            <a-input v-model:value="form.color" placeholder="如: #1890ff" />
          </a-form-item>
        </a-col>
      </a-row>

      <a-row :gutter="16">
        <a-col :span="12">
          <a-form-item label="形状">
            <a-select v-model:value="form.shape" allowClear placeholder="可选">
              <a-select-option v-for="s in SHAPES" :key="s.value" :value="s.value">
                {{ s.label }}
              </a-select-option>
            </a-select>
          </a-form-item>
        </a-col>
        <a-col :span="12">
          <a-form-item label="DN 模板">
            <a-input v-model:value="form.dnTemplate" placeholder="可选" />
          </a-form-item>
        </a-col>
      </a-row>

      <a-form-item label="描述">
        <a-textarea v-model:value="form.description" :rows="2" placeholder="可选" />
      </a-form-item>
    </a-form>

    <a-divider style="margin: 16px 0">字段配置</a-divider>

    <NodeTypeFieldEditor v-model:fields="form.fields" />
  </a-modal>
</template>
