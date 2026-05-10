<script setup lang="ts">
import { ref, watch } from 'vue'
import { Modal, Form, Input, InputNumber, Select, Switch } from 'ant-design-vue'
import type { NodeTypeFieldItem } from '@/api/types'
import { nodeApi } from '@/api/node'

interface Props {
  visible: boolean
  topologyId: string
  nodeTypeId: string
  nodeTypeName: string
}

const props = defineProps<Props>()
const emit = defineEmits<{
  (e: 'close'): void
  (e: 'created', nodeId: string, name: string): void
}>()

const fields = ref<NodeTypeFieldItem[]>([])
const formData = ref<Record<string, string>>({})
const creating = ref(false)
const fieldErrors = ref<Record<string, string>>({})
const nodeName = ref('')
const nodeNameError = ref('')

watch(
  () => props.visible,
  async (v) => {
    if (!v) return
    formData.value = {}
    fieldErrors.value = {}
    nodeName.value = `${props.nodeTypeName}_${Date.now().toString(36).slice(0, 6)}`
    nodeNameError.value = ''
    try {
      const { nodeTypeApi } = await import('@/api/types')
      const typeDetail = await nodeTypeApi.get(props.nodeTypeId)
      fields.value = typeDetail.fields || []
      // Initialize defaults
      for (const field of fields.value) {
        if (field.defaultValue) {
          formData.value[field.fieldKey] = field.defaultValue
        }
      }
    } catch {
      fields.value = []
    }
  },
  { immediate: true }
)

function getFieldValue(key: string): string {
  return formData.value[key] || ''
}

function setFieldValue(key: string, value: string) {
  formData.value[key] = value
  // 清除该字段的错误提示
  if (fieldErrors.value[key]) {
    delete fieldErrors.value[key]
  }
}

async function handleCreate() {
  // 校验 name
  if (!nodeName.value.trim()) {
    nodeNameError.value = '节点名称不能为空'
    return
  }
  nodeNameError.value = ''

  // 校验必填字段
  const newErrors: Record<string, string> = {}
  for (const field of fields.value) {
    if (field.required && !formData.value[field.fieldKey]) {
      newErrors[field.fieldKey] = '此字段为必填项'
    }
  }

  if (Object.keys(newErrors).length > 0) {
    fieldErrors.value = newErrors
    return
  }

  creating.value = true
  const trimmedName = nodeName.value.trim()
  try {
    const result = await nodeApi.create(props.topologyId, {
      nodeTypeId: props.nodeTypeId,
      name: trimmedName,
      status: 'online',
    })
    // Set attributes
    if (Object.keys(formData.value).length > 0) {
      const attrs: Record<string, string | null> = {}
      for (const key in formData.value) {
        attrs[key] = formData.value[key] || null
      }
      await nodeApi.setAttrs(result.id, attrs)
    }
    emit('created', result.id, trimmedName)
  } catch {
    // ignore
  } finally {
    creating.value = false
  }
}
</script>

<template>
  <Modal
    :open="visible"
    title="创建节点"
    :confirm-loading="creating"
    @cancel="emit('close')"
    @ok="handleCreate"
    ok-text="创建"
  >
    <div class="node-type-name">{{ nodeTypeName }}</div>

    <Form layout="vertical" class="attrs-form">
      <Form.Item
        label="节点名称"
        required
        :validate-status="nodeNameError ? 'error' : ''"
        :help="nodeNameError"
      >
        <Input
          v-model:value="nodeName"
          placeholder="请输入节点名称"
        />
      </Form.Item>

      <Form.Item
        v-for="field in fields"
        :key="field.id"
        :label="field.fieldLabel"
        :required="field.required"
        :validate-status="fieldErrors[field.fieldKey] ? 'error' : ''"
        :help="fieldErrors[field.fieldKey]"
      >
        <template v-if="field.fieldType === 'text'">
          <Input
            :value="getFieldValue(field.fieldKey)"
            @input="(e: any) => setFieldValue(field.fieldKey, e.target.value)"
            :maxlength="field.maxLength || undefined"
            :showCount="!!field.maxLength"
          />
        </template>
        <template v-else-if="field.fieldType === 'number'">
          <InputNumber
            :value="Number(getFieldValue(field.fieldKey))"
            @change="(v: any) => setFieldValue(field.fieldKey, String(v ?? ''))"
            style="width: 100%"
          />
        </template>
        <template v-else-if="field.fieldType === 'select'">
          <Select
            :value="getFieldValue(field.fieldKey)"
            @change="(v: any) => setFieldValue(field.fieldKey, String(v))"
          >
            <Select.Option
              v-for="opt in (field.options || '').split(',')"
              :key="opt.trim()"
              :value="opt.trim()"
            >
              {{ opt.trim() }}
            </Select.Option>
          </Select>
        </template>
        <template v-else-if="field.fieldType === 'boolean'">
          <Switch
            :checked="getFieldValue(field.fieldKey) === 'true'"
            @change="(v: any) => setFieldValue(field.fieldKey, String(v))"
          />
        </template>
      </Form.Item>
    </Form>
  </Modal>
</template>

<style scoped>
.node-type-name {
  font-size: 16px;
  font-weight: 500;
  margin-bottom: 16px;
  padding-bottom: 8px;
  border-bottom: 1px solid #f0f0f0;
}

.attrs-form {
  margin-top: 8px;
}

.no-required {
  text-align: center;
  color: #999;
  padding: 20px;
}
</style>
