<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { Modal, Input, Button, Alert, Table, message } from 'ant-design-vue'
import { buildGeneratePreview, type GeneratePreview, type FieldLike } from '@/utils/jsonFieldMatch'

interface Props {
  open: boolean
  existingFields: Pick<FieldLike, 'fieldKey'>[]
  sortOrderStart: number
}
const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'update:open', v: boolean): void
  (e: 'apply', fields: FieldLike[]): void
}>()

const jsonText = ref('')
const parseError = ref('')
const preview = ref<GeneratePreview | null>(null)

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
const canApply = computed(() => preview.value !== null && parseError.value === '')
const totalCreateCount = computed(() => preview.value?.toCreate.length ?? 0)

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
  preview.value = buildGeneratePreview(
    parsed as Record<string, unknown>,
    props.existingFields,
    props.sortOrderStart,
  )
}

function doApply() {
  if (!preview.value) return
  emit('apply', preview.value.toCreate)
  if (preview.value.toCreate.length === 0) {
    message.info('未生成任何字段')
  }
  emit('update:open', false)
}

function doCancel() {
  emit('update:open', false)
}

const previewColumns = [
  { title: 'Key', dataIndex: 'fieldKey', key: 'fieldKey', width: 160, ellipsis: true },
  { title: 'Type', dataIndex: 'fieldType', key: 'fieldType', width: 90 },
  { title: 'Label', dataIndex: 'fieldLabel', key: 'fieldLabel', width: 140, ellipsis: true },
  { title: 'Default', dataIndex: 'defaultValue', key: 'defaultValue', ellipsis: true },
]
</script>

<template>
  <Modal
    :open="open"
    title="从 JSON 生成字段"
    :width="640"
    :styles="{ body: { maxHeight: 'calc(100vh - 200px)', overflowY: 'auto' } }"
    @cancel="doCancel"
  >
    <div>
      <div class="hint">粘贴 JSON：</div>
      <Input.TextArea
        v-model:value="jsonText"
        :rows="8"
        placeholder='{"deviceName": "sw-01", "portCount": 24, "enabled": true}'
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

        <div v-if="preview.toCreate.length > 0" class="group">
          <div class="group-title create">
            <span class="icon">✓</span> 将新建字段（{{ preview.toCreate.length }}）
          </div>
          <Table
            :columns="previewColumns"
            :data-source="preview.toCreate"
            :pagination="false"
            size="small"
            :row-key="(r: FieldLike) => r.fieldKey"
          />
        </div>

        <div v-if="preview.skippedExisting.length > 0" class="group">
          <div class="group-title skip">
            <span class="icon">⊘</span> 已存在跳过（{{ preview.skippedExisting.length }}）
          </div>
          <div class="group-body">
            <span v-for="k in preview.skippedExisting" :key="k" class="tag-key">{{ k }}</span>
          </div>
        </div>

        <div v-if="preview.skippedInferable.length > 0" class="group">
          <div class="group-title skip">
            <span class="icon">⊘</span> 无法推断类型跳过（{{ preview.skippedInferable.length }}）
          </div>
          <div class="group-body">
            <span v-for="k in preview.skippedInferable" :key="k" class="tag-key">{{ k }}</span>
          </div>
        </div>
      </div>
    </div>

    <template #footer>
      <Button @click="doCancel">取消</Button>
      <Button type="primary" :disabled="!canApply" @click="doApply">
        确定生成（{{ totalCreateCount }}）
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
.group-title.create { color: #52c41a; }
.group-title.skip { color: #8c8c8c; }
.group-title .icon { display: inline-block; margin-right: 4px; }
.group-body { padding-left: 20px; }
.tag-key { display: inline-block; padding: 2px 8px; margin: 2px 4px 2px 0; background: #f0f0f0; border-radius: 3px; font-family: monospace; font-size: 11px; color: #666; }
</style>
