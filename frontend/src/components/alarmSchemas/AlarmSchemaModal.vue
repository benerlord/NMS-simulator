<script setup lang="ts">
import { ref, watch } from 'vue'
import { message, Select } from 'ant-design-vue'
import AlarmSchemaFieldEditor from './AlarmSchemaFieldEditor.vue'
import { alarmSchemaApi, type AlarmSchemaFieldInput } from '@/api/alarmSchema'

const props = defineProps<{
  visible: boolean
  schemaId: string | null
}>()

const emit = defineEmits<{
  (e: 'update:visible', v: boolean): void
  (e: 'saved'): void
}>()

const form = ref({
  code: '',
  name: '',
  description: '',
  displayFieldKey: null as string | null,
})
const fields = ref<AlarmSchemaFieldInput[]>([])
const saving = ref(false)

watch(
  () => props.visible,
  async (v) => {
    if (!v) return
    if (props.schemaId) {
      try {
        const d = await alarmSchemaApi.get(props.schemaId)
        form.value = { code: d.code, name: d.name, description: d.description ?? '', displayFieldKey: d.displayFieldKey ?? null }
        fields.value = d.fields.map(f => ({
          fieldKey: f.fieldKey,
          fieldLabel: f.fieldLabel,
          fieldType: f.fieldType,
          maxLength: f.maxLength ?? null,
          defaultValue: f.defaultValue ?? null,
          options: f.options ?? null,
          required: f.required,
          sortOrder: f.sortOrder,
        }))
      } catch (e: any) {
        message.error(e?.message || '加载告警模板失败')
      }
    } else {
      form.value = { code: '', name: '', description: '', displayFieldKey: null }
      fields.value = []
    }
  },
)

async function handleOk() {
  if (!form.value.code.trim() || !form.value.name.trim()) {
    message.error('Code 和名称为必填项')
    return
  }
  saving.value = true
  try {
    if (props.schemaId) {
      await alarmSchemaApi.update(props.schemaId, {
        name: form.value.name,
        description: form.value.description || null,
        displayFieldKey: form.value.displayFieldKey,
        fields: fields.value,
      })
      message.success('更新成功')
    } else {
      await alarmSchemaApi.create({
        code: form.value.code,
        name: form.value.name,
        description: form.value.description || null,
        displayFieldKey: form.value.displayFieldKey,
        fields: fields.value,
      })
      message.success('创建成功')
    }
    emit('saved')
    emit('update:visible', false)
  } catch (e: any) {
    message.error(e?.message || '保存失败')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <a-modal
    :open="visible"
    :title="schemaId ? '编辑告警模板' : '新建告警模板'"
    width="800px"
    :confirm-loading="saving"
    ok-text="保存"
    cancel-text="取消"
    @update:open="(v: boolean) => emit('update:visible', v)"
    @ok="handleOk"
  >
    <a-form layout="vertical">
      <a-form-item label="Code（SQL 标识符）" required>
        <a-input
          v-model:value="form.code"
          :disabled="!!schemaId"
          placeholder="如: host_alarm（仅字母/数字/下划线）"
        />
      </a-form-item>
      <a-form-item label="名称" required>
        <a-input v-model:value="form.name" placeholder="如: 主机告警" />
      </a-form-item>
      <a-form-item label="描述">
        <a-textarea v-model:value="form.description" :rows="2" placeholder="可选" />
      </a-form-item>
      <a-form-item label="卡片标题字段">
        <Select
          v-model:value="form.displayFieldKey"
          allow-clear
          placeholder="默认：sort_order 最小的字段"
        >
          <Select.Option v-for="f in fields" :key="f.fieldKey" :value="f.fieldKey">
            {{ f.fieldLabel }} ({{ f.fieldKey }})
          </Select.Option>
        </Select>
      </a-form-item>
      <a-form-item label="告警字段">
        <AlarmSchemaFieldEditor v-model:fields="fields" />
      </a-form-item>
    </a-form>
  </a-modal>
</template>
