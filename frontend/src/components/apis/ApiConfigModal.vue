<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Modal, Form, Input, Select, Switch, Spin } from 'ant-design-vue'
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
}

const DEFAULT_TEMPLATE_PLACEHOLDER =
  '{"code":0,"data":"{{items}}","total":"{{total}}","pageNo":"{{pageNo}}","pageSize":"{{pageSize}}"}'

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
    }
    const tpl = cfg.response?.template
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
  if (formState.value.dataSource !== 'sql') return {}
  const cfg: Record<string, unknown> = {}
  if (formState.value.params.length > 0) {
    cfg.params = formState.value.params
  }
  const tpl = formState.value.responseTemplate.trim()
  if (tpl) {
    cfg.response = { template: tpl }
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
</style>
