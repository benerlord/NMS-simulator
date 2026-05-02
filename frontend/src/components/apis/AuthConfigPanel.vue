<script setup lang="ts">
import { computed } from 'vue'
import { Form, Input, Select, Alert } from 'ant-design-vue'
import type { AuthConfig, AuthType } from '@/api/api_config'

interface Props {
  modelValue: AuthConfig
}

const props = defineProps<Props>()
const emit = defineEmits<{
  (e: 'update:modelValue', v: AuthConfig): void
}>()

const typeOptions: { label: string; value: AuthType }[] = [
  { label: '无鉴权 (none)', value: 'none' },
  { label: 'X-Auth-Token (xtoken)', value: 'xtoken' },
  { label: 'Basic', value: 'basic' },
]

function setField<K extends keyof AuthConfig>(key: K, value: AuthConfig[K]) {
  emit('update:modelValue', { ...props.modelValue, [key]: value })
}

function onTypeChange(v: AuthType) {
  // 切换到 none 时清空 headerName，避免脏数据残留
  const next: AuthConfig = { type: v }
  if (v === 'xtoken') {
    next.headerName = props.modelValue.headerName || 'X-Auth-Token'
  }
  emit('update:modelValue', next)
}

const isXToken = computed(() => props.modelValue.type === 'xtoken')
const isBasic = computed(() => props.modelValue.type === 'basic')
</script>

<template>
  <div class="auth-config-panel">
    <Form.Item label="认证类型">
      <Select
        :value="modelValue.type"
        :options="typeOptions"
        style="max-width: 280px"
        @update:value="(v: unknown) => onTypeChange(v as AuthType)"
      />
      <div class="hint">
        通过 <code>/tokens</code> 页面颁发对应类型 token；调用方按下方提示在请求中携带凭证。
      </div>
    </Form.Item>

    <Form.Item v-if="isXToken" label="Header 名称">
      <Input
        :value="modelValue.headerName ?? 'X-Auth-Token'"
        placeholder="X-Auth-Token"
        :maxlength="100"
        style="max-width: 280px"
        @update:value="(v: string) => setField('headerName', v || 'X-Auth-Token')"
      />
      <div class="hint">
        默认 <code>X-Auth-Token</code>。调用方需在该 header 携带颁发的 token 字符串。
      </div>
    </Form.Item>

    <Alert
      v-if="isXToken"
      type="info"
      show-icon
      :message="'调用示例'"
      class="auth-alert"
    >
      <template #description>
        <pre class="snippet">curl -H "{{ modelValue.headerName || 'X-Auth-Token' }}: &lt;token&gt;" \
  http://127.0.0.1:8080{{ '<api_path>' }}</pre>
      </template>
    </Alert>

    <Alert
      v-if="isBasic"
      type="info"
      show-icon
      message="Basic 认证使用提示"
      class="auth-alert"
    >
      <template #description>
        <div>
          1. 在 <code>/tokens</code> 页面以 basic 类型颁发 token，<strong>token 字段填用户名</strong>，密码写入 meta 段；
        </div>
        <div>
          2. 调用方需将 <code>用户名:密码</code> 做 base64 后通过 <code>Authorization: Basic &lt;b64&gt;</code> header 发送。
        </div>
        <pre class="snippet">curl -u admin:secret http://127.0.0.1:8080{{ '<api_path>' }}
# 等价于
curl -H "Authorization: Basic YWRtaW46c2VjcmV0" ...</pre>
      </template>
    </Alert>

    <div v-if="modelValue.type === 'none'" class="hint">
      未启用鉴权。任何调用方都可命中本接口；如需保护，请切换到 xtoken 或 basic。
    </div>
  </div>
</template>

<style scoped>
.auth-config-panel {
  padding: 4px 0;
}

.hint {
  font-size: 12px;
  color: #8c8c8c;
  margin-top: 4px;
}

.auth-alert {
  margin-top: 12px;
}

.snippet {
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 12px;
  margin: 6px 0 0 0;
  padding: 8px;
  background: rgba(0, 0, 0, 0.04);
  border-radius: 4px;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
