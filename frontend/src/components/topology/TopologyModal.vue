<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { Modal, Form, Input, Select, message } from 'ant-design-vue'
import { apiGet, apiPost, apiPut } from '@/api/http'
import { alarmSchemaApi, type AlarmSchemaItem } from '@/api/alarmSchema'
import { topologyApi, type TopologyDetail } from '@/api/topology'
import type { DomainItem } from '@/api/domain'
import { domainApi } from '@/api/domain'

interface Props {
  open: boolean
  topology?: {
    id: string
    name: string
    description: string | null
    domainId?: string | null
  } | null
}

const props = defineProps<Props>()
const emit = defineEmits<{
  (e: 'update:open', v: boolean): void
  (e: 'saved'): void
}>()

const domains = ref<DomainItem[]>([])
const alarmSchemas = ref<AlarmSchemaItem[]>([])
const loading = ref(false)
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const formRef = ref<{ validateFields?: () => Promise<void> } | null>(null)

const formState = ref<{ name: string; description: string; domainId: string | null }>({
  name: '',
  description: '',
  domainId: null,
})

const selectedAlarmSchemaId = ref<string | null>(null)
const initialAlarmSchemaId = ref<string | null>(null)
const initialAlarmCount = ref(0)

const isEdit = computed(() => !!props.topology)
const title = computed(() => (isEdit.value ? '编辑拓扑' : '新建拓扑'))

onMounted(async () => {
  try {
    const res = await domainApi.list()
    domains.value = res.items
  } catch {}
})

async function loadAlarmSchemas() {
  try {
    alarmSchemas.value = await alarmSchemaApi.list()
  } catch {}
}

watch(
  () => props.open,
  async (open) => {
    if (open) {
      formState.value = {
        name: props.topology?.name ?? '',
        description: props.topology?.description ?? '',
        domainId: props.topology?.domainId ?? null,
      }

      if (props.topology?.id) {
        // Editing — fetch full detail to get alarm schema binding and count
        try {
          const detail = await apiGet<TopologyDetail>(`/topologies/${props.topology.id}`)
          selectedAlarmSchemaId.value = detail.alarmSchemaId ?? null
          initialAlarmSchemaId.value = detail.alarmSchemaId ?? null
          initialAlarmCount.value = detail.nodeAlarmCount ?? 0
        } catch {
          selectedAlarmSchemaId.value = null
          initialAlarmSchemaId.value = null
          initialAlarmCount.value = 0
        }
      } else {
        // Creating — reset alarm fields
        selectedAlarmSchemaId.value = null
        initialAlarmSchemaId.value = null
        initialAlarmCount.value = 0
      }

      await loadAlarmSchemas()
    }
  },
)

function close() {
  emit('update:open', false)
}

async function handleSubmit() {
  try {
    if (formRef.value?.validateFields) {
      await formRef.value.validateFields()
    }
    loading.value = true

    if (isEdit.value && props.topology) {
      // Update topology basic fields
      await apiPut<TopologyDetail>(`/topologies/${props.topology.id}`, { ...formState.value })

      // Handle alarm schema binding change
      const newSid = selectedAlarmSchemaId.value
      if (newSid !== initialAlarmSchemaId.value) {
        if (initialAlarmCount.value > 0) {
          // Confirm before clearing existing alarms
          await new Promise<void>((resolve, reject) => {
            Modal.confirm({
              title: '切换告警模板将清空已有告警数据',
              content: `当前拓扑下有 ${initialAlarmCount.value} 条告警，是否确认清空并切换？`,
              okText: '清空并切换',
              okType: 'danger',
              cancelText: '取消',
              onOk: () => resolve(),
              onCancel: () => reject(new Error('user_cancelled')),
            })
          })
          await topologyApi.bindAlarmSchema(props.topology.id, newSid, true)
        } else {
          await topologyApi.bindAlarmSchema(props.topology.id, newSid, false)
        }
      }

      message.success('更新成功')
    } else {
      // Create topology
      const result = await apiPost<TopologyDetail>('/topologies', { ...formState.value })

      // Bind alarm schema if selected
      if (selectedAlarmSchemaId.value) {
        await topologyApi.bindAlarmSchema(result.id, selectedAlarmSchemaId.value, false)
      }

      message.success('创建成功')
    }

    emit('saved')
    close()
  } catch (err) {
    // Silently ignore user-cancelled confirm dialog
    if (err instanceof Error && err.message === 'user_cancelled') {
      return
    }
    // Other errors (validation, network) are handled by http interceptor or thrown
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <Modal
    :open="open"
    :title="title"
    :confirm-loading="loading"
    ok-text="确定"
    cancel-text="取消"
    @ok="handleSubmit"
    @cancel="close"
  >
    <Form
      ref="formRef"
      :model="formState"
      layout="vertical"
      class="topology-form"
    >
      <Form.Item
        label="名称"
        name="name"
        :rules="[{ required: true, message: '请输入拓扑名称' }]"
      >
        <Input v-model:value="formState.name" placeholder="请输入拓扑名称" :maxlength="100" />
      </Form.Item>

      <Form.Item
        label="描述"
        name="description"
      >
        <Input.TextArea
          v-model:value="formState.description"
          placeholder="请输入描述（可选）"
          :rows="3"
          :maxlength="500"
        />
      </Form.Item>

      <Form.Item
        label="所属网管/设备"
        name="domainId"
      >
        <Select
          v-model:value="formState.domainId"
          placeholder="可选，选择后画布仅展示该网管/设备的节点类型"
          allow-clear
        >
          <Select.Option
            v-for="d in domains"
            :key="d.id"
            :value="d.id"
          >
            {{ d.name }}
          </Select.Option>
        </Select>
      </Form.Item>

      <Form.Item
        label="告警模板"
      >
        <Select
          v-model:value="selectedAlarmSchemaId"
          allow-clear
          placeholder="不绑定"
        >
          <Select.Option
            v-for="s in alarmSchemas"
            :key="s.id"
            :value="s.id"
          >
            {{ s.name }} ({{ s.code }})
          </Select.Option>
        </Select>
      </Form.Item>
    </Form>
  </Modal>
</template>

<style scoped>
.topology-form {
  padding-top: 8px;
}
</style>
