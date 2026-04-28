<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { Modal, Form, Input, Select } from 'ant-design-vue'
import type { TokenAuthType, TokenCreate } from '@/api/token'

interface Props {
  open: boolean
}

const props = defineProps<Props>()
const emit = defineEmits<{
  (e: 'update:open', v: boolean): void
  (e: 'submit', data: TokenCreate): Promise<void>
}>()

const loading = ref(false)
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const formRef = ref<{ validateFields?: () => Promise<void> } | null>(null)

interface FormState {
  token: string
  expiresAtLocal: string
  authType: TokenAuthType
  issuedByApi: string
  password: string
  metaJson: string
}

function defaultExpiresAtLocal(): string {
  const d = new Date(Date.now() + 24 * 60 * 60 * 1000)
  // Build "YYYY-MM-DDTHH:mm" in local time without seconds (datetime-local format).
  const pad = (n: number) => n.toString().padStart(2, '0')
  return (
    `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}` +
    `T${pad(d.getHours())}:${pad(d.getMinutes())}`
  )
}

function emptyForm(): FormState {
  return {
    token: '',
    expiresAtLocal: defaultExpiresAtLocal(),
    authType: 'xtoken',
    issuedByApi: '',
    password: '',
    metaJson: '',
  }
}

const formState = ref<FormState>(emptyForm())

const authTypeOptions = [
  { label: 'X-Auth-Token', value: 'xtoken' },
  { label: 'Basic', value: 'basic' },
]

watch(
  () => props.open,
  (open) => {
    if (open) {
      formState.value = emptyForm()
    }
  },
)

const metaParseError = computed<string | null>(() => {
  const raw = formState.value.metaJson.trim()
  if (!raw) return null
  try {
    const parsed = JSON.parse(raw)
    if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
      return 'meta 必须是 JSON 对象（如 {"key":"value"}）'
    }
    return null
  } catch (e) {
    return (e as Error).message
  }
})

function close() {
  emit('update:open', false)
}

function buildMeta(): Record<string, unknown> {
  const meta: Record<string, unknown> = {}
  const raw = formState.value.metaJson.trim()
  if (raw) {
    try {
      const parsed = JSON.parse(raw)
      if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
        Object.assign(meta, parsed)
      }
    } catch {
      // gated by validator
    }
  }
  if (formState.value.authType === 'basic' && formState.value.password) {
    meta.password = formState.value.password
  }
  return meta
}

async function handleSubmit() {
  try {
    if (formRef.value?.validateFields) {
      await formRef.value.validateFields()
    }
    if (metaParseError.value) {
      throw new Error(metaParseError.value)
    }
    loading.value = true
    const localStr = formState.value.expiresAtLocal
    if (!localStr) return
    // datetime-local is interpreted as local time; convert to ISO 8601 with Z.
    const expiresIso = new Date(localStr).toISOString()
    const payload: TokenCreate = {
      token: formState.value.token.trim(),
      expiresAt: expiresIso,
      authType: formState.value.authType,
      issuedByApi: formState.value.issuedByApi.trim() || null,
      meta: buildMeta(),
    }
    await emit('submit', payload)
    close()
  } catch {
    // validation or backend error: keep modal open
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <Modal
    :open="open"
    title="颁发 Token"
    :confirm-loading="loading"
    ok-text="颁发"
    cancel-text="取消"
    :width="640"
    @ok="handleSubmit"
    @cancel="close"
  >
    <Form
      ref="formRef"
      :model="formState"
      layout="vertical"
      class="token-form"
    >
      <Form.Item
        label="Token / 用户名"
        name="token"
        :rules="[{ required: true, message: '请输入 Token 字符串' }]"
      >
        <Input
          v-model:value="formState.token"
          placeholder="xtoken 模式：完整 token；basic 模式：用户名"
          :maxlength="500"
        />
      </Form.Item>

      <div class="form-row">
        <Form.Item
          label="认证类型"
          name="authType"
          :rules="[{ required: true, message: '请选择认证类型' }]"
          class="form-col-half"
        >
          <Select v-model:value="formState.authType" :options="authTypeOptions" />
        </Form.Item>

        <Form.Item
          label="过期时间（本地时间）"
          name="expiresAtLocal"
          :rules="[{ required: true, message: '请选择过期时间' }]"
          class="form-col-half"
        >
          <input
            v-model="formState.expiresAtLocal"
            type="datetime-local"
            class="dt-input"
          />
        </Form.Item>
      </div>

      <Form.Item
        v-if="formState.authType === 'basic'"
        label="密码"
        name="password"
        :rules="[{ required: true, message: 'Basic 模式必须提供密码' }]"
      >
        <Input.Password
          v-model:value="formState.password"
          placeholder="将存入 meta.password 字段"
        />
        <div class="hint">
          Basic 认证模式下，请求方需用 <code>{{ formState.token || '<user>' }}:&lt;密码&gt;</code> 做 base64 后通过 Authorization header 发送。
        </div>
      </Form.Item>

      <Form.Item label="颁发接口（可选）" name="issuedByApi">
        <Input
          v-model:value="formState.issuedByApi"
          placeholder="例：api_xxx，仅用于追踪 token 由哪条 mock 接口颁发"
          :maxlength="500"
        />
      </Form.Item>

      <Form.Item label="附加元数据 meta（JSON 对象，可选）" name="metaJson">
        <Input.TextArea
          v-model:value="formState.metaJson"
          :rows="4"
          placeholder='{"username":"admin","scope":"read"}'
          spellcheck="false"
          class="meta-textarea"
        />
        <div v-if="metaParseError" class="hint hint-error">
          {{ metaParseError }}
        </div>
        <div v-else class="hint">
          自由附加字段，存入 tokens 表 <code>meta</code> 列。Basic 模式的密码会自动并入。
        </div>
      </Form.Item>
    </Form>
  </Modal>
</template>

<style scoped>
.token-form {
  padding-top: 8px;
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

.meta-textarea :deep(textarea) {
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 12px;
  line-height: 1.5;
}

.dt-input {
  width: 100%;
  height: 32px;
  padding: 4px 11px;
  border: 1px solid #d9d9d9;
  border-radius: 6px;
  font-size: 14px;
  background: #fff;
  outline: none;
  transition: border-color 0.2s;
}

.dt-input:hover {
  border-color: #4096ff;
}

.dt-input:focus {
  border-color: #1677ff;
  box-shadow: 0 0 0 2px rgba(5, 145, 255, 0.1);
}
</style>
