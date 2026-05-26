<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Card, Button, Space, Table, Tag, Popconfirm, message } from 'ant-design-vue'
import { PlusOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons-vue'
import { domainApi, type DomainItem } from '@/api/domain'
import DomainModal from '@/components/domain/DomainModal.vue'

const domains = ref<DomainItem[]>([])
const loading = ref(false)
const modalOpen = ref(false)
const editingDomain = ref<DomainItem | null>(null)

async function fetchDomains() {
  loading.value = true
  try {
    const res = await domainApi.list()
    domains.value = res.items
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editingDomain.value = null
  modalOpen.value = true
}

function openEdit(item: DomainItem) {
  editingDomain.value = item
  modalOpen.value = true
}

async function handleCreate(data: { name: string; description?: string | null }) {
  await domainApi.create(data)
  message.success('创建成功')
  modalOpen.value = false
  fetchDomains()
}

async function handleUpdate(data: { name?: string | null; description?: string | null }) {
  if (!editingDomain.value) return
  await domainApi.update(editingDomain.value.id, data)
  message.success('更新成功')
  modalOpen.value = false
  fetchDomains()
}

async function handleDelete(item: DomainItem) {
  await domainApi.delete(item.id)
  message.success('已删除')
  fetchDomains()
}

const columns = [
  { title: '名称', dataIndex: 'name', key: 'name', width: 200 },
  { title: '描述', dataIndex: 'description', key: 'description', ellipsis: true },
  {
    title: '拓扑数', key: 'topologyCount', width: 80, align: 'center' as const,
  },
  { title: '创建时间', dataIndex: 'createdAt', key: 'createdAt', width: 180 },
  { title: '操作', key: 'action', width: 120, fixed: 'right' as const },
]

function formatDate(iso: string): string {
  if (!iso) return '-'
  const d = new Date(iso)
  return d.toLocaleString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

onMounted(fetchDomains)
</script>

<template>
  <Card title="网管/设备管理" :bordered="false">
    <template #extra>
      <Button type="primary" @click="openCreate">
        <template #icon><PlusOutlined /></template>
        新建网管/设备
      </Button>
    </template>

    <Table
      :data-source="domains"
      :columns="columns"
      :loading="loading"
      :pagination="false"
      row-key="id"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'description'">
          {{ record.description || '-' }}
        </template>
        <template v-else-if="column.key === 'topologyCount'">
          <Tag :color="record.topologyCount > 0 ? 'blue' : 'default'">
            {{ record.topologyCount }}
          </Tag>
        </template>
        <template v-else-if="column.key === 'createdAt'">
          {{ formatDate(record.createdAt) }}
        </template>
        <template v-else-if="column.key === 'action'">
          <Space>
            <a @click="openEdit(record)"><EditOutlined /></a>
            <Popconfirm
              :title="record.topologyCount > 0 ? `该网管/设备下有 ${record.topologyCount} 个拓扑，删除后拓扑将变为无限制，确认删除？` : '确定删除该网管/设备？'"
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

  <DomainModal
    v-model:open="modalOpen"
    :editing="editingDomain"
    @create="handleCreate"
    @update="handleUpdate"
  />
</template>
