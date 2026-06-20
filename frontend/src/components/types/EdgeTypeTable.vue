<script setup lang="ts">
import { ref, computed } from 'vue'
import { PlusOutlined, EditOutlined, DeleteOutlined, SearchOutlined, ExportOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import EdgeTypeModal from './EdgeTypeModal.vue'
import { useEdgeTypes, useNodeTypes } from '@/composables/useTypes'
import { edgeTypeApi } from '@/api/types'
import { downloadJson, timestampFilename } from '@/utils/download'
import type { EdgeTypeDetail, EdgeTypeCreate, EdgeTypeUpdate } from '@/api/types'

const {
  edgeTypes,
  edgeTypesLoading,
  fetchEdgeTypes,
  createEdgeType,
  updateEdgeType,
  deleteEdgeType,
  deleteEdgeTypes,
} = useEdgeTypes()

const { nodeTypes, fetchNodeTypes } = useNodeTypes()

defineExpose({ refresh: fetchEdgeTypes })

const modalOpen = ref(false)
const modalEditing = ref<EdgeTypeDetail | null>(null)
const modalLoading = ref(false)

function openCreate() {
  modalEditing.value = null
  modalOpen.value = true
}

function openEdit(item: EdgeTypeDetail) {
  modalEditing.value = item
  modalOpen.value = true
}

async function handleCreate(data: EdgeTypeCreate) {
  modalLoading.value = true
  try {
    await createEdgeType(data)
    message.success('创建成功')
    modalOpen.value = false
  } finally {
    modalLoading.value = false
  }
}

async function handleUpdate(id: string, data: EdgeTypeUpdate) {
  modalLoading.value = true
  try {
    await updateEdgeType(id, data)
    message.success('更新成功')
    modalOpen.value = false
  } finally {
    modalLoading.value = false
  }
}

async function handleDelete(item: EdgeTypeDetail) {
  try {
    await deleteEdgeType(item.id)
    message.success('删除成功')
  } catch {}
}

const selectedRowKeys = ref<string[]>([])
const searchText = ref('')

const filteredEdgeTypes = computed(() => {
  const kw = searchText.value.trim().toLowerCase()
  if (!kw) return edgeTypes.value
  return edgeTypes.value.filter(et =>
    et.code.toLowerCase().includes(kw) ||
    et.name.toLowerCase().includes(kw) ||
    (et.description ?? '').toLowerCase().includes(kw)
  )
})

async function handleExport() {
  try {
    const ids = selectedRowKeys.value.length > 0 ? selectedRowKeys.value : undefined
    const result = await edgeTypeApi.export(ids)
    downloadJson(result.items, timestampFilename('edge-types-export'))
    message.success(`已导出 ${result.items.length} 个边类型`)
  } catch {}
}

async function handleBatchDelete() {
  if (selectedRowKeys.value.length === 0) return
  try {
    const result = await deleteEdgeTypes(selectedRowKeys.value)
    if (result.skipped.length > 0) {
      const skippedInfo = result.skipped.map(s => `${s.id}: ${s.reason}`).join('; ')
      message.warning(`部分类型未能删除: ${skippedInfo}`)
    } else {
      message.success(`成功删除 ${result.deletedCount} 个边类型`)
    }
    selectedRowKeys.value = []
  } catch {}
}

fetchEdgeTypes()
fetchNodeTypes()
</script>

<template>
  <div class="edge-type-table">
    <div class="table-toolbar">
      <span class="toolbar-title">边类型</span>
      <a-space>
        <a-input-search
          v-model:value="searchText"
          placeholder="搜索代码/名称/描述"
          allow-clear
          style="width: 220px"
        />
        <a-popconfirm
          :title="`确定删除选中的 ${selectedRowKeys.length} 个边类型？`"
          :disabled="selectedRowKeys.length === 0"
          ok-text="确定"
          cancel-text="取消"
          @confirm="handleBatchDelete"
        >
          <a-button :disabled="selectedRowKeys.length === 0" danger>
            <template #icon><DeleteOutlined /></template>
            批量删除
          </a-button>
        </a-popconfirm>
        <a-button @click="handleExport">
          <template #icon><ExportOutlined /></template>
          批量导出
        </a-button>
        <a-button type="primary" @click="openCreate">
          <template #icon><PlusOutlined /></template>
          新建边类型
        </a-button>
      </a-space>
    </div>

    <a-table
      :dataSource="filteredEdgeTypes"
      :loading="edgeTypesLoading"
      :pagination="{
        defaultPageSize: 10,
        pageSizeOptions: ['10', '20', '50'],
        showSizeChanger: true,
        showTotal: (total: number) => `共 ${total} 条`,
      }"
      rowKey="id"
      :rowSelection="{ selectedRowKeys, onChange: (keys: string[]) => { selectedRowKeys = keys } }"
    >
      <a-table-column title="代码" dataIndex="code" width="140" />
      <a-table-column title="名称" dataIndex="name" width="120" />
      <a-table-column title="语义" dataIndex="semantic" width="100">
        <template #default="{ text }">
          <a-tag>{{ text }}</a-tag>
        </template>
      </a-table-column>
      <a-table-column title="颜色" dataIndex="color" width="80">
        <template #default="{ text }">
          <span v-if="text" class="color-swatch" :style="{ backgroundColor: text }"></span>
          <span v-else class="placeholder">-</span>
        </template>
      </a-table-column>
      <a-table-column title="线条样式" dataIndex="lineStyle" width="90">
        <template #default="{ text }">
          {{ text ?? '-' }}
        </template>
      </a-table-column>
      <a-table-column title="有向" dataIndex="directed" width="60">
        <template #default="{ text }">
          <a-tag :color="text ? 'blue' : 'default'">{{ text ? '是' : '否' }}</a-tag>
        </template>
      </a-table-column>
      <a-table-column title="唯一目标" dataIndex="exclusiveTarget" width="90">
        <template #default="{ text }">
          <a-tag :color="text ? 'orange' : 'default'">{{ text ? '是' : '否' }}</a-tag>
        </template>
      </a-table-column>
      <a-table-column title="字段数" dataIndex="fields" width="80">
        <template #default="{ text }">
          {{ text?.length ?? 0 }}
        </template>
      </a-table-column>
      <a-table-column title="操作" width="160" fixed="right">
        <template #default="{ record }">
          <a-space>
            <a-button type="link" size="small" @click="openEdit(record)">
              <template #icon><EditOutlined /></template>
            </a-button>
            <a-popconfirm
              title="确定删除该边类型？"
              ok-text="确定"
              cancel-text="取消"
              @confirm="handleDelete(record)"
            >
              <a-button type="link" size="small" danger>
                <template #icon><DeleteOutlined /></template>
              </a-button>
            </a-popconfirm>
          </a-space>
        </template>
      </a-table-column>

    </a-table>

    <EdgeTypeModal
      v-model:open="modalOpen"
      :editing="modalEditing"
      :loading="modalLoading"
      :node-types="nodeTypes"
      @create="handleCreate"
      @update="handleUpdate"
    />
  </div>
</template>

<style scoped>
.edge-type-table {
  margin-bottom: 32px;
}

.table-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.toolbar-title {
  font-size: 16px;
  font-weight: 500;
  color: rgba(0, 0, 0, 0.85);
}

.color-swatch {
  display: inline-block;
  width: 20px;
  height: 20px;
  border-radius: 4px;
  border: 1px solid rgba(0, 0, 0, 0.1);
}

.placeholder {
  color: rgba(0, 0, 0, 0.25);
}
</style>
