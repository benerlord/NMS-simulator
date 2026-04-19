<script setup lang="ts">
import { ref } from 'vue'
import { PlusOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import EdgeTypeModal from './EdgeTypeModal.vue'
import EdgeTypeFieldEditor from './EdgeTypeFieldEditor.vue'
import { useEdgeTypes } from '@/composables/useTypes'
import type { EdgeTypeDetail, EdgeTypeCreate, EdgeTypeUpdate, EdgeTypeFieldCreate, EdgeTypeFieldUpdate } from '@/api/types'

const {
  edgeTypes,
  edgeTypesLoading,
  fetchEdgeTypes,
  createEdgeType,
  updateEdgeType,
  deleteEdgeType,
  createEdgeTypeField,
  updateEdgeTypeField,
  deleteEdgeTypeField,
} = useEdgeTypes()

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

async function handleCreateField(typeId: string, data: EdgeTypeFieldCreate) {
  try {
    await createEdgeTypeField(typeId, data)
    message.success('字段添加成功')
  } catch {}
}

async function handleUpdateField(typeId: string, fieldId: number, data: EdgeTypeFieldUpdate) {
  try {
    await updateEdgeTypeField(typeId, fieldId, data)
    message.success('字段更新成功')
  } catch {}
}

async function handleDeleteField(typeId: string, fieldId: number) {
  try {
    await deleteEdgeTypeField(typeId, fieldId)
    message.success('字段删除成功')
  } catch {}
}

const expandedRowKeys = ref<string[]>([])

fetchEdgeTypes()
</script>

<template>
  <div class="edge-type-table">
    <div class="table-toolbar">
      <span class="toolbar-title">边类型</span>
      <a-button type="primary" @click="openCreate">
        <template #icon><PlusOutlined /></template>
        新建边类型
      </a-button>
    </div>

    <a-table
      :dataSource="edgeTypes"
      :loading="edgeTypesLoading"
      :pagination="{ pageSize: 10 }"
      rowKey="id"
      :expandedRowKeys="expandedRowKeys"
      @expand="(expanded: boolean, record: EdgeTypeDetail) => { if (expanded) expandedRowKeys = [record.id]; else expandedRowKeys = [] }"
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

      <template #expandedRowRender="{ record }">
        <EdgeTypeFieldEditor
          :fields="record.fields"
          :loading="edgeTypesLoading"
          @create="(data) => handleCreateField(record.id, data)"
          @update="(fieldId, data) => handleUpdateField(record.id, fieldId, data)"
          @delete="(fieldId) => handleDeleteField(record.id, fieldId)"
        />
      </template>
    </a-table>

    <EdgeTypeModal
      v-model:open="modalOpen"
      :editing="modalEditing"
      :loading="modalLoading"
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
