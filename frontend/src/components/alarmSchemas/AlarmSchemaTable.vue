<script setup lang="ts">
import { onMounted, ref, h } from 'vue'
import { Modal, Menu, MenuItem, message } from 'ant-design-vue'
import {
  PlusOutlined, ExportOutlined, ImportOutlined, DownOutlined,
} from '@ant-design/icons-vue'
import { useAlarmSchemas } from '@/composables/useAlarmSchemas'
import AlarmSchemaModal from './AlarmSchemaModal.vue'
import {
  alarmSchemaApi,
  type AlarmSchemaImportPreview,
} from '@/api/alarmSchema'
import { downloadBlob, timestampExcelFilename } from '@/utils/download'

const { schemas, loading, fetchSchemas, deleteSchema } = useAlarmSchemas()
const modalVisible = ref(false)
const editingId = ref<string | null>(null)
const fieldsCount = ref<Record<string, number>>({})
const selectedRowKeys = ref<string[]>([])
const fileInputRef = ref<HTMLInputElement | null>(null)

async function refresh() {
  await fetchSchemas()
  for (const s of schemas.value) {
    try {
      const d = await alarmSchemaApi.get(s.id)
      fieldsCount.value[s.id] = d.fields.length
    } catch {
      fieldsCount.value[s.id] = 0
    }
  }
}

function handleCreate() {
  editingId.value = null
  modalVisible.value = true
}

function handleEdit(id: string) {
  editingId.value = id
  modalVisible.value = true
}

function handleDelete(id: string, name: string) {
  Modal.confirm({
    title: `确定删除告警模板"${name}"？`,
    content: '若被拓扑引用将无法删除。',
    okText: '删除',
    okType: 'danger',
    cancelText: '取消',
    onOk: () => deleteSchema(id).then(refresh),
  })
}

async function handleExport(ids?: string[]) {
  try {
    const blob = await alarmSchemaApi.export(ids)
    downloadBlob(blob, timestampExcelFilename('alarm-schemas-export'))
    message.success('导出成功')
  } catch {}
}

function handleExportMenuClick({ key }: { key: string }) {
  if (key === 'all') {
    handleExport()
  } else if (key === 'selected') {
    if (selectedRowKeys.value.length === 0) {
      message.warning('请先勾选要导出的模板')
      return
    }
    handleExport(selectedRowKeys.value)
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

  let preview: AlarmSchemaImportPreview
  try {
    preview = await alarmSchemaApi.importPreview(file)
  } catch {
    return
  }

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

  if (preview.toUpdate.length > 0) {
    Modal.confirm({
      title: '确认导入',
      content: h('div', { style: { lineHeight: '1.8' } }, children),
      okText: '确认导入',
      cancelText: '取消',
      width: 480,
      onOk: () => doImport(file),
    })
  } else {
    await doImport(file)
  }
}

async function doImport(file: File) {
  try {
    const result = await alarmSchemaApi.import(file)
    const parts: string[] = []
    if (result.created) parts.push(`新建 ${result.created} 个`)
    if (result.updated) parts.push(`更新 ${result.updated} 个`)
    parts.push(`导入 ${result.totalFields} 个字段`)
    message.success(parts.join('，'))
    if (result.errors.length) {
      message.warning(result.errors.slice(0, 3).join('；') + (result.errors.length > 3 ? '…' : ''))
    }
    refresh()
  } catch {}
}

const columns = [
  { title: 'Code', dataIndex: 'code', key: 'code', width: 180 },
  { title: '名称', dataIndex: 'name', key: 'name' },
  { title: '字段数', key: 'fieldsCount', width: 100 },
  { title: '描述', dataIndex: 'description', key: 'description' },
  { title: '操作', key: 'actions', width: 140 },
]

onMounted(refresh)
</script>

<template>
  <div>
    <input
      ref="fileInputRef"
      type="file"
      accept=".xlsx"
      style="display: none"
      @change="handleFileChosen"
    />

    <div style="margin-bottom: 16px; display: flex; gap: 8px;">
      <a-button type="primary" @click="handleCreate">
        <template #icon><PlusOutlined /></template>
        新建告警模板
      </a-button>

      <a-dropdown>
        <a-button>
          <template #icon><ExportOutlined /></template>
          批量导出
          <DownOutlined />
        </a-button>
        <template #overlay>
          <Menu @click="handleExportMenuClick">
            <MenuItem key="all">全部导出</MenuItem>
            <MenuItem key="selected" :disabled="selectedRowKeys.length === 0">
              导出选中（{{ selectedRowKeys.length }} 项）
            </MenuItem>
          </Menu>
        </template>
      </a-dropdown>

      <a-button @click="handleImportClick">
        <template #icon><ImportOutlined /></template>
        导入
      </a-button>
    </div>

    <a-table
      :columns="columns"
      :data-source="schemas"
      :loading="loading"
      :pagination="{
        defaultPageSize: 10,
        pageSizeOptions: ['10', '20', '50'],
        showSizeChanger: true,
        showTotal: (total: number) => `共 ${total} 条`,
      }"
      :row-selection="{
        selectedRowKeys,
        onChange: (keys: string[]) => (selectedRowKeys = keys),
      }"
      row-key="id"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'fieldsCount'">
          {{ fieldsCount[record.id] ?? '-' }}
        </template>
        <template v-if="column.key === 'description'">
          <span style="color: rgba(0,0,0,0.45)">{{ record.description || '-' }}</span>
        </template>
        <template v-if="column.key === 'actions'">
          <a-space>
            <a-button type="link" size="small" @click="handleEdit(record.id)">编辑</a-button>
            <a-button type="link" size="small" danger @click="handleDelete(record.id, record.name)">删除</a-button>
          </a-space>
        </template>
      </template>
    </a-table>

    <AlarmSchemaModal
      v-model:visible="modalVisible"
      :schema-id="editingId"
      @saved="refresh"
    />
  </div>
</template>
