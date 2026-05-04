<script setup lang="ts">
import { ref, computed } from 'vue'
import { PlusOutlined, EditOutlined, DeleteOutlined, SearchOutlined, ExportOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import NodeTypeModal from './NodeTypeModal.vue'
import NodeTypeFieldEditor from './NodeTypeFieldEditor.vue'
import { useNodeTypes } from '@/composables/useTypes'
import { nodeTypeApi } from '@/api/types'
import { downloadJson, timestampFilename } from '@/utils/download'
import type { NodeTypeDetail, NodeTypeCreate, NodeTypeUpdate, NodeTypeFieldCreate, NodeTypeFieldUpdate } from '@/api/types'

const {
  nodeTypes,
  nodeTypesLoading,
  fetchNodeTypes,
  createNodeType,
  updateNodeType,
  deleteNodeType,
  deleteNodeTypes,
  createNodeTypeField,
  updateNodeTypeField,
  deleteNodeTypeField,
} = useNodeTypes()

defineExpose({ refresh: fetchNodeTypes })

const modalOpen = ref(false)
const modalEditing = ref<NodeTypeDetail | null>(null)
const modalLoading = ref(false)

function openCreate() {
  modalEditing.value = null
  modalOpen.value = true
}

function openEdit(item: NodeTypeDetail) {
  modalEditing.value = item
  modalOpen.value = true
}

async function handleCreate(data: NodeTypeCreate) {
  modalLoading.value = true
  try {
    await createNodeType(data)
    message.success('创建成功')
    modalOpen.value = false
  } finally {
    modalLoading.value = false
  }
}

async function handleUpdate(id: string, data: NodeTypeUpdate) {
  modalLoading.value = true
  try {
    await updateNodeType(id, data)
    message.success('更新成功')
    modalOpen.value = false
  } finally {
    modalLoading.value = false
  }
}

async function handleDelete(item: NodeTypeDetail) {
  try {
    await deleteNodeType(item.id)
    message.success('删除成功')
  } catch {}
}

async function handleCreateField(typeId: string, data: NodeTypeFieldCreate) {
  try {
    await createNodeTypeField(typeId, data)
    message.success('字段添加成功')
  } catch {}
}

async function handleUpdateField(typeId: string, fieldId: number, data: NodeTypeFieldUpdate) {
  try {
    await updateNodeTypeField(typeId, fieldId, data)
    message.success('字段更新成功')
  } catch {}
}

async function handleDeleteField(typeId: string, fieldId: number) {
  try {
    await deleteNodeTypeField(typeId, fieldId)
    message.success('字段删除成功')
  } catch {}
}

// Expanded rows for showing fields
const expandedRowKeys = ref<string[]>([])
const selectedRowKeys = ref<string[]>([])
const searchText = ref('')
const categoryFilter = ref<string[]>([])

const categoryOptions = computed(() => {
  const cats = [...new Set(nodeTypes.value.map(nt => nt.category))]
  return cats.map(c => ({ label: c, value: c }))
})

const filteredNodeTypes = computed(() => {
  let list = nodeTypes.value
  const kw = searchText.value.trim().toLowerCase()
  if (kw) {
    list = list.filter(nt =>
      nt.code.toLowerCase().includes(kw) ||
      nt.name.toLowerCase().includes(kw) ||
      (nt.description ?? '').toLowerCase().includes(kw) ||
      nt.category.toLowerCase().includes(kw)
    )
  }
  if (categoryFilter.value.length > 0) {
    list = list.filter(nt => categoryFilter.value.includes(nt.category))
  }
  return list
})

async function handleExport() {
  try {
    const ids = selectedRowKeys.value.length > 0 ? selectedRowKeys.value : undefined
    const result = await nodeTypeApi.export(ids)
    downloadJson(result.items, timestampFilename('node-types-export'))
    message.success(`已导出 ${result.items.length} 个节点类型`)
  } catch {}
}

async function handleBatchDelete() {
  if (selectedRowKeys.value.length === 0) return
  try {
    const result = await deleteNodeTypes(selectedRowKeys.value)
    if (result.skipped.length > 0) {
      const skippedInfo = result.skipped.map(s => `${s.id}: ${s.reason}`).join('; ')
      message.warning(`部分类型未能删除: ${skippedInfo}`)
    } else {
      message.success(`成功删除 ${result.deletedCount} 个节点类型`)
    }
    selectedRowKeys.value = []
  } catch {}
}

fetchNodeTypes()
</script>

<template>
  <div class="node-type-table">
    <div class="table-toolbar">
      <span class="toolbar-title">节点类型</span>
      <a-space>
        <a-input-search
          v-model:value="searchText"
          placeholder="搜索代码/名称/描述"
          allow-clear
          style="width: 220px"
        />
        <a-select
          v-model:value="categoryFilter"
          mode="multiple"
          placeholder="分类筛选"
          :options="categoryOptions"
          :max-tag-count="1"
          allow-clear
          style="width: 160px"
        />
        <a-popconfirm
          :title="`确定删除选中的 ${selectedRowKeys.length} 个节点类型？`"
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
          新建节点类型
        </a-button>
      </a-space>
    </div>

    <a-table
      :dataSource="filteredNodeTypes"
      :loading="nodeTypesLoading"
      :pagination="{ pageSize: 10 }"
      rowKey="id"
      :rowSelection="{ selectedRowKeys, onChange: (keys: string[]) => { selectedRowKeys = keys } }"
      :expandedRowKeys="expandedRowKeys"
      @expand="(expanded: boolean, record: NodeTypeDetail) => { if (expanded) expandedRowKeys = [record.id]; else expandedRowKeys = [] }"
    >
      <a-table-column title="代码" dataIndex="code" width="120" />
      <a-table-column title="名称" dataIndex="name" width="140" />
      <a-table-column title="分类" dataIndex="category" width="100">
        <template #default="{ text }">
          <a-tag>{{ text }}</a-tag>
        </template>
      </a-table-column>
      <a-table-column title="图标" dataIndex="icon" width="80">
        <template #default="{ text }">
          <span v-if="text">{{ text }}</span>
          <span v-else class="placeholder">-</span>
        </template>
      </a-table-column>
      <a-table-column title="颜色" dataIndex="color" width="80">
        <template #default="{ text }">
          <span v-if="text" class="color-swatch" :style="{ backgroundColor: text }"></span>
          <span v-else class="placeholder">-</span>
        </template>
      </a-table-column>
      <a-table-column title="渲染模式" dataIndex="renderMode" width="100" />
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
              title="确定删除该节点类型？"
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

      <template #expandedRowRender="{ record }">
        <NodeTypeFieldEditor
          :fields="record.fields"
          :loading="nodeTypesLoading"
          @create="(data) => handleCreateField(record.id, data)"
          @update="(fieldId, data) => handleUpdateField(record.id, fieldId, data)"
          @delete="(fieldId) => handleDeleteField(record.id, fieldId)"
        />
      </template>
    </a-table>

    <NodeTypeModal
      v-model:open="modalOpen"
      :editing="modalEditing"
      :loading="modalLoading"
      @create="handleCreate"
      @update="handleUpdate"
    />
  </div>
</template>

<style scoped>
.node-type-table {
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
