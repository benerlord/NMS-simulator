<script setup lang="ts">
import { ref } from 'vue'
import { Table, Button, Space, Tag, Popconfirm, Input } from 'ant-design-vue'
import {
  SearchOutlined,
  PlusOutlined,
  ImportOutlined,
  ExportOutlined,
} from '@ant-design/icons-vue'
import type { TopologyListItem } from '@/api/topology'

interface Props {
  items: TopologyListItem[]
  total: number
  page: number
  pageSize: number
  loading: boolean
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'pageChange', page: number, pageSize: number): void
  (e: 'search', name: string): void
  (e: 'sort', sort: string): void
  (e: 'create'): void
  (e: 'edit', item: TopologyListItem): void
  (e: 'delete', id: string): void
  (e: 'enterCanvas', id: string): void
  (e: 'export', item: TopologyListItem): void
  (e: 'import'): void
}>()

const nameInput = ref('')

function handleSearch() {
  emit('search', nameInput.value)
}

function onEditItem(item: TopologyListItem) {
  emit('edit', item)
}

function onDeleteItem(id: string) {
  emit('delete', id)
}

function onCreate() {
  emit('create')
}

function onEnterCanvas(id: string) {
  emit('enterCanvas', id)
}

function onExport(item: TopologyListItem) {
  emit('export', item)
}

function onImport() {
  emit('import')
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function handleTableChange(pagination: any, _filters: any, sorter: any) {
  const page = pagination.current ?? 1
  const size = pagination.pageSize ?? 20
  emit('pageChange', page, size)

  const field = sorter.field
  if (field) {
    const dir = sorter.order === 'ascend' ? 'asc' : 'desc'
    emit('sort', `${field},${dir}`)
  }
}

const columns = [
  {
    title: '名称',
    dataIndex: 'name',
    key: 'name',
    sorter: true,
    width: 200,
  },
  {
    title: '描述',
    dataIndex: 'description',
    key: 'description',
    ellipsis: true,
  },
  {
    title: '版本',
    dataIndex: 'version',
    key: 'version',
    width: 80,
  },
  {
    title: '创建时间',
    dataIndex: 'createdAt',
    key: 'createdAt',
    sorter: true,
    width: 180,
  },
  {
    title: '更新时间',
    dataIndex: 'updatedAt',
    key: 'updatedAt',
    sorter: true,
    width: 180,
  },
  {
    title: '操作',
    key: 'action',
    width: 220,
    fixed: 'right' as const,
  },
]

function formatDate(iso: string): string {
  if (!iso) return '-'
  const d = new Date(iso)
  return d.toLocaleString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}
</script>

<template>
  <div class="topology-table">
    <!-- Toolbar -->
    <div class="toolbar">
      <Space>
        <Input
          v-model:value="nameInput"
          placeholder="按名称搜索"
          style="width: 200px"
          allow-clear
          @press-enter="handleSearch"
        >
          <template #prefix>
            <SearchOutlined />
          </template>
        </Input>
        <Button type="primary" @click="handleSearch">搜索</Button>
      </Space>

      <Space>
        <Button @click="onImport">
          <template #icon><ImportOutlined /></template>
          导入
        </Button>
        <Button @click="onCreate">
          <template #icon><PlusOutlined /></template>
          新建
        </Button>
      </Space>
    </div>

    <!-- Table -->
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
      :scroll="{ x: 900 }"
      @change="handleTableChange"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'name'">
          <a @click="onEditItem(record as TopologyListItem)">{{ (record as TopologyListItem).name }}</a>
        </template>

        <template v-else-if="column.key === 'description'">
          {{ (record as TopologyListItem).description || '-' }}
        </template>

        <template v-else-if="column.key === 'version'">
          <Tag>{{ (record as TopologyListItem).version }}</Tag>
        </template>

        <template v-else-if="column.key === 'createdAt'">
          {{ formatDate((record as TopologyListItem).createdAt) }}
        </template>

        <template v-else-if="column.key === 'updatedAt'">
          {{ formatDate((record as TopologyListItem).updatedAt) }}
        </template>

        <template v-else-if="column.key === 'action'">
          <Space>
            <a @click="onEditItem(record as TopologyListItem)">编辑</a>
            <a @click="onExport(record as TopologyListItem)">
              <ExportOutlined />
              导出
            </a>
            <Popconfirm
              title="确定删除该拓扑？"
              ok-text="确定"
              cancel-text="取消"
              @confirm="onDeleteItem((record as TopologyListItem).id)"
            >
              <a style="color: #ff4d4f">删除</a>
            </Popconfirm>
            <a @click="onEnterCanvas((record as TopologyListItem).id)">进入画布</a>
          </Space>
        </template>
      </template>

      <template #emptyText>
        <a-empty description="暂无拓扑数据">
          <template #image>
            <span style="font-size: 48px; opacity: 0.3">📋</span>
          </template>
        </a-empty>
      </template>
    </Table>
  </div>
</template>

<style scoped>
.toolbar {
  display: flex;
  justify-content: space-between;
  margin-bottom: 16px;
}
</style>
