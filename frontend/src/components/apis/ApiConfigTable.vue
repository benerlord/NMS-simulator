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
  message,
  Modal,
} from 'ant-design-vue'
import { SearchOutlined, ReloadOutlined, PlusOutlined, ExportOutlined, ImportOutlined, DeleteOutlined, CopyOutlined, FolderAddOutlined, EditOutlined } from '@ant-design/icons-vue'
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
  (e: 'create', category?: string | null, domainId?: string | null): void
  (e: 'edit', id: string): void
  (e: 'duplicate', id: string): void
  (e: 'renameCategory', domainId: string, oldName: string, newName: string): void
  (e: 'deleteCategory', domainId: string, name: string): void
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
// When searching, expand groups that contain matching results
watch(
  [() => props.items, () => props.domains, searchKeyword],
  () => {
    const kw = searchKeyword.value.trim().toLowerCase()
    const domainKeys = new Set(props.domains.map(d => d.name))
    const subGroupKeysByDomain = new Map<string, Set<string>>()

    for (const d of props.domains) {
      subGroupKeysByDomain.set(d.id, new Set())
    }

    for (const api of props.items) {
      const dId = api.domainId || null
      const cat = api.category
      if (dId && cat && cat !== props.domains.find(d => d.id === dId)?.name) {
        subGroupKeysByDomain.get(dId)?.add(cat)
      }
    }

    if (kw) {
      const hasDomainMatch = new Map<string, boolean>()
      const hasSubGroupMatch = new Map<string, boolean>()
      for (const dk of domainKeys) {
        hasDomainMatch.set(dk, false)
      }

      for (const api of props.items) {
        if (!api.name.toLowerCase().includes(kw) && !api.path.toLowerCase().includes(kw)) continue
        const dk = api.domainName || null
        const cat = api.category
        if (dk && domainKeys.has(dk)) {
          if (!cat || cat === dk) {
            hasDomainMatch.set(dk, true)
          } else {
            hasSubGroupMatch.set(`${dk}::${cat}`, true)
          }
        }
      }

      for (const dk of domainKeys) {
        const subKeys = subGroupKeysByDomain.get(props.domains.find(d => d.name === dk)?.id || '') || new Set()
        const anySubMatch = [...subKeys].some(sg => hasSubGroupMatch.get(`${dk}::${sg}`))
        if (hasDomainMatch.get(dk) || anySubMatch) {
          collapsedGroups.value.delete(dk)
        } else {
          collapsedGroups.value.add(dk)
        }
        for (const sg of subKeys) {
          if (hasSubGroupMatch.get(`${dk}::${sg}`)) {
            collapsedGroups.value.delete(sg)
          } else {
            collapsedGroups.value.add(sg)
          }
        }
      }
    } else {
      const allKeys = new Set(domainKeys)
      for (const sgs of subGroupKeysByDomain.values()) {
        for (const sg of sgs) allKeys.add(sg)
      }
      allKeys.add('__none__')
      collapsedGroups.value = allKeys
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

function handleCreateInCategory(category: string | null, domainId?: string | null) {
  emit('create', category, domainId)
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

async function handleExportByCategory(apiIds: string[]) {
  // 空目录直接提示并返回，避免传 {} 给后端被解释成"导出全部"
  if (apiIds.length === 0) {
    message.info('该目录下暂无接口可导出')
    return
  }
  try {
    const result = await apiConfigApi.export({ ids: apiIds })
    const blob = new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' })
    downloadBlob(blob, timestampExcelFilename('apis-export').replace('.xlsx', '.json'))
    message.success(`已导出 ${result.apis.length} 个接口`)
  } catch {}
}

async function handleDuplicate(record: ApiConfigItem) {
  try {
    const result = await apiConfigApi.duplicate(record.id)
    message.success('接口已复制')
    emit('duplicate', result.id)
  } catch {}
}

const editingCategory = ref<{ domainId: string; oldName: string } | null>(null)
const editingCategoryName = ref('')
const newCategoryDomainId = ref<string | null>(null)
const newCategoryName = ref('')

function startRenameCategory(domainId: string, name: string) {
  editingCategory.value = { domainId, oldName: name }
  editingCategoryName.value = name
}

function confirmRenameCategory() {
  if (editingCategory.value && editingCategoryName.value.trim()) {
    emit('renameCategory', editingCategory.value.domainId, editingCategory.value.oldName, editingCategoryName.value.trim())
    editingCategory.value = null
  }
}

function cancelRenameCategory() {
  editingCategory.value = null
}

function handleDeleteCategory(domainId: string, name: string) {
  emit('deleteCategory', domainId, name)
}

function startAddCategory(domainId: string) {
  newCategoryDomainId.value = domainId
  newCategoryName.value = ''
}

function confirmAddCategory() {
  if (newCategoryDomainId.value && newCategoryName.value.trim()) {
    handleCreateInCategory(newCategoryName.value.trim(), newCategoryDomainId.value)
    newCategoryDomainId.value = null
  }
}

function cancelAddCategory() {
  newCategoryDomainId.value = null
}

function handleImportClick() {
  fileInputRef.value?.click()
}

async function handleDeleteDirectory(domainId: string, domainName: string) {
  try {
    const result = await apiConfigApi.deleteDirectory(domainId)
    message.success(`已删除目录'${domainName}'及 ${result.deletedApis} 个接口`)
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
  const newCategories = new Set<string>()

  for (const api of doc.apis) {
    if (!api.method || !api.path) {
      errors.push('缺少 method/path，跳过')
      continue
    }
    const cat = api.category as string | undefined
    if (cat && !props.domains.some(d => d.name === cat)) {
      newCategories.add(cat)
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

  if (newCategories.size > 0) {
    if (children.length) children.push(h('br'))
    children.push(
      h('div', { style: { color: '#1890ff' } },
        `ℹ 将自动创建 ${newCategories.size} 个目录：${[...newCategories].join('、')}`),
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
      if (result.autoCreatedDomains.length) {
        message.info(`自动创建了 ${result.autoCreatedDomains.length} 个目录：${result.autoCreatedDomains.join('、')}`)
      }
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
  { title: '操作', key: 'action', width: 170, fixed: 'right' as const },
]

// 每个分组渲染独立 Table，但 selectedApiIds 是全局 Set。
// onChange 只携带"当前 Table 可见行的新选中状态"，因此合并时必须先剔除该作用域内的旧 id，再加入 keys，
// 否则会把其它分组的选择整体覆盖掉。
function buildRowSelection(scopedApis: ApiConfigItem[]) {
  const scopedIds = scopedApis.map(a => a.id)
  return {
    selectedRowKeys: scopedIds.filter(id => selectedApiIds.value.has(id)),
    onChange: (keys: (string | number)[]) => {
      const next = new Set(selectedApiIds.value)
      for (const id of scopedIds) next.delete(id)
      for (const k of keys) next.add(k as string)
      selectedApiIds.value = next
    },
  }
}

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

type SubGroup = { categoryKey: string; categoryName: string; domainId: string; apis: ApiConfigItem[]; allIds: string[]; totalCount: number }
type DomainGroup = { categoryKey: string; categoryName: string; domainId: string; apis: ApiConfigItem[]; allIds: string[]; totalCount: number; subGroups: SubGroup[] }
type NoneGroup = { categoryKey: '__none__'; categoryName: string; domainId: null; apis: ApiConfigItem[]; allIds: string[]; totalCount: number; subGroups: SubGroup[] }

function resolveDomainId(api: ApiConfigItem, nameToId: Map<string, string>): string | null {
  if (api.domainId) return api.domainId
  if (api.domainName) return nameToId.get(api.domainName) ?? null
  return null
}

const groupedDomains = computed(() => {
  const kw = searchKeyword.value.trim().toLowerCase()
  const domainMap = new Map<string, DomainGroup>()
  for (const d of props.domains) {
    domainMap.set(d.id, { categoryKey: d.name, categoryName: d.name, domainId: d.id, apis: [], allIds: [], totalCount: 0, subGroups: [] })
  }
  const domainNameToId = new Map(props.domains.map(d => [d.name, d.id]))
  const noneGroup: NoneGroup = { categoryKey: '__none__', categoryName: '未归类', domainId: null, apis: [], allIds: [], totalCount: 0, subGroups: [] }

  for (const api of props.items) {
    const dId = resolveDomainId(api, domainNameToId)
    const matchesKw = !kw || api.name.toLowerCase().includes(kw) || api.path.toLowerCase().includes(kw)

    if (!dId) {
      noneGroup.totalCount++
      noneGroup.allIds.push(api.id)
      if (matchesKw) noneGroup.apis.push(api)
      continue
    }

    const dg = domainMap.get(dId)!
    dg.totalCount++
    dg.allIds.push(api.id)

    const cat = api.category
    if (!cat || cat === dg.categoryName) {
      if (matchesKw) dg.apis.push(api)
    } else {
      let sg = dg.subGroups.find(s => s.categoryKey === cat)
      if (!sg) {
        sg = { categoryKey: cat, categoryName: cat, domainId: dId, apis: [], allIds: [], totalCount: 0 }
        dg.subGroups.push(sg)
      }
      sg.totalCount++
      sg.allIds.push(api.id)
      if (matchesKw) sg.apis.push(api)
    }
  }

  for (const dg of domainMap.values()) {
    dg.subGroups.sort((a, b) => a.categoryName.localeCompare(b.categoryName))
  }

  const sorted = [...domainMap.values()].sort((a, b) => a.categoryName.localeCompare(b.categoryName))
  if (noneGroup.totalCount > 0) sorted.push(noneGroup)
  return sorted
})
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

    <!-- Domain groups with nested sub-groups -->
    <div v-for="group in groupedDomains" :key="group.categoryKey" class="domain-group">
      <!-- Domain header -->
      <div class="domain-group-header" @click="toggleGroup(group.categoryKey)">
        <span class="group-arrow">{{ collapsedGroups.has(group.categoryKey) ? '▶' : '▼' }}</span>
        <span class="group-title">{{ group.categoryName }} ({{ group.totalCount }})</span>
        <Button size="small" class="group-add-btn" @click.stop="handleExportByCategory(group.allIds)"><ExportOutlined /></Button>
        <Button size="small" class="group-add-btn" @click.stop="handleCreateInCategory(group.categoryKey === '__none__' ? null : group.categoryName, group.domainId)">+</Button>
        <template v-if="group.domainId">
          <Button size="small" class="group-add-btn" @click.stop="startAddCategory(group.domainId)" title="添加子目录"><FolderAddOutlined /></Button>
          <Popconfirm
            :title="`确定删除目录'${group.categoryName}'及其下的 ${group.totalCount} 个接口？此操作不可恢复`"
            ok-text="确定"
            cancel-text="取消"
            @confirm="handleDeleteDirectory(group.domainId, group.categoryName)"
          >
            <Button size="small" class="group-add-btn" @click.stop title="删除目录"><DeleteOutlined /></Button>
          </Popconfirm>
        </template>
      </div>
      <div v-show="!collapsedGroups.has(group.categoryKey)" class="domain-group-body">
        <!-- Domain direct APIs -->
        <Table
          v-if="group.apis.length > 0"
          :data-source="group.apis"
          :columns="columns"
          :loading="loading"
          :pagination="false"
          size="small"
          row-key="id"
          :row-selection="buildRowSelection(group.apis)"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'method'">
              <Tag :color="METHOD_COLORS[(record as ApiConfigItem).method]">{{ (record as ApiConfigItem).method }}</Tag>
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
                <a @click="handleDuplicate(record as ApiConfigItem)" title="复制"><CopyOutlined /></a>
                <Popconfirm title="确定删除该接口配置？" ok-text="确定" cancel-text="取消" @confirm="onDelete((record as ApiConfigItem).id)">
                  <a style="color: #ff4d4f">删除</a>
                </Popconfirm>
              </Space>
            </template>
          </template>
        </Table>

        <!-- Sub-groups nested under domain -->
        <div v-for="sub in group.subGroups" :key="sub.categoryKey" class="sub-group">
          <div class="sub-group-header" @click="toggleGroup(sub.categoryKey)">
            <span class="group-arrow">{{ collapsedGroups.has(sub.categoryKey) ? '▶' : '▼' }}</span>
            <span class="group-title">{{ sub.categoryName }} ({{ sub.totalCount }})</span>
            <Button size="small" class="group-add-btn" @click.stop="handleExportByCategory(sub.allIds)"><ExportOutlined /></Button>
            <Button size="small" class="group-add-btn" @click.stop="handleCreateInCategory(sub.categoryName, sub.domainId)">+</Button>
            <Button size="small" class="group-add-btn" @click.stop="startRenameCategory(sub.domainId, sub.categoryName)" title="重命名"><EditOutlined /></Button>
            <Popconfirm
              :title="`确定删除子目录'${sub.categoryName}'？其下的接口将归入未分类`"
              ok-text="确定"
              cancel-text="取消"
              @confirm="handleDeleteCategory(sub.domainId, sub.categoryName)"
            >
              <Button size="small" class="group-add-btn" @click.stop title="删除子目录"><DeleteOutlined /></Button>
            </Popconfirm>
          </div>
          <div v-if="editingCategory && editingCategory.domainId === sub.domainId && editingCategory.oldName === sub.categoryKey" style="padding: 8px 16px; background: #f0f5ff;">
            <Space>
              <Input v-model:value="editingCategoryName" size="small" style="width: 200px" @pressEnter="confirmRenameCategory" />
              <Button size="small" type="primary" @click="confirmRenameCategory">确定</Button>
              <Button size="small" @click="cancelRenameCategory">取消</Button>
            </Space>
          </div>
          <div v-show="!collapsedGroups.has(sub.categoryKey)" class="domain-group-body">
            <Table
              :data-source="sub.apis"
              :columns="columns"
              :loading="loading"
              :pagination="false"
              size="small"
              row-key="id"
              :row-selection="buildRowSelection(sub.apis)"
            >
              <template #bodyCell="{ column, record }">
                <template v-if="column.key === 'method'">
                  <Tag :color="METHOD_COLORS[(record as ApiConfigItem).method]">{{ (record as ApiConfigItem).method }}</Tag>
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
                    <a @click="handleDuplicate(record as ApiConfigItem)" title="复制"><CopyOutlined /></a>
                    <Popconfirm title="确定删除该接口配置？" ok-text="确定" cancel-text="取消" @confirm="onDelete((record as ApiConfigItem).id)">
                      <a style="color: #ff4d4f">删除</a>
                    </Popconfirm>
                  </Space>
                </template>
              </template>
            </Table>
          </div>
        </div>
      </div>
    </div>

    <div v-if="items.length === 0 && domains.length === 0" style="text-align: center; padding: 48px 0; color: rgba(0,0,0,0.35);">
      暂无接口配置
    </div>

    <Modal
      v-model:open="newCategoryDomainId"
      title="添加子目录"
      @ok="confirmAddCategory"
      @cancel="cancelAddCategory"
    >
      <Input v-model:value="newCategoryName" placeholder="请输入子目录名称" @pressEnter="confirmAddCategory" />
    </Modal>
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

.sub-group {
  margin: 0;
  border: none;
  border-top: 1px dashed #e8e8e8;
  border-radius: 0;
}

.sub-group-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px 8px 32px;
  background: #f6f8fa;
  cursor: pointer;
  user-select: none;
  transition: background 0.2s;
}

.sub-group-header:hover {
  background: #eef1f5;
}

.placeholder {
  color: rgba(0, 0, 0, 0.25);
}
</style>
