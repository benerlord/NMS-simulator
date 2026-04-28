<script setup lang="ts">
import { computed } from 'vue'
import { Table, Tag, Button, Popconfirm, Tooltip } from 'ant-design-vue'
import type { TokenItem } from '@/api/token'

interface Props {
  items: TokenItem[]
  total: number
  page: number
  pageSize: number
  loading?: boolean
}

const props = defineProps<Props>()
const emit = defineEmits<{
  (e: 'pageChange', page: number, pageSize: number): void
  (e: 'revoke', token: string): Promise<void>
}>()

const columns = [
  { title: 'Token', dataIndex: 'token', key: 'token', width: 280, ellipsis: true },
  { title: '状态', key: 'status', width: 110 },
  { title: '颁发时间', dataIndex: 'issuedAt', key: 'issuedAt', width: 180 },
  { title: '过期时间', dataIndex: 'expiresAt', key: 'expiresAt', width: 180 },
  { title: '颁发接口', dataIndex: 'issuedByApi', key: 'issuedByApi', width: 160, ellipsis: true },
  { title: 'meta', key: 'meta', ellipsis: true },
  { title: '操作', key: 'actions', width: 100, fixed: 'right' as const },
]

function fmtTime(iso: string): string {
  if (!iso) return '-'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const pad = (n: number) => n.toString().padStart(2, '0')
  return (
    `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ` +
    `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
  )
}

function tokenStatus(record: TokenItem): {
  label: string
  color: string
} {
  if (record.revoked) return { label: '已撤销', color: 'default' }
  const expires = new Date(record.expiresAt).getTime()
  if (Number.isFinite(expires) && expires <= Date.now()) {
    return { label: '已过期', color: 'warning' }
  }
  return { label: '有效', color: 'success' }
}

function summarizeMeta(meta: Record<string, unknown>): string {
  const keys = Object.keys(meta || {})
  if (keys.length === 0) return '-'
  return keys.map((k) => (k === 'password' ? `${k}:••••` : `${k}:${String(meta[k])}`)).join(', ')
}

const pagination = computed(() => ({
  current: props.page,
  pageSize: props.pageSize,
  total: props.total,
  showSizeChanger: true,
  showTotal: (t: number) => `共 ${t} 条`,
}))

function handleTableChange(pag: { current?: number; pageSize?: number }) {
  emit('pageChange', pag.current ?? 1, pag.pageSize ?? props.pageSize)
}

async function handleRevoke(token: string) {
  await emit('revoke', token)
}
</script>

<template>
  <Table
    :columns="columns"
    :data-source="items"
    :loading="loading"
    :pagination="pagination"
    :scroll="{ x: 1100 }"
    row-key="token"
    size="middle"
    @change="handleTableChange"
  >
    <template #bodyCell="{ column, record }">
      <template v-if="column.key === 'token'">
        <Tooltip :title="record.token">
          <span class="token-cell">{{ record.token }}</span>
        </Tooltip>
      </template>

      <template v-else-if="column.key === 'status'">
        <Tag :color="tokenStatus(record as TokenItem).color">{{ tokenStatus(record as TokenItem).label }}</Tag>
      </template>

      <template v-else-if="column.key === 'issuedAt'">
        {{ fmtTime(record.issuedAt) }}
      </template>

      <template v-else-if="column.key === 'expiresAt'">
        {{ fmtTime(record.expiresAt) }}
      </template>

      <template v-else-if="column.key === 'issuedByApi'">
        {{ record.issuedByApi || '-' }}
      </template>

      <template v-else-if="column.key === 'meta'">
        <Tooltip :title="JSON.stringify(record.meta || {}, null, 2)">
          <span class="meta-cell">{{ summarizeMeta(record.meta || {}) }}</span>
        </Tooltip>
      </template>

      <template v-else-if="column.key === 'actions'">
        <Popconfirm
          v-if="!record.revoked"
          title="确认撤销该 Token？"
          ok-text="撤销"
          cancel-text="取消"
          @confirm="handleRevoke(record.token)"
        >
          <Button type="link" size="small" danger>撤销</Button>
        </Popconfirm>
        <span v-else class="muted">已撤销</span>
      </template>
    </template>
  </Table>
</template>

<style scoped>
.token-cell {
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 12px;
}

.meta-cell {
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 12px;
  color: #595959;
}

.muted {
  color: #8c8c8c;
  font-size: 12px;
}
</style>
