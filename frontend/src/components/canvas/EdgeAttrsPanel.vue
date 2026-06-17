<script setup lang="ts">
import { ref, watch } from 'vue'
import { Form, Input, InputNumber, Select, Switch, Button, Spin, Tooltip } from 'ant-design-vue'
import type { EdgeTypeFieldItem } from '@/api/types'
import { edgeApi } from '@/api/edge'
import ArrayJsonInput from './ArrayJsonInput.vue'
import { validateFields } from '@/utils/fieldValidation'

interface Props {
  visible: boolean
  edgeId: string | null
  edgeTypeId: string | null
  attrs: Record<string, string | null>
}

const props = defineProps<Props>()
const emit = defineEmits<{
  (e: 'close'): void
  (e: 'update', edgeId: string, attrs: Record<string, string | null>): void
  (e: 'delete', edgeId: string): void
}>()

const fields = ref<EdgeTypeFieldItem[]>([])
const formData = ref<Record<string, string>>({})
const loading = ref(false)
const saving = ref(false)
const fieldErrors = ref<Record<string, string>>({})

watch(
  () => props.edgeTypeId,
  async (newTypeId) => {
    if (!newTypeId) {
      fields.value = []
      return
    }
    const { edgeTypeApi } = await import('@/api/types')
    try {
      const typeDetail = await edgeTypeApi.get(newTypeId)
      fields.value = typeDetail.fields || []
    } catch {
      fields.value = []
    }
  },
  { immediate: true },
)

watch(
  () => props.attrs,
  (newAttrs) => {
    if (newAttrs) {
      formData.value = {}
      for (const k in newAttrs) {
        formData.value[k] = newAttrs[k] || ''
      }
    }
  },
  { immediate: true },
)

async function handleSave() {
  if (!props.edgeId) return
  const errs = validateFields(fields.value, formData.value)
  if (Object.keys(errs).length > 0) {
    fieldErrors.value = errs
    return
  }
  fieldErrors.value = {}
  saving.value = true
  try {
    const attrs: Record<string, string | null> = {}
    for (const key in formData.value) {
      attrs[key] = formData.value[key] || null
    }
    await edgeApi.setAttrs(props.edgeId, attrs)
    emit('update', props.edgeId, attrs)
  } catch {
    // ignore
  } finally {
    saving.value = false
  }
}

function getFieldValue(key: string): string {
  return formData.value[key] || ''
}

function setFieldValue(key: string, value: string) {
  formData.value[key] = value
}
</script>

<template>
  <Transition name="slide">
    <div v-if="visible" class="edge-attrs-panel">
      <div class="panel-header">
        <span class="panel-title">边属性</span>
        <Button type="text" size="small" @click="emit('close')">×</Button>
      </div>

      <div class="panel-content">
        <Spin v-if="loading" tip="加载中..." />
        <template v-else>
          <div class="edge-id">ID: {{ edgeId }}</div>

          <Form
            layout="horizontal"
            class="attrs-form"
            :label-col="{ flex: '100px' }"
            :wrapper-col="{ flex: 'auto' }"
          >
            <Form.Item
              v-for="field in fields"
              :key="field.id"
              :validate-status="fieldErrors[field.fieldKey] ? 'error' : ''"
              :help="fieldErrors[field.fieldKey]"
            >
              <template #label>
                <Tooltip :title="field.fieldLabel" placement="left">
                  <span class="attr-label-text">{{ field.fieldLabel }}</span>
                </Tooltip>
              </template>
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
              <template v-else-if="field.fieldType === 'array'">
                <ArrayJsonInput
                  :value="getFieldValue(field.fieldKey)"
                  @update:value="(v: string) => setFieldValue(field.fieldKey, v)"
                  :placeholder="field.defaultValue || '[]'"
                />
              </template>
            </Form.Item>
          </Form>
        </template>
      </div>

      <div v-if="!loading" class="panel-footer">
        <Button danger @click="edgeId && emit('delete', edgeId)">
          删除
        </Button>
        <Button type="primary" :loading="saving" @click="handleSave">
          保存
        </Button>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.edge-attrs-panel {
  position: absolute;
  top: 0;
  right: 0;
  width: 380px;
  height: 100%;
  background: #fff;
  border-left: 1px solid #e8e8e8;
  box-shadow: -2px 0 8px rgba(0, 0, 0, 0.1);
  display: flex;
  flex-direction: column;
  z-index: 100;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid #e8e8e8;
}

.panel-title {
  font-weight: 500;
  font-size: 14px;
}

.panel-content {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

.edge-id {
  font-size: 12px;
  color: #999;
  margin-bottom: 16px;
  padding-bottom: 8px;
  border-bottom: 1px solid #f0f0f0;
  word-break: break-all;
}

.attrs-form {
  margin-top: 8px;
}

.attrs-form :deep(.ant-form-item) {
  margin-bottom: 12px;
}

.attr-label-text {
  display: inline-block;
  max-width: 100px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  vertical-align: bottom;
}

.panel-footer {
  padding: 12px 16px;
  border-top: 1px solid #e8e8e8;
  display: flex;
  justify-content: space-between;
  gap: 8px;
}

.slide-enter-active,
.slide-leave-active {
  transition: transform 0.2s ease;
}

.slide-enter-from,
.slide-leave-to {
  transform: translateX(100%);
}
</style>
