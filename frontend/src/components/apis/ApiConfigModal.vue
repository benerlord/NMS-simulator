<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  Modal,
  Form,
  Input,
  InputNumber,
  Select,
  Switch,
  Spin,
  Collapse,
  CollapsePanel,
} from 'ant-design-vue'
import { apiGet } from '@/api/http'
import {
  apiConfigApi,
  type ApiConfigCreate,
  type ApiConfigUpdate,
  type DataSource,
  type HttpMethod,
} from '@/api/api_config'
import type { TopologyListItem, PageResult } from '@/api/topology'
import SqlEditor from './SqlEditor.vue'
import SqlViewPanel from './SqlViewPanel.vue'
import SqlRunner from './SqlRunner.vue'
import ParamMappingTable, { type ParamMapping } from './ParamMappingTable.vue'

interface Props {
  open: boolean
  apiId?: string | null
}

const props = defineProps<Props>()
const emit = defineEmits<{
  (e: 'update:open', v: boolean): void
  (e: 'createSubmit', data: ApiConfigCreate): Promise<void>
  (e: 'updateSubmit', id: string, data: ApiConfigUpdate): Promise<void>
}>()

const loading = ref(false)
const detailLoading = ref(false)
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const formRef = ref<{ validateFields?: () => Promise<void> } | null>(null)
const sqlEditorRef = ref<{
  insertAtCursor: (text: string) => void
  focus: () => void
} | null>(null)

function handleInsertFromPanel(text: string) {
  sqlEditorRef.value?.insertAtCursor(text)
}

interface FormState {
  name: string
  method: HttpMethod
  path: string
  groupName: string
  dataSource: DataSource
  topologyId: string | undefined
  sqlText: string
  enabled: boolean
  params: ParamMapping[]
  responseTemplate: string
  staticBody: string
  faultEnabled: boolean
  faultDelayMs: number | undefined
  faultErrorRate: number | undefined
  faultErrorStatus: number | undefined
}

const DEFAULT_TEMPLATE_PLACEHOLDER =
  '{"code":0,"data":"{{items}}","total":"{{total}}","pageNo":"{{pageNo}}","pageSize":"{{pageSize}}"}'

const DEFAULT_STATIC_PLACEHOLDER = '{"code":0,"data":{"hello":"world"}}'

function emptyForm(): FormState {
  return {
    name: '',
    method: 'GET',
    path: '',
    groupName: '',
    dataSource: 'static',
    topologyId: undefined,
    sqlText: '',
    enabled: true,
    params: [],
    responseTemplate: '',
    staticBody: '',
    faultEnabled: false,
    faultDelayMs: undefined,
    faultErrorRate: undefined,
    faultErrorStatus: undefined,
  }
}

const formState = ref<FormState>(emptyForm())
const topologies = ref<TopologyListItem[]>([])
const loadingTopologies = ref(false)

const isEdit = computed(() => !!props.apiId)
const title = computed(() => (isEdit.value ? '编辑接口' : '新建接口'))
const modalWidth = computed(() =>
  formState.value.dataSource === 'sql' ? '1100px' : '720px',
)

const methodOptions = [
  { label: 'GET', value: 'GET' },
  { label: 'POST', value: 'POST' },
  { label: 'PUT', value: 'PUT' },
  { label: 'PATCH', value: 'PATCH' },
  { label: 'DELETE', value: 'DELETE' },
]

const dataSourceOptions = [
  { label: '静态 (static)', value: 'static' },
  { label: 'SQL', value: 'sql' },
]

async function loadTopologies() {
  loadingTopologies.value = true
  try {
    const result = await apiGet<PageResult<TopologyListItem>>('/topologies', {
      page: 1,
      pageSize: 200,
      sort: 'updated_at,desc',
    })
    topologies.value = result.items
  } finally {
    loadingTopologies.value = false
  }
}

async function loadDetail(id: string) {
  detailLoading.value = true
  try {
    const detail = await apiConfigApi.get(id)
    const cfg = (detail.config ?? {}) as {
      params?: ParamMapping[]
      response?: { template?: string }
      staticBody?: unknown
      fault?: {
        delayMs?: unknown
        errorRate?: unknown
        errorStatus?: unknown
      }
    }
    const tpl = cfg.response?.template
    const staticBodyRaw = cfg.staticBody
    const fault = cfg.fault && typeof cfg.fault === 'object' ? cfg.fault : null
    const toNum = (v: unknown): number | undefined =>
      typeof v === 'number' && Number.isFinite(v) ? v : undefined
    formState.value = {
      name: detail.name,
      method: detail.method,
      path: detail.path,
      groupName: detail.groupName ?? '',
      dataSource: detail.dataSource,
      topologyId: detail.topologyId ?? undefined,
      sqlText: detail.sqlText ?? '',
      enabled: detail.enabled,
      params: Array.isArray(cfg.params) ? cfg.params : [],
      responseTemplate:
        typeof tpl === 'string'
          ? tpl
          : tpl !== undefined
            ? JSON.stringify(tpl, null, 2)
            : '',
      staticBody:
        staticBodyRaw === undefined
          ? ''
          : typeof staticBodyRaw === 'string'
            ? staticBodyRaw
            : JSON.stringify(staticBodyRaw, null, 2),
      faultEnabled: !!fault,
      faultDelayMs: fault ? toNum(fault.delayMs) : undefined,
      faultErrorRate: fault ? toNum(fault.errorRate) : undefined,
      faultErrorStatus: fault ? toNum(fault.errorStatus) : undefined,
    }
  } finally {
    detailLoading.value = false
  }
}

watch(
  () => props.open,
  (open) => {
    if (!open) return
    loadTopologies()
    if (props.apiId) {
      loadDetail(props.apiId)
    } else {
      formState.value = emptyForm()
    }
  },
)

function close() {
  emit('update:open', false)
}

function buildConfig(): Record<string, unknown> {
  const cfg: Record<string, unknown> = {}
  if (formState.value.dataSource === 'sql') {
    if (formState.value.params.length > 0) {
      cfg.params = formState.value.params
    }
    const tpl = formState.value.responseTemplate.trim()
    if (tpl) {
      cfg.response = { template: tpl }
    }
  } else if (formState.value.dataSource === 'static') {
    const raw = formState.value.staticBody.trim()
    if (raw) {
      try {
        cfg.staticBody = JSON.parse(raw)
      } catch {
        // Form validator gates submit; unreachable in practice.
      }
    }
  }

  if (formState.value.faultEnabled) {
    const fault: Record<string, unknown> = {}
    if (
      typeof formState.value.faultDelayMs === 'number' &&
      formState.value.faultDelayMs > 0
    ) {
      fault.delayMs = formState.value.faultDelayMs
    }
    if (
      typeof formState.value.faultErrorRate === 'number' &&
      formState.value.faultErrorRate > 0
    ) {
      fault.errorRate = formState.value.faultErrorRate
    }
    if (
      typeof formState.value.faultErrorStatus === 'number' &&
      formState.value.faultErrorStatus >= 400
    ) {
      fault.errorStatus = formState.value.faultErrorStatus
    }
    if (Object.keys(fault).length > 0) {
      cfg.fault = fault
    }
  }
  return cfg
}

const templateParseError = computed<string | null>(() => {
  const tpl = formState.value.responseTemplate.trim()
  if (!tpl) return null
  try {
    JSON.parse(tpl)
    return null
  } catch (e) {
    return (e as Error).message
  }
})

const faultPanelHeader = computed(() => {
  if (!formState.value.faultEnabled) return '异常注入（未启用）'
  const parts: string[] = []
  const d = formState.value.faultDelayMs
  if (typeof d === 'number' && d > 0) parts.push(`延迟 ${d}ms`)
  const r = formState.value.faultErrorRate
  if (typeof r === 'number' && r > 0) {
    const s = formState.value.faultErrorStatus
    parts.push(
      `${(r * 100).toFixed(0)}% → ${typeof s === 'number' && s >= 400 ? s : 500}`,
    )
  }
  return parts.length > 0
    ? `异常注入（${parts.join('，')}）`
    : '异常注入（已启用，未配置参数）'
})

const staticBodyParseError = computed<string | null>(() => {
  const raw = formState.value.staticBody.trim()
  if (!raw) return null
  try {
    JSON.parse(raw)
    return null
  } catch (e) {
    return (e as Error).message
  }
})

async function handleSubmit() {
  try {
    if (formRef.value?.validateFields) {
      await formRef.value.validateFields()
    }
    loading.value = true
    const sqlText =
      formState.value.dataSource === 'sql' ? formState.value.sqlText : null
    const config = buildConfig()

    if (isEdit.value && props.apiId) {
      const payload: ApiConfigUpdate = {
        name: formState.value.name.trim(),
        path: formState.value.path.trim(),
        groupName: formState.value.groupName.trim() || null,
        dataSource: formState.value.dataSource,
        sqlText,
        config,
      }
      await emit('updateSubmit', props.apiId, payload)
    } else {
      const payload: ApiConfigCreate = {
        name: formState.value.name.trim(),
        method: formState.value.method,
        path: formState.value.path.trim(),
        enabled: formState.value.enabled,
        dataSource: formState.value.dataSource,
        groupName: formState.value.groupName.trim() || null,
        topologyId: formState.value.topologyId || null,
        sqlText,
        config,
      }
      await emit('createSubmit', payload)
    }
    close()
  } catch {
    // validation or backend error: keep modal open; interceptor shows toast
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <Modal
    :open="open"
    :title="title"
    :confirm-loading="loading"
    ok-text="确定"
    cancel-text="取消"
    :width="modalWidth"
    @ok="handleSubmit"
    @cancel="close"
  >
    <Spin :spinning="detailLoading">
      <Form
        ref="formRef"
        :model="formState"
        layout="vertical"
        class="api-form"
      >
        <Form.Item
          label="名称"
          name="name"
          :rules="[{ required: true, message: '请输入接口名称' }]"
        >
          <Input
            v-model:value="formState.name"
            placeholder="示例：查询交换机列表"
            :maxlength="100"
          />
        </Form.Item>

        <div class="form-row">
          <Form.Item
            label="方法"
            name="method"
            :rules="[{ required: true, message: '请选择方法' }]"
            class="form-col-method"
          >
            <Select
              v-model:value="formState.method"
              :options="methodOptions"
              :disabled="isEdit"
            />
          </Form.Item>

          <Form.Item
            label="路径"
            name="path"
            :rules="[
              { required: true, message: '请输入路径' },
              { pattern: /^\//, message: '路径必须以 / 开头' },
            ]"
            class="form-col-path"
          >
            <Input v-model:value="formState.path" placeholder="/api/v1/switches" />
          </Form.Item>
        </div>

        <div class="form-row">
          <Form.Item label="分组" name="groupName" class="form-col-half">
            <Input v-model:value="formState.groupName" placeholder="可选，例：设备管理" />
          </Form.Item>

          <Form.Item
            label="数据源"
            name="dataSource"
            :rules="[{ required: true, message: '请选择数据源' }]"
            class="form-col-half"
          >
            <Select v-model:value="formState.dataSource" :options="dataSourceOptions" />
          </Form.Item>
        </div>

        <Form.Item label="绑定拓扑" name="topologyId">
          <Select
            v-model:value="formState.topologyId"
            placeholder="可选，绑定拓扑后 SQL 可引用该拓扑视图"
            :loading="loadingTopologies"
            allow-clear
            show-search
            option-filter-prop="label"
            :disabled="isEdit"
            :options="topologies.map((t) => ({ label: t.name, value: t.id }))"
          />
          <div v-if="isEdit" class="hint">编辑时拓扑绑定请通过列表操作，此字段不可改</div>
        </Form.Item>

        <Form.Item
          v-if="formState.dataSource === 'sql'"
          label="SQL 语句"
          name="sqlText"
          :rules="[{ required: true, message: 'SQL 模式下 sqlText 不得为空' }]"
        >
          <div class="sql-editor-row">
            <SqlViewPanel
              :topology-id="formState.topologyId ?? null"
              class="sql-view-col"
              @insert="handleInsertFromPanel"
            />
            <div class="sql-editor-col">
              <SqlEditor
                ref="sqlEditorRef"
                v-model="formState.sqlText"
                min-height="200px"
              />
              <SqlRunner
                :topology-id="formState.topologyId ?? null"
                :sql-text="formState.sqlText"
                :params="formState.params"
                @insert="handleInsertFromPanel"
              />
            </div>
          </div>
        </Form.Item>

        <Form.Item
          v-if="formState.dataSource === 'sql'"
          label="参数映射"
          name="params"
        >
          <ParamMappingTable v-model="formState.params" />
        </Form.Item>

        <Form.Item
          v-if="formState.dataSource === 'sql'"
          label="响应模板"
          name="responseTemplate"
        >
          <Input.TextArea
            v-model:value="formState.responseTemplate"
            :rows="8"
            :placeholder="DEFAULT_TEMPLATE_PLACEHOLDER"
            spellcheck="false"
            class="tpl-textarea"
          />
          <div v-if="templateParseError" class="hint hint-error">
            JSON 解析失败：{{ templateParseError }}
          </div>
          <div v-else class="hint" v-pre>
            占位符：{{items}} / {{total}} / {{page}} 或 {{pageNo}} / {{pageSize}} / {{uuid}} / {{now}}。
            整串匹配（如 "data": "{{items}}"）注入原值保持数组/对象类型；子串匹配做文本替换。留空走默认模板。
          </div>
        </Form.Item>

        <Form.Item
          v-if="formState.dataSource === 'static'"
          label="静态响应体"
          name="staticBody"
          :rules="[
            {
              validator: async (_rule: unknown, value: string) => {
                if (!value || !value.trim()) return
                try {
                  JSON.parse(value)
                } catch (e) {
                  throw new Error('静态响应体不是合法 JSON：' + (e as Error).message)
                }
              },
            },
          ]"
        >
          <Input.TextArea
            v-model:value="formState.staticBody"
            :rows="8"
            :placeholder="DEFAULT_STATIC_PLACEHOLDER"
            spellcheck="false"
            class="tpl-textarea"
          />
          <div v-if="staticBodyParseError" class="hint hint-error">
            JSON 解析失败：{{ staticBodyParseError }}
          </div>
          <div v-else class="hint">
            整段原样作为 HTTP 响应体返回（不走模板）。支持对象 / 数组 / 标量。留空时返回
            <code>{"code":0,"data":null}</code> 兜底。
          </div>
        </Form.Item>

        <Collapse :bordered="false" class="fault-collapse">
          <CollapsePanel key="fault" :header="faultPanelHeader">
            <Form.Item label="启用异常注入" name="faultEnabled">
              <Switch
                v-model:checked="formState.faultEnabled"
                checked-children="开"
                un-checked-children="关"
              />
              <div class="hint">
                开启后请求会按 <code>delayMs</code> 注入延迟、按 <code>errorRate</code>
                概率短路返回 <code>{ "code": 50001 }</code> 错误响应（HTTP 状态由
                <code>errorStatus</code> 决定）。延迟先于错误判定，错误命中时延迟同样生效。
              </div>
            </Form.Item>

            <div v-if="formState.faultEnabled" class="form-row fault-row">
              <Form.Item
                label="固定延迟 (ms)"
                name="faultDelayMs"
                class="form-col-third"
              >
                <InputNumber
                  v-model:value="formState.faultDelayMs"
                  :min="0"
                  :max="60000"
                  :step="100"
                  placeholder="0 ~ 60000"
                  style="width: 100%"
                />
                <div class="hint">单次请求固定延迟，留空或 0 不延迟。</div>
              </Form.Item>

              <Form.Item
                label="错误概率 (0-1)"
                name="faultErrorRate"
                class="form-col-third"
              >
                <InputNumber
                  v-model:value="formState.faultErrorRate"
                  :min="0"
                  :max="1"
                  :step="0.05"
                  placeholder="0 ~ 1"
                  style="width: 100%"
                />
                <div class="hint">如 0.1 = 10% 概率返回错误，留空或 0 不注入。</div>
              </Form.Item>

              <Form.Item
                label="错误状态码"
                name="faultErrorStatus"
                class="form-col-third"
                :rules="[
                  {
                    validator: async (_rule: unknown, value: number | null | undefined) => {
                      if (value === null || value === undefined) return
                      if (!Number.isInteger(value) || value < 400 || value > 599) {
                        throw new Error('错误状态码须为 400 ~ 599 之间的整数')
                      }
                    },
                  },
                ]"
              >
                <InputNumber
                  v-model:value="formState.faultErrorStatus"
                  :min="400"
                  :max="599"
                  :step="1"
                  placeholder="400 ~ 599 (默认 500)"
                  style="width: 100%"
                />
                <div class="hint">命中错误时返回的 HTTP 状态码，留空默认 500。</div>
              </Form.Item>
            </div>
          </CollapsePanel>
        </Collapse>

        <Form.Item v-if="!isEdit" label="启用" name="enabled">
          <Switch
            v-model:checked="formState.enabled"
            checked-children="启用"
            un-checked-children="禁用"
          />
        </Form.Item>
      </Form>
    </Spin>
  </Modal>
</template>

<style scoped>
.api-form {
  padding-top: 8px;
}

.form-row {
  display: flex;
  gap: 12px;
}

.form-col-method {
  flex: 0 0 120px;
}

.form-col-path {
  flex: 1;
}

.form-col-half {
  flex: 1;
}

.hint {
  font-size: 12px;
  color: #8c8c8c;
  margin-top: 4px;
}

.hint-error {
  color: #d4380d;
}

.tpl-textarea :deep(textarea) {
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 12px;
  line-height: 1.5;
}

.sql-editor-row {
  display: flex;
  gap: 12px;
  align-items: stretch;
  min-height: 220px;
}

.sql-view-col {
  flex: 0 0 260px;
  max-height: 420px;
}

.sql-editor-col {
  flex: 1;
  min-width: 0;
}

.fault-collapse {
  margin-bottom: 16px;
  background: #fafafa;
}

.fault-collapse :deep(.ant-collapse-header) {
  font-weight: 500;
}

.form-col-third {
  flex: 1;
  min-width: 0;
}

.fault-row {
  margin-top: 4px;
}
</style>
