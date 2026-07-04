<script setup lang="ts">
import { ref, watch, nextTick, computed } from 'vue'
import { Button, Collapse, Form, Input, InputNumber, Select, Switch, Spin, Empty, message, Popconfirm } from 'ant-design-vue'
import ArrayJsonInput from './ArrayJsonInput.vue'
import { PlusOutlined, DeleteOutlined, ImportOutlined } from '@ant-design/icons-vue'
import JsonFillValuesModal from '@/components/shared/JsonFillValuesModal.vue'
import { nodeAlarmApi, type NodeAlarmItem } from '@/api/nodeAlarm'
import { nodeGroupApi, type NodeGroupAlarmItem } from '@/api/nodeGroup'
import { alarmSchemaApi, type AlarmSchemaFieldItem, type AlarmSchemaDetail } from '@/api/alarmSchema'
import { apiGet } from '@/api/http'
import type { TopologyDetail } from '@/api/topology'

interface Props {
  topologyId: string
  nodeId?: string | null
  nodeGroupId?: string | null
  context?: 'node' | 'group'
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'count-change', count: number): void
}>()

type AlarmItem = NodeAlarmItem | NodeGroupAlarmItem

const loading = ref(false)
const schema = ref<AlarmSchemaDetail | null>(null)
const schemaFields = ref<AlarmSchemaFieldItem[]>([])
const alarms = ref<AlarmItem[]>([])
const alarmSchemaId = ref<string | null>(null)
const dirtyAlarmIds = ref<Set<string>>(new Set())
const fieldErrors = ref<Record<string, Record<string, string>>>({})

const hasSchema = computed(() => !!alarmSchemaId.value)

const effectiveContext = computed(() => props.context ?? 'node')
const entityId = computed(() =>
  effectiveContext.value === 'group' ? props.nodeGroupId : props.nodeId,
)

async function apiListAlarms(id: string): Promise<AlarmItem[]> {
  if (effectiveContext.value === 'group') {
    return await nodeGroupApi.listAlarms(id)
  }
  return await nodeAlarmApi.listByNode(id)
}

async function apiCreateAlarm(id: string): Promise<AlarmItem> {
  if (effectiveContext.value === 'group') {
    return await nodeGroupApi.createAlarm(id)
  }
  return await nodeAlarmApi.create(id)
}

async function apiUpdateAttrs(
  alarmId: string,
  attrs: Record<string, string | null>,
): Promise<AlarmItem> {
  if (effectiveContext.value === 'group') {
    return await nodeGroupApi.updateAlarmAttrs(alarmId, { attrs })
  }
  return await nodeAlarmApi.updateAttrs(alarmId, attrs)
}

async function apiDeleteAlarm(alarmId: string): Promise<unknown> {
  if (effectiveContext.value === 'group') {
    return await nodeGroupApi.deleteAlarm(alarmId)
  }
  return await nodeAlarmApi.delete(alarmId)
}

async function loadAll() {
  const id = entityId.value
  if (!id) return
  loading.value = true
  try {
    const topo = await apiGet<TopologyDetail>(`/topologies/${props.topologyId}`)
    alarmSchemaId.value = topo.alarmSchemaId ?? null
    if (alarmSchemaId.value) {
      const d = await alarmSchemaApi.get(alarmSchemaId.value)
      schema.value = d
      schemaFields.value = [...d.fields].sort((a, b) => a.sortOrder - b.sortOrder)
    } else {
      schema.value = null
      schemaFields.value = []
    }
    alarms.value = await apiListAlarms(id)
    dirtyAlarmIds.value.clear()
    emit('count-change', alarms.value.length)
  } finally {
    loading.value = false
  }
}

watch(entityId, loadAll, { immediate: true })

async function handleAdd() {
  const id = entityId.value
  if (!id) return
  try {
    const created = await apiCreateAlarm(id)
    alarms.value.push(created)
    emit('count-change', alarms.value.length)
  } catch (e: any) {
    message.error(e?.message || '新增告警失败')
  }
}

async function handleDelete(alarmId: string) {
  try {
    await apiDeleteAlarm(alarmId)
    alarms.value = alarms.value.filter(a => a.id !== alarmId)
    dirtyAlarmIds.value.delete(alarmId)
    emit('count-change', alarms.value.length)
  } catch (e: any) {
    message.error(e?.message || '删除失败')
  }
}

function markDirty(alarmId: string) {
  dirtyAlarmIds.value.add(alarmId)
}

function getCollapseHeader(alarm: AlarmItem): string {
  const displayKey = schema.value?.displayFieldKey
  let field: AlarmSchemaFieldItem | null = null
  if (displayKey) {
    field = schemaFields.value.find(f => f.fieldKey === displayKey) ?? null
  }
  if (!field) field = schemaFields.value[0] ?? null
  if (!field) return `告警 #${alarm.alarmIndex}`
  const v = alarm.attrs[field.fieldKey] || ''
  return `${v || '(空)'}  #${alarm.alarmIndex}`
}

function validateAlarm(alarm: AlarmItem): boolean {
  const errs: Record<string, string> = {}
  for (const f of schemaFields.value) {
    const v = alarm.attrs[f.fieldKey]
    if (f.required && (!v || String(v).trim() === '')) {
      errs[f.fieldKey] = `${f.fieldLabel}必填`
    }
    if (f.fieldType === 'text' && f.maxLength && v && String(v).length > f.maxLength) {
      errs[f.fieldKey] = `不能超过 ${f.maxLength} 字符`
    }
    if (f.fieldType === 'array' && v) {
      try {
        const parsed = JSON.parse(String(v))
        if (!Array.isArray(parsed)) {
          errs[f.fieldKey] = '必须是 JSON array'
        }
      } catch {
        errs[f.fieldKey] = 'JSON 语法错误'
      }
    }
  }
  fieldErrors.value[alarm.id] = errs
  return Object.keys(errs).length === 0
}

async function saveDirty(): Promise<boolean> {
  for (const a of alarms.value) {
    if (dirtyAlarmIds.value.has(a.id) && !validateAlarm(a)) {
      await nextTick()
      const el = document.querySelector('.ant-form-item-has-error') as HTMLElement | null
      el?.scrollIntoView({ behavior: 'smooth', block: 'center' })
      message.error('请检查告警字段')
      return false
    }
  }
  for (const a of [...alarms.value]) {
    if (!dirtyAlarmIds.value.has(a.id)) continue
    try {
      const updated = await apiUpdateAttrs(a.id, a.attrs)
      const idx = alarms.value.findIndex(x => x.id === a.id)
      if (idx >= 0) alarms.value[idx] = updated
      dirtyAlarmIds.value.delete(a.id)
    } catch (e: any) {
      message.error(`告警 #${a.alarmIndex} 保存失败：${e?.message || ''}`)
      return false
    }
  }
  return true
}

const jsonModalOpen = ref(false)
const jsonTargetAlarmId = ref<string | null>(null)

const jsonTargetAlarm = computed(() =>
  alarms.value.find((a) => a.id === jsonTargetAlarmId.value) ?? null,
)

const jsonCurrentValues = computed<Record<string, string>>(() => {
  const src = jsonTargetAlarm.value?.attrs ?? {}
  const r: Record<string, string> = {}
  for (const k in src) r[k] = src[k] ?? ''
  return r
})

function openJsonModal(alarmId: string) {
  jsonTargetAlarmId.value = alarmId
  jsonModalOpen.value = true
}

function handleJsonApply(values: Record<string, string>) {
  const a = jsonTargetAlarm.value
  if (!a) return
  for (const [k, v] of Object.entries(values)) {
    a.attrs[k] = v
  }
  markDirty(a.id)
}

defineExpose({ saveDirty })
</script>

<template>
  <Spin v-if="loading" tip="加载中..." />
  <div v-else-if="!hasSchema" class="alarm-empty">
    <Empty description="本拓扑未配置告警模板" />
    <div class="hint">去拓扑管理 → 编辑拓扑 → 选择告警模板</div>
  </div>
  <div v-else class="alarms-list">
    <div class="alarms-toolbar">
      <Button type="primary" size="small" @click="handleAdd">
        <PlusOutlined /> 新增告警
      </Button>
    </div>
    <Empty v-if="alarms.length === 0" description="暂无告警，点击上方新增" />
    <Collapse v-else>
      <Collapse.Panel v-for="a in alarms" :key="a.id" :header="getCollapseHeader(a)">
        <template #extra>
          <Popconfirm title="确定删除该条告警？" @confirm="handleDelete(a.id)">
            <DeleteOutlined class="danger-icon" @click.stop />
          </Popconfirm>
        </template>
        <div class="alarm-json-toolbar">
          <Button size="small" @click="openJsonModal(a.id)">
            <template #icon><ImportOutlined /></template>
            从 JSON 填充
          </Button>
        </div>
        <Form layout="vertical">
          <Form.Item
            v-for="f in schemaFields"
            :key="f.id"
            :label="f.fieldLabel + (f.required ? ' *' : '')"
            :validate-status="fieldErrors[a.id]?.[f.fieldKey] ? 'error' : ''"
            :help="fieldErrors[a.id]?.[f.fieldKey]"
          >
            <template v-if="f.fieldType === 'text'">
              <Input
                :value="a.attrs[f.fieldKey] || ''"
                :maxlength="f.maxLength || undefined"
                :show-count="!!f.maxLength"
                @update:value="(v: string) => { a.attrs[f.fieldKey] = v; markDirty(a.id) }"
              />
            </template>
            <template v-else-if="f.fieldType === 'number'">
              <InputNumber
                style="width: 100%"
                :value="a.attrs[f.fieldKey] ? Number(a.attrs[f.fieldKey]) : null"
                @change="(v: any) => { a.attrs[f.fieldKey] = v == null ? null : String(v); markDirty(a.id) }"
              />
            </template>
            <template v-else-if="f.fieldType === 'select'">
              <Select
                :value="a.attrs[f.fieldKey]"
                allow-clear
                @change="(v: any) => { a.attrs[f.fieldKey] = v == null ? null : String(v); markDirty(a.id) }"
              >
                <Select.Option v-for="opt in (f.options || '').split(',')" :key="opt.trim()" :value="opt.trim()">
                  {{ opt.trim() }}
                </Select.Option>
              </Select>
            </template>
            <template v-else-if="f.fieldType === 'boolean'">
              <Switch
                :checked="a.attrs[f.fieldKey] === 'true'"
                @change="(v: any) => { a.attrs[f.fieldKey] = String(v); markDirty(a.id) }"
              />
            </template>
            <template v-else-if="f.fieldType === 'array'">
              <ArrayJsonInput
                :value="a.attrs[f.fieldKey] || ''"
                @update:value="(v: string) => { a.attrs[f.fieldKey] = v || null; markDirty(a.id) }"
                :placeholder="f.defaultValue || '[]'"
              />
            </template>
          </Form.Item>
        </Form>
      </Collapse.Panel>
    </Collapse>
  </div>
  <JsonFillValuesModal
    v-model:open="jsonModalOpen"
    :fields="schemaFields"
    :current-values="jsonCurrentValues"
    @apply="handleJsonApply"
  />
</template>

<style scoped>
.alarm-empty { padding: 32px 16px; text-align: center; }
.alarm-empty .hint { color: #999; font-size: 12px; margin-top: 8px; }
.alarms-toolbar { margin-bottom: 12px; }
.danger-icon { color: #f5222d; cursor: pointer; }
.alarm-json-toolbar {
  margin-bottom: 8px;
}
</style>
