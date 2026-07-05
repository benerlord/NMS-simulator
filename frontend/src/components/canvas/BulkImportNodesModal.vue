<script setup lang="ts">
import { ref, computed, watch, onBeforeUnmount } from 'vue'
import { Modal, Input, Select, InputNumber, Button, Alert, Form, message } from 'ant-design-vue'
import BulkImportPreview from './BulkImportPreview.vue'
import { parseBulkJson, buildBulkPreview } from '@/utils/jsonBulkNodes'
import type { BulkPreview } from '@/utils/jsonBulkNodes'
import { nodeApi } from '@/api/node'
import type { NodeTypeDetail, NodeTypeFieldItem } from '@/api/types'
import type { FieldLike } from '@/utils/jsonFieldMatch'

interface Props {
  open: boolean
  topologyId: string
  nodeType: NodeTypeDetail | null
  defaultStartX: number
  defaultStartY: number
  existingNames: string[]
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'update:open', v: boolean): void
  (e: 'imported', createdIds: string[]): void
}>()

const step = ref<1 | 2>(1)
const jsonText = ref('')
const nameKey = ref<string>('__auto__')
const startX = ref(0)
const startY = ref(0)
const cols = ref(6)
const parseError = ref('')
const preview = ref<BulkPreview | null>(null)
const submitting = ref(false)

const fields = computed<FieldLike[]>(() => {
  const src = (props.nodeType?.fields ?? []) as NodeTypeFieldItem[]
  return src.map((f) => ({
    fieldKey: f.fieldKey,
    fieldLabel: f.fieldLabel,
    fieldType: f.fieldType as FieldLike['fieldType'],
    maxLength: f.maxLength ?? null,
    defaultValue: f.defaultValue ?? null,
    options: f.options ?? null,
    required: !!f.required,
    sortOrder: f.sortOrder ?? 0,
  }))
})

const parsedItems = ref<Record<string, unknown>[]>([])

const nameKeyOptions = computed(() => {
  const opts = [{ value: '__auto__', label: `自动生成 ${props.nodeType?.name ?? ''}_<idx>` }]
  if (parsedItems.value.length > 0) {
    const first = parsedItems.value[0]
    for (const k of Object.keys(first)) {
      opts.push({ value: k, label: k })
    }
  }
  return opts
})

const largeArrayWarning = computed(() =>
  parsedItems.value.length > 500 ? '数组超过 500 项，性能考虑建议分批' : ''
)

const emptyArrayWarning = computed(() =>
  parsedItems.value.length === 0 && jsonText.value.trim().startsWith('[]')
    ? '数组为空，没有可导入项'
    : ''
)

const canParse = computed(() => jsonText.value.trim().length > 0)
const canImport = computed(() => preview.value && preview.value.valid.length > 0)

let parseDebounceTimer: ReturnType<typeof setTimeout> | null = null
watch(jsonText, (v) => {
  if (parseDebounceTimer) clearTimeout(parseDebounceTimer)
  parseDebounceTimer = setTimeout(() => {
    const r = parseBulkJson(v)
    if (r.ok) {
      parsedItems.value = r.items
      // 若当前选中的 nameKey 不在新 keys 中，重置
      if (nameKey.value !== '__auto__' && r.items.length > 0) {
        const firstKeys = Object.keys(r.items[0])
        if (!firstKeys.includes(nameKey.value)) {
          nameKey.value = '__auto__'
        }
      }
    } else {
      parsedItems.value = []
    }
  }, 400)
})

onBeforeUnmount(() => {
  if (parseDebounceTimer) {
    clearTimeout(parseDebounceTimer)
    parseDebounceTimer = null
  }
})

watch(
  () => props.open,
  (v) => {
    if (v) {
      step.value = 1
      jsonText.value = ''
      nameKey.value = '__auto__'
      startX.value = Math.round(props.defaultStartX)
      startY.value = Math.round(props.defaultStartY)
      cols.value = 6
      parseError.value = ''
      preview.value = null
      parsedItems.value = []
    }
  },
)

function goPreview() {
  parseError.value = ''
  preview.value = null
  const r = parseBulkJson(jsonText.value)
  if (!r.ok) {
    parseError.value = r.error
    return
  }
  parsedItems.value = r.items
  const existingSet = new Set(props.existingNames)
  preview.value = buildBulkPreview(
    r.items,
    fields.value,
    nameKey.value,
    props.nodeType?.name ?? 'node',
    existingSet,
    { startX: startX.value, startY: startY.value, cols: cols.value },
  )
  step.value = 2
}

function backToEdit() {
  step.value = 1
}

async function confirmImport() {
  if (!preview.value || !props.nodeType) return
  submitting.value = true
  try {
    const items = preview.value.valid.map((v) => ({
      name: v.name,
      x: v.x,
      y: v.y,
      attrs: v.attrs as Record<string, string | null>,
    }))
    const resp = await nodeApi.bulkCreate(props.topologyId, {
      nodeTypeId: props.nodeType.id,
      items,
    })
    const totalCreated = resp.created.length
    const backendSkipped = resp.skipped.length
    if (backendSkipped > 0) {
      message.warning(`成功导入 ${totalCreated} 个，服务端跳过 ${backendSkipped} 个（详情见弹窗）`)
      Modal.info({
        title: '服务端跳过详情',
        content: resp.skipped.map((s) => `${s.name || '(空)'}：${s.reason}`).join('\n'),
      })
    } else {
      message.success(`成功导入 ${totalCreated} 个节点`)
    }
    emit('imported', resp.created.map((c) => c.id))
    emit('update:open', false)
  } catch (err: any) {
    message.error(`批量导入失败：${err?.message ?? '未知错误'}`)
  } finally {
    submitting.value = false
  }
}

function doCancel() {
  emit('update:open', false)
}
</script>

<template>
  <Modal
    :open="open"
    :title="`批量导入 ${nodeType?.name ?? ''}`"
    :width="820"
    :footer="null"
    :styles="{ body: { maxHeight: 'calc(100vh - 180px)', overflowY: 'auto' } }"
    @cancel="doCancel"
  >
    <!-- Step 1: 输入 -->
    <div v-if="step === 1">
      <Form layout="vertical">
        <a-row :gutter="16">
          <a-col :span="12">
            <Form.Item label="名称来源">
              <Select v-model:value="nameKey" :options="nameKeyOptions" />
            </Form.Item>
          </a-col>
          <a-col :span="4">
            <Form.Item label="起始 X">
              <InputNumber v-model:value="startX" style="width: 100%" />
            </Form.Item>
          </a-col>
          <a-col :span="4">
            <Form.Item label="起始 Y">
              <InputNumber v-model:value="startY" style="width: 100%" />
            </Form.Item>
          </a-col>
          <a-col :span="4">
            <Form.Item label="每行列数">
              <InputNumber v-model:value="cols" :min="1" :max="20" style="width: 100%" />
            </Form.Item>
          </a-col>
        </a-row>

        <Form.Item label="JSON 数组">
          <Input.TextArea
            v-model:value="jsonText"
            :rows="12"
            placeholder='[{"name":"sw-01","ip":"10.0.0.1"}, {"name":"sw-02","ip":"10.0.0.2"}]'
            style="font-family: Consolas, Monaco, monospace; font-size: 12px;"
          />
        </Form.Item>
      </Form>

      <Alert
        v-if="largeArrayWarning"
        :message="largeArrayWarning"
        type="warning"
        show-icon
        style="margin-bottom: 12px;"
      />
      <Alert
        v-if="emptyArrayWarning"
        :message="emptyArrayWarning"
        type="warning"
        show-icon
        style="margin-bottom: 12px;"
      />
      <Alert
        v-if="parseError"
        :message="parseError"
        type="error"
        show-icon
        style="margin-bottom: 12px;"
      />

      <div class="modal-footer">
        <Button @click="doCancel">取消</Button>
        <Button type="primary" :disabled="!canParse" @click="goPreview">解析预览</Button>
      </div>
    </div>

    <!-- Step 2: 预览 -->
    <div v-else-if="step === 2 && preview">
      <BulkImportPreview :preview="preview" />
      <div class="modal-footer">
        <Button @click="backToEdit">返回编辑</Button>
        <Button
          type="primary"
          :disabled="!canImport"
          :loading="submitting"
          @click="confirmImport"
        >
          确认导入 {{ preview.valid.length }} 条
        </Button>
      </div>
    </div>
  </Modal>
</template>

<style scoped>
.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding-top: 12px;
  border-top: 1px solid #f0f0f0;
  margin-top: 12px;
}
</style>
