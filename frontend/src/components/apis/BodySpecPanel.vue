<script setup lang="ts">
import { computed } from 'vue'
import { Form, Input, Select, Switch, Tooltip } from 'ant-design-vue'
import { InfoCircleOutlined } from '@ant-design/icons-vue'
import type { BodyContentType, BodySpec } from '@/api/api_config'

interface Props {
  modelValue: BodySpec | null
}

const props = defineProps<Props>()
const emit = defineEmits<{
  (e: 'update:modelValue', v: BodySpec | null): void
}>()

const contentTypeOptions: { label: string; value: BodyContentType }[] = [
  { label: 'application/json', value: 'application/json' },
  {
    label: 'application/x-www-form-urlencoded',
    value: 'application/x-www-form-urlencoded',
  },
  { label: 'text/plain', value: 'text/plain' },
]

const enabled = computed(() => props.modelValue !== null)

function defaultBody(): BodySpec {
  return {
    contentType: 'application/json',
    required: false,
    example: '',
    description: '',
  }
}

function onToggle(checked: boolean) {
  emit('update:modelValue', checked ? defaultBody() : null)
}

function setField<K extends keyof BodySpec>(key: K, value: BodySpec[K]) {
  if (!props.modelValue) return
  emit('update:modelValue', { ...props.modelValue, [key]: value })
}

const examplePlaceholder = `示例（仅文档展示，不做 schema 校验）：

{
  "grantType": "password",
  "userName": "imocthirdparty"
}`

const exampleParseHint = computed<string | null>(() => {
  const ct = props.modelValue?.contentType
  const raw = (props.modelValue?.example ?? '').trim()
  if (!raw) return null
  if (ct !== 'application/json') return null
  try {
    JSON.parse(raw)
    return null
  } catch (e) {
    return (e as Error).message
  }
})
</script>

<template>
  <div class="body-spec-panel">
    <div class="header">
      <span class="title">
        请求体声明
        <Tooltip title="开启后将校验 body 是否必填；contentType / example 仅用于文档展示，本期不做 schema 严格校验（content-type 严格匹配延后到 LEGACY-02）。">
          <InfoCircleOutlined class="info-icon" />
        </Tooltip>
      </span>
      <Switch
        :checked="enabled"
        checked-children="启用"
        un-checked-children="未声明"
        @change="(v: unknown) => onToggle(Boolean(v))"
      />
    </div>

    <div v-if="enabled && modelValue" class="body-form">
      <div class="form-row">
        <Form.Item label="Content-Type" class="form-col-half">
          <Select
            :value="modelValue.contentType"
            :options="contentTypeOptions"
            @update:value="(v: unknown) => setField('contentType', v as BodyContentType)"
          />
        </Form.Item>

        <Form.Item label="必填" class="form-col-half">
          <Switch
            :checked="modelValue.required"
            checked-children="必填"
            un-checked-children="可空"
            @update:checked="(v: unknown) => setField('required', Boolean(v))"
          />
          <div class="hint">必填且 body 为空时返回 400 + 40026</div>
        </Form.Item>
      </div>

      <Form.Item label="示例（example）">
        <Input.TextArea
          :value="modelValue.example ?? ''"
          :rows="6"
          :placeholder="examplePlaceholder"
          spellcheck="false"
          class="example-textarea"
          @update:value="(v: string) => setField('example', v)"
        />
        <div v-if="exampleParseHint" class="hint hint-error">
          JSON 解析失败：{{ exampleParseHint }}（仅提示，不阻塞提交）
        </div>
        <div v-else class="hint">
          仅用于接口文档/调试参考。本期不做 body schema 校验，schema 字段保留给后续版本。
        </div>
      </Form.Item>

      <Form.Item label="说明（description）">
        <Input
          :value="modelValue.description ?? ''"
          placeholder="可选：解释该 body 的业务含义"
          @update:value="(v: string) => setField('description', v)"
        />
      </Form.Item>
    </div>

    <div v-else class="placeholder">
      未声明请求体。开启后可配置 contentType / required / example。
    </div>
  </div>
</template>

<style scoped>
.body-spec-panel {
  border: 1px solid #f0f0f0;
  border-radius: 6px;
  padding: 12px;
  background: #fafafa;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.title {
  font-weight: 500;
  color: #595959;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.info-icon {
  color: #8c8c8c;
  font-size: 13px;
  cursor: help;
}

.body-form {
  padding-top: 4px;
}

.form-row {
  display: flex;
  gap: 12px;
}

.form-col-half {
  flex: 1;
}

.hint {
  font-size: 12px;
  color: #8c8c8c;
  margin-top: 4px;
}

.hint-error {
  color: #d4380d;
}

.example-textarea :deep(textarea) {
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 12px;
  line-height: 1.5;
}

.placeholder {
  font-size: 12px;
  color: #8c8c8c;
  padding: 8px 0;
}
</style>
