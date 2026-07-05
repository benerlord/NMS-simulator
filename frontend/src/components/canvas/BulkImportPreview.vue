<script setup lang="ts">
import { computed } from 'vue'
import { Alert, Collapse, Table, Tag, Tooltip } from 'ant-design-vue'
import type { BulkPreview } from '@/utils/jsonBulkNodes'

interface Props {
  preview: BulkPreview
}
const props = defineProps<Props>()

const validColumns = [
  { title: '#', dataIndex: 'index', width: 60 },
  { title: 'Name', dataIndex: 'name', width: 160 },
  { title: 'X', dataIndex: 'x', width: 70 },
  { title: 'Y', dataIndex: 'y', width: 70 },
  { title: 'attrs 摘要', key: 'attrsSummary' },
  { title: '警告', key: 'warnings', width: 100 },
]

const skippedColumns = [
  { title: '#', dataIndex: 'index', width: 60 },
  { title: 'Name', dataIndex: 'name', width: 160 },
  { title: '理由', dataIndex: 'reason' },
]

const dupColumns = [
  { title: '#', dataIndex: 'index', width: 60 },
  { title: 'Name', dataIndex: 'name' },
]

const activeKey = computed(() => {
  const keys: string[] = []
  if (props.preview.valid.length > 0) keys.push('valid')
  if (props.preview.skipped.length > 0) keys.push('skipped')
  if (props.preview.duplicatesInBatch.length > 0) keys.push('dup')
  return keys
})

function attrsSummary(attrs: Record<string, string>): string {
  const entries = Object.entries(attrs)
  if (entries.length === 0) return '-'
  const short = entries.slice(0, 3).map(([k, v]) => `${k}=${v}`).join(', ')
  return entries.length > 3 ? `${short}, ...(${entries.length - 3})` : short
}
</script>

<template>
  <div class="bulk-preview">
    <Alert
      v-if="preview.unmatchedKeys.length > 0"
      type="info"
      show-icon
      style="margin-bottom: 12px"
    >
      <template #message>
        JSON 中以下 key 未在字段定义里，将被忽略：
        <Tag v-for="k in preview.unmatchedKeys" :key="k">{{ k }}</Tag>
      </template>
    </Alert>

    <Collapse :active-key="activeKey" :bordered="false">
      <Collapse.Panel key="valid" :header="`✅ 将导入 (${preview.valid.length})`">
        <Table
          :columns="validColumns"
          :data-source="preview.valid"
          :pagination="false"
          size="small"
          :row-key="(r: any) => `v-${r.index}`"
          :scroll="{ y: 240 }"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'attrsSummary'">
              <span class="attrs-summary">{{ attrsSummary(record.attrs) }}</span>
            </template>
            <template v-else-if="column.key === 'warnings'">
              <Tooltip v-if="record.warnings.length > 0" :title="record.warnings.join(', ')">
                <Tag color="orange">{{ record.warnings.length }} 字段跳过</Tag>
              </Tooltip>
              <span v-else>-</span>
            </template>
          </template>
        </Table>
      </Collapse.Panel>

      <Collapse.Panel
        v-if="preview.skipped.length > 0"
        key="skipped"
        :header="`⏭️ 将跳过 (${preview.skipped.length})`"
      >
        <Table
          :columns="skippedColumns"
          :data-source="preview.skipped"
          :pagination="false"
          size="small"
          :row-key="(r: any) => `s-${r.index}`"
          :scroll="{ y: 240 }"
        />
      </Collapse.Panel>

      <Collapse.Panel
        v-if="preview.duplicatesInBatch.length > 0"
        key="dup"
        :header="`⚠️ 批次内重名 (${preview.duplicatesInBatch.length})`"
      >
        <Table
          :columns="dupColumns"
          :data-source="preview.duplicatesInBatch"
          :pagination="false"
          size="small"
          :row-key="(r: any) => `d-${r.index}`"
          :scroll="{ y: 240 }"
        />
      </Collapse.Panel>
    </Collapse>
  </div>
</template>

<style scoped>
.bulk-preview { padding: 4px 0; }
.attrs-summary {
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 11px;
  color: #666;
}
</style>
