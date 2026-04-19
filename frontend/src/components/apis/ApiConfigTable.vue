<script setup lang="ts">
import { ref } from 'vue'
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
import { SearchOutlined, ReloadOutlined, PlusOutlined } from '@ant-design/icons-vue'
import type { ApiConfigItem, HttpMethod } from '@/api/api_config'

interface Props {
  items: ApiConfigItem[]
  total: number
  page: number
  pageSize: number
  loading: boolean
}

defineProps<Props>()

const emit = defineEmits<{
  (e: 'pageChange', page: number, pageSize: number): void
  (
    e: 'filterChange',
    filters: { method?: HttpMethod | null; enabled?: boolean | null; path?: string | null },
  ): void
  (e: 'toggleEnabled', id: string, value: boolean): void
  (e: 'delete', id: string): void
  (e: 'refresh'): void
  (e: 'create'): void
  (e: 'edit', id: string): void
}>()

const pathInput = ref('')
const methodFilter = ref<HttpMethod | undefined>(undefined)
const enabledFilter = ref<'true' | 'false' | undefined>(undefined)

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
    path: pathInput.value || null,
  })
}

function resetFilters() {
  pathInput.value = ''
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

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function handleTableChange(pagination: any) {
  const p = pagination.current ?? 1
  const ps = pagination.pageSize ?? 20
  emit('pageChange', p, ps)
}

const columns = [
  { title: '名称', dataIndex: 'name', key: 'name', width: 180 },
  { title: '方法', dataIndex: 'method', key: 'method', width: 100 },
  { title: '路径', dataIndex: 'path', key: 'path', ellipsis: true },
  { title: '分组', dataIndex: 'groupName', key: 'groupName', width: 120 },
  { title: '数据源', dataIndex: 'dataSource', key: 'dataSource', width: 100 },
  { title: '启用', dataIndex: 'enabled', key: 'enabled', width: 90 },
  { title: '更新时间', dataIndex: 'updatedAt', key: 'updatedAt', width: 180 },
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
          v-model:value="pathInput"
          placeholder="按路径搜索"
          style="width: 220px"
          allow-clear
          @press-enter="applyFilters"
        >
          <template #prefix>
            <SearchOutlined />
          </template>
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
        <Button type="primary" @click="applyFilters">搜索</Button>
        <Button @click="resetFilters">重置</Button>
      </Space>

      <Space>
        <Button @click="emit('refresh')">
          <template #icon><ReloadOutlined /></template>
          刷新
        </Button>
        <Button type="primary" @click="emit('create')">
          <template #icon><PlusOutlined /></template>
          新建
        </Button>
      </Space>
    </div>

    <Table
      :data-source="items"
      :columns="columns"
      :loading="loading"
      :pagination="{
        current: page,
        pageSize: pageSize,
        total: total,
        showSizeChanger: true,
        showQuickJumper: true,
        showTotal: (t: number) => `共 ${t} 条`,
      }"
      row-key="id"
      :scroll="{ x: 1100 }"
      @change="handleTableChange"
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

        <template v-else-if="column.key === 'groupName'">
          {{ (record as ApiConfigItem).groupName || '-' }}
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

        <template v-else-if="column.key === 'updatedAt'">
          {{ formatDate((record as ApiConfigItem).updatedAt) }}
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

      <template #emptyText>
        <a-empty description="暂无接口配置" />
      </template>
    </Table>
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
</style>
