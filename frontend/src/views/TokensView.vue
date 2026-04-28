<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { Card, Button, Space, Switch, message, Modal as AntModal } from 'ant-design-vue'
import { useTokens } from '@/composables/useTokens'
import TokenTable from '@/components/tokens/TokenTable.vue'
import TokenCreateModal from '@/components/tokens/TokenCreateModal.vue'
import type { TokenCreate } from '@/api/token'

const {
  items,
  total,
  loading,
  page,
  pageSize,
  notExpired,
  fetchTokens,
  createToken,
  revokeToken,
  deleteExpired,
  onPageChange,
  onFilterChange,
} = useTokens()

const modalOpen = ref(false)

onMounted(() => {
  fetchTokens()
})

function handleNew() {
  modalOpen.value = true
}

async function handleCreate(data: TokenCreate) {
  await createToken(data)
  message.success(`Token ${data.token} 已颁发`)
}

async function handleRevoke(token: string) {
  await revokeToken(token)
  message.success(`Token ${token} 已撤销`)
}

function handleNotExpiredToggle(checked: boolean | string | number) {
  onFilterChange({ notExpired: !!checked })
}

function handleDeleteExpired() {
  AntModal.confirm({
    title: '清理过期 Token',
    content: '将永久删除所有 expires_at 早于当前时间的 Token，确认操作？',
    okText: '清理',
    cancelText: '取消',
    okButtonProps: { danger: true },
    onOk: async () => {
      const count = await deleteExpired()
      message.success(`已清理 ${count} 条过期 Token`)
    },
  })
}
</script>

<template>
  <Card title="Token 管理" :bordered="false" class="tokens-card">
    <template #extra>
      <Space>
        <span class="filter-label">仅显示有效</span>
        <Switch
          :checked="notExpired"
          checked-children="开"
          un-checked-children="关"
          @change="handleNotExpiredToggle"
        />
        <Button @click="fetchTokens">刷新</Button>
        <Button danger @click="handleDeleteExpired">清理过期</Button>
        <Button type="primary" @click="handleNew">颁发 Token</Button>
      </Space>
    </template>

    <TokenTable
      :items="items"
      :total="total"
      :page="page"
      :page-size="pageSize"
      :loading="loading"
      @page-change="onPageChange"
      @revoke="handleRevoke"
    />

    <TokenCreateModal v-model:open="modalOpen" @submit="handleCreate" />
  </Card>
</template>

<style scoped>
.tokens-card {
  margin: 16px;
}

.filter-label {
  font-size: 13px;
  color: #595959;
}
</style>
