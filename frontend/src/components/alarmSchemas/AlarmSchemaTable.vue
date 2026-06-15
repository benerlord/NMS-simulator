<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { Modal } from 'ant-design-vue'
import { useAlarmSchemas } from '@/composables/useAlarmSchemas'
import AlarmSchemaModal from './AlarmSchemaModal.vue'
import { alarmSchemaApi } from '@/api/alarmSchema'

const { schemas, loading, fetchSchemas, deleteSchema } = useAlarmSchemas()
const modalVisible = ref(false)
const editingId = ref<string | null>(null)
const fieldsCount = ref<Record<string, number>>({})

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
    <div style="margin-bottom: 16px">
      <a-button type="primary" @click="handleCreate">新建告警模板</a-button>
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
