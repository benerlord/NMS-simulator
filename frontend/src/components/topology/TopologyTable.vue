<script setup lang="ts">
import { h, ref } from 'vue'
import { Table, Button, Space, Tag, Input, Modal, Alert, message } from 'ant-design-vue'
import {
  SearchOutlined,
  PlusOutlined,
  ImportOutlined,
  ExportOutlined,
} from '@ant-design/icons-vue'
import { apiGet } from '@/api/http'
import type { TopologyListItem, TopologyDeleteImpact } from '@/api/topology'

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

// LEGACY-07: 删除前先调 delete-impact 端点预扫描受影响接口，再弹 Modal.confirm
async function onDeleteItem(record: TopologyListItem) {
  let impact: TopologyDeleteImpact | null = null
  try {
    impact = await apiGet<TopologyDeleteImpact>(`/topologies/${record.id}/delete-impact`)
  } catch {
    // 预扫描失败：弹通用确认框，不阻断
    message.warning('预扫描失败，但仍可继续删除')
  }

  const affectedCount = impact?.affectedApiCount ?? 0
  const affectedApis = impact?.affectedApis ?? []

  Modal.confirm({
    title: `删除拓扑 "${record.name}"`,
    width: 540,
    okText: '确认删除',
    okButtonProps: { danger: true },
    cancelText: '取消',
    icon: null,
    content: () =>
      h('div', [
        affectedCount > 0
          ? h(Alert, {
              type: 'warning',
              showIcon: true,
              message: `${affectedCount} 个接口配置当前绑定此拓扑，将被自动解绑（接口配置保留，仅 topology_id 置空）`,
              style: 'margin-bottom: 12px',
            })
          : h(Alert, {
              type: 'info',
              showIcon: true,
              message: '该拓扑当前未被任何接口配置引用',
              style: 'margin-bottom: 12px',
            }),
        affectedApis.length > 0
          ? h(
              'div',
              {
                style:
                  'max-height: 200px; overflow-y: auto; padding: 8px 12px; background: #fafafa; border: 1px solid #f0f0f0; border-radius: 4px; margin-bottom: 8px',
              },
              [
                h(
                  'div',
                  { style: 'font-size: 12px; color: #888; margin-bottom: 6px' },
                  affectedApis.length < affectedCount
                    ? `受影响接口（前 ${affectedApis.length} 个，共 ${affectedCount} 个）：`
                    : '受影响接口：',
                ),
                ...affectedApis.map((api) =>
                  h(
                    'div',
                    { style: 'font-size: 13px; line-height: 1.6' },
                    [
                      h(
                        'span',
                        {
                          style:
                            'display: inline-block; width: 56px; color: #1677ff; font-weight: 500',
                        },
                        api.method,
                      ),
                      h('span', {}, api.name + ' '),
                      h('span', { style: 'color: #999' }, api.path),
                    ],
                  ),
                ),
              ],
            )
          : null,
      ]),
    onOk: () => {
      emit('delete', record.id)
    },
  })
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
          <a @click="onEnterCanvas((record as TopologyListItem).id)">{{ (record as TopologyListItem).name }}</a>
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
            <a
              style="color: #ff4d4f"
              @click="onDeleteItem(record as TopologyListItem)"
            >
              删除
            </a>
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
