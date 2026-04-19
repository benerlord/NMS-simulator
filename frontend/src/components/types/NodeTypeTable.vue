<script setup lang="ts">
import { ref } from 'vue'
import { PlusOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import NodeTypeModal from './NodeTypeModal.vue'
import NodeTypeFieldEditor from './NodeTypeFieldEditor.vue'
import { useNodeTypes } from '@/composables/useTypes'
import type { NodeTypeDetail, NodeTypeCreate, NodeTypeUpdate, NodeTypeFieldCreate, NodeTypeFieldUpdate } from '@/api/types'

const {
  nodeTypes,
  nodeTypesLoading,
  fetchNodeTypes,
  createNodeType,
  updateNodeType,
  deleteNodeType,
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

fetchNodeTypes()
</script>

<template>
  <div class="node-type-table">
    <div class="table-toolbar">
      <span class="toolbar-title">节点类型</span>
      <a-button type="primary" @click="openCreate">
        <template #icon><PlusOutlined /></template>
        新建节点类型
      </a-button>
    </div>

    <a-table
      :dataSource="nodeTypes"
      :loading="nodeTypesLoading"
      :pagination="{ pageSize: 10 }"
      rowKey="id"
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
