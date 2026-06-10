<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { Modal, Form, Input } from 'ant-design-vue'
import type { DomainItem } from '@/api/domain'

interface Props {
  open: boolean
  editing: DomainItem | null
}

const props = defineProps<Props>()
const emit = defineEmits<{
  (e: 'update:open', v: boolean): void
  (e: 'create', data: { name: string; description?: string | null }): void
  (e: 'update', data: { name?: string | null; description?: string | null }): void
}>()

const loading = ref(false)
const formRef = ref<{ validateFields?: () => Promise<void> } | null>(null)

const formState = ref<{ name: string; description: string }>({
  name: '',
  description: '',
})

const isEdit = computed(() => !!props.editing)
const title = computed(() => (isEdit.value ? '编辑网管/设备' : '新建网管/设备'))

watch(
  () => props.open,
  (open) => {
    if (open) {
      formState.value = {
        name: props.editing?.name ?? '',
        description: props.editing?.description ?? '',
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
    if (isEdit.value) {
      await emit('update', { ...formState.value })
    } else {
      await emit('create', { ...formState.value })
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
    <Form
      ref="formRef"
      :model="formState"
      layout="vertical"
    >
      <Form.Item
        label="名称"
        name="name"
        :rules="[{ required: true, message: '请输入名称' }]"
      >
        <Input v-model:value="formState.name" placeholder="如：北京网管、思科 NMS" :maxlength="100" />
      </Form.Item>

      <Form.Item
        label="描述"
        name="description"
      >
        <Input.TextArea
          v-model:value="formState.description"
          placeholder="可选，描述该域对应的网管环境"
          :rows="3"
          :maxlength="500"
        />
      </Form.Item>
    </Form>
  </Modal>
</template>
