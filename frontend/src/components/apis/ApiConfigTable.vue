<script setup lang="ts">
import { ref, computed, watch, h } from 'vue'
import {
  Table,
  Space,
  Tag,
  Switch,
  Popconfirm,
  Input,
  Select,
  Button,
} from 'ant-design-vue'
import { SearchOutlined, ReloadOutlined, PlusOutlined, ExportOutlined, ImportOutlined, DeleteOutlined } from '@ant-design/icons-vue'
import { message, Modal, Popconfirm } from 'ant-design-vue'
import { apiConfigApi } from '@/api/api_config'
import { downloadBlob, timestampExcelFilename } from '@/utils/download'
import type { ApiConfigItem, HttpMethod } from '@/api/api_config'
import type { DomainItem } from '@/api/domain'

interface Props {
  items: ApiConfigItem[]
  domains: DomainItem[]
  total: number
  page: number
  pageSize: number
  loading: boolean
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'pageChange', page: number, pageSize: number): void
  (
    e: 'filterChange',
    filters: { method?: HttpMethod | null; enabled?: boolean | null },
  ): void
  (e: 'toggleEnabled', id: string, value: boolean): void
  (e: 'delete', id: string): void
  (e: 'refresh'): void
  (e: 'create', domainId?: string | null): void
  (e: 'edit', id: string): void
}>()

const methodFilter = ref<HttpMethod | undefined>(undefined)
const enabledFilter = ref<'true' | 'false' | undefined>(undefined)
const collapsedGroups = ref(new Set<string>())
const searchKeyword = ref('')
const selectedApiIds = ref<Set<string>>(new Set())
const fileInputRef = ref<HTMLInputElement>()

function toggleGroup(key: string) {
  if (collapsedGroups.value.has(key)) {
    collapsedGroups.value.delete(key)
  } else {
    collapsedGroups.value.add(key)
  }
}

// Auto-collapse all groups by default whenever items or domains change
// When searching, also auto-collapse groups with no matching results
watch(
  [() => props.items, () => props.domains, searchKeyword],
  () => {
    const kw = searchKeyword.value.trim().toLowerCase()
    const keys = new Set<string>()
    for (const d of props.domains) keys.add(d.id)
    for (const api of props.items) keys.add(api.domainId || '__none__')
    if (kw) {
      // When searching: expand groups with matches, collapse empty ones
      for (const key of keys) {
        const hasMatch = props.items.some(
          api => (api.domainId || '__none__') === key && (api.name.toLowerCase().includes(kw) || api.path.toLowerCase().includes(kw)),
        )
        if (hasMatch) {
          // Expand matching groups so user can see results
          collapsedGroups.value.delete(key)
        } else {
          // Collapse empty groups
          collapsedGroups.value.add(key)
        }
      }
    } else {
      collapsedGroups.value = keys
    }
  },
  { immediate: true },
)

const METHOD_COLORS: Record<HttpMethod, string> = {
  GET: 'green',
  POST: 'blue',
  PUT: 'orange',
  PATCH: 'purple',
  DELETE: 'red',
}

const methodOptions = [
  { label: 'GET', value: 'GET' },
  { label: 'POST', value: 'POST' },
  { label: 'PUT', value: 'PUT' },
  { label: 'PATCH', value: 'PATCH' },
  { label: 'DELETE', value: 'DELETE' },
]

const enabledOptions = [
  { label: '启用', value: 'true' },
  { label: '禁用', value: 'false' },
]

function applyFilters() {
  const enabledVal =
    enabledFilter.value === 'true' ? true : enabledFilter.value === 'false' ? false : null
  emit('filterChange', {
    method: methodFilter.value ?? null,
    enabled: enabledVal,
  })
}

function resetFilters() {
  methodFilter.value = undefined
  enabledFilter.value = undefined
  applyFilters()
}

function onToggle(id: string, value: boolean | string | number) {
  emit('toggleEnabled', id, Boolean(value))
}

function onDelete(id: string) {
  emit('delete', id)
}

function handleCreateInDomain(domainId: string | null) {
  emit('create', domainId)
}

async function handleExport() {
  try {
    const ids = selectedApiIds.value.size > 0 ? [...selectedApiIds.value] : undefined
    const result = await apiConfigApi.export(ids ? { ids } : {})
    const blob = new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' })
    downloadBlob(blob, timestampExcelFilename('apis-export').replace('.xlsx', '.json'))
    message.success(ids ? `已导出 ${ids.length} 个接口` : '导出成功')
    selectedApiIds.value.clear()
  } catch {}
}

async function handleExportDomain(domainId: string | null) {
  try {
    const result = await apiConfigApi.export(domainId ? { domainId } : {})
    const blob = new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' })
    downloadBlob(blob, timestampExcelFilename('apis-export').replace('.xlsx', '.json'))
    message.success('导出成功')
  } catch {}
}

function handleImportClick() {
  fileInputRef.value?.click()
}

async function handleClearDirectory(domainId: string, domainName: string) {
  try {
    const result = await apiConfigApi.clearDirectory(domainId)
    message.success(`已清空 ${result.clearedCount} 个接口的归属`)
    emit('refresh')
  } catch {}
}

async function handleFileChosen(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return

  if (!file.name.endsWith('.json')) {
    message.error('仅支持 .json 文件')
    return
  }

  // Read file content for preview
  let doc: { apis: Array<Record<string, unknown>> }
  try {
    const text = await file.text()
    doc = JSON.parse(text)
    if (!doc.apis || !Array.isArray(doc.apis)) {
      message.error('格式无效：缺少 apis 数组')
      return
    }
  } catch {
    message.error('JSON 解析失败')
    return
  }

  // Build preview
  const toCreate: Array<{ method: string; path: string; name: string }> = []
  const toUpdate: Array<{ method: string; path: string; oldName: string; newName: string }> = []
  const errors: string[] = []

  for (const api of doc.apis) {
    if (!api.method || !api.path) {
      errors.push('缺少 method/path，跳过')
      continue
    }
    const existing = props.items.find(
      item =>
        item.method === api.method &&
        item.path === api.path,
    )
    if (existing) {
      toUpdate.push({
        method: api.method as string,
        path: api.path as string,
        oldName: existing.name,
        newName: (api.name as string) || '',
      })
    } else {
      toCreate.push({
        method: api.method as string,
        path: api.path as string,
        name: (api.name as string) || '',
      })
    }
  }

  // Show preview modal
  const children: ReturnType<typeof h>[] = []

  if (toCreate.length) {
    children.push(
      h('div', { style: { fontWeight: 'bold', marginBottom: '4px' } },
        `将新建 ${toCreate.length} 个接口：`),
      ...toCreate.map(item =>
        h('div', { style: { paddingLeft: '8px' } },
          `+ ${item.method} ${item.path} ${item.name}`),
      ),
    )
  }

  if (toUpdate.length) {
    if (children.length) children.push(h('br'))
    children.push(
      h('div', { style: { fontWeight: 'bold', marginBottom: '4px' } },
        `将更新 ${toUpdate.length} 个接口：`),
      ...toUpdate.map(item => {
        const namePart = item.oldName !== item.newName
          ? `（${item.oldName} → ${item.newName}）`
          : `（${item.newName || '(空)'}）`
        return h('div', { style: { paddingLeft: '8px' } },
          `~ ${item.method} ${item.path} ${namePart}`)
      }),
    )
  }

  if (errors.length) {
    if (children.length) children.push(h('br'))
    children.push(
      h('div', { style: { color: '#faad14' } },
        `⚠ 有 ${errors.length} 行将被跳过。`),
    )
  }

  if (toCreate.length === 0 && toUpdate.length === 0 && errors.length > 0) {
    message.warning('没有可导入的接口')
    return
  }

  Modal.confirm({
    title: '确认导入',
    content: () => h('div', { style: { lineHeight: '1.8' } }, children),
    okText: '确认导入',
    cancelText: '取消',
    width: 520,
    onOk: async () => {
      const result = await apiConfigApi.import(file)
      const parts: string[] = []
      if (result.created) parts.push(`新建 ${result.created} 个`)
      if (result.updated) parts.push(`更新 ${result.updated} 个`)
      message.success(parts.join('，') || '导入完成')
      if (result.errors.length) {
        message.warning(result.errors.join('；'))
      }
      emit('refresh')
    },
  })
}

const columns = [
  { title: '名称', dataIndex: 'name', key: 'name', width: 180 },
  { title: '方法', dataIndex: 'method', key: 'method', width: 100 },
  { title: '路径', dataIndex: 'path', key: 'path', ellipsis: true },
  { title: '分类', dataIndex: 'category', key: 'category', width: 100 },
  { title: '数据源', dataIndex: 'dataSource', key: 'dataSource', width: 100 },
  { title: '启用', dataIndex: 'enabled', key: 'enabled', width: 90 },
  { title: '操作', key: 'action', width: 140, fixed: 'right' as const },
]

function formatDate(iso: string): string {
  if (!iso) return '-'
  const d = new Date(iso)
  return d.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}
</script>

<template>
  <div class="api-config-table">
    <div class="toolbar">
      <Space wrap>
        <Input
          v-model:value="searchKeyword"
          placeholder="搜索接口名称或路径..."
          style="width: 260px"
          allow-clear
        >
          <template #prefix><SearchOutlined /></template>
        </Input>
        <Select
          v-model:value="methodFilter"
          :options="methodOptions"
          placeholder="方法"
          style="width: 120px"
          allow-clear
          @change="applyFilters"
        />
        <Select
          v-model:value="enabledFilter"
          :options="enabledOptions"
          placeholder="状态"
          style="width: 120px"
          allow-clear
          @change="applyFilters"
        />
        <Button @click="resetFilters">重置</Button>
      </Space>

      <Space>
        <Button @click="handleExport">
          <template #icon><ExportOutlined /></template>
          {{ selectedApiIds.size > 0 ? `导出 (${selectedApiIds.size})` : '导出' }}
        </Button>
        <Button @click="handleImportClick">
          <template #icon><ImportOutlined /></template>
          导入
        </Button>
        <input
          ref="fileInputRef"
          type="file"
          accept=".json"
          style="display: none"
          @change="handleFileChosen"
        />
        <Button @click="emit('refresh')">
          <template #icon><ReloadOutlined /></template>
          刷新
        </Button>
        <Button type="primary" @click="emit('create')">
          <template #icon><PlusOutlined /></template>
          新建接口
        </Button>
      </Space>
    </div>

    <div v-for="group in (() => {
      const kw = searchKeyword.trim().toLowerCase()
      const map: Record<string, { domainId: string | null; domainName: string; apis: ApiConfigItem[]; totalCount: number }> = {}
      for (const d of domains) {
        map[d.id] = { domainId: d.id, domainName: d.name, apis: [], totalCount: 0 }
      }
      for (const api of items) {
        const key = api.domainId || '__none__'
        if (!map[key]) map[key] = { domainId: api.domainId, domainName: api.domainName || '未归类', apis: [], totalCount: 0 }
        map[key].totalCount++
        if (!kw || api.name.toLowerCase().includes(kw) || api.path.toLowerCase().includes(kw)) {
          map[key].apis.push(api)
        }
      }
      const sorted = Object.values(map).sort((a, b) => {
        if (a.domainId === null) return 1
        if (b.domainId === null) return -1
        return a.domainName.localeCompare(b.domainName)
      })
      return sorted
    })()" :key="group.domainId || '__none__'" class="domain-group">
      <div class="domain-group-header" @click="toggleGroup(group.domainId || '__none__')">
        <span class="group-arrow">{{ collapsedGroups.has(group.domainId || '__none__') ? '▶' : '▼' }}</span>
        <span class="group-title">{{ group.domainName }} ({{ group.totalCount }})</span>
        <Button size="small" class="group-add-btn" @click.stop="handleExportDomain(group.domainId)"><ExportOutlined /></Button>
        <Button size="small" class="group-add-btn" @click.stop="handleCreateInDomain(group.domainId)">+</Button>
        <Popconfirm
          v-if="group.domainId"
          :title="`确定清空目录'${group.domainName}'下的所有接口归属？接口不会被删除，将移至未归类`"
          ok-text="确定"
          cancel-text="取消"
          @confirm="handleClearDirectory(group.domainId!, group.domainName)"
        >
          <Button size="small" class="group-add-btn" @click.stop><DeleteOutlined /></Button>
        </Popconfirm>
      </div>
      <div v-show="!collapsedGroups.has(group.domainId || '__none__')" class="domain-group-body">
        <Table
          :data-source="group.apis"
          :columns="columns"
          :loading="loading"
          :pagination="false"
          size="small"
          row-key="id"
          :row-selection="{
            selectedRowKeys: [...selectedApiIds],
            onChange: (keys: (string | number)[]) => { selectedApiIds.value = new Set(keys as string[]) },
            onSelectAll: (selected: boolean) => { if (!selected) selectedApiIds.value = new Set() },
          }"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'method'">
              <Tag :color="METHOD_COLORS[(record as ApiConfigItem).method]">
                {{ (record as ApiConfigItem).method }}
              </Tag>
            </template>

            <template v-else-if="column.key === 'path'">
              <code>{{ (record as ApiConfigItem).path }}</code>
            </template>

            <template v-else-if="column.key === 'category'">
              <Tag v-if="(record as ApiConfigItem).category" color="blue">{{ (record as ApiConfigItem).category }}</Tag>
              <span v-else class="placeholder">-</span>
            </template>

            <template v-else-if="column.key === 'dataSource'">
              <Tag v-if="(record as ApiConfigItem).dataSource === 'sql'" color="geekblue">SQL</Tag>
              <Tag v-else>静态</Tag>
            </template>

            <template v-else-if="column.key === 'enabled'">
              <Switch
                :checked="(record as ApiConfigItem).enabled"
                checked-children="启用"
                un-checked-children="禁用"
                @change="(v: boolean | string | number) => onToggle((record as ApiConfigItem).id, v)"
              />
            </template>

            <template v-else-if="column.key === 'action'">
              <Space>
                <a @click="emit('edit', (record as ApiConfigItem).id)">编辑</a>
                <Popconfirm
                  title="确定删除该接口配置？"
                  ok-text="确定"
                  cancel-text="取消"
                  @confirm="onDelete((record as ApiConfigItem).id)"
                >
                  <a style="color: #ff4d4f">删除</a>
                </Popconfirm>
              </Space>
            </template>
          </template>
        </Table>
      </div>
    </div>

    <div v-if="items.length === 0 && domains.length === 0" style="text-align: center; padding: 48px 0; color: rgba(0,0,0,0.35);">
      暂无接口配置
    </div>
  </div>
</template>

<style scoped>
.toolbar {
  display: flex;
  justify-content: space-between;
  margin-bottom: 16px;
  gap: 12px;
  flex-wrap: wrap;
}

code {
  padding: 2px 6px;
  background: #f5f5f5;
  border-radius: 3px;
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 12px;
}

.domain-group {
  margin-bottom: 4px;
  border: 1px solid #f0f0f0;
  border-radius: 4px;
  overflow: hidden;
}

.domain-group-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  background: #fafafa;
  cursor: pointer;
  user-select: none;
  transition: background 0.2s;
}

.domain-group-header:hover {
  background: #f0f0f0;
}

.group-arrow {
  font-size: 10px;
  width: 14px;
  color: rgba(0, 0, 0, 0.45);
}

.group-title {
  flex: 1;
  font-size: 14px;
  font-weight: 500;
  color: rgba(0, 0, 0, 0.85);
}

.group-add-btn {
  flex-shrink: 0;
}

.domain-group-body {
  border-top: 1px solid #f0f0f0;
}

.placeholder {
  color: rgba(0, 0, 0, 0.25);
}
</style>
