# JSON 一键填字段值 / 生成字段定义 - 设计方案

- 日期：2026-07-03
- 作者：benerlord
- 主题：在 6 处编辑器/面板加"从 JSON 填充/生成"按钮，一次性把 API 返回的 JSON 导入为字段值（Mode A）或字段定义（Mode B），减少逐字段复制粘贴

---

## 1. 背景与目标

### 现状痛点

- 用户为 Mock API 配置响应模板时，经常从真实 API 抓一份 JSON 返回体
- JSON 常有几十个字段，映射到画布节点属性 / 告警字段 / 字段定义时需要**逐字段复制粘贴 key 和 value**
- 全流程手工，字段一多就非常低效

### 目标

在 6 个位置加"从 JSON 一键导入"入口：

| 位置 | 模式 | 用途 |
|---|---|---|
| `NodeAttrsPanel` (画布，编辑节点) | **A · 填值** | 用 JSON 填节点属性值 |
| `NodeAttrsModal` (画布，新建节点) | **A · 填值** | 用 JSON 填新节点属性值 |
| `NodeAlarmsTab` (画布，每条告警 Collapse 内) | **A · 填值** | 用 JSON 填告警字段值 |
| `NodeTypeFieldEditor` (节点类型编辑器) | **B · 建字段** | 从 JSON 生成节点类型字段定义 |
| `EdgeTypeFieldEditor` (边类型编辑器) | **B · 建字段** | 从 JSON 生成边类型字段定义 |
| `AlarmSchemaFieldEditor` (告警模板编辑器) | **B · 建字段** | 从 JSON 生成告警模板字段定义 |

### 非目标

- 不改后端（纯前端功能）
- 不改任何 schema / 表结构 / API
- 不做"从已有 Mock 接口直接拉 JSON"入口（未来可加"从接口选择"按钮）
- 不做本次填充的撤销（不点保存即视为放弃）
- 不引入前端测试框架（保持项目现状）

---

## 2. 决策要点

| 决策 | 选项 | 结论 | 理由 |
|---|---|---|---|
| 匹配严格度 | 精确 / 宽松（三级） / 别名映射表 | **宽松** | 覆盖 90% 命名风格差异（camelCase ↔ snake_case ↔ kebab-case），无需改 schema |
| 流程 | 直接应用 / 预览确认 / 逐字段选择 | **预览确认** | 与项目现有"Excel 导入预览"一致；批量操作必需的"可见性" |
| JSON 结构 | 只顶层 / 顶层+扁平嵌套 / 顶层+智能识别 | **只顶层** | fieldKey 通常是单层单词，嵌套扁平化几乎用不上 |
| 6 处入口是否共享组件 | 各自实现 / 共享 | **共享 2 个 Modal + 1 个 utils** | Mode A/B 各自 shape 通用，代码复用最大化 |
| Mode B 遇到已存在字段 | 跳过 / 更新 / 让用户选 | **跳过** | 主场景是"新建类型时字段表空"；已存在字段用户已思考过，粘贴 JSON 覆盖误伤大 |
| Mode B 是否推 `select` 类型 | 是 / 否 | **否** | 单个 JSON 值给不出候选枚举，硬推是"看似方便实则埋坑"，让用户手工改 |
| `fieldKey` 是否规范化 | 是（剥特殊字符/驼峰化） / 否 | **否** | 破坏"所见即所得"的直觉，后端 schema 校验兜底 |

---

## 3. 架构

### 3.1 组件结构

```
frontend/src/
├── utils/
│   └── jsonFieldMatch.ts               （新增，纯函数库）
│       ├── keyMatch(jsonKey, fieldKey): boolean
│       ├── buildFillPreview(json, fields, currentValues): FillPreview
│       └── buildGeneratePreview(json, existingFields): GeneratePreview
│
└── components/
    └── shared/
        ├── JsonFillValuesModal.vue     （新增，Mode A）
        └── JsonGenerateFieldsModal.vue （新增，Mode B）
```

### 3.2 数据流

**Mode A · 填值**：

```
JSON text → parse → buildFillPreview(json, fields, currentValues)
    → FillPreview { toFill / toOverwrite / incompatible / unmatched }
    → 用户预览 & 确认
    → emit apply(values: Record<string, string>)
    → 父组件循环调各自 setter：setFieldValue(k, v)
```

**Mode B · 建字段**：

```
JSON text → parse → buildGeneratePreview(json, existingFields)
    → GeneratePreview { toCreate / skippedExisting / skippedInferable }
    → 用户预览 & 确认
    → emit apply(fields: FieldLike[])
    → 父组件 append 到 localFields，按具体字段 shape 补默认值
```

**关键设计**：`jsonFieldMatch.ts` 是纯函数，Modal 组件调它得到 preview 结构后直接渲染；工具函数用 `Pick<FieldLike, '...'>` 而非具体类型，跨 `NodeTypeFieldItem / EdgeTypeFieldItem / AlarmSchemaFieldItem` 通用。

### 3.3 兼容性

- 3 个新组件 + 6 个入口位置**增量**改动（各加一个按钮 + Modal 挂载），不动主流程
- 6 个位置未打开 JSON 功能时行为完全不变
- 无后端 / 无 schema 变化，零回归风险

---

## 4. 数据结构

### 4.1 `utils/jsonFieldMatch.ts`

```typescript
export interface FieldLike {
  fieldKey: string
  fieldLabel: string
  fieldType: 'text' | 'number' | 'select' | 'boolean' | 'array'
  maxLength?: number | null
  defaultValue?: string | null
  options?: string | null
  required: boolean
  sortOrder: number
}

export interface FillPreview {
  toFill: Array<{ fieldKey: string; fieldLabel: string; newValue: string }>
  toOverwrite: Array<{ fieldKey: string; fieldLabel: string; oldValue: string; newValue: string }>
  incompatible: Array<{ fieldKey: string; fieldLabel: string; jsonValue: unknown; reason: string }>
  unmatched: string[]  // JSON keys 里没匹配到任何字段的
}

export interface GeneratePreview {
  toCreate: FieldLike[]
  skippedExisting: string[]      // JSON keys 命中已有字段
  skippedInferable: string[]     // null / object
}

export function keyMatch(jsonKey: string, fieldKey: string): boolean
export function buildFillPreview(
  json: Record<string, unknown>,
  fields: Pick<FieldLike, 'fieldKey' | 'fieldLabel' | 'fieldType' | 'options'>[],
  currentValues: Record<string, string>,
): FillPreview
export function buildGeneratePreview(
  json: Record<string, unknown>,
  existingFields: Pick<FieldLike, 'fieldKey'>[],
): GeneratePreview
```

### 4.2 `JsonFillValuesModal` 接口

```typescript
interface Props {
  open: boolean
  fields: Pick<FieldLike, 'fieldKey' | 'fieldLabel' | 'fieldType' | 'options'>[]
  currentValues: Record<string, string>
}

const emits = defineEmits<{
  (e: 'update:open', v: boolean): void
  (e: 'apply', values: Record<string, string>): void
}>()
```

### 4.3 `JsonGenerateFieldsModal` 接口

```typescript
interface Props {
  open: boolean
  existingFields: Pick<FieldLike, 'fieldKey'>[]
  sortOrderStart: number       // 追加起始序号（父组件传 existingFields.length）
}

const emits = defineEmits<{
  (e: 'update:open', v: boolean): void
  (e: 'apply', fields: FieldLike[]): void
}>()
```

---

## 5. 匹配算法与类型规则

### 5.1 宽松匹配 `keyMatch(jsonKey, fieldKey)`

三级降级，命中任一即算匹配：

```typescript
function normalize(s: string): string {
  return s.replace(/[_\-\s]/g, '').toLowerCase()
}

function keyMatch(jsonKey: string, fieldKey: string): boolean {
  if (jsonKey === fieldKey) return true                              // 精确
  if (jsonKey.toLowerCase() === fieldKey.toLowerCase()) return true  // 忽略大小写
  return normalize(jsonKey) === normalize(fieldKey)                  // camel/snake/kebab 互通
}
```

**冲突规则**：若一个 JSON key 按宽松匹配同时命中多个 fieldKey，按"字段列表里第一个命中的"为准。

### 5.2 Mode A · 值类型转换（`buildFillPreview`）

| 字段类型 | JSON 值类型 | 处理 |
|---|---|---|
| `text` | string | 直接用 |
| `text` | number / boolean | `String(v)` |
| `text` | null | 空字符串 `''`（JSON 显式 null 视为"清空该字段"） |
| `text` | object / array | **跳过**（"类型不兼容"） |
| `number` | number | `String(v)` |
| `number` | string | 尝试 `Number(v)`，`isNaN` 则跳过 |
| `number` | 其它 | 跳过 |
| `select` | string | 检查是否在 `field.options` 里；不在则跳过 |
| `select` | 其它 | 跳过 |
| `boolean` | boolean | `String(v)` |
| `boolean` | string `'true'`/`'false'` | 原样 |
| `boolean` | 其它 | 跳过 |
| `array` | array | `JSON.stringify(v)` |
| `array` | string 且合法 JSON array | 原样 |
| `array` | 其它 | 跳过 |

**覆盖判定**：
- `currentValues[fieldKey]` 为空 → "将填充"
- `currentValues[fieldKey]` 等于新值 → "将填充"（简化 UI）
- `currentValues[fieldKey]` 不等于新值 → "将覆盖已有值"（展示旧值 → 新值）

### 5.3 Mode B · 类型推断（`buildGeneratePreview`）

对每个 JSON key，先按 5.1 查是否 `existingFields.some(f => keyMatch(jsonKey, f.fieldKey))`：
- 命中 → "已存在跳过"
- 未命中 → 按下表推断 `fieldType`，生成 `FieldLike`

| JSON 值类型 | 推断 fieldType | defaultValue | 备注 |
|---|---|---|---|
| string | `text` | 原字符串 | `maxLength = max(50, ceil((value.length + 20) / 10) * 10)`（下限 50，向上取整到 10 的倍数） |
| number | `number` | `String(v)` | — |
| boolean | `boolean` | `'true'` / `'false'` | — |
| array | `array` | `JSON.stringify(v)` | — |
| null | — | — | **跳过**（"无法推断类型"） |
| object | — | — | **跳过**（顶层限制） |

**生成的 FieldLike**：

```typescript
{
  fieldKey: jsonKey,
  fieldLabel: jsonKey,                    // 默认 = key，用户可后续在表格里改
  fieldType: <inferred>,
  maxLength: <only for text>,
  defaultValue: <as above>,
  options: null,                          // 永不推 select
  required: false,
  sortOrder: sortOrderStart + i,
}
```

**不推 select 的理由**：单个 JSON 值给不出候选枚举，硬推是"看似方便实则埋坑"。用户想改成 select 就在表格里改 fieldType 并填 options。

---

## 6. UX 流程

### 6.1 入口按钮

**Mode A** 挂载：
- `NodeAttrsPanel`：面板顶部 `<Button size="small" icon="ImportOutlined">从 JSON 填充</Button>`
- `NodeAttrsModal`：Modal 头部区域（节点类型名下方）
- `NodeAlarmsTab`：**每条 Collapse.Panel 内、Form 上方**，按钮回调闭包捕获当前 `alarm.id`，只影响那条

**Mode B** 挂载：三个字段编辑器的 `toolbar-top`（"新增字段"按钮右侧）

### 6.2 JsonFillValuesModal 布局

```
┌─────────────────────────────────────────────────────────┐
│ 从 JSON 填充字段                              [×]        │
├─────────────────────────────────────────────────────────┤
│  粘贴 JSON：                                             │
│  ┌───────────────────────────────────────────────────┐  │
│  │  {                                                │  │
│  │    "deviceName": "sw-01",                         │  │
│  │    "ipAddress": "10.0.0.1",                       │  │
│  │    "portCount": 24                                │  │
│  │  }                                                │  │
│  └───────────────────────────────────────────────────┘  │
│  [ 解析预览 ]                                            │
│                                                         │
│  ──────────  预览结果  ──────────                       │
│                                                         │
│  ✓ 将填充（2）：                                         │
│    deviceName（设备名称）  ← "sw-01"                     │
│    portCount（端口数）      ← 24                         │
│                                                         │
│  ⚠ 将覆盖已有值（1）：                                    │
│    ipAddress（IP 地址）                                  │
│      当前: "192.168.1.1"  →  新值: "10.0.0.1"           │
│                                                         │
│  ⊘ 类型不兼容跳过（0）                                    │
│                                                         │
│  ○ 未匹配的 JSON key（0）                                │
│                                                         │
├─────────────────────────────────────────────────────────┤
│                            [ 取消 ]  [ 确定填充 (3) ]    │
└─────────────────────────────────────────────────────────┘
```

**交互步骤**：
1. TextArea 粘贴 JSON（monospace、rows=8）
2. 点"解析预览" → 底部渲染四组：**将填充 / 将覆盖已有值 / 类型不兼容跳过 / 未匹配 JSON key**
3. JSON 语法错误 → 显示"解析失败：<msg>"，"确定"禁用
4. 分组为空则整个隐藏
5. 点"确定填充 (N)" → emit `apply(Record<string, string>)`，Modal 关闭

### 6.3 JsonGenerateFieldsModal 布局

```
┌─────────────────────────────────────────────────────────┐
│ 从 JSON 生成字段                              [×]        │
├─────────────────────────────────────────────────────────┤
│  粘贴 JSON：                                             │
│  ┌───────────────────────────────────────────────────┐  │
│  │  {                                                │  │
│  │    "deviceName": "sw-01",                         │  │
│  │    "portCount": 24,                               │  │
│  │    "enabled": true,                               │  │
│  │    "tags": ["core", "prod"]                       │  │
│  │  }                                                │  │
│  └───────────────────────────────────────────────────┘  │
│  [ 解析预览 ]                                            │
│                                                         │
│  ──────────  预览结果  ──────────                       │
│                                                         │
│  ✓ 将新建字段（4）：                                     │
│    ┌────────────┬────────┬────────┬──────────────┐      │
│    │ Key        │ Type   │ Label  │ Default      │      │
│    ├────────────┼────────┼────────┼──────────────┤      │
│    │ deviceName │ text   │ deviceName │ sw-01    │      │
│    │ portCount  │ number │ portCount  │ 24       │      │
│    │ enabled    │ boolean│ enabled    │ true     │      │
│    │ tags       │ array  │ tags       │ ["core",…│      │
│    └────────────┴────────┴────────┴──────────────┘      │
│                                                         │
│  ⊘ 已存在跳过（1）：ipAddress                            │
│  ⊘ 无法推断类型跳过（0）                                  │
│                                                         │
├─────────────────────────────────────────────────────────┤
│                            [ 取消 ]  [ 确定生成 (4) ]    │
└─────────────────────────────────────────────────────────┘
```

### 6.4 共通细节

- 尺寸 `width=640px`，body `max-height: calc(100vh - 200px)` + `overflow-y: auto`
- TextArea 语法错误红色提示（antd `Alert type="error"`）
- "解析预览"按钮：JSON 为空则禁用
- 关闭 Modal 时清空 TextArea 与预览状态
- 点"确定"后自动关闭

---

## 7. 六处入口集成

### 7.1 Mode A 三处

| 入口 | fields 来源 | currentValues | apply 回调 |
|---|---|---|---|
| `NodeAttrsPanel.vue` | `fields.value`（`NodeTypeFieldItem[]`） | `formData.value` | 逐 key 调 `setFieldValue(k, v)` |
| `NodeAttrsModal.vue` | `fields.value`（`NodeTypeFieldItem[]`） | `formData.value` | 逐 key 调 `setFieldValue(k, v)` |
| `NodeAlarmsTab.vue` | `schemaFields.value` | 当前那条 `alarm.attrs` | 逐 key `alarm.attrs[k] = v` + `markDirty(alarm.id)` |

告警的按钮**在每条 Collapse.Panel 内部 Form 之前**，回调闭包锁定 `alarm.id`。

### 7.2 Mode B 三处

三个字段编辑器的字段 shape 一致（`fieldKey/fieldLabel/fieldType/maxLength/defaultValue/options/required/sortOrder`），Modal emit `FieldLike[]` 后：

| 入口 | 具体字段类型 | 补默认值 |
|---|---|---|
| `NodeTypeFieldEditor.vue` | `NodeTypeFieldInput` | shape 完全一致，直接 append |
| `EdgeTypeFieldEditor.vue` | `EdgeTypeFieldInput` | shape 完全一致，直接 append |
| `AlarmSchemaFieldEditor.vue` | `AlarmSchemaFieldInput` | 可能有额外 `mapping_target` 字段，实施时 T3 具体核对，补 `null` |

统一 append 模式：

```typescript
function handleJsonGenerate(newFields: FieldLike[]) {
  emit('update:fields', [...localFields.value, ...newFields])
}
```

### 7.3 涉及文件（9 处）

| 文件 | 改动类型 |
|---|---|
| `frontend/src/utils/jsonFieldMatch.ts` | **新增** |
| `frontend/src/components/shared/JsonFillValuesModal.vue` | **新增** |
| `frontend/src/components/shared/JsonGenerateFieldsModal.vue` | **新增** |
| `frontend/src/components/canvas/NodeAttrsPanel.vue` | +按钮 + Modal + handleJsonApply |
| `frontend/src/components/canvas/NodeAttrsModal.vue` | 同上 |
| `frontend/src/components/canvas/NodeAlarmsTab.vue` | 按钮进每条 Collapse.Panel + Modal + handleJsonApply（锁 alarmId） |
| `frontend/src/components/types/NodeTypeFieldEditor.vue` | toolbar-top +按钮 + Modal + handleJsonGenerate |
| `frontend/src/components/types/EdgeTypeFieldEditor.vue` | 同上 |
| `frontend/src/components/alarmSchemas/AlarmSchemaFieldEditor.vue` | 同上 |

---

## 8. 错误处理

| 场景 | 处理 |
|---|---|
| JSON 语法错误（`JSON.parse` 抛错） | 预览区显示"解析失败：`<msg>`"（antd `Alert type="error"`），"确定"禁用 |
| JSON 顶层非对象（数组/字符串/数字/null） | 显示"JSON 顶层必须是对象 `{}`"，"确定"禁用 |
| JSON 为空对象 `{}` | 显示"未从 JSON 提取到任何字段"，"确定"禁用 |
| Mode A 所有 key 都跳过/未匹配 | 允许点"确定"（emit 空对象），toast 提示"未填充任何字段" |
| Mode B 所有 key 都被跳过 | 允许点"确定"（emit 空数组），toast "未生成任何字段" |
| 极大 JSON（>500KB） | 无特殊处理（YAGNI 不做体积限制） |
| 用户改 TextArea 未重新预览 | 预览状态过期，不自动重算；点"确定"按最后一次预览 emit |
| Modal 关闭 | `jsonText / preview / parseError` 全部清空 |
| 父组件写入失败 | 各入口 handleJsonApply 自己 try/catch；Modal 只 emit |
| Mode B 生成字段 sortOrder 冲突 | 一律 `existingFields.length + i` 追加到尾部 |
| `fieldKey` 含特殊字符（如 `$id`） | 不过滤，原样生成；后端 schema 校验兜底 |

**关键决策**：**不做客户端 `fieldKey` 规范化**。原因：破坏"所见即所得"的直觉，后端 schema 校验已能兜底。

---

## 9. 测试计划

按顺序手工验收，全绿即通过。

### 9.1 Mode A · 填值

1. **画布编辑节点填值（golden path）**：一个节点类型有 `deviceName / ipAddress / portCount / enabled` 四个字段。打开画布上一个已有节点属性面板 → 点"从 JSON 填充" → 粘贴 `{"deviceName":"sw-01","ipAddress":"10.0.0.1","portCount":24,"enabled":true}` → 点"解析预览" → 四条都进"将填充" → 点"确定填充 (4)"。预期：面板 4 个字段被写入正确值，保存落库成功。

2. **宽松匹配命中**：字段 `device_name`，JSON `{"deviceName": "sw-01"}` → 预览命中，label 显示中文名。

3. **覆盖已有值**：节点已有 `ipAddress = "1.1.1.1"`，粘贴 `{"ipAddress": "10.0.0.1"}` → 预览"将覆盖已有值"分组显示 `1.1.1.1 → 10.0.0.1`。

4. **类型不兼容跳过**：`portCount` 是 number，粘贴 `{"portCount": "not-a-number"}` → 预览"类型不兼容跳过"。

5. **未匹配 JSON key**：字段只有 `deviceName`，粘贴 `{"deviceName":"x","unknownKey":"y"}` → `unknownKey` 显示在"未匹配"分组。

6. **画布新建节点填值**：`NodeAttrsModal` 打开时点"从 JSON 填充" → 粘贴 → 确定 → 创建节点落库成功。

7. **告警字段填值（按钮在 Collapse.Panel 内）**：拓扑绑告警模板，新增一条告警 → 展开 → 点内部"从 JSON 填充" → 只影响这条 → 保存告警成功。

### 9.2 Mode B · 建字段

8. **节点类型建字段（golden path）**：新建节点类型 → 点"从 JSON 生成字段" → 粘贴 `{"deviceName":"sw-01","portCount":24,"enabled":true,"tags":["core","prod"]}` → 预览显示 4 条新建（text / number / boolean / array），Type 列推断正确 → 确定 → 字段表新增 4 行，保存类型成功。

9. **已存在跳过**：字段表已有 `deviceName` → 粘贴 `{"deviceName":"x","new_field":"y"}` → `deviceName` 进"已存在跳过"，`new_field` 进"将新建" → 确定后只新增 `new_field`。

10. **无法推断类型跳过**：粘贴 `{"foo": null, "bar": {"nested": 1}, "baz": "abc"}` → `foo` 和 `bar` 分到"无法推断类型跳过"，只有 `baz` 进"将新建"。

11. **边类型建字段**：编辑边类型 → 同 Mode B 流程 → append → 保存成功。

12. **告警模板建字段**：编辑告警模板 → 同流程 → 保存成功。

### 9.3 边缘

13. **JSON 语法错误**：粘贴 `{deviceName: sw-01}`（缺引号） → 显示"解析失败: Unexpected token ..."，"确定"禁用。

14. **JSON 顶层非对象**：粘贴 `[1,2,3]` → 显示"JSON 顶层必须是对象 {}"。

15. **空对象**：粘贴 `{}` → 显示"未从 JSON 提取到任何字段"。

16. **改 JSON 未重新预览**：粘贴 A → 预览 → 改成 B → 直接点确定 → 按 A 的预览 emit（设计里明确接受的行为）。

### 9.4 不做的自动化测试

项目当前无前端测试框架（无 vitest / jest 配置），保持一致不引入。工具函数 `jsonFieldMatch.ts` 是纯函数，日后加测试框架可先补它。

---

## 10. 影响文件清单

### 新增（3）

- `frontend/src/utils/jsonFieldMatch.ts`
- `frontend/src/components/shared/JsonFillValuesModal.vue`
- `frontend/src/components/shared/JsonGenerateFieldsModal.vue`

### 修改（6）

- `frontend/src/components/canvas/NodeAttrsPanel.vue`
- `frontend/src/components/canvas/NodeAttrsModal.vue`
- `frontend/src/components/canvas/NodeAlarmsTab.vue`
- `frontend/src/components/types/NodeTypeFieldEditor.vue`
- `frontend/src/components/types/EdgeTypeFieldEditor.vue`
- `frontend/src/components/alarmSchemas/AlarmSchemaFieldEditor.vue`

---

## 11. 未来工作（超出本次范围）

- 从已有 Mock 接口下拉选择、直接拉取该接口的样例响应 JSON
- 支持嵌套 JSON 扁平化（`a.b.c` 形式的 key 匹配）
- 支持 `select` 类型的枚举推断（如粘贴一批数组，自动从中提取候选枚举）
- 支持从 JSON Schema / OpenAPI 拉取字段定义（对应 Mode B 的高级模式）
- 用户级别别名映射表（对应 Q2 的 C 选项）
- 前端单元测试框架搭建（vitest + 覆盖 `jsonFieldMatch.ts`）
