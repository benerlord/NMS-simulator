<script setup lang="ts">
import { Table, Input, AutoComplete, Select, Switch, Button, Space, Tooltip } from 'ant-design-vue'
import { PlusOutlined, DeleteOutlined, InfoCircleOutlined } from '@ant-design/icons-vue'
import { computed } from 'vue'

export interface ParamMapping {
  name: string
  in: 'query' | 'path' | 'body'
  type: 'string' | 'int' | 'bool'
  required: boolean
  bindTo: string
}

interface Props {
  modelValue: ParamMapping[]
  availableFieldNames?: string[]
}

const props = defineProps<Props>()
const emit = defineEmits<{
  (e: 'update:modelValue', v: ParamMapping[]): void
}>()

const inOptions = [
  { label: 'query', value: 'query' },
  { label: 'path', value: 'path' },
  { label: 'body', value: 'body' },
]

const typeOptions = [
  { label: 'string', value: 'string' },
  { label: 'int', value: 'int' },
  { label: 'bool', value: 'bool' },
]

function update(next: ParamMapping[]) {
  emit('update:modelValue', next)
}

function addRow() {
  update([
    ...props.modelValue,
    { name: '', in: 'query', type: 'string', required: false, bindTo: '' },
  ])
}

function removeRow(index: number) {
  const next = props.modelValue.slice()
  next.splice(index, 1)
  update(next)
}

function setField<K extends keyof ParamMapping>(
  index: number,
  key: K,
  value: ParamMapping[K],
) {
  const next = props.modelValue.slice()
  next[index] = { ...next[index], [key]: value }
  update(next)
}

const nameOptions = computed(() =>
  (props.availableFieldNames ?? []).map((n) => ({ label: n, value: n })),
)

const columns = [
  { title: '参数名', key: 'name', width: 160 },
  { title: '位置', key: 'in', width: 100 },
  { title: '类型', key: 'type', width: 100 },
  { title: '必填', key: 'required', width: 70 },
  { title: 'SQL 绑定名 (:xxx)', key: 'bindTo', width: 180 },
  { title: '操作', key: 'action', width: 70 },
]
</script>

<template>
  <div class="param-mapping">
    <div class="header">
      <span class="title">
        参数映射
        <Tooltip :overlay-style="{ maxWidth: '420px' }">
          <template #title>
            <div class="tooltip-body">
              <div class="tooltip-heading">用途</div>
              <div>把请求里 query/path/body 字段的值绑定到 SQL 的 <code>:命名参数</code></div>
              <div class="tooltip-heading mt">字段说明</div>
              <div><code>参数名</code>：请求里的字段名（如 <code>pageNo</code>）</div>
              <div><code>位置</code>：query / path / body（path 用 <code>/api/{id}</code> 里的 <code>{id}</code>）</div>
              <div><code>类型</code>：自动转 int/bool 失败时 → 400 + 40023</div>
              <div><code>必填</code>：缺失时 → 400 + 40022</div>
              <div><code>SQL 绑定名</code>：SQL 里 <code>:xxx</code> 的 <code>xxx</code>（snake_case）</div>
              <div class="tooltip-heading mt">示例</div>
              <div>SQL：<code>WHERE topology_id = :topology_id</code></div>
              <div>映射：参数名=<code>topologyId</code>，位置=query，SQL 绑定名=<code>topology_id</code></div>
            </div>
          </template>
          <InfoCircleOutlined class="info-icon" />
        </Tooltip>
      </span>
      <Button size="small" @click="addRow">
        <template #icon><PlusOutlined /></template>
        新增参数
      </Button>
    </div>

    <Table
      :data-source="modelValue"
      :columns="columns"
      :pagination="false"
      size="small"
      :row-key="(_: ParamMapping, index?: number) => index ?? 0"
    >
      <template #bodyCell="{ column, index }">
        <template v-if="column.key === 'name'">
          <AutoComplete
            :value="modelValue[index].name"
            :options="nameOptions"
            placeholder="选择或输入参数名"
            size="small"
            style="width: 100%"
            @update:value="(v: unknown) => setField(index, 'name', String(v ?? ''))"
          />
        </template>

        <template v-else-if="column.key === 'in'">
          <Select
            :value="modelValue[index].in"
            :options="inOptions"
            size="small"
            style="width: 100%"
            @update:value="(v: unknown) => setField(index, 'in', v as ParamMapping['in'])"
          />
        </template>

        <template v-else-if="column.key === 'type'">
          <Select
            :value="modelValue[index].type"
            :options="typeOptions"
            size="small"
            style="width: 100%"
            @update:value="(v: unknown) => setField(index, 'type', v as ParamMapping['type'])"
          />
        </template>

        <template v-else-if="column.key === 'required'">
          <Switch
            :checked="modelValue[index].required"
            size="small"
            @update:checked="(v: unknown) => setField(index, 'required', Boolean(v))"
          />
        </template>

        <template v-else-if="column.key === 'bindTo'">
          <AutoComplete
            :value="modelValue[index].bindTo"
            :options="nameOptions"
            :placeholder="availableFieldNames?.length ? '选择或输入列名（snake_case）' : '请先运行 SQL 测试以获取列名'"
            size="small"
            style="width: 100%"
            @update:value="(v: unknown) => setField(index, 'bindTo', String(v ?? ''))"
          />
        </template>

        <template v-else-if="column.key === 'action'">
          <Space>
            <a style="color: #ff4d4f" @click="removeRow(index)">
              <DeleteOutlined />
            </a>
          </Space>
        </template>
      </template>

      <template #emptyText>
        <span style="color: #999; font-size: 12px">暂无参数，点击右上"新增参数"</span>
      </template>
    </Table>
  </div>
</template>

<style scoped>
.param-mapping {
  border: 1px solid #f0f0f0;
  border-radius: 6px;
  padding: 12px;
  background: #fafafa;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
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
</style>

<style>
/* Tooltip content 通过 Teleport 渲染到 body，scoped 样式无法穿透 */
.tooltip-body {
  font-size: 12px;
  line-height: 1.6;
}
.tooltip-body .tooltip-heading {
  font-weight: 500;
  margin-bottom: 4px;
}
.tooltip-body .tooltip-heading.mt {
  margin-top: 6px;
}
.tooltip-body code {
  background: rgba(255, 255, 255, 0.16);
  padding: 0 4px;
  border-radius: 2px;
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 11px;
}
</style>
