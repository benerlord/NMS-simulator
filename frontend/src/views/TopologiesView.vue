<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'

import TopologyTable from '@/components/topology/TopologyTable.vue'
import TopologyModal from '@/components/topology/TopologyModal.vue'
import { useTopologies } from '@/composables/useTopologies'
import type { TopologyCreate, TopologyUpdate } from '@/api/topology'

const {
  items,
  total,
  loading,
  page,
  pageSize,
  fetchTopologies,
  createTopology,
  updateTopology,
  deleteTopology,
  onPageChange,
  onSearch,
  onSort,
} = useTopologies()

const modalOpen = ref(false)
const editingTopology = ref<{ id: string; name: string; description: string | null } | null>(null)
const router = useRouter()

onMounted(() => {
  fetchTopologies()
})

function handleCreate() {
  editingTopology.value = null
  modalOpen.value = true
}

function handleEdit(item: { id: string; name: string; description: string | null }) {
  editingTopology.value = { ...item }
  modalOpen.value = true
}

async function handleModalSubmit(data: TopologyCreate | TopologyUpdate) {
  try {
    if (editingTopology.value) {
      await updateTopology(editingTopology.value.id, data as TopologyUpdate)
      message.success('更新成功')
    } else {
      await createTopology(data as TopologyCreate)
      message.success('创建成功')
    }
  } catch (e) {
    // error is handled by http interceptor
    throw e
  }
}

async function handleDelete(id: string) {
  try {
    await deleteTopology(id)
    message.success('删除成功')
  } catch {
    // error is handled by http interceptor
  }
}

function handleEnterCanvas(id: string) {
  router.push(`/topologies/${id}/canvas`)
}
</script>

<template>
  <a-card title="拓扑管理">
    <TopologyTable
      :items="items"
      :total="total"
      :page="page"
      :page-size="pageSize"
      :loading="loading"
      @page-change="onPageChange"
      @search="onSearch"
      @sort="onSort"
      @create="handleCreate"
      @edit="handleEdit"
      @delete="handleDelete"
      @enter-canvas="handleEnterCanvas"
    />

    <TopologyModal
      v-model:open="modalOpen"
      :topology="editingTopology"
      @submit="handleModalSubmit"
    />
  </a-card>
</template>
