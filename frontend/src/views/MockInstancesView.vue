<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Card, Button, Space, Table, Tag, Switch, Popconfirm, Typography, Tooltip, message } from 'ant-design-vue'
import { PlusOutlined, EditOutlined, DeleteOutlined, FileTextOutlined } from '@ant-design/icons-vue'
import { mockInstanceApi, type MockInstanceItem } from '@/api/mockInstance'
import MockInstanceModal from '@/components/mockInstance/MockInstanceModal.vue'
import InstanceLogsDrawer from '@/components/mockInstance/InstanceLogsDrawer.vue'

const instances = ref<MockInstanceItem[]>([])
const loading = ref(false)
const modalOpen = ref(false)
const editingInstance = ref<MockInstanceItem | null>(null)
const logsDrawerOpen = ref(false)
const logsInstance = ref<MockInstanceItem | null>(null)

function openLogs(item: MockInstanceItem) {
  logsInstance.value = item
  logsDrawerOpen.value = true
}

async function fetchInstances() {
  loading.value = true
  try {
    const res = await mockInstanceApi.list()
    instances.value = res.items
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editingInstance.value = null
  modalOpen.value = true
}

function openEdit(item: MockInstanceItem) {
  editingInstance.value = item
  modalOpen.value = true
}

async function handleCreate(data: { name: string; topologyId: string; port: number; description?: string | null; sslEnabled: boolean }) {
  await mockInstanceApi.create(data)
  message.success('实例创建成功')
  modalOpen.value = false
  fetchInstances()
}

async function handleUpdate(data: { name?: string | null; topologyId?: string | null; port?: number; description?: string | null; sslEnabled?: boolean }) {
  if (!editingInstance.value) return
  await mockInstanceApi.update(editingInstance.value.id, data)
  message.success('实例更新成功')
  modalOpen.value = false
  fetchInstances()
}

async function handleDelete(item: MockInstanceItem) {
  await mockInstanceApi.delete(item.id)
  message.success('实例已删除')
  fetchInstances()
}

async function handleToggleEnabled(item: MockInstanceItem, checked: boolean) {
  await mockInstanceApi.patchEnabled(item.id, checked)
  message.success(checked ? '已启用' : '已禁用')
  fetchInstances()
}

const columns = [
  { title: '名称', dataIndex: 'name', key: 'name', width: 180 },
  { title: '端口', dataIndex: 'port', key: 'port', width: 80 },
  { title: '协议', key: 'protocol', width: 80, align: 'center' as const },
  { title: '访问地址', key: 'url', width: 240 },
  { title: '所属拓扑', dataIndex: 'topologyName', key: 'topologyName', width: 160 },
  { title: '启用', key: 'enabled', width: 90, align: 'center' as const },
  { title: '接口数', key: 'apiCount', width: 80, align: 'center' as const },
  { title: '创建时间', dataIndex: 'createdAt', key: 'createdAt', width: 180 },
  { title: '操作', key: 'action', width: 150, fixed: 'right' as const },
]

function formatDate(iso: string): string {
  if (!iso) return '-'
  const d = new Date(iso)
  return d.toLocaleString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

onMounted(fetchInstances)
</script>

<template>
  <Card title="实例管理" :bordered="false">
    <template #extra>
      <Button type="primary" @click="openCreate">
        <template #icon><PlusOutlined /></template>
        新建实例
      </Button>
    </template>

    <Table
      :data-source="instances"
      :columns="columns"
      :loading="loading"
      :pagination="false"
      row-key="id"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'topologyName'">
          <Tag color="blue">{{ record.topologyName }}</Tag>
        </template>
        <template v-else-if="column.key === 'protocol'">
          <Tag :color="record.sslEnabled ? 'green' : 'blue'">
            {{ record.sslEnabled ? 'HTTPS' : 'HTTP' }}
          </Tag>
        </template>
        <template v-else-if="column.key === 'url'">
          <Tooltip v-if="!record.enabled" title="实例未启用，当前不可访问">
            <Typography.Text copyable code type="secondary">{{ record.url }}</Typography.Text>
          </Tooltip>
          <Typography.Text v-else copyable code>{{ record.url }}</Typography.Text>
        </template>
        <template v-else-if="column.key === 'enabled'">
          <Switch
            :checked="record.enabled"
            checked-children="启用"
            un-checked-children="禁用"
            @change="(v: boolean) => handleToggleEnabled(record, v)"
          />
        </template>
        <template v-else-if="column.key === 'apiCount'">
          <Tag :color="record.apiCount > 0 ? 'green' : 'default'">{{ record.apiCount }}</Tag>
        </template>
        <template v-else-if="column.key === 'createdAt'">
          {{ formatDate(record.createdAt) }}
        </template>
        <template v-else-if="column.key === 'action'">
          <Space>
            <a @click="openEdit(record)"><EditOutlined /></a>
            <a @click="openLogs(record)" title="请求日志"><FileTextOutlined /></a>
            <Popconfirm
              title="确定删除该实例？"
              ok-text="确定"
              cancel-text="取消"
              @confirm="handleDelete(record)"
            >
              <a style="color: #ff4d4f"><DeleteOutlined /></a>
            </Popconfirm>
          </Space>
        </template>
      </template>
    </Table>
  </Card>

  <MockInstanceModal
    v-model:open="modalOpen"
    :editing="editingInstance"
    @create="handleCreate"
    @update="handleUpdate"
  />

  <InstanceLogsDrawer
    v-if="logsInstance"
    v-model:open="logsDrawerOpen"
    :instance-id="logsInstance.id"
    :instance-name="logsInstance.name"
    :instance-port="logsInstance.port"
  />
</template>
