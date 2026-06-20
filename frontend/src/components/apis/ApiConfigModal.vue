<script setup lang="ts">
import { computed, h, ref, watch } from 'vue'
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
  Alert,
  Checkbox,
} from 'ant-design-vue'
import { apiGet } from '@/api/http'
import {
  apiConfigApi,
  type ApiConfigCreate,
  type ApiConfigUpdate,
  type AuthConfig,
  type BodySpec,
  type DataSource,
  type HeaderSpec,
  type HttpMethod,
  type QuerySpec,
  type TopologySwitchPreview,
} from '@/api/api_config'
import { domainApi, type DomainItem } from '@/api/domain'
import type { TopologyListItem, PageResult } from '@/api/topology'
import SqlEditor from './SqlEditor.vue'
import SqlViewPanel from './SqlViewPanel.vue'
import SqlRunner from './SqlRunner.vue'
import ParamMappingTable, { type ParamMapping } from './ParamMappingTable.vue'
import HeaderSpecTable from './HeaderSpecTable.vue'
import QuerySpecTable from './QuerySpecTable.vue'
import BodySpecPanel from './BodySpecPanel.vue'
import AuthConfigPanel from './AuthConfigPanel.vue'

interface Props {
  open: boolean
  apiId?: string | null
  presetCategory?: string | null
  presetDomainId?: string | null
}

const props = defineProps<Props>()
const emit = defineEmits<{
  (e: 'update:open', v: boolean): void
  (e: 'createSubmit', data: ApiConfigCreate): Promise<void>
  (e: 'updateSubmit', id: string, data: ApiConfigUpdate): Promise<void>
}>()

const loading = ref(false)
const detailLoading = ref(false)
const domains = ref<DomainItem[]>([])
const categoryOptions = ref<{ label: string; value: string }[]>([])

async function loadCategories(domainId: string) {
  if (!domainId) {
    categoryOptions.value = []
    return
  }
  try {
    const cats = await domainApi.fetchCategories(domainId)
    categoryOptions.value = cats.map(c => ({ label: c, value: c }))
  } catch {
    categoryOptions.value = []
  }
}

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
  domainId: string | null
  category: string
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
  // M5：请求规格（headers / query / body）+ 鉴权
  requestHeaders: HeaderSpec[]
  requestQuery: QuerySpec[]
  // 旧字段：仅从 loadDetail 读入做兼容，buildConfig 不再使用（改为
  // 按 requestQuery.length > 0 派生）。Task 2 重构后保留仅为状态层兼容。
  requestQueryStrict: boolean
  requestBody: BodySpec | null
  authConfig: AuthConfig
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
    domainId: null,
    category: '',
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
    requestHeaders: [],
    requestQuery: [],
    requestQueryStrict: false,
    requestBody: null,
    authConfig: { type: 'none' },
  }
}

const formState = ref<FormState>(emptyForm())
const topologies = ref<TopologyListItem[]>([])
const loadingTopologies = ref(false)
// LEGACY-06: 编辑模式下记录初始 topology_id，用于切换检测、回滚与提交时差异判断
const originalTopologyId = ref<string | null>(null)

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

async function loadDomains() {
  try {
    const res = await domainApi.list()
    domains.value = res.items
    // Load categories for current domain if set
    if (formState.value.domainId) {
      loadCategories(formState.value.domainId)
    }
  } catch {}
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
      request?: {
        headers?: HeaderSpec[]
        query?: QuerySpec[]
        body?: BodySpec | null
      }
      auth?: AuthConfig
    }
    const tpl = cfg.response?.template
    const staticBodyRaw = cfg.staticBody
    const fault = cfg.fault && typeof cfg.fault === 'object' ? cfg.fault : null
    const toNum = (v: unknown): number | undefined =>
      typeof v === 'number' && Number.isFinite(v) ? v : undefined
    // M5: 反向回填 request / auth
    const req =
      cfg.request && typeof cfg.request === 'object' ? cfg.request : null
    // 严格白名单触发条件：cfg.request 中"显式存在 query 字段"（即便为空数组）
    const queryDeclared =
      !!req && Object.prototype.hasOwnProperty.call(req, 'query')
    const auth =
      cfg.auth && typeof cfg.auth === 'object' && cfg.auth.type
        ? cfg.auth
        : { type: 'none' as const }
    formState.value = {
      name: detail.name,
      method: detail.method,
      path: detail.path,
      groupName: detail.groupName ?? '',
      domainId: detail.domainId ?? null,
      category: detail.category ?? '',
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
      requestHeaders: Array.isArray(req?.headers) ? req!.headers : [],
      requestQuery: Array.isArray(req?.query) ? req!.query : [],
      requestQueryStrict: queryDeclared,
      requestBody:
        req?.body && typeof req.body === 'object' ? (req.body as BodySpec) : null,
      authConfig: { ...auth },
    }
    // LEGACY-06: 记录初始 topology_id，用于变更检测与回滚
    originalTopologyId.value = detail.topologyId ?? null
  } finally {
    detailLoading.value = false
  }
}

watch(
  () => props.open,
  async (open) => {
    if (!open) return
    loadTopologies()
    loadDomains()
    if (props.apiId) {
      await loadDetail(props.apiId)
      // Task 3: Tab 默认选中：第一个有数据的；都没有则 header
      if (formState.value.requestHeaders.length > 0) {
        requestSpecActiveTab.value = 'header'
      } else if (formState.value.requestQuery.length > 0) {
        requestSpecActiveTab.value = 'query'
      } else if (formState.value.requestBody) {
        requestSpecActiveTab.value = 'body'
      } else {
        requestSpecActiveTab.value = 'header'
      }
    } else {
      formState.value = emptyForm()
      requestSpecActiveTab.value = 'header'
      if (props.presetDomainId) {
        formState.value.domainId = props.presetDomainId
        loadCategories(props.presetDomainId)
      }
      if (props.presetCategory) {
        formState.value.category = props.presetCategory
      }
      originalTopologyId.value = null
    }
  },
)

watch(
  () => formState.value.domainId,
  (newDomainId) => {
    if (newDomainId) {
      loadCategories(newDomainId)
    } else {
      categoryOptions.value = []
    }
  },
)

function close() {
  emit('update:open', false)
}

// LEGACY-06: 编辑模式下切换拓扑的二次确认 + 预扫描
async function handleTopologyChange(newId: string | undefined) {
  if (!isEdit.value || !props.apiId) return
  // 切回原值不弹窗（用户可能误点又恢复）
  if ((newId ?? null) === originalTopologyId.value) return
  if (!newId) return // 切到 undefined（清空）暂不弹窗，等用户保存时一并处理

  let preview: TopologySwitchPreview | null = null
  try {
    preview = await apiConfigApi.fetchTopologySwitchPreview(props.apiId, newId)
  } catch {
    // 预扫描失败不阻断流程，弹窗内退化为通用提示
  }

  // 用 ref 让 Modal 内部的 Checkbox 状态可被 onOk 读取
  const clearSql = ref(false)
  const oldId = originalTopologyId.value

  Modal.confirm({
    title: '切换绑定拓扑',
    width: 520,
    okText: '确认切换',
    cancelText: '取消',
    icon: null,
    content: () =>
      h('div', [
        h('p', { style: 'margin-bottom: 12px' }, '编辑模式下切换拓扑会让 SQL 引用的视图集合发生变化。'),
        preview && preview.missingViews.length > 0
          ? h(Alert, {
              type: 'warning',
              showIcon: true,
              message: `${preview.missingViews.length} 个视图引用在新拓扑下不存在`,
              description: preview.missingViews.join('、'),
              style: 'margin-bottom: 12px',
            })
          : preview
            ? h(Alert, {
                type: 'success',
                showIcon: true,
                message: 'SQL 引用的所有视图在新拓扑下都存在',
                style: 'margin-bottom: 12px',
              })
            : h(Alert, {
                type: 'info',
                showIcon: true,
                message: '预扫描未完成，建议切换后通过"运行预览"验证',
                style: 'margin-bottom: 12px',
              }),
        h('div', { style: 'margin-top: 8px' }, [
          h(
            Checkbox,
            {
              checked: clearSql.value,
              'onUpdate:checked': (v: boolean) => {
                clearSql.value = v
              },
            },
            () => '切换时同时清空 SQL（默认保留以便手动调整）',
          ),
        ]),
      ]),
    onOk: () => {
      if (clearSql.value) {
        formState.value.sqlText = ''
      }
      // 不立即调 PATCH /topology；保留 formState.topologyId=newId 由 handleSubmit 落库
    },
    onCancel: () => {
      // 回滚 Select 值；nextTick 不必要，v-model 同步赋值即可
      formState.value.topologyId = oldId ?? undefined
    },
  })
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

  // M5: 写 cfg.request（headers 非空 / query 非空 / body 非 null 任一满足）
  const request: Record<string, unknown> = {}
  if (formState.value.requestHeaders.length > 0) {
    request.headers = formState.value.requestHeaders
  }
  if (formState.value.requestQuery.length > 0) {
    request.query = formState.value.requestQuery
  }
  if (formState.value.requestBody) {
    request.body = formState.value.requestBody
  }
  if (Object.keys(request).length > 0) {
    cfg.request = request
  }

  // M5: 写 cfg.auth（type !== 'none' 才写，none 视为未启用）
  if (formState.value.authConfig.type !== 'none') {
    const auth: Record<string, unknown> = { type: formState.value.authConfig.type }
    if (
      formState.value.authConfig.type === 'xtoken' &&
      formState.value.authConfig.headerName
    ) {
      auth.headerName = formState.value.authConfig.headerName
    }
    cfg.auth = auth
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

const responseTemplateTooltip = () => h('div', { style: 'font-size:12px;line-height:1.6' }, [
  h('div', { style: 'font-weight:500;margin-bottom:4px' }, '内置占位符'),
  h('div', null, [
    h('code', null, '{{items}}'), ' 当前页行数组 / ',
    h('code', null, '{{total}}'), ' 总数 / ',
    h('code', null, '{{count}}'), ' 本页行数',
  ]),
  h('div', null, [
    h('code', null, '{{page}}'), ' = ',
    h('code', null, '{{pageNo}}'), ' / ',
    h('code', null, '{{pageSize}}'), ' / ',
    h('code', null, '{{offset}}'),
  ]),
  h('div', null, [
    h('code', null, '{{totalPageNo}}'), ' = ',
    h('code', null, '{{totalPages}}'), ' / ',
    h('code', null, '{{hasNext}}'), ' / ',
    h('code', null, '{{hasPrev}}'),
  ]),
  h('div', null, [
    h('code', null, '{{uuid}}'), ' / ',
    h('code', null, '{{now}}'), '（ISO-8601 UTC）',
  ]),
  h('div', { style: 'margin-top:6px;font-weight:500' }, '表达式（{{ }} 内可写算术）'),
  h('div', null, '+ - * / %，函数：ceil/floor/round/abs/min/max/int'),
  h('div', null, [h('code', null, '"total": "{{total + 1}}"')]),
  h('div', { style: 'margin-top:6px;font-weight:500' }, '注入规则'),
  h('div', null, [h('code', null, '"data": "{{items}}"'), ' 整串匹配 → 注入原数组（不加引号）']),
  h('div', null, [h('code', null, '"msg": "共{{total}}条"'), ' 子串 → 文本替换']),
])

// Task 3: 请求规格 Tab 状态 + 计数徽章
const requestSpecActiveTab = ref<'header' | 'query' | 'body'>('header')

const headerCount = computed(() => formState.value.requestHeaders.length)
const queryCount = computed(() => formState.value.requestQuery.length)
const bodyTabLabel = computed(() =>
  formState.value.requestBody ? '请求体 ✓' : '请求体',
)

const requestPanelHeader = computed(() => {
  const parts: string[] = []
  if (formState.value.requestHeaders.length > 0) {
    parts.push(`headers ${formState.value.requestHeaders.length}`)
  }
  if (formState.value.requestQuery.length > 0) {
    parts.push(`query 严格 ${formState.value.requestQuery.length}`)
  }
  if (formState.value.requestBody) {
    parts.push(`body${formState.value.requestBody.required ? '*' : ''}`)
  }
  return parts.length > 0
    ? `请求规格（${parts.join('，')}）`
    : '请求规格（未声明）'
})

const authPanelHeader = computed(() => {
  const t = formState.value.authConfig.type
  if (t === 'none') return '鉴权配置（未启用）'
  if (t === 'xtoken') {
    const h = formState.value.authConfig.headerName || 'X-Auth-Token'
    return `鉴权配置（xtoken / ${h}）`
  }
  return '鉴权配置（Basic）'
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

const sqlColumnNames = ref<string[]>([])

function onSqlColumns(cols: string[]) {
  sqlColumnNames.value = cols
}

const columnNamesHint = computed(() =>
  sqlColumnNames.value.map(c => '{{' + c + '}}').join('、'),
)

const availableFieldNames = computed<string[]>(() => {
  const names = new Set<string>()
  // SQL 列名（snake_case，来自数据库）
  for (const col of sqlColumnNames.value) names.add(col)
  for (const q of formState.value.requestQuery) {
    const n = q.name.trim()
    if (n) names.add(n)
  }
  const body = formState.value.requestBody
  if (body && body.contentType === 'application/json') {
    const raw = (body.example ?? '').trim()
    if (raw) {
      try {
        const parsed = JSON.parse(raw)
        if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
          for (const k of Object.keys(parsed)) {
            if (k) names.add(k)
          }
        }
      } catch {
        // example is not valid JSON — skip, no body field suggestions
      }
    }
  }
  return [...names].sort()
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

    const categoryName = formState.value.category || null
    const resolvedDomainId = formState.value.domainId || null

    if (isEdit.value && props.apiId) {
      // LEGACY-06: 编辑模式下若 topologyId 变化，先独立 PATCH /topology 解耦失败可重试
      const newTopoId = formState.value.topologyId ?? null
      if (newTopoId !== originalTopologyId.value) {
        await apiConfigApi.patchTopology(props.apiId, newTopoId)
        originalTopologyId.value = newTopoId
      }
      const payload: ApiConfigUpdate = {
        name: formState.value.name.trim(),
        path: formState.value.path.trim(),
        groupName: formState.value.groupName.trim() || null,
        domainId: resolvedDomainId,
        category: categoryName,
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
        domainId: resolvedDomainId,
        category: categoryName,
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

          <Form.Item label="所属子目录" name="category" class="form-col-half">
            <Select
              v-model:value="formState.category"
              :options="categoryOptions"
              placeholder="选择或输入子目录名称"
              allow-clear
              show-search
              option-filter-prop="label"
            />
          </Form.Item>
        </div>

        <div class="form-row">
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
            :options="topologies.map((t) => ({ label: t.name, value: t.id }))"
            @change="handleTopologyChange"
          />
          <div v-if="isEdit" class="hint">
            切换拓扑会弹窗确认并预扫描 SQL 视图引用；保存时独立调用 PATCH /topology
          </div>
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
              :request-field-names="availableFieldNames"
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
                @columns="onSqlColumns"
              />
            </div>
          </div>
        </Form.Item>

        <Form.Item
          v-if="formState.dataSource === 'sql'"
          label="参数映射"
          name="params"
        >
          <ParamMappingTable
            v-model="formState.params"
            :available-field-names="availableFieldNames"
          />
        </Form.Item>

        <Form.Item
          v-if="formState.dataSource === 'sql'"
          label="响应模板"
          name="responseTemplate"
          :tooltip="{ title: responseTemplateTooltip, overlayStyle: { maxWidth: '420px' } }"
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
          <div v-if="sqlColumnNames.length > 0" class="hint hint-columns">
            查询列名（snake_case）：{{ columnNamesHint }}
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
          <CollapsePanel key="request" :header="requestPanelHeader">
            <a-tabs v-model:active-key="requestSpecActiveTab" type="card">
              <a-tab-pane key="header" :tab="`请求头 (${headerCount})`">
                <HeaderSpecTable v-model="formState.requestHeaders" />
              </a-tab-pane>
              <a-tab-pane key="query" :tab="`请求 Query (${queryCount})`">
                <QuerySpecTable v-model="formState.requestQuery" />
              </a-tab-pane>
              <a-tab-pane key="body" :tab="bodyTabLabel">
                <BodySpecPanel v-model="formState.requestBody" />
              </a-tab-pane>
            </a-tabs>
          </CollapsePanel>

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

          <CollapsePanel key="auth" :header="authPanelHeader">
            <AuthConfigPanel v-model="formState.authConfig" />
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

.hint-columns {
  color: #1890ff;
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
