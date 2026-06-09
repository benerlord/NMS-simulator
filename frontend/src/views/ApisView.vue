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
const presetCategory = ref<string | null>(null)
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

function handleCreate(category?: string | null) {
  editingApiId.value = null
  presetCategory.value = category ?? null
  modalOpen.value = true
}

function handleEdit(id: string) {
  editingApiId.value = id
  presetCategory.value = null
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

function handleDuplicate(newId: string) {
  editingApiId.value = newId
  presetCategory.value = null
  modalOpen.value = true
}

async function handleRenameCategory(domainId: string, oldName: string, newName: string) {
  try {
    await domainApi.renameCategory(domainId, oldName, newName)
    message.success('子目录已重命名')
    fetchApis()
  } catch {}
}

async function handleDeleteCategory(domainId: string, name: string) {
  try {
    await domainApi.deleteCategory(domainId, name)
    message.success('子目录已删除')
    fetchApis()
  } catch {}
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
      @refresh="() => { fetchApis(); fetchDomains() }"
      @create="handleCreate"
      @edit="handleEdit"
      @duplicate="handleDuplicate"
      @rename-category="handleRenameCategory"
      @delete-category="handleDeleteCategory"
    />

    <ApiConfigModal
      v-model:open="modalOpen"
      :api-id="editingApiId"
      :preset-category="presetCategory"
      @create-submit="handleCreateSubmit"
      @update-submit="handleUpdateSubmit"
    />
  </a-card>
</template>
