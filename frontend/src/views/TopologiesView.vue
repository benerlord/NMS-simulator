<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'

import TopologyTable from '@/components/topology/TopologyTable.vue'
import TopologyModal from '@/components/topology/TopologyModal.vue'
import { useTopologies } from '@/composables/useTopologies'
import type { TopologyListItem } from '@/api/topology'
import { downloadBlob, timestampExcelFilename } from '@/utils/download'

const {
  items,
  total,
  loading,
  page,
  pageSize,
  fetchTopologies,
  deleteTopology,
  exportTopologyExcel,
  importTopologyExcel,
  onPageChange,
  onSearch,
  onSort,
} = useTopologies()

const modalOpen = ref(false)
const editingTopology = ref<{ id: string; name: string; description: string | null; domainId?: string | null } | null>(null)
const router = useRouter()
const fileInputRef = ref<HTMLInputElement | null>(null)

onMounted(() => {
  fetchTopologies()
})

function handleCreate() {
  editingTopology.value = null
  modalOpen.value = true
}

function handleEdit(item: { id: string; name: string; description: string | null; domainId?: string | null }) {
  editingTopology.value = { ...item }
  modalOpen.value = true
}

async function handleModalSaved() {
  await fetchTopologies()
}

async function handleDelete(id: string) {
  try {
    // LEGACY-07: 后端返回 unboundApiCount，回显告知用户解绑了多少接口
    const result = await deleteTopology(id)
    const unbound = result?.unboundApiCount ?? 0
    if (unbound > 0) {
      message.success(`删除成功，已自动解绑 ${unbound} 个接口配置`)
    } else {
      message.success('删除成功')
    }
  } catch {
    // error toast handled by http interceptor
  }
}

function handleEnterCanvas(id: string) {
  router.push(`/topologies/${id}/canvas`)
}

function sanitizeFileName(name: string): string {
  // strip path-unsafe chars; keep CJK / dash / underscore / dot / space
  return name.replace(/[\\/:*?"<>|]+/g, '_').replace(/\s+/g, '_').slice(0, 80) || 'topology'
}

async function handleExport(item: TopologyListItem) {
  try {
    const blob = await exportTopologyExcel(item.id)
    downloadBlob(blob, timestampExcelFilename(`topology-${sanitizeFileName(item.name)}`))
    message.success('导出成功')
  } catch {
    // error toast handled by http interceptor
  }
}

function handleImportClick() {
  fileInputRef.value?.click()
}

async function handleFileChosen(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  if (!file.name.toLowerCase().endsWith('.xlsx')) {
    message.error('仅支持 .xlsx 文件')
    return
  }
  try {
    const result = await importTopologyExcel(file)
    const parts = [
      `已创建拓扑 "${result.topologyName}"`,
      `${result.counts.nodes} 节点`,
      `${result.counts.edges} 边`,
    ]
    if (result.counts.groups) parts.push(`${result.counts.groups} 组`)
    message.success(parts.join('，'))
    if (result.warnings.length) {
      message.warning(result.warnings.join('；'))
    }
    if (result.errors.length) {
      const preview = result.errors.slice(0, 3).join('；')
      const more = result.errors.length > 3 ? '…' : ''
      message.error(`${result.errors.length} 行被跳过：${preview}${more}`)
    }
  } catch (err) {
    message.error((err as Error).message || '导入失败')
  }
}
</script>

<template>
  <a-card title="拓扑管理">
    <input
      ref="fileInputRef"
      type="file"
      accept=".xlsx"
      style="display: none"
      @change="handleFileChosen"
    />

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
      @export="handleExport"
      @import="handleImportClick"
    />

    <TopologyModal
      v-model:open="modalOpen"
      :topology="editingTopology"
      @saved="handleModalSaved"
    />
  </a-card>
</template>
