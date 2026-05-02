<script setup lang="ts">
import { Table, Input, Switch, Button, Space, Tooltip } from 'ant-design-vue'
import { PlusOutlined, DeleteOutlined, InfoCircleOutlined } from '@ant-design/icons-vue'
import type { HeaderSpec } from '@/api/api_config'

interface Props {
  modelValue: HeaderSpec[]
}

const props = defineProps<Props>()
const emit = defineEmits<{
  (e: 'update:modelValue', v: HeaderSpec[]): void
}>()

function update(next: HeaderSpec[]) {
  emit('update:modelValue', next)
}

function addRow() {
  update([
    ...props.modelValue,
    { name: '', required: false, expectValue: '', example: '', description: '' },
  ])
}

function removeRow(index: number) {
  const next = props.modelValue.slice()
  next.splice(index, 1)
  update(next)
}

function setField<K extends keyof HeaderSpec>(
  index: number,
  key: K,
  value: HeaderSpec[K],
) {
  const next = props.modelValue.slice()
  next[index] = { ...next[index], [key]: value }
  update(next)
}

const columns = [
  { title: '名称', key: 'name', width: 180 },
  { title: '必填', key: 'required', width: 70 },
  { title: 'expectValue', key: 'expectValue', width: 200 },
  { title: '示例', key: 'example', width: 160 },
  { title: '说明', key: 'description' },
  { title: '操作', key: 'action', width: 60 },
]
</script>

<template>
  <div class="header-spec-table">
    <div class="header">
      <span class="title">
        请求头声明
        <Tooltip title="声明的字段会做必填 / expectValue 校验。HTTP 标准头（User-Agent / Accept 等）由浏览器自动注入，不做严格白名单。">
          <InfoCircleOutlined class="info-icon" />
        </Tooltip>
      </span>
      <Button size="small" @click="addRow">
        <template #icon><PlusOutlined /></template>
        新增请求头
      </Button>
    </div>

    <Table
      :data-source="modelValue"
      :columns="columns"
      :pagination="false"
      size="small"
      :row-key="(_: HeaderSpec, index?: number) => index ?? 0"
    >
      <template #bodyCell="{ column, index }">
        <template v-if="column.key === 'name'">
          <Input
            :value="modelValue[index].name"
            placeholder="例：X-Auth-Token"
            size="small"
            @update:value="(v: string) => setField(index, 'name', v)"
          />
        </template>

        <template v-else-if="column.key === 'required'">
          <Switch
            :checked="modelValue[index].required"
            size="small"
            @update:checked="(v: unknown) => setField(index, 'required', Boolean(v))"
          />
        </template>

        <template v-else-if="column.key === 'expectValue'">
          <Input
            :value="modelValue[index].expectValue ?? ''"
            placeholder="留空则不校验值"
            size="small"
            @update:value="(v: string) => setField(index, 'expectValue', v || null)"
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
          暂无声明请求头，点击右上"新增请求头"
        </span>
      </template>
    </Table>
  </div>
</template>

<style scoped>
.header-spec-table {
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
