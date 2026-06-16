# 字段类型新增 `array` — 设计文档

- **日期**：2026-06-16
- **范围**：系统级新增第 5 种字段类型 `array`，覆盖节点类型 / 边类型 / 告警模板的字段定义，画布上的节点/边/告警属性编辑器，以及 Excel 导入导出
- **不在范围**：JSON 批量填充功能（Spec 2，依赖本 spec）；对齐 bug（与 Spec 2 一起）；元素类型同质性约束；array 项拖拽排序

## 1. 背景与动机

当前字段类型只支持 `text / number / select / boolean`。网管接口文档常返回 array 类型字段（如 `ports: [1,2,3]`、`tags: ["a","b"]`、`subnets: ["10.0.0.0/24"]`）。用户需要：

1. 在节点类型 / 边类型 / 告警模板里定义这种字段
2. 在画布上编辑、查看 array 字段的值
3. Excel 导入导出包含 array 字段的类型定义
4. 为后续 Spec 2（JSON 粘贴 → 自动填表）提供目标字段类型

## 2. 决策汇总

| # | 决策 | 选择 | 理由 |
|---|------|------|------|
| Q1 | 编辑器 UI | **D** JSON textarea + 实时 parse 校验 | 与 Spec 2 JSON 粘贴格式一致；保留 JSON 完整表达能力；用户群体（网管/测试）技术水平足够 |
| Q2 | 必填 + 空数组 `[]` | **B** `[]` 算"已填" | 网管 API `ports: []` 是合法"无内容"语义；尊重用户意图 |
| Q3 | Excel 序列化 | **A** JSON 原文写入单元格 | 与编辑器格式一致；无信息丢失 |

## 3. 后端改动

### 3.1 Pydantic schema pattern 扩展（7 处）

| 文件 | 类 | 行 | 改动 |
|---|---|---|---|
| `schemas/node_type.py` | `NodeTypeFieldInput.field_type` | 18 | pattern 加 `\|array` |
| `schemas/node_type.py` | `NodeTypeFieldCreate.field_type`（legacy） | 65 | 同上 |
| `schemas/node_type.py` | `NodeTypeFieldUpdate.field_type`（legacy） | 85 | 同上 |
| `schemas/node_type.py` | `EdgeTypeFieldInput.field_type` | 183 | 同上 |
| `schemas/node_type.py` | `EdgeTypeFieldCreate.field_type`（legacy） | 233 | 同上 |
| `schemas/node_type.py` | `EdgeTypeFieldUpdate.field_type`（legacy） | 253 | 同上 |
| `schemas/alarm.py` | `AlarmSchemaFieldInput.field_type` | 14 | 同上 |

最终 pattern：`^(text|number|select|boolean|array)$`

### 3.2 新增 `validate_array_default` validator

当 `field_type == 'array'` 且 `default_value` 不为空时，校验是合法 JSON array：

```python
@model_validator(mode='after')
def validate_array_default(self) -> 'NodeTypeFieldInput':
    if self.field_type != 'array' or not self.default_value:
        return self
    try:
        import json
        v = json.loads(self.default_value)
    except json.JSONDecodeError:
        raise ValueError('array 类型的 default_value 必须是合法 JSON')
    if not isinstance(v, list):
        raise ValueError('array 类型的 default_value 必须是 JSON array')
    return self
```

加到所有 7 个 input/create/update schema（Node + Edge + AlarmSchema）。

### 3.3 max_length 校验逻辑

现有 `validate_max_length_for_text` 只对 `field_type == 'text'` 强制 max_length。array 自动落入"不要求 max_length"分支，无需改 validator。

### 3.4 存储格式

- `node_attrs.value` / `edge_attrs.value` 列保持 TEXT 类型
- array 字段的 value 存 JSON.stringify 后的字符串（如 `"[1,2,3]"`）
- 不改 DB schema、不加新列、不写迁移

### 3.5 节点/边 set_attrs 接口

- 现有 `set_node_attrs(node_id, attrs: list[NodeAttrSet])`，body 是 `[{fieldKey, value: str}]`
- value 现在已是 string —— array 字段把 JSON 字符串放在 value 即可
- **不**在后端 set_attrs 时额外校验 array 类型，保持 K-V 接口类型无关
- 前端 ArrayJsonInput 组件 + Pydantic 的 default_value 校验已足够防御

### 3.6 Excel 导入导出

**导出（`_build_node_types_excel` 等）：**

- "字段类型"列写 `'array'` 字符串
- "默认值"列写原 JSON 字符串（如 `'["a","b"]'`）
- **不**显式设置 `cell.number_format='@'`，依赖 openpyxl 默认行为（字符串以 `[1,2]` 写入会被识别为字符串，因为有方括号）
- 若测试发现 `[123]` 被识别为数字，再加 `cell.number_format='@'`

**导入（`_import_node_types_xlsx` 等）：**

- 读取"默认值"单元格内容（已是 str） → 不做特殊处理
- 字段类型为 `'array'` 时由 Pydantic `validate_array_default` 把关
- 校验失败 → 当前 import 流程已捕获 `ValueError` 加入 errors 列表 + 跳过该行

### 3.7 不动

- DB schema 不变
- 节点/边 CRUD 端点逻辑不变
- 整批同步 `_sync_node_type_fields` / `_sync_edge_type_fields` 不变（只是接受新枚举值）
- 现有 4 种 fieldType 行为完全不变

## 4. 前端 — 类型管理 3 处字段编辑器

### 4.1 TS 类型联合扩展（4 处）

`frontend/src/api/types.ts`：

```ts
fieldType: 'text' | 'number' | 'select' | 'boolean' | 'array'
```

涉及：
- `NodeTypeFieldItem.fieldType`
- `NodeTypeFieldInput.fieldType`
- `EdgeTypeFieldItem.fieldType`
- `EdgeTypeFieldInput.fieldType`

`frontend/src/api/alarmSchema.ts`：同步扩展 `AlarmSchemaField*` 的 fieldType 联合。

### 4.2 字段类型 Select 选项扩展（3 处）

`NodeTypeFieldEditor.vue` / `EdgeTypeFieldEditor.vue` / `AlarmSchemaFieldEditor.vue` 都加：

```vue
<Select.Option value="array">array</Select.Option>
```

### 4.3 列禁用规则（无需改代码）

| 列 | text | number | select | boolean | **array** |
|---|---|---|---|---|---|
| MaxLen | ✓ | 禁 | 禁 | 禁 | **禁** |
| Default | ✓ | ✓ | ✓ | ✓ | ✓ |
| Options | 禁 | 禁 | ✓ | 禁 | **禁** |
| Required | ✓ | ✓ | ✓ | ✓ | ✓ |

现有 `:disabled="record.fieldType !== 'text'"` 等写法已让 array 自动落入禁用分支，无需改。

### 4.4 Default 列对 array 的提示

Default 列保持 `<Input>`，但 fieldType=array 时：
- placeholder 改为 `'JSON: ["a","b"]'`
- 失焦时 JSON.parse 校验：非合法 array → `message.warning('默认值必须是 JSON array')`
- **不**阻止保存（后端 `validate_array_default` 兜底）

### 4.5 类型管理表格的 fieldType Tag 显示

NodeTypeTable / EdgeTypeTable 的"字段类型"列用 `<a-tag>` 显示。array 复用默认色，不专门配色。

### 4.6 不动

- field_key 不可变约束、↑↓ 排序、删除、Affix 工具栏全部不变
- 类型管理列表的搜索/分类/批量操作不变
- 三个编辑器结构与告警模板编辑器（V2 紧凑表格）保持一致

## 5. 前端 — 画布属性编辑器对 array 的支持

### 5.1 涉及组件

- `NodeAttrsModal.vue`（创建节点弹窗）
- `NodeAttrsPanel.vue`（编辑节点抽屉的"属性" Tab）
- `EdgeAttrsPanel.vue`（编辑边属性抽屉）
- `NodeAlarmsTab.vue`（编辑节点抽屉的"告警" Tab 内的告警卡片）

### 5.2 新增组件 `ArrayJsonInput.vue`

`frontend/src/components/canvas/ArrayJsonInput.vue`：

```vue
<script setup lang="ts">
import { computed } from 'vue'
import { Input } from 'ant-design-vue'

const props = defineProps<{
  value: string  // JSON string，例如 '["a","b"]' 或 '' 或 '[]'
  placeholder?: string
}>()

const emit = defineEmits<{
  (e: 'update:value', v: string): void
}>()

const parseError = computed(() => {
  const v = props.value
  if (!v) return ''  // 空串算"未填"，由 required 校验处理
  try {
    const parsed = JSON.parse(v)
    if (!Array.isArray(parsed)) return '必须是 JSON array（如 ["a","b"]）'
    return ''
  } catch {
    return 'JSON 语法错误'
  }
})

function handleInput(e: Event) {
  emit('update:value', (e.target as HTMLTextAreaElement).value)
}
</script>

<template>
  <div class="array-json-input">
    <Input.TextArea
      :value="value"
      :placeholder="placeholder"
      :auto-size="{ minRows: 2, maxRows: 6 }"
      :status="parseError ? 'error' : undefined"
      @input="handleInput"
    />
    <div v-if="parseError" class="error-hint">{{ parseError }}</div>
  </div>
</template>

<style scoped>
.array-json-input { display: flex; flex-direction: column; gap: 2px; }
.error-hint { font-size: 12px; color: #ff4d4f; }
</style>
```

要点：
- Antd `Input.TextArea` + `auto-size: { minRows: 2, maxRows: 6 }` 自适应高度
- 实时 parse 校验，错误时显示红边 + 错误文案
- **不**阻止用户保存，保存时由表单整体校验 + 后端兜底
- 接口与现有 Input 控件一致（`value` prop + `update:value` emit）

### 5.3 4 个组件加 array 渲染分支

`NodeAttrsModal.vue` / `NodeAttrsPanel.vue` / `EdgeAttrsPanel.vue` / `NodeAlarmsTab.vue` 都在 fieldType 分支末尾加：

```vue
<template v-else-if="field.fieldType === 'array'">
  <ArrayJsonInput
    :value="getFieldValue(field.fieldKey)"
    @update:value="(v: string) => setFieldValue(field.fieldKey, v)"
    :placeholder="field.defaultValue || '[]'"
  />
</template>
```

import 加 `import ArrayJsonInput from './ArrayJsonInput.vue'`（AlarmsTab 路径相对调整）。

### 5.4 表单整体校验逻辑增强

抽 helper 到 `frontend/src/utils/fieldValidation.ts`：

```ts
import type { NodeTypeFieldItem } from '@/api/types'

export function validateFields(
  fields: NodeTypeFieldItem[],
  formData: Record<string, string>,
): Record<string, string> {
  const errs: Record<string, string> = {}
  for (const field of fields) {
    const value = formData[field.fieldKey] ?? ''
    if (field.required && !value) {
      errs[field.fieldKey] = '此字段为必填项'
      continue
    }
    if (field.fieldType === 'array' && value) {
      try {
        const parsed = JSON.parse(value)
        if (!Array.isArray(parsed)) errs[field.fieldKey] = '必须是 JSON array'
      } catch {
        errs[field.fieldKey] = 'JSON 语法错误'
      }
    }
  }
  return errs
}
```

`NodeAttrsModal.handleCreate` / `NodeAttrsPanel.handleSave` / `EdgeAttrsPanel.handleSave` / `NodeAlarmsTab` 的校验逻辑都改用这个 helper。

### 5.5 创建节点 Modal 的默认值应用

现有 watch 块：
```ts
for (const field of fields.value) {
  if (field.defaultValue) {
    formData.value[field.fieldKey] = field.defaultValue
  }
}
```

array 的 default_value 也是 JSON 字符串，直接塞进 formData，textarea 自然显示原文。无需改。

### 5.6 不动

- 抽屉宽度（保持 380px）
- Modal 宽度 + 双列网格（保持 720px / a-col :md=12）
- array 字段在双列中占一格
- 告警 Tab 整体结构、节点名称行、底部按钮固定
- 节点/边 set_attrs 调用方式

## 6. 测试

### 6.1 后端 pytest（`backend/tests/test_array_field_type.py`）

| 用例 | 覆盖 |
|---|---|
| `test_create_node_type_with_array_field` | POST 类型含 `fieldType="array"` → 落库 |
| `test_create_with_array_default_value_valid` | `defaultValue='["a","b"]'` → 成功 |
| `test_create_with_array_default_value_invalid_not_list` | `defaultValue='"abc"'` → 422 |
| `test_create_with_array_default_value_invalid_json` | `defaultValue='[1,2'` → 422 |
| `test_create_with_array_default_value_empty_array` | `defaultValue='[]'` → 成功 |
| `test_create_with_array_default_value_null` | `defaultValue=None` → 成功 |
| `test_array_field_pattern_accepted` | `fieldType='array'` 通过 pattern |
| `test_set_attrs_with_json_array_string` | PUT attrs `value='["a","b"]'` → GET 一致 |
| `test_update_node_type_change_field_type_to_array` | 改字段类型为 array → 成功 |
| `test_edge_type_array_field_symmetric` | 边类型对称用例 |
| `test_alarm_schema_array_field` | 告警模板对称用例 |
| `test_excel_export_array_field_default_preserved` | 导出 → 默认值 JSON 保留 |
| `test_excel_import_array_field_default_parsed` | 导入 → 默认值落库 |
| `test_excel_import_array_invalid_default_rejected` | 导入非法 array → 错误信息收集 |

### 6.2 前端 smoke 测试（人工）

1. 类型管理 → 新建节点类型 → 字段类型下拉新增 `array` 选项
2. 选 array → MaxLen / Options 列变灰；Default 列 placeholder = `'JSON: ["a","b"]'`
3. Default 列输入 `"abc"` 离焦 → toast 警告
4. Default 列输入 `["x","y"]` 离焦 → 无警告
5. 保存类型 → 列表"字段数"+1
6. 边类型 + 告警模板 Tab 重复 1-5
7. 画布拖含 array 字段的节点类型 → 创建节点 Modal 中 array 字段渲染为 textarea
8. textarea 自适应 2 行起，超 6 行内部滚动
9. 输入 `[1,2` → 红边 + "JSON 语法错误"
10. 输入 `"abc"` → 红边 + "必须是 JSON array"
11. 输入 `["a","b"]` → 无错误
12. 必填 array 字段未填 → 点创建 → 红色提示 + 滚动定位
13. 必填 array 填 `[]` → 创建成功
14. 双击节点 → 抽屉 array 字段显示原 JSON
15. 抽屉编辑 array → 保存 → 重开 → 持久化
16. 边属性面板 array 字段同款渲染
17. 告警卡片 array 字段同款渲染

## 7. 文件清单

### 后端

- `backend/app/admin/schemas/node_type.py` — 6 处 pattern + 6 处新增 `validate_array_default`
- `backend/app/admin/schemas/alarm.py` — 1 处 pattern + 1 处新增 validator
- `backend/tests/test_array_field_type.py`（新）

### 前端

- `frontend/src/api/types.ts` — 4 处 fieldType 联合扩展
- `frontend/src/api/alarmSchema.ts` — fieldType 联合扩展
- `frontend/src/components/types/NodeTypeFieldEditor.vue` — Select 加 array + Default 失焦校验
- `frontend/src/components/types/EdgeTypeFieldEditor.vue` — 同上
- `frontend/src/components/alarmSchemas/AlarmSchemaFieldEditor.vue` — 同上
- `frontend/src/components/canvas/ArrayJsonInput.vue`（新）
- `frontend/src/components/canvas/NodeAttrsModal.vue` — array 分支 + 用 `validateFields` helper
- `frontend/src/components/canvas/NodeAttrsPanel.vue` — array 分支 + helper
- `frontend/src/components/canvas/EdgeAttrsPanel.vue` — array 分支 + helper
- `frontend/src/components/canvas/NodeAlarmsTab.vue` — array 分支
- `frontend/src/utils/fieldValidation.ts`（新）

## 8. 风险

| 风险 | 缓解 |
|---|---|
| Excel cell `[123]` 被 openpyxl 识别为数字 | 加测试覆盖；必要时 `cell.number_format = '@'` 强制文本 |
| 用户给 array 字段填超长 JSON | `node_attrs.value` TEXT 无长度限制；前端 textarea 限 6 行内部滚动 |
| 旧数据迁移 | 不需要 — array 是新增类型，旧字段不动 |
| 旧 Excel 文件导入 | 旧文件无 array 字段，行为不变 |
| `ArrayJsonInput` 事件签名一致性 | 组件内适配，对外暴露 `value` + `update:value`，与现有 Input 一致 |
| 4 个组件的校验逻辑重复 | 抽 `validateFields` 到 `utils/fieldValidation.ts` |

## 9. 兼容性

- DB schema 不变
- 现有 4 种 fieldType 行为完全不变
- 旧节点类型 + 旧节点 attrs 不受影响
- Excel 导入导出格式向后兼容（旧文件读取行为不变）
- 节点/边 set_attrs API 不变

## 10. 不在范围内

- JSON 批量填充（Spec 2，依赖本 spec）
- NodeAttrsModal/Panel 的对齐 bug（Spec 2 一并修复）
- array 元素类型同质性约束（YAGNI）
- array 项拖拽排序（D 模式编辑器里手动调）
- 嵌套数组/对象的特殊渲染（一律按 JSON 文本编辑）
- 跨语言/i18n 错误信息
