<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { message } from 'ant-design-vue'
import { ReloadOutlined } from '@ant-design/icons-vue'

import {
  settingsApi,
  type SettingItem,
  type SettingsRuntime,
} from '@/api/settings'

interface FormState {
  autosaveInterval: number
  mockPathPrefix: string
}

const loading = ref(false)
const saving = ref(false)
const runtime = ref<SettingsRuntime | null>(null)
const items = ref<SettingItem[]>([])

const form = reactive<FormState>({
  autosaveInterval: 60,
  mockPathPrefix: '',
})

function pickValue(key: string): string | number | null {
  return items.value.find((i) => i.key === key)?.value ?? null
}

function applySnapshot(snapshot: { items: SettingItem[]; runtime: SettingsRuntime }) {
  items.value = snapshot.items
  runtime.value = snapshot.runtime
  const interval = pickValue('autosave_interval')
  const prefix = pickValue('mock_path_prefix')
  form.autosaveInterval = typeof interval === 'number' ? interval : Number(interval ?? 60)
  form.mockPathPrefix = typeof prefix === 'string' ? prefix : prefix == null ? '' : String(prefix)
}

async function loadSettings() {
  loading.value = true
  try {
    const snapshot = await settingsApi.list()
    applySnapshot(snapshot)
  } finally {
    loading.value = false
  }
}

function validatePrefix(value: string): string | null {
  const trimmed = value.trim()
  if (trimmed === '') return null
  if (!trimmed.startsWith('/')) return 'mock_path_prefix 必须以 / 开头或留空'
  return null
}

async function handleSave() {
  const prefixError = validatePrefix(form.mockPathPrefix)
  if (prefixError) {
    message.error(prefixError)
    return
  }
  saving.value = true
  try {
    const snapshot = await settingsApi.update({
      autosaveInterval: form.autosaveInterval,
      mockPathPrefix: form.mockPathPrefix.trim(),
    })
    applySnapshot(snapshot)
    message.success('设置已保存并热生效')
  } catch {
    // http interceptor already toasts
  } finally {
    saving.value = false
  }
}

onMounted(loadSettings)
</script>

<template>
  <a-card title="系统设置" :loading="loading">
    <template #extra>
      <a-button @click="loadSettings">
        <template #icon><ReloadOutlined /></template>
        刷新
      </a-button>
    </template>

    <a-alert
      type="info"
      show-icon
      :message="`应用基础信息为只读：${runtime?.appHost ?? ''}:${runtime?.appPort ?? ''} · 日志级别 ${runtime?.logLevel ?? ''}。修改这些项需调整 .env 后重启后端进程。`"
      style="margin-bottom: 16px"
    />

    <a-descriptions
      title="应用基础（只读，需重启）"
      :column="2"
      bordered
      size="small"
      style="margin-bottom: 24px"
    >
      <a-descriptions-item label="监听地址">{{ runtime?.appHost ?? '-' }}</a-descriptions-item>
      <a-descriptions-item label="监听端口">{{ runtime?.appPort ?? '-' }}</a-descriptions-item>
      <a-descriptions-item label="日志级别">{{ runtime?.logLevel ?? '-' }}</a-descriptions-item>
      <a-descriptions-item label="数据库路径">{{ runtime?.dbPath ?? '-' }}</a-descriptions-item>
    </a-descriptions>

    <a-form layout="vertical" :model="form" @submit.prevent="handleSave">
      <a-divider orientation="left">业务设置（可热生效）</a-divider>

      <a-form-item label="画布自动保存间隔（秒）" name="autosaveInterval">
        <a-input-number
          v-model:value="form.autosaveInterval"
          :min="5"
          :max="3600"
          style="width: 200px"
        />
        <div class="hint">范围 5–3600 秒。修改后下次画布加载即生效。</div>
      </a-form-item>

      <a-form-item label="模拟接口路径前缀" name="mockPathPrefix">
        <a-input
          v-model:value="form.mockPathPrefix"
          placeholder="留空则按原路径挂载（例：/rest/openapi/...）"
          style="max-width: 400px"
        />
        <div class="hint">
          形如 <code>/mock</code>，所有用户配置的接口将统一挂载在该前缀下；留空表示根路径直挂。
          保存后立即重新绑定全部 mock 路由，无需重启。
        </div>
      </a-form-item>

      <a-form-item>
        <a-button type="primary" :loading="saving" @click="handleSave">保存</a-button>
      </a-form-item>
    </a-form>
  </a-card>
</template>

<style scoped>
.hint {
  color: rgba(0, 0, 0, 0.45);
  font-size: 12px;
  margin-top: 4px;
}
code {
  background: rgba(0, 0, 0, 0.06);
  padding: 0 4px;
  border-radius: 2px;
}
</style>
