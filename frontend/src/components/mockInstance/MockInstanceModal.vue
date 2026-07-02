<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { Modal, Form, Input, InputNumber, Select, Radio } from 'ant-design-vue'
import { apiGet } from '@/api/http'
import type { MockInstanceItem } from '@/api/mockInstance'
import type { TopologyListItem } from '@/api/topology'

interface Props {
  open: boolean
  editing: MockInstanceItem | null
}

const props = defineProps<Props>()
const emit = defineEmits<{
  (e: 'update:open', v: boolean): void
  (e: 'create', data: { name: string; topologyId: string; port: number; description?: string | null; sslEnabled: boolean }): void
  (e: 'update', data: { name?: string | null; topologyId?: string | null; port?: number; description?: string | null; sslEnabled?: boolean }): void
}>()

const loading = ref(false)
const formRef = ref<{ validateFields?: () => Promise<void> } | null>(null)
const topologies = ref<TopologyListItem[]>([])

const formState = ref<{ name: string; topologyId: string; port: number | undefined; description: string; sslEnabled: boolean }>({
  name: '',
  topologyId: '',
  port: undefined,
  description: '',
  sslEnabled: false,
})

const isEdit = computed(() => !!props.editing)
const title = computed(() => (isEdit.value ? '编辑实例' : '新建实例'))

onMounted(async () => {
  try {
    const res = await apiGet<{ items: TopologyListItem[] }>('/topologies', { page: 1, pageSize: 500 })
    topologies.value = res.items
  } catch {}
})

watch(
  () => props.open,
  (open) => {
    if (open) {
      formState.value = {
        name: props.editing?.name ?? '',
        topologyId: props.editing?.topologyId ?? '',
        port: props.editing?.port ?? undefined,
        description: props.editing?.description ?? '',
        sslEnabled: props.editing?.sslEnabled ?? false,
      }
    }
  },
)

function close() {
  emit('update:open', false)
}

async function handleSubmit() {
  try {
    if (formRef.value?.validateFields) await formRef.value.validateFields()
    loading.value = true
    if (isEdit.value) {
      await emit('update', { ...formState.value })
    } else {
      await emit('create', { ...formState.value, port: formState.value.port! })
    }
    close()
  } catch {
    // validation failed
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
    <Form ref="formRef" :model="formState" layout="vertical">
      <Form.Item
        label="名称"
        name="name"
        :rules="[{ required: true, message: '请输入实例名称' }]"
      >
        <Input v-model:value="formState.name" placeholder="如：北京-设备查询" :maxlength="100" />
      </Form.Item>

      <Form.Item
        label="端口"
        name="port"
        :rules="[{ required: true, message: '请输入端口号' }]"
      >
        <InputNumber
          v-model:value="formState.port"
          :min="1"
          :max="65535"
          placeholder="1 ~ 65535"
          style="width: 100%"
        />
      </Form.Item>

      <Form.Item
        label="协议"
        name="sslEnabled"
        :extra="formState.sslEnabled ? '使用系统自签证书，客户端需跳过证书校验' : undefined"
      >
        <Radio.Group v-model:value="formState.sslEnabled">
          <Radio :value="false">HTTP</Radio>
          <Radio :value="true">HTTPS</Radio>
        </Radio.Group>
      </Form.Item>

      <Form.Item
        label="所属拓扑"
        name="topologyId"
        :rules="[{ required: true, message: '请选择拓扑' }]"
      >
        <Select
          v-model:value="formState.topologyId"
          placeholder="选择拓扑"
          show-search
          option-filter-prop="label"
        >
          <Select.Option
            v-for="t in topologies"
            :key="t.id"
            :value="t.id"
            :label="t.name"
          >
            {{ t.name }}
          </Select.Option>
        </Select>
      </Form.Item>

      <Form.Item label="描述" name="description">
        <Input.TextArea
          v-model:value="formState.description"
          placeholder="可选描述"
          :rows="3"
          :maxlength="200"
        />
      </Form.Item>
    </Form>
  </Modal>
</template>
