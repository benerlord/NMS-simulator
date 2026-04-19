<script setup lang="ts">
import { computed, ref } from 'vue'
import { Button, Table, Alert, Tag, Collapse, Tooltip } from 'ant-design-vue'
import { PlayCircleOutlined } from '@ant-design/icons-vue'
import { executeSql, type SqlExecuteResult } from '@/api/sql'
import type { ParamMapping } from './ParamMappingTable.vue'
import { ApiError } from '@/api/http'

interface Props {
  topologyId: string | null | undefined
  sqlText: string
  params?: ParamMapping[]
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'insert', text: string): void
}>()

const loading = ref(false)
const result = ref<SqlExecuteResult | null>(null)
const errorMsg = ref<string | null>(null)

const canRun = computed(() => !!props.topologyId && !!props.sqlText?.trim())

const columns = computed(() => {
  if (!result.value || result.value.items.length === 0) return []
  return Object.keys(result.value.items[0]).map((key) => ({
    title: key,
    dataIndex: key,
    key,
    ellipsis: true,
    customRender: ({ text }: { text: unknown }) => formatCell(text),
  }))
})

const dataSource = computed(() => {
  if (!result.value) return []
  return result.value.items.map((row, idx) => ({ ...row, _rowKey: idx }))
})

function formatCell(value: unknown): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

function paramsToDict(): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  if (!props.params) return out
  for (const p of props.params) {
    const key = (p.bindTo || p.name || '').trim().replace(/^:/, '')
    if (!key) continue
    // preview defaults to null so SQL patterns like `:p IS NULL OR col = :p` pass
    out[key] = null
  }
  return out
}

async function run() {
  if (!canRun.value || !props.topologyId) return
  loading.value = true
  errorMsg.value = null
  try {
    result.value = await executeSql({
      topologyId: props.topologyId,
      sql: props.sqlText,
      params: paramsToDict(),
      page: 1,
      pageSize: 10,
    })
  } catch (err) {
    result.value = null
    if (err instanceof ApiError) {
      errorMsg.value = `[${err.code}] ${err.message}`
    } else if (err instanceof Error) {
      errorMsg.value = err.message
    } else {
      errorMsg.value = '运行失败'
    }
  } finally {
    loading.value = false
  }
}

function insertColumn(col: string) {
  emit('insert', col)
}
</script>

<template>
  <div class="sql-runner">
    <div class="runner-toolbar">
      <Tooltip :title="canRun ? '' : '请先绑定拓扑并填写 SQL'">
        <Button
          type="primary"
          size="small"
          :loading="loading"
          :disabled="!canRun"
          @click="run"
        >
          <template #icon><PlayCircleOutlined /></template>
          运行预览
        </Button>
      </Tooltip>
      <span v-if="result" class="runner-meta">
        共 {{ result.total }} 条 · 展示前 {{ result.items.length }} ·
        {{ result.durationMs }} ms
      </span>
    </div>

    <Alert
      v-if="errorMsg"
      type="error"
      :message="errorMsg"
      show-icon
      class="runner-alert"
    />

    <div v-if="result && columns.length === 0" class="runner-empty">
      查询成功，但无数据返回
    </div>

    <div v-if="result && columns.length > 0" class="runner-result">
      <div class="runner-cols">
        <span class="runner-cols-label">结果列（点击插入）：</span>
        <Tag
          v-for="c in columns"
          :key="c.key"
          class="runner-col-tag"
          @click="insertColumn(String(c.key))"
        >
          {{ c.key }}
        </Tag>
      </div>

      <Table
        :columns="columns"
        :data-source="dataSource"
        :pagination="false"
        size="small"
        :scroll="{ x: 'max-content', y: 200 }"
        row-key="_rowKey"
        class="runner-table"
      />

      <Collapse :bordered="false" class="runner-sql-collapse">
        <Collapse.Panel key="sql" header="查看生成的 SQL">
          <pre class="runner-sql">{{ result.generatedSql }}</pre>
          <div class="runner-bound">
            绑定参数：{{ JSON.stringify(result.boundParams) }}
          </div>
        </Collapse.Panel>
      </Collapse>
    </div>
  </div>
</template>

<style scoped>
.sql-runner {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 8px;
}

.runner-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
}

.runner-meta {
  font-size: 12px;
  color: #8c8c8c;
}

.runner-alert {
  font-size: 12px;
}

.runner-empty {
  padding: 10px;
  border: 1px dashed #e8e8e8;
  border-radius: 6px;
  text-align: center;
  color: #8c8c8c;
  font-size: 12px;
}

.runner-result {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.runner-cols {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
  padding: 6px 8px;
  background: #fafafa;
  border: 1px solid #f0f0f0;
  border-radius: 6px;
  font-size: 12px;
}

.runner-cols-label {
  color: #8c8c8c;
  margin-right: 4px;
}

.runner-col-tag {
  cursor: pointer;
  font-family: 'Consolas', 'Monaco', monospace;
  margin: 0;
  user-select: none;
}

.runner-col-tag:hover {
  color: #1677ff;
  border-color: #1677ff;
}

.runner-table :deep(.ant-table-cell) {
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 12px;
}

.runner-sql-collapse :deep(.ant-collapse-header) {
  padding: 4px 12px !important;
  font-size: 12px;
}

.runner-sql-collapse :deep(.ant-collapse-content-box) {
  padding: 8px 12px !important;
}

.runner-sql {
  margin: 0;
  padding: 8px;
  background: #1e1e1e;
  color: #e0e0e0;
  border-radius: 4px;
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 11px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 180px;
  overflow: auto;
}

.runner-bound {
  margin-top: 6px;
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 11px;
  color: #595959;
  word-break: break-all;
}
</style>
