<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { Modal, Input, Button, Alert, message } from 'ant-design-vue'
import { buildFillPreview, type FillPreview, type FieldLike } from '@/utils/jsonFieldMatch'

interface Props {
  open: boolean
  fields: Pick<FieldLike, 'fieldKey' | 'fieldLabel' | 'fieldType' | 'options'>[]
  currentValues: Record<string, string>
}
const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'update:open', v: boolean): void
  (e: 'apply', values: Record<string, string>): void
}>()

const jsonText = ref('')
const parseError = ref('')
const preview = ref<FillPreview | null>(null)

watch(
  () => props.open,
  (v) => {
    if (v) {
      jsonText.value = ''
      parseError.value = ''
      preview.value = null
    }
  },
)

const canPreview = computed(() => jsonText.value.trim().length > 0)

const totalApplyCount = computed(() => {
  if (!preview.value) return 0
  return preview.value.toFill.length + preview.value.toOverwrite.length
})

const canApply = computed(() => preview.value !== null && parseError.value === '')

function doParse() {
  parseError.value = ''
  preview.value = null
  let parsed: unknown
  try {
    parsed = JSON.parse(jsonText.value)
  } catch (e: any) {
    parseError.value = `解析失败：${e?.message || '未知错误'}`
    return
  }
  if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
    parseError.value = 'JSON 顶层必须是对象 {}'
    return
  }
  if (Object.keys(parsed as Record<string, unknown>).length === 0) {
    parseError.value = '未从 JSON 提取到任何字段'
    return
  }
  preview.value = buildFillPreview(
    parsed as Record<string, unknown>,
    props.fields,
    props.currentValues,
  )
}

function doApply() {
  if (!preview.value) return
  const values: Record<string, string> = {}
  for (const it of preview.value.toFill) values[it.fieldKey] = it.newValue
  for (const it of preview.value.toOverwrite) values[it.fieldKey] = it.newValue
  emit('apply', values)
  if (Object.keys(values).length === 0) {
    message.info('未填充任何字段')
  }
  emit('update:open', false)
}

function doCancel() {
  emit('update:open', false)
}
</script>

<template>
  <Modal
    :open="open"
    title="从 JSON 填充字段"
    :width="640"
    :styles="{ body: { maxHeight: 'calc(100vh - 200px)', overflowY: 'auto' } }"
    @cancel="doCancel"
  >
    <div>
      <div class="hint">粘贴 JSON：</div>
      <Input.TextArea
        v-model:value="jsonText"
        :rows="8"
        placeholder='{"deviceName": "sw-01", "ip": "10.0.0.1"}'
        style="font-family: 'Consolas', 'Monaco', monospace; font-size: 12px;"
      />
      <div class="parse-toolbar">
        <Button type="primary" :disabled="!canPreview" @click="doParse">
          解析预览
        </Button>
      </div>

      <Alert
        v-if="parseError"
        :message="parseError"
        type="error"
        show-icon
        style="margin-top: 12px;"
      />

      <div v-if="preview" class="preview-section">
        <div class="divider">预览结果</div>

        <div v-if="preview.toFill.length > 0" class="group">
          <div class="group-title fill">
            <span class="icon">✓</span> 将填充（{{ preview.toFill.length }}）
          </div>
          <div class="group-body">
            <div v-for="it in preview.toFill" :key="it.fieldKey" class="row">
              <span class="key">{{ it.fieldKey }}</span>
              <span class="label">（{{ it.fieldLabel }}）</span>
              <span class="arrow">←</span>
              <span class="value">{{ it.newValue }}</span>
            </div>
          </div>
        </div>

        <div v-if="preview.toOverwrite.length > 0" class="group">
          <div class="group-title overwrite">
            <span class="icon">⚠</span> 将覆盖已有值（{{ preview.toOverwrite.length }}）
          </div>
          <div class="group-body">
            <div v-for="it in preview.toOverwrite" :key="it.fieldKey" class="row overwrite-row">
              <div>
                <span class="key">{{ it.fieldKey }}</span>
                <span class="label">（{{ it.fieldLabel }}）</span>
              </div>
              <div class="sub">
                当前: <span class="old">{{ it.oldValue }}</span>
                →
                新值: <span class="new">{{ it.newValue }}</span>
              </div>
            </div>
          </div>
        </div>

        <div v-if="preview.incompatible.length > 0" class="group">
          <div class="group-title incompatible">
            <span class="icon">⊘</span> 类型不兼容跳过（{{ preview.incompatible.length }}）
          </div>
          <div class="group-body">
            <div v-for="it in preview.incompatible" :key="it.fieldKey" class="row">
              <span class="key">{{ it.fieldKey }}</span>
              <span class="label">（{{ it.fieldLabel }}）</span>
              <span class="reason">— {{ it.reason }}</span>
            </div>
          </div>
        </div>

        <div v-if="preview.unmatched.length > 0" class="group">
          <div class="group-title unmatched">
            <span class="icon">○</span> 未匹配的 JSON key（{{ preview.unmatched.length }}）
          </div>
          <div class="group-body">
            <span v-for="k in preview.unmatched" :key="k" class="tag-key">{{ k }}</span>
          </div>
        </div>
      </div>
    </div>

    <template #footer>
      <Button @click="doCancel">取消</Button>
      <Button type="primary" :disabled="!canApply" @click="doApply">
        确定填充（{{ totalApplyCount }}）
      </Button>
    </template>
  </Modal>
</template>

<style scoped>
.hint { font-size: 12px; color: #666; margin-bottom: 4px; }
.parse-toolbar { margin-top: 8px; }
.divider { font-size: 12px; color: #999; text-align: center; margin: 12px 0 8px; }
.preview-section { margin-top: 8px; }
.group { margin-bottom: 12px; padding: 8px 12px; background: #fafafa; border-radius: 4px; }
.group-title { font-size: 13px; font-weight: 500; margin-bottom: 6px; }
.group-title.fill { color: #52c41a; }
.group-title.overwrite { color: #faad14; }
.group-title.incompatible { color: #8c8c8c; }
.group-title.unmatched { color: #bfbfbf; }
.group-title .icon { display: inline-block; margin-right: 4px; }
.group-body { padding-left: 20px; }
.row { line-height: 1.9; font-size: 12px; }
.overwrite-row { padding: 4px 0; border-bottom: 1px dashed #eee; }
.overwrite-row:last-child { border-bottom: none; }
.row .key { font-family: monospace; color: #1f1f1f; }
.row .label { color: #888; margin-right: 8px; }
.row .arrow { margin: 0 8px; color: #52c41a; }
.row .value { font-family: monospace; color: #1890ff; }
.row .reason { color: #ff4d4f; margin-left: 8px; font-size: 11px; }
.row .old { font-family: monospace; color: #999; text-decoration: line-through; }
.row .new { font-family: monospace; color: #1890ff; }
.row .sub { padding-left: 12px; color: #666; font-size: 11px; }
.tag-key { display: inline-block; padding: 2px 8px; margin: 2px 4px 2px 0; background: #f0f0f0; border-radius: 3px; font-family: monospace; font-size: 11px; color: #666; }
</style>
