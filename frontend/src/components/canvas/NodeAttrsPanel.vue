<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { Form, Input, InputNumber, Select, Switch, Button, Spin, Tabs } from 'ant-design-vue'
import type { NodeTypeFieldItem } from '@/api/types'
import { nodeApi } from '@/api/node'
import { useRoute } from 'vue-router'
import NodeAlarmsTab from './NodeAlarmsTab.vue'

interface Props {
  visible: boolean
  nodeId: string | null
  nodeTypeId: string | null
  nodeName: string
  attrs: Record<string, string | null>
}

const props = defineProps<Props>()
const emit = defineEmits<{
  (e: 'close'): void
  (e: 'update', nodeId: string, attrs: Record<string, string | null>): void
  (e: 'delete', nodeId: string, nodeName: string): void
  (e: 'rename', nodeId: string, newName: string): void
}>()

const route = useRoute()
const topologyId = computed(() => route.params.id as string)

const fields = ref<NodeTypeFieldItem[]>([])
const formData = ref<Record<string, string>>({})
const loading = ref(false)
const saving = ref(false)
const editingName = ref('')

const activeTab = ref<'attrs' | 'alarms'>('attrs')
const alarmCount = ref(0)
const alarmsTabRef = ref<InstanceType<typeof NodeAlarmsTab> | null>(null)

watch(
  () => props.nodeName,
  (v) => { if (v) editingName.value = v },
  { immediate: true },
)

watch(
  () => props.nodeId,
  async (newId) => {
    if (!newId || !props.visible) return
    loading.value = true
    try {
      const node = await nodeApi.get(newId)
      formData.value = {}
      if (node.attrs) {
        for (const k in node.attrs) {
          formData.value[k] = node.attrs[k] || ''
        }
      }
    } catch {
      // ignore
    } finally {
      loading.value = false
    }
  },
  { immediate: true },
)

watch(
  () => props.nodeTypeId,
  async (newTypeId) => {
    if (!newTypeId) {
      fields.value = []
      return
    }
    const { nodeTypeApi } = await import('@/api/types')
    try {
      const typeDetail = await nodeTypeApi.get(newTypeId)
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

// Reset tab to attrs when switching to a different node
watch(
  () => props.nodeId,
  () => { activeTab.value = 'attrs' },
)

async function handleSave() {
  if (!props.nodeId) return
  saving.value = true
  try {
    const attrs: Record<string, string | null> = {}
    for (const key in formData.value) {
      attrs[key] = formData.value[key] || null
    }
    await nodeApi.setAttrs(props.nodeId, attrs)
    emit('update', props.nodeId, attrs)

    const trimmedName = editingName.value.trim()
    if (trimmedName && trimmedName !== props.nodeName) {
      await nodeApi.update(props.nodeId, { name: trimmedName })
      emit('rename', props.nodeId, trimmedName)
    }

    // Save alarm tab dirty state
    if (alarmsTabRef.value) {
      const ok = await alarmsTabRef.value.saveDirty()
      if (!ok) {
        saving.value = false
        return
      }
    }
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
    <div v-if="visible" class="node-attrs-panel">
      <div class="panel-header">
        <span class="panel-title">节点属性</span>
        <Button type="text" size="small" @click="emit('close')">×</Button>
      </div>

      <div class="panel-content">
        <Tabs v-model:active-key="activeTab">
          <Tabs.TabPane key="attrs" tab="属性">
            <Spin v-if="loading" tip="加载中..." />
            <template v-else>
              <div class="node-name-row">
                <span class="node-name-label">节点名称</span>
                <Input
                  v-model:value="editingName"
                  :maxlength="100"
                  placeholder="请输入节点名称"
                />
              </div>

              <Form layout="vertical" class="attrs-form">
                <Form.Item
                  v-for="field in fields"
                  :key="field.id"
                  :label="field.fieldLabel"
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
            </template>
          </Tabs.TabPane>

          <Tabs.TabPane key="alarms" :tab="`告警(${alarmCount})`">
            <NodeAlarmsTab
              ref="alarmsTabRef"
              :node-id="nodeId"
              :topology-id="topologyId"
              @count-change="(c) => alarmCount = c"
            />
          </Tabs.TabPane>
        </Tabs>
      </div>

      <div v-if="!loading" class="panel-footer">
        <Button danger @click="nodeId && emit('delete', nodeId, nodeName)">
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
.node-attrs-panel {
  position: absolute;
  top: 0;
  right: 0;
  width: 320px;
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

.node-name-row {
  margin-bottom: 16px;
  padding-bottom: 8px;
  border-bottom: 1px solid #f0f0f0;
}

.node-name-label {
  display: block;
  font-size: 12px;
  color: #999;
  margin-bottom: 4px;
}

.attrs-form {
  margin-top: 8px;
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
