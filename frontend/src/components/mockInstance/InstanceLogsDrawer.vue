<script setup lang="ts">
import { ref, watch, onBeforeUnmount } from 'vue'
import { Drawer, Table, Tag, Switch, Button, Space, Popconfirm, Empty, message } from 'ant-design-vue'
import { ReloadOutlined, DeleteOutlined } from '@ant-design/icons-vue'
import { requestLogApi, type RequestLogItem } from '@/api/mockInstance'

const props = defineProps<{
  open: boolean
  instanceId: string
  instanceName: string
  instancePort: number
}>()

const emit = defineEmits<{ 'update:open': [value: boolean] }>()

const logs = ref<RequestLogItem[]>([])
const loading = ref(false)
const autoRefresh = ref(true)
const hasMore = ref(false)
let timer: ReturnType<typeof setInterval> | null = null

function methodColor(m: string): string {
  const map: Record<string, string> = { GET: 'blue', POST: 'green', PUT: 'orange', DELETE: 'red', PATCH: 'purple' }
  return map[m.toUpperCase()] || 'default'
}

function statusColor(s: number): string {
  if (s < 300) return 'green'
  if (s < 400) return 'blue'
  if (s < 500) return 'orange'
  return 'red'
}

function formatTime(ts: string): string {
  if (!ts) return '-'
  const d = new Date(ts.replace(' ', 'T'))
  return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

async function fetchLogs(append = false) {
  loading.value = true
  try {
    const before = append && logs.value.length > 0 ? logs.value[logs.value.length - 1].ts : undefined
    const res = await requestLogApi.fetchLogs(props.instanceId, { limit: 100, before })
    if (append) {
      logs.value.push(...res.items)
    } else {
      logs.value = res.items
    }
    hasMore.value = res.hasMore
  } finally {
    loading.value = false
  }
}

async function handleClear() {
  await requestLogApi.clearLogs(props.instanceId)
  logs.value = []
  hasMore.value = false
  message.success('日志已清空')
}

function startPolling() {
  stopPolling()
  timer = setInterval(() => fetchLogs(false), 2000)
}

function stopPolling() {
  if (timer) {
    clearInterval(timer)
    timer = null
  }
}

watch(() => props.open, (val) => {
  if (val) {
    fetchLogs(false)
    if (autoRefresh.value) startPolling()
  } else {
    stopPolling()
  }
})

watch(autoRefresh, (val) => {
  if (val && props.open) startPolling()
  else stopPolling()
})

onBeforeUnmount(stopPolling)

const columns = [
  { title: '时间', dataIndex: 'ts', key: 'ts', width: 90 },
  { title: '方法', dataIndex: 'method', key: 'method', width: 80 },
  { title: '路径', dataIndex: 'path', key: 'path', ellipsis: true },
  { title: '状态码', dataIndex: 'statusCode', key: 'statusCode', width: 80, align: 'center' as const },
  { title: '耗时', dataIndex: 'durationMs', key: 'durationMs', width: 80, align: 'right' as const },
  { title: 'IP', dataIndex: 'clientIp', key: 'clientIp', width: 130 },
]
</script>

<template>
  <Drawer
    :open="open"
    :title="`请求日志 — ${instanceName}(:${instancePort})`"
    width="700"
    @close="emit('update:open', false)"
  >
    <template #extra>
      <Space>
        <span style="font-size: 13px">自动刷新</span>
        <Switch v-model:checked="autoRefresh" size="small" />
        <Button size="small" :loading="loading" @click="fetchLogs(false)">
          <template #icon><ReloadOutlined /></template>
        </Button>
        <Popconfirm title="确定清空该实例的所有日志？" @confirm="handleClear">
          <Button size="small" danger>
            <template #icon><DeleteOutlined /></template>
            清空
          </Button>
        </Popconfirm>
      </Space>
    </template>

    <Table
      v-if="logs.length > 0"
      :data-source="logs"
      :columns="columns"
      :loading="loading"
      :pagination="false"
      size="small"
      row-key="id"
      :scroll="{ y: 'calc(100vh - 260px)' }"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'ts'">
          {{ formatTime(record.ts) }}
        </template>
        <template v-else-if="column.key === 'method'">
          <Tag :color="methodColor(record.method)">{{ record.method }}</Tag>
        </template>
        <template v-else-if="column.key === 'statusCode'">
          <Tag :color="statusColor(record.statusCode)">{{ record.statusCode }}</Tag>
        </template>
        <template v-else-if="column.key === 'durationMs'">
          {{ record.durationMs }}ms
        </template>
      </template>
    </Table>

    <div v-if="hasMore" style="text-align: center; margin-top: 12px">
      <Button size="small" :loading="loading" @click="fetchLogs(true)">加载更多</Button>
    </div>

    <Empty v-if="!loading && logs.length === 0" description="暂无请求日志" />
  </Drawer>
</template>
