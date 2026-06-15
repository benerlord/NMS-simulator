<script setup lang="ts">
import { ref, computed, h } from 'vue'
import { PlusOutlined, EditOutlined, DeleteOutlined, SearchOutlined, ExportOutlined, ImportOutlined, DownOutlined } from '@ant-design/icons-vue'
import { message, Modal, Dropdown, Menu, MenuItem, Tag, Select } from 'ant-design-vue'
import NodeTypeModal from './NodeTypeModal.vue'
import { useNodeTypes } from '@/composables/useTypes'
import { nodeTypeApi } from '@/api/types'
import { domainApi, type DomainItem } from '@/api/domain'
import { downloadBlob, timestampExcelFilename } from '@/utils/download'
import type { NodeTypeDetail, NodeTypeCreate, NodeTypeUpdate, TypeImportPreview, TypeImportResult } from '@/api/types'

const {
  nodeTypes,
  nodeTypesLoading,
  fetchNodeTypes,
  createNodeType,
  updateNodeType,
  deleteNodeType,
  deleteNodeTypes,
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

const selectedRowKeys = ref<string[]>([])
const fileInputRef = ref<HTMLInputElement>()
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
    const blob = await nodeTypeApi.export(ids)
    downloadBlob(blob, timestampExcelFilename('node-types-export'))
    message.success('导出成功')
  } catch {}
}

const pendingImportFile = ref<File | null>(null)

function handleImportClick() {
  fileInputRef.value?.click()
}

async function handleFileChosen(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return

  // 1. 预览导入结果
  let preview: TypeImportPreview
  try {
    preview = await nodeTypeApi.importPreview(file)
  } catch {
    return
  }

  // 2. 构建预览 VNode 列表
  const children: ReturnType<typeof h>[] = []

  if (preview.toCreate.length) {
    children.push(
      h('div', { style: { fontWeight: 'bold', marginBottom: '4px' } },
        `将新建（${preview.toCreate.length} 个）：`),
      ...preview.toCreate.map(item =>
        h('div', { style: { paddingLeft: '8px' } },
          `• ${item.code}（${item.name || item.code}）`),
      ),
    )
  }

  if (preview.toUpdate.length) {
    if (children.length) children.push(h('br'))
    children.push(
      h('div', { style: { fontWeight: 'bold', marginBottom: '4px' } },
        `将覆盖（字段将被替换）（${preview.toUpdate.length} 个）：`),
      ...preview.toUpdate.map(item => {
        const nameChanged = item.oldName && item.oldName !== item.name
        const text = nameChanged
          ? `• ${item.code}（${item.oldName} → ${item.name}）`
          : `• ${item.code}（${item.name || item.code}）`
        return h('div', { style: { paddingLeft: '8px' } }, text)
      }),
    )
  }

  if (preview.errors.length) {
    if (children.length) children.push(h('br'))
    children.push(
      h('div', { style: { color: '#faad14' } },
        `⚠ 有 ${preview.errors.length} 行因缺少必填字段将被跳过。`),
    )
  }

  // 3. 弹窗确认（如有覆盖）或直接导入
  if (preview.toUpdate.length > 0) {
    pendingImportFile.value = file
    Modal.confirm({
      title: '确认导入',
      content: h('div', { style: { lineHeight: '1.8' } }, children),
      okText: '确认导入',
      cancelText: '取消',
      width: 480,
      onOk: () => doImport(file),
    })
  } else {
    // 全部新建，直接导入
    await doImport(file)
  }
}

async function doImport(file: File) {
  pendingImportFile.value = null
  try {
    const result = await nodeTypeApi.import(file)
    const parts: string[] = []
    if (result.created) parts.push(`新建 ${result.created} 个`)
    if (result.updated) parts.push(`更新 ${result.updated} 个`)
    parts.push(`导入 ${result.totalFields} 个字段`)
    message.success(parts.join('，'))
    if (result.errors.length) {
      message.warning(result.errors.join('；'))
    }
    fetchNodeTypes()
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

const domains = ref<DomainItem[]>([])
const domainModalVisible = ref(false)
const domainIdsForBatch = ref<string[]>([])

const hasAssociatedTypes = computed(() =>
  filteredNodeTypes.value
    .filter(nt => selectedRowKeys.value.includes(nt.id))
    .some(nt => nt.domainIds.length > 0)
)

async function loadDomains() {
  try {
    const res = await domainApi.list()
    domains.value = res.items
  } catch {}
}

function handleBatchMenuClick({ key }: { key: string }) {
  switch (key) {
    case 'associate-domain':
      domainIdsForBatch.value = []
      domainModalVisible.value = true
      break
    case 'unbind-domain':
      Modal.confirm({
        title: `确认解除 ${selectedRowKeys.value.length} 个节点类型的网管/设备关联？`,
        content: '解除后这些类型将变为全局可用',
        okText: '确定',
        cancelText: '取消',
        onOk: async () => {
          await nodeTypeApi.batchUpdateDomains(selectedRowKeys.value, [])
          message.success('已解除关联')
          selectedRowKeys.value = []
          fetchNodeTypes()
        },
      })
      break
    case 'batch-delete':
      handleBatchDelete()
      break
  }
}

async function handleBatchAssociateDomains() {
  await nodeTypeApi.batchUpdateDomains(selectedRowKeys.value, domainIdsForBatch.value)
  message.success(`已关联 ${selectedRowKeys.value.length} 个类型`)
  domainModalVisible.value = false
  selectedRowKeys.value = []
  fetchNodeTypes()
}

async function removeDomain(typeId: string, domainId: string) {
  const nt = nodeTypes.value.find(t => t.id === typeId)
  if (!nt) return
  const newDomains = nt.domainIds.filter(id => id !== domainId)
  await nodeTypeApi.updateDomains(typeId, newDomains)
  fetchNodeTypes()
}

fetchNodeTypes()
loadDomains()
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
        <a-dropdown v-if="selectedRowKeys.length > 0">
          <a-button>
            批量操作（{{ selectedRowKeys.length }}）
            <DownOutlined />
          </a-button>
          <template #overlay>
            <Menu @click="handleBatchMenuClick">
              <MenuItem key="associate-domain">🔗 关联网管/设备</MenuItem>
              <MenuItem key="unbind-domain" :disabled="!hasAssociatedTypes">✂ 解除关联</MenuItem>
              <Menu.Divider />
              <MenuItem key="batch-delete" danger>🗑 批量删除</MenuItem>
            </Menu>
          </template>
        </a-dropdown>
        <a-button @click="handleExport">
          <template #icon><ExportOutlined /></template>
          批量导出
        </a-button>
        <a-button @click="handleImportClick">
          <template #icon><ImportOutlined /></template>
          导入
        </a-button>
        <input
          ref="fileInputRef"
          type="file"
          accept=".xlsx"
          style="display: none"
          @change="handleFileChosen"
        />
        <a-button type="primary" @click="openCreate">
          <template #icon><PlusOutlined /></template>
          新建节点类型
        </a-button>
      </a-space>
    </div>

    <a-table
      :dataSource="filteredNodeTypes"
      :loading="nodeTypesLoading"
      :pagination="{
        defaultPageSize: 10,
        pageSizeOptions: ['10', '20', '50'],
        showSizeChanger: true,
        showTotal: (total: number) => `共 ${total} 条`,
      }"
      rowKey="id"
      :rowSelection="{ selectedRowKeys, onChange: (keys: string[]) => { selectedRowKeys = keys } }"
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
      <a-table-column title="所属网管/设备" key="domains" width="200">
        <template #default="{ record }">
          <template v-if="record.domainNames?.length">
            <Tag
              v-for="(name, idx) in record.domainNames"
              :key="name"
              color="blue"
              closable
              @close="removeDomain(record.id, record.domainIds[idx])"
            >
              {{ name }}
            </Tag>
          </template>
          <span v-else class="placeholder">-</span>
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

    </a-table>

    <NodeTypeModal
      v-model:open="modalOpen"
      :editing="modalEditing"
      :loading="modalLoading"
      @create="handleCreate"
      @update="handleUpdate"
    />

    <Modal
      v-model:open="domainModalVisible"
      title="关联网管/设备"
      ok-text="确定"
      cancel-text="取消"
      @ok="handleBatchAssociateDomains"
    >
      <Select
        v-model:value="domainIdsForBatch"
        mode="multiple"
        placeholder="选择网管/设备（可多选）"
        style="width: 100%"
      >
        <Select.Option
          v-for="d in domains"
          :key="d.id"
          :value="d.id"
        >
          {{ d.name }}
        </Select.Option>
      </Select>
    </Modal>
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
