<script setup lang="ts">
import { Table, Input, Select, Switch, Button, Space, Tooltip } from 'ant-design-vue'
import { PlusOutlined, DeleteOutlined, InfoCircleOutlined } from '@ant-design/icons-vue'
import type { QueryParamType, QuerySpec } from '@/api/api_config'

interface Props {
  modelValue: QuerySpec[]
}

const props = defineProps<Props>()
const emit = defineEmits<{
  (e: 'update:modelValue', v: QuerySpec[]): void
}>()

const typeOptions: { label: string; value: QueryParamType }[] = [
  { label: 'string', value: 'string' },
  { label: 'int', value: 'int' },
  { label: 'bool', value: 'bool' },
]

function update(next: QuerySpec[]) {
  emit('update:modelValue', next)
}

function addRow() {
  update([
    ...props.modelValue,
    { name: '', type: 'string', required: false, example: '', description: '' },
  ])
}

function removeRow(index: number) {
  const next = props.modelValue.slice()
  next.splice(index, 1)
  update(next)
}

function setField<K extends keyof QuerySpec>(
  index: number,
  key: K,
  value: QuerySpec[K],
) {
  const next = props.modelValue.slice()
  next[index] = { ...next[index], [key]: value }
  update(next)
}

const columns = [
  { title: '参数名', key: 'name', width: 180 },
  { title: '类型', key: 'type', width: 100 },
  { title: '必填', key: 'required', width: 70 },
  { title: '示例', key: 'example', width: 160 },
  { title: '说明', key: 'description' },
  { title: '操作', key: 'action', width: 60 },
]
</script>

<template>
  <div class="query-spec-table">
    <div class="header">
      <span class="title">
        Query 参数声明
        <Tooltip title="严格白名单：只要本表存在（哪怕空），调用方传入未声明字段就会被 400 拒绝（错误码 40025）。如要允许任意 query，移除整段声明。">
          <InfoCircleOutlined class="info-icon" />
        </Tooltip>
      </span>
      <Button size="small" @click="addRow">
        <template #icon><PlusOutlined /></template>
        新增 Query 参数
      </Button>
    </div>

    <Table
      :data-source="modelValue"
      :columns="columns"
      :pagination="false"
      size="small"
      :row-key="(_: QuerySpec, index?: number) => index ?? 0"
    >
      <template #bodyCell="{ column, index }">
        <template v-if="column.key === 'name'">
          <Input
            :value="modelValue[index].name"
            placeholder="例：topologyId"
            size="small"
            @update:value="(v: string) => setField(index, 'name', v)"
          />
        </template>

        <template v-else-if="column.key === 'type'">
          <Select
            :value="modelValue[index].type"
            :options="typeOptions"
            size="small"
            style="width: 100%"
            @update:value="(v: unknown) => setField(index, 'type', v as QueryParamType)"
          />
        </template>

        <template v-else-if="column.key === 'required'">
          <Switch
            :checked="modelValue[index].required"
            size="small"
            @update:checked="(v: unknown) => setField(index, 'required', Boolean(v))"
          />
        </template>

        <template v-else-if="column.key === 'example'">
          <Input
            :value="modelValue[index].example ?? ''"
            placeholder="文档示例"
            size="small"
            @update:value="(v: string) => setField(index, 'example', v || null)"
          />
        </template>

        <template v-else-if="column.key === 'description'">
          <Input
            :value="modelValue[index].description ?? ''"
            placeholder="字段说明"
            size="small"
            @update:value="(v: string) => setField(index, 'description', v || null)"
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
        <span style="color: #999; font-size: 12px">
          暂无声明 query 参数，点击右上"新增 Query 参数"
        </span>
      </template>
    </Table>
  </div>
</template>

<style scoped>
.query-spec-table {
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
