<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'

import TopologyTable from '@/components/topology/TopologyTable.vue'
import TopologyModal from '@/components/topology/TopologyModal.vue'
import { useTopologies } from '@/composables/useTopologies'
import type {
  TopologyCreate,
  TopologyExportDoc,
  TopologyListItem,
  TopologyUpdate,
} from '@/api/topology'

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
  exportTopology,
  importTopology,
  onPageChange,
  onSearch,
  onSort,
} = useTopologies()

const modalOpen = ref(false)
const editingTopology = ref<{ id: string; name: string; description: string | null } | null>(null)
const router = useRouter()
const fileInputRef = ref<HTMLInputElement | null>(null)

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
    throw e
  }
}

async function handleDelete(id: string) {
  try {
    await deleteTopology(id)
    message.success('删除成功')
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

function downloadJson(filename: string, payload: unknown) {
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

async function handleExport(item: TopologyListItem) {
  try {
    const doc = await exportTopology(item.id)
    const date = new Date().toISOString().slice(0, 10)
    downloadJson(`topology-${sanitizeFileName(item.name)}-${date}.json`, doc)
    message.success(`已导出 ${doc.nodes.length} 节点 / ${doc.edges.length} 边`)
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
  input.value = '' // allow re-selecting the same file later
  if (!file) return
  let text: string
  try {
    text = await file.text()
  } catch (err) {
    message.error(`无法读取文件：${(err as Error).message}`)
    return
  }
  let doc: TopologyExportDoc
  try {
    doc = JSON.parse(text) as TopologyExportDoc
  } catch (err) {
    message.error(`JSON 解析失败：${(err as Error).message}`)
    return
  }
  if (!doc || typeof doc !== 'object' || !doc.schemaVersion || !doc.topology) {
    message.error('文件不是有效的拓扑导出文档（缺少 schemaVersion / topology 字段）')
    return
  }
  try {
    const result = await importTopology(doc)
    message.success(
      `已导入：${result.name}（${result.nodeCount} 节点 / ${result.edgeCount} 边 / ${result.canvasCount} 坐标）`,
    )
  } catch {
    // error toast handled by http interceptor
  }
}
</script>

<template>
  <a-card title="拓扑管理">
    <input
      ref="fileInputRef"
      type="file"
      accept="application/json,.json"
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
      @submit="handleModalSubmit"
    />
  </a-card>
</template>
