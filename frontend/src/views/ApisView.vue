<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { message } from 'ant-design-vue'

import ApiConfigTable from '@/components/apis/ApiConfigTable.vue'
import ApiConfigModal from '@/components/apis/ApiConfigModal.vue'
import { useApiConfigs } from '@/composables/useApiConfigs'
import { domainApi, type DomainItem } from '@/api/domain'
import type { ApiConfigCreate, ApiConfigUpdate } from '@/api/api_config'

const {
  items,
  total,
  loading,
  page,
  pageSize,
  fetchApis,
  createApi,
  updateApi,
  toggleEnabled,
  deleteApi,
  onPageChange,
  onFilterChange,
} = useApiConfigs()

const modalOpen = ref(false)
const editingApiId = ref<string | null>(null)
const presetDomainId = ref<string | null>(null)
const domains = ref<DomainItem[]>([])

async function fetchDomains() {
  try {
    const res = await domainApi.list()
    domains.value = res.items
  } catch {}
}

onMounted(() => {
  fetchApis()
  fetchDomains()
})

function handleCreate(domainId?: string | null) {
  editingApiId.value = null
  presetDomainId.value = domainId ?? null
  modalOpen.value = true
}

function handleEdit(id: string) {
  editingApiId.value = id
  presetDomainId.value = null
  modalOpen.value = true
}

async function handleCreateSubmit(data: ApiConfigCreate) {
  try {
    await createApi(data)
    message.success('创建成功')
  } catch (e) {
    throw e
  }
}

async function handleUpdateSubmit(id: string, data: ApiConfigUpdate) {
  try {
    await updateApi(id, data)
    message.success('更新成功')
  } catch (e) {
    throw e
  }
}

async function handleToggleEnabled(id: string, value: boolean) {
  try {
    await toggleEnabled(id, value)
    message.success(value ? '已启用' : '已禁用')
  } catch {
    // http interceptor handles error toast
  }
}

async function handleDelete(id: string) {
  try {
    await deleteApi(id)
    message.success('删除成功')
  } catch {
    // http interceptor handles error toast
  }
}
</script>

<template>
  <a-card title="接口配置">
    <ApiConfigTable
      :items="items"
      :domains="domains"
      :total="total"
      :page="page"
      :page-size="pageSize"
      :loading="loading"
      @page-change="onPageChange"
      @filter-change="onFilterChange"
      @toggle-enabled="handleToggleEnabled"
      @delete="handleDelete"
      @refresh="fetchApis"
      @create="handleCreate"
      @edit="handleEdit"
    />

    <ApiConfigModal
      v-model:open="modalOpen"
      :api-id="editingApiId"
      :preset-domain-id="presetDomainId"
      @create-submit="handleCreateSubmit"
      @update-submit="handleUpdateSubmit"
    />
  </a-card>
</template>
