<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { Modal, Form, Input } from 'ant-design-vue'
import type { TopologyCreate, TopologyUpdate } from '@/api/topology'

interface Props {
  open: boolean
  topology?: { id: string; name: string; description: string | null } | null
}

const props = defineProps<Props>()
const emit = defineEmits<{
  (e: 'update:open', v: boolean): void
  (e: 'submit', data: TopologyCreate | TopologyUpdate): Promise<void>
}>()

const loading = ref(false)
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const formRef = ref<{ validateFields?: () => Promise<void> } | null>(null)

const formState = ref<{ name: string; description: string }>({
  name: '',
  description: '',
})

const isEdit = computed(() => !!props.topology)
const title = computed(() => (isEdit.value ? '编辑拓扑' : '新建拓扑'))

watch(
  () => props.open,
  (open) => {
    if (open) {
      formState.value = {
        name: props.topology?.name ?? '',
        description: props.topology?.description ?? '',
      }
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
    await emit('submit', { ...formState.value })
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
    </Form>
  </Modal>
</template>

<style scoped>
.topology-form {
  padding-top: 8px;
}
</style>
