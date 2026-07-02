# JSON 一键填字段值 / 生成字段定义 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 6 处编辑器/面板加"从 JSON 填充/生成"按钮，一次性把 API 返回 JSON 导入为字段值（Mode A · 3 处）或字段定义（Mode B · 3 处），减少逐字段复制粘贴。

**Architecture:** 3 个新前端模块（1 个纯函数库 + 2 个 Modal）+ 6 个入口位置的增量集成。零后端改动、零 schema 变更。工具函数用 `Pick<FieldLike, ...>` 参数、跨 `NodeType/EdgeType/AlarmSchema` 三种字段类型天然通用。

**Tech Stack:** Vue 3.5 `<script setup>` + Ant Design Vue 4（`Modal + Alert + Textarea + Table + Tag + Button + Empty`）+ TypeScript。**无测试框架**（保持项目现状），验证靠 `npx tsc --noEmit` + 手工验收。

**Spec：** `docs/superpowers/specs/2026-07-03-json-to-node-fields-design.md`

---

## File Structure

| 文件 | Task | 责任 |
|------|------|------|
| `frontend/src/utils/jsonFieldMatch.ts` | T1 | 纯函数：keyMatch + buildFillPreview + buildGeneratePreview + 类型定义 |
| `frontend/src/components/shared/JsonFillValuesModal.vue` | T2 | Mode A · 弹窗（TextArea + 预览分组 + emit apply） |
| `frontend/src/components/shared/JsonGenerateFieldsModal.vue` | T3 | Mode B · 弹窗（TextArea + 预览分组 + Table + emit apply） |
| `frontend/src/components/canvas/NodeAttrsPanel.vue` | T4 | Mode A 入口按钮 + Modal 挂载 |
| `frontend/src/components/canvas/NodeAttrsModal.vue` | T4 | Mode A 入口按钮 + Modal 挂载 |
| `frontend/src/components/canvas/NodeAlarmsTab.vue` | T5 | Mode A 入口按钮（每条 Collapse.Panel 内） + Modal 挂载（锁 alarmId） |
| `frontend/src/components/types/NodeTypeFieldEditor.vue` | T6 | Mode B 入口按钮 + Modal 挂载 |
| `frontend/src/components/types/EdgeTypeFieldEditor.vue` | T6 | Mode B 入口按钮 + Modal 挂载 |
| `frontend/src/components/alarmSchemas/AlarmSchemaFieldEditor.vue` | T6 | Mode B 入口按钮 + Modal 挂载 |

---

## 工作环境约定

- 主仓直接工作：`C:/Users/benerlord/Desktop/InterfaceTest`（不开 worktree）
- 分支：`main`
- 前端 smoke test：`cd /c/Users/benerlord/Desktop/InterfaceTest/frontend && npx tsc --noEmit` — 必须 exit 0
- 每个 Task 完成后 commit；commit message 用 Conventional Commits 中文说明
- 每次 commit 尾部保留 `Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>`
- 该项目**无前端测试框架**（无 vitest / jest 配置），本次不引入。所有工具函数正确性靠"用 node 直接跑一个内联脚本 assert"进行 smoke 验证

---

## Task 1: 核心工具库 `utils/jsonFieldMatch.ts`

**Files:**
- Create: `frontend/src/utils/jsonFieldMatch.ts`

- [ ] **Step 1: 创建工具库文件（含全部三个纯函数 + 类型定义）**

用下面的内容创建 `frontend/src/utils/jsonFieldMatch.ts`：

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
  unmatched: string[]
}

export interface GeneratePreview {
  toCreate: FieldLike[]
  skippedExisting: string[]
  skippedInferable: string[]
}

function normalize(s: string): string {
  return s.replace(/[_\-\s]/g, '').toLowerCase()
}

export function keyMatch(jsonKey: string, fieldKey: string): boolean {
  if (jsonKey === fieldKey) return true
  if (jsonKey.toLowerCase() === fieldKey.toLowerCase()) return true
  return normalize(jsonKey) === normalize(fieldKey)
}

type MatchableField = Pick<FieldLike, 'fieldKey' | 'fieldLabel' | 'fieldType' | 'options'>

function coerceValue(
  jsonValue: unknown,
  fieldType: FieldLike['fieldType'],
  options: string | null | undefined,
): { ok: true; value: string } | { ok: false; reason: string } {
  if (fieldType === 'text') {
    if (jsonValue === null) return { ok: true, value: '' }
    if (typeof jsonValue === 'string') return { ok: true, value: jsonValue }
    if (typeof jsonValue === 'number' || typeof jsonValue === 'boolean') {
      return { ok: true, value: String(jsonValue) }
    }
    return { ok: false, reason: 'text 字段不支持 object/array 值' }
  }
  if (fieldType === 'number') {
    if (typeof jsonValue === 'number') return { ok: true, value: String(jsonValue) }
    if (typeof jsonValue === 'string') {
      const n = Number(jsonValue)
      if (Number.isNaN(n)) return { ok: false, reason: '值无法解析为数字' }
      return { ok: true, value: jsonValue }
    }
    return { ok: false, reason: 'number 字段值必须是数字或数字字符串' }
  }
  if (fieldType === 'select') {
    if (typeof jsonValue !== 'string') return { ok: false, reason: 'select 字段值必须是字符串' }
    const opts = (options || '').split(',').map((s) => s.trim()).filter(Boolean)
    if (!opts.includes(jsonValue)) return { ok: false, reason: `值不在选项列表 [${opts.join(', ')}] 中` }
    return { ok: true, value: jsonValue }
  }
  if (fieldType === 'boolean') {
    if (typeof jsonValue === 'boolean') return { ok: true, value: String(jsonValue) }
    if (jsonValue === 'true' || jsonValue === 'false') return { ok: true, value: jsonValue }
    return { ok: false, reason: 'boolean 字段值必须是 true/false' }
  }
  if (fieldType === 'array') {
    if (Array.isArray(jsonValue)) return { ok: true, value: JSON.stringify(jsonValue) }
    if (typeof jsonValue === 'string') {
      try {
        const p = JSON.parse(jsonValue)
        if (Array.isArray(p)) return { ok: true, value: jsonValue }
      } catch { /* ignore */ }
      return { ok: false, reason: '值不是合法的 JSON array 字符串' }
    }
    return { ok: false, reason: 'array 字段值必须是数组' }
  }
  return { ok: false, reason: `未知字段类型 ${fieldType}` }
}

export function buildFillPreview(
  json: Record<string, unknown>,
  fields: MatchableField[],
  currentValues: Record<string, string>,
): FillPreview {
  const result: FillPreview = { toFill: [], toOverwrite: [], incompatible: [], unmatched: [] }

  for (const [jsonKey, jsonValue] of Object.entries(json)) {
    const matched = fields.find((f) => keyMatch(jsonKey, f.fieldKey))
    if (!matched) {
      result.unmatched.push(jsonKey)
      continue
    }
    const coerced = coerceValue(jsonValue, matched.fieldType, matched.options)
    if (!coerced.ok) {
      result.incompatible.push({
        fieldKey: matched.fieldKey,
        fieldLabel: matched.fieldLabel,
        jsonValue,
        reason: coerced.reason,
      })
      continue
    }
    const current = currentValues[matched.fieldKey] ?? ''
    if (current === '' || current === coerced.value) {
      result.toFill.push({
        fieldKey: matched.fieldKey,
        fieldLabel: matched.fieldLabel,
        newValue: coerced.value,
      })
    } else {
      result.toOverwrite.push({
        fieldKey: matched.fieldKey,
        fieldLabel: matched.fieldLabel,
        oldValue: current,
        newValue: coerced.value,
      })
    }
  }
  return result
}

function inferField(jsonKey: string, jsonValue: unknown, sortOrder: number):
  | { ok: true; field: FieldLike }
  | { ok: false; reason: string } {
  if (jsonValue === null) return { ok: false, reason: 'null 无法推断类型' }
  if (typeof jsonValue === 'object' && !Array.isArray(jsonValue)) {
    return { ok: false, reason: '嵌套 object 不支持' }
  }
  if (typeof jsonValue === 'string') {
    const maxLength = Math.max(50, Math.ceil((jsonValue.length + 20) / 10) * 10)
    return {
      ok: true,
      field: {
        fieldKey: jsonKey,
        fieldLabel: jsonKey,
        fieldType: 'text',
        maxLength,
        defaultValue: jsonValue,
        options: null,
        required: false,
        sortOrder,
      },
    }
  }
  if (typeof jsonValue === 'number') {
    return {
      ok: true,
      field: {
        fieldKey: jsonKey,
        fieldLabel: jsonKey,
        fieldType: 'number',
        maxLength: null,
        defaultValue: String(jsonValue),
        options: null,
        required: false,
        sortOrder,
      },
    }
  }
  if (typeof jsonValue === 'boolean') {
    return {
      ok: true,
      field: {
        fieldKey: jsonKey,
        fieldLabel: jsonKey,
        fieldType: 'boolean',
        maxLength: null,
        defaultValue: String(jsonValue),
        options: null,
        required: false,
        sortOrder,
      },
    }
  }
  if (Array.isArray(jsonValue)) {
    return {
      ok: true,
      field: {
        fieldKey: jsonKey,
        fieldLabel: jsonKey,
        fieldType: 'array',
        maxLength: null,
        defaultValue: JSON.stringify(jsonValue),
        options: null,
        required: false,
        sortOrder,
      },
    }
  }
  return { ok: false, reason: `未识别的 JSON 值类型 ${typeof jsonValue}` }
}

export function buildGeneratePreview(
  json: Record<string, unknown>,
  existingFields: Pick<FieldLike, 'fieldKey'>[],
  sortOrderStart: number,
): GeneratePreview {
  const result: GeneratePreview = { toCreate: [], skippedExisting: [], skippedInferable: [] }
  let i = 0

  for (const [jsonKey, jsonValue] of Object.entries(json)) {
    const exists = existingFields.some((f) => keyMatch(jsonKey, f.fieldKey))
    if (exists) {
      result.skippedExisting.push(jsonKey)
      continue
    }
    const inferred = inferField(jsonKey, jsonValue, sortOrderStart + i)
    if (!inferred.ok) {
      result.skippedInferable.push(jsonKey)
      continue
    }
    result.toCreate.push(inferred.field)
    i += 1
  }
  return result
}
```

- [ ] **Step 2: Smoke test —— tsc 通过**

```bash
cd /c/Users/benerlord/Desktop/InterfaceTest/frontend && npx tsc --noEmit
```

Expected: exit 0

- [ ] **Step 3: Smoke test —— 内联 node 脚本验证核心行为**

创建临时脚本验证三个纯函数的关键行为。用下面的命令跑（`--input-type=module` 让 node 支持 ES 模块语法，`tsx` 或原生 ES module 都能跑；这里用 `tsx` 因为它能读 ts 源）：

```bash
cd /c/Users/benerlord/Desktop/InterfaceTest/frontend && npx tsx -e "
import { keyMatch, buildFillPreview, buildGeneratePreview } from './src/utils/jsonFieldMatch.ts'
import assert from 'node:assert'

// keyMatch 三级匹配
assert.strictEqual(keyMatch('deviceName', 'deviceName'), true, '精确')
assert.strictEqual(keyMatch('DeviceName', 'devicename'), true, '忽略大小写')
assert.strictEqual(keyMatch('deviceName', 'device_name'), true, 'camel↔snake')
assert.strictEqual(keyMatch('device-name', 'DeviceName'), true, 'kebab↔camel')
assert.strictEqual(keyMatch('foo', 'bar'), false, '不匹配')

// buildFillPreview 分组
const fields = [
  { fieldKey: 'deviceName', fieldLabel: '设备名', fieldType: 'text', options: null },
  { fieldKey: 'portCount', fieldLabel: '端口数', fieldType: 'number', options: null },
  { fieldKey: 'ip', fieldLabel: 'IP', fieldType: 'text', options: null },
]
const cur = { ip: '1.1.1.1' }
const p1 = buildFillPreview(
  { deviceName: 'sw-01', portCount: 'not-a-num', ip: '10.0.0.1', unknownKey: 'x' },
  fields, cur,
)
assert.strictEqual(p1.toFill.length, 1, 'toFill = deviceName only')
assert.strictEqual(p1.toFill[0].fieldKey, 'deviceName')
assert.strictEqual(p1.toOverwrite.length, 1, 'toOverwrite = ip')
assert.strictEqual(p1.toOverwrite[0].oldValue, '1.1.1.1')
assert.strictEqual(p1.toOverwrite[0].newValue, '10.0.0.1')
assert.strictEqual(p1.incompatible.length, 1, 'incompatible = portCount')
assert.deepStrictEqual(p1.unmatched, ['unknownKey'])

// buildGeneratePreview 分组
const p2 = buildGeneratePreview(
  { newField: 'abc', existing: 'x', badNull: null, badObj: { a: 1 } },
  [{ fieldKey: 'existing' }],
  10,
)
assert.strictEqual(p2.toCreate.length, 1, 'toCreate = newField only')
assert.strictEqual(p2.toCreate[0].fieldKey, 'newField')
assert.strictEqual(p2.toCreate[0].fieldType, 'text')
assert.strictEqual(p2.toCreate[0].sortOrder, 10)
assert.deepStrictEqual(p2.skippedExisting, ['existing'])
assert.deepStrictEqual(p2.skippedInferable.sort(), ['badNull', 'badObj'])

console.log('OK — all assertions passed')
"
```

Expected: `OK — all assertions passed`

**若 tsx 未装**：先跑 `cd /c/Users/benerlord/Desktop/InterfaceTest/frontend && npx --yes tsx -e "console.log('tsx OK')"` 让 npx 自动下载，然后再跑上面的 assertion 命令。tsx 是无副作用的 dev-time 工具，不需要装进 package.json。

- [ ] **Step 4: Commit**

```bash
cd /c/Users/benerlord/Desktop/InterfaceTest && git add frontend/src/utils/jsonFieldMatch.ts && git commit -m "$(cat <<'EOF'
feat(utils): 新增 jsonFieldMatch 纯函数库

- keyMatch：精确 → 忽略大小写 → snake/camel/kebab 互转三级降级匹配
- buildFillPreview：Mode A 用，返回 toFill/toOverwrite/incompatible/unmatched 四组
- buildGeneratePreview：Mode B 用，返回 toCreate/skippedExisting/skippedInferable 三组
- FieldLike 类型跨 NodeType/EdgeType/AlarmSchema 通用

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: `JsonFillValuesModal.vue`（Mode A 弹窗）

**Files:**
- Create: `frontend/src/components/shared/JsonFillValuesModal.vue`

- [ ] **Step 1: 创建 Mode A 弹窗组件**

用下面的内容创建 `frontend/src/components/shared/JsonFillValuesModal.vue`：

```vue
<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { Modal, Input, Button, Alert, message } from 'ant-design-vue'
import { buildFillPreview, type FillPreview, type FieldLike } from '@/utils/jsonFieldMatch'

interface Props {
  open: boolean
  fields: Pick<FieldLike, 'fieldKey' | 'fieldLabel' | 'fieldType' | 'options'>[]
  currentValues: Record<string, string>
}
const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'update:open', v: boolean): void
  (e: 'apply', values: Record<string, string>): void
}>()

const jsonText = ref('')
const parseError = ref('')
const preview = ref<FillPreview | null>(null)

watch(
  () => props.open,
  (v) => {
    if (v) {
      jsonText.value = ''
      parseError.value = ''
      preview.value = null
    }
  },
)

const canPreview = computed(() => jsonText.value.trim().length > 0)

const totalApplyCount = computed(() => {
  if (!preview.value) return 0
  return preview.value.toFill.length + preview.value.toOverwrite.length
})

const canApply = computed(() => preview.value !== null && parseError.value === '')

function doParse() {
  parseError.value = ''
  preview.value = null
  let parsed: unknown
  try {
    parsed = JSON.parse(jsonText.value)
  } catch (e: any) {
    parseError.value = `解析失败：${e?.message || '未知错误'}`
    return
  }
  if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
    parseError.value = 'JSON 顶层必须是对象 {}'
    return
  }
  if (Object.keys(parsed as Record<string, unknown>).length === 0) {
    parseError.value = '未从 JSON 提取到任何字段'
    return
  }
  preview.value = buildFillPreview(
    parsed as Record<string, unknown>,
    props.fields,
    props.currentValues,
  )
}

function doApply() {
  if (!preview.value) return
  const values: Record<string, string> = {}
  for (const it of preview.value.toFill) values[it.fieldKey] = it.newValue
  for (const it of preview.value.toOverwrite) values[it.fieldKey] = it.newValue
  emit('apply', values)
  if (Object.keys(values).length === 0) {
    message.info('未填充任何字段')
  }
  emit('update:open', false)
}

function doCancel() {
  emit('update:open', false)
}
</script>

<template>
  <Modal
    :open="open"
    title="从 JSON 填充字段"
    :width="640"
    :styles="{ body: { maxHeight: 'calc(100vh - 200px)', overflowY: 'auto' } }"
    @cancel="doCancel"
  >
    <div>
      <div class="hint">粘贴 JSON：</div>
      <Input.TextArea
        v-model:value="jsonText"
        :rows="8"
        placeholder='{"deviceName": "sw-01", "ip": "10.0.0.1"}'
        style="font-family: 'Consolas', 'Monaco', monospace; font-size: 12px;"
      />
      <div class="parse-toolbar">
        <Button type="primary" :disabled="!canPreview" @click="doParse">
          解析预览
        </Button>
      </div>

      <Alert
        v-if="parseError"
        :message="parseError"
        type="error"
        show-icon
        style="margin-top: 12px;"
      />

      <div v-if="preview" class="preview-section">
        <div class="divider">预览结果</div>

        <div v-if="preview.toFill.length > 0" class="group">
          <div class="group-title fill">
            <span class="icon">✓</span> 将填充（{{ preview.toFill.length }}）
          </div>
          <div class="group-body">
            <div v-for="it in preview.toFill" :key="it.fieldKey" class="row">
              <span class="key">{{ it.fieldKey }}</span>
              <span class="label">（{{ it.fieldLabel }}）</span>
              <span class="arrow">←</span>
              <span class="value">{{ it.newValue }}</span>
            </div>
          </div>
        </div>

        <div v-if="preview.toOverwrite.length > 0" class="group">
          <div class="group-title overwrite">
            <span class="icon">⚠</span> 将覆盖已有值（{{ preview.toOverwrite.length }}）
          </div>
          <div class="group-body">
            <div v-for="it in preview.toOverwrite" :key="it.fieldKey" class="row overwrite-row">
              <div>
                <span class="key">{{ it.fieldKey }}</span>
                <span class="label">（{{ it.fieldLabel }}）</span>
              </div>
              <div class="sub">
                当前: <span class="old">{{ it.oldValue }}</span>
                →
                新值: <span class="new">{{ it.newValue }}</span>
              </div>
            </div>
          </div>
        </div>

        <div v-if="preview.incompatible.length > 0" class="group">
          <div class="group-title incompatible">
            <span class="icon">⊘</span> 类型不兼容跳过（{{ preview.incompatible.length }}）
          </div>
          <div class="group-body">
            <div v-for="it in preview.incompatible" :key="it.fieldKey" class="row">
              <span class="key">{{ it.fieldKey }}</span>
              <span class="label">（{{ it.fieldLabel }}）</span>
              <span class="reason">— {{ it.reason }}</span>
            </div>
          </div>
        </div>

        <div v-if="preview.unmatched.length > 0" class="group">
          <div class="group-title unmatched">
            <span class="icon">○</span> 未匹配的 JSON key（{{ preview.unmatched.length }}）
          </div>
          <div class="group-body">
            <span v-for="k in preview.unmatched" :key="k" class="tag-key">{{ k }}</span>
          </div>
        </div>
      </div>
    </div>

    <template #footer>
      <Button @click="doCancel">取消</Button>
      <Button type="primary" :disabled="!canApply" @click="doApply">
        确定填充（{{ totalApplyCount }}）
      </Button>
    </template>
  </Modal>
</template>

<style scoped>
.hint { font-size: 12px; color: #666; margin-bottom: 4px; }
.parse-toolbar { margin-top: 8px; }
.divider { font-size: 12px; color: #999; text-align: center; margin: 12px 0 8px; }
.preview-section { margin-top: 8px; }
.group { margin-bottom: 12px; padding: 8px 12px; background: #fafafa; border-radius: 4px; }
.group-title { font-size: 13px; font-weight: 500; margin-bottom: 6px; }
.group-title.fill { color: #52c41a; }
.group-title.overwrite { color: #faad14; }
.group-title.incompatible { color: #8c8c8c; }
.group-title.unmatched { color: #bfbfbf; }
.group-title .icon { display: inline-block; margin-right: 4px; }
.group-body { padding-left: 20px; }
.row { line-height: 1.9; font-size: 12px; }
.overwrite-row { padding: 4px 0; border-bottom: 1px dashed #eee; }
.overwrite-row:last-child { border-bottom: none; }
.row .key { font-family: monospace; color: #1f1f1f; }
.row .label { color: #888; margin-right: 8px; }
.row .arrow { margin: 0 8px; color: #52c41a; }
.row .value { font-family: monospace; color: #1890ff; }
.row .reason { color: #ff4d4f; margin-left: 8px; font-size: 11px; }
.row .old { font-family: monospace; color: #999; text-decoration: line-through; }
.row .new { font-family: monospace; color: #1890ff; }
.row .sub { padding-left: 12px; color: #666; font-size: 11px; }
.tag-key { display: inline-block; padding: 2px 8px; margin: 2px 4px 2px 0; background: #f0f0f0; border-radius: 3px; font-family: monospace; font-size: 11px; color: #666; }
</style>
```

- [ ] **Step 2: Smoke test —— tsc 通过**

```bash
cd /c/Users/benerlord/Desktop/InterfaceTest/frontend && npx tsc --noEmit
```

Expected: exit 0

- [ ] **Step 3: Commit**

```bash
cd /c/Users/benerlord/Desktop/InterfaceTest && git add frontend/src/components/shared/JsonFillValuesModal.vue && git commit -m "$(cat <<'EOF'
feat(shared): 新增 JsonFillValuesModal（Mode A · 填值弹窗）

- TextArea 粘贴 JSON → 解析预览 → emit apply
- 预览分四组：将填充 / 将覆盖已有值 / 类型不兼容跳过 / 未匹配 JSON key
- 空分组隐藏；JSON 语法错误 / 非对象 / 空对象各自的错误提示
- 关闭时清空状态

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: `JsonGenerateFieldsModal.vue`（Mode B 弹窗）

**Files:**
- Create: `frontend/src/components/shared/JsonGenerateFieldsModal.vue`

- [ ] **Step 1: 创建 Mode B 弹窗组件**

用下面的内容创建 `frontend/src/components/shared/JsonGenerateFieldsModal.vue`：

```vue
<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { Modal, Input, Button, Alert, Table, message } from 'ant-design-vue'
import { buildGeneratePreview, type GeneratePreview, type FieldLike } from '@/utils/jsonFieldMatch'

interface Props {
  open: boolean
  existingFields: Pick<FieldLike, 'fieldKey'>[]
  sortOrderStart: number
}
const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'update:open', v: boolean): void
  (e: 'apply', fields: FieldLike[]): void
}>()

const jsonText = ref('')
const parseError = ref('')
const preview = ref<GeneratePreview | null>(null)

watch(
  () => props.open,
  (v) => {
    if (v) {
      jsonText.value = ''
      parseError.value = ''
      preview.value = null
    }
  },
)

const canPreview = computed(() => jsonText.value.trim().length > 0)
const canApply = computed(() => preview.value !== null && parseError.value === '')
const totalCreateCount = computed(() => preview.value?.toCreate.length ?? 0)

function doParse() {
  parseError.value = ''
  preview.value = null
  let parsed: unknown
  try {
    parsed = JSON.parse(jsonText.value)
  } catch (e: any) {
    parseError.value = `解析失败：${e?.message || '未知错误'}`
    return
  }
  if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
    parseError.value = 'JSON 顶层必须是对象 {}'
    return
  }
  if (Object.keys(parsed as Record<string, unknown>).length === 0) {
    parseError.value = '未从 JSON 提取到任何字段'
    return
  }
  preview.value = buildGeneratePreview(
    parsed as Record<string, unknown>,
    props.existingFields,
    props.sortOrderStart,
  )
}

function doApply() {
  if (!preview.value) return
  emit('apply', preview.value.toCreate)
  if (preview.value.toCreate.length === 0) {
    message.info('未生成任何字段')
  }
  emit('update:open', false)
}

function doCancel() {
  emit('update:open', false)
}

const previewColumns = [
  { title: 'Key', dataIndex: 'fieldKey', key: 'fieldKey', width: 160, ellipsis: true },
  { title: 'Type', dataIndex: 'fieldType', key: 'fieldType', width: 90 },
  { title: 'Label', dataIndex: 'fieldLabel', key: 'fieldLabel', width: 140, ellipsis: true },
  { title: 'Default', dataIndex: 'defaultValue', key: 'defaultValue', ellipsis: true },
]
</script>

<template>
  <Modal
    :open="open"
    title="从 JSON 生成字段"
    :width="640"
    :styles="{ body: { maxHeight: 'calc(100vh - 200px)', overflowY: 'auto' } }"
    @cancel="doCancel"
  >
    <div>
      <div class="hint">粘贴 JSON：</div>
      <Input.TextArea
        v-model:value="jsonText"
        :rows="8"
        placeholder='{"deviceName": "sw-01", "portCount": 24, "enabled": true}'
        style="font-family: 'Consolas', 'Monaco', monospace; font-size: 12px;"
      />
      <div class="parse-toolbar">
        <Button type="primary" :disabled="!canPreview" @click="doParse">
          解析预览
        </Button>
      </div>

      <Alert
        v-if="parseError"
        :message="parseError"
        type="error"
        show-icon
        style="margin-top: 12px;"
      />

      <div v-if="preview" class="preview-section">
        <div class="divider">预览结果</div>

        <div v-if="preview.toCreate.length > 0" class="group">
          <div class="group-title create">
            <span class="icon">✓</span> 将新建字段（{{ preview.toCreate.length }}）
          </div>
          <Table
            :columns="previewColumns"
            :data-source="preview.toCreate"
            :pagination="false"
            size="small"
            :row-key="(r: FieldLike) => r.fieldKey"
          />
        </div>

        <div v-if="preview.skippedExisting.length > 0" class="group">
          <div class="group-title skip">
            <span class="icon">⊘</span> 已存在跳过（{{ preview.skippedExisting.length }}）
          </div>
          <div class="group-body">
            <span v-for="k in preview.skippedExisting" :key="k" class="tag-key">{{ k }}</span>
          </div>
        </div>

        <div v-if="preview.skippedInferable.length > 0" class="group">
          <div class="group-title skip">
            <span class="icon">⊘</span> 无法推断类型跳过（{{ preview.skippedInferable.length }}）
          </div>
          <div class="group-body">
            <span v-for="k in preview.skippedInferable" :key="k" class="tag-key">{{ k }}</span>
          </div>
        </div>
      </div>
    </div>

    <template #footer>
      <Button @click="doCancel">取消</Button>
      <Button type="primary" :disabled="!canApply" @click="doApply">
        确定生成（{{ totalCreateCount }}）
      </Button>
    </template>
  </Modal>
</template>

<style scoped>
.hint { font-size: 12px; color: #666; margin-bottom: 4px; }
.parse-toolbar { margin-top: 8px; }
.divider { font-size: 12px; color: #999; text-align: center; margin: 12px 0 8px; }
.preview-section { margin-top: 8px; }
.group { margin-bottom: 12px; padding: 8px 12px; background: #fafafa; border-radius: 4px; }
.group-title { font-size: 13px; font-weight: 500; margin-bottom: 6px; }
.group-title.create { color: #52c41a; }
.group-title.skip { color: #8c8c8c; }
.group-title .icon { display: inline-block; margin-right: 4px; }
.group-body { padding-left: 20px; }
.tag-key { display: inline-block; padding: 2px 8px; margin: 2px 4px 2px 0; background: #f0f0f0; border-radius: 3px; font-family: monospace; font-size: 11px; color: #666; }
</style>
```

- [ ] **Step 2: Smoke test —— tsc 通过**

```bash
cd /c/Users/benerlord/Desktop/InterfaceTest/frontend && npx tsc --noEmit
```

Expected: exit 0

- [ ] **Step 3: Commit**

```bash
cd /c/Users/benerlord/Desktop/InterfaceTest && git add frontend/src/components/shared/JsonGenerateFieldsModal.vue && git commit -m "$(cat <<'EOF'
feat(shared): 新增 JsonGenerateFieldsModal（Mode B · 建字段弹窗）

- TextArea 粘贴 JSON → 解析预览 → emit apply(FieldLike[])
- 预览分三组：将新建字段（Table 展示 key/type/label/default） / 已存在跳过 / 无法推断类型跳过
- 关闭时清空状态

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: 画布节点属性两处入口集成（Mode A · Panel + Modal）

**Files:**
- Modify: `frontend/src/components/canvas/NodeAttrsPanel.vue`
- Modify: `frontend/src/components/canvas/NodeAttrsModal.vue`

- [ ] **Step 1: 修改 `NodeAttrsPanel.vue` 加"从 JSON 填充"入口**

在文件顶部 import 处追加：

```typescript
import { ImportOutlined } from '@ant-design/icons-vue'
import JsonFillValuesModal from '@/components/shared/JsonFillValuesModal.vue'
```

在 `<script setup>` 末尾 `setFieldValue` 之前追加：

```typescript
const jsonModalOpen = ref(false)

function handleJsonApply(values: Record<string, string>) {
  for (const [k, v] of Object.entries(values)) {
    setFieldValue(k, v)
  }
}
```

在 template 的 `.panel-header` 里、`<span class="panel-title">节点属性</span>` 之后、 `<Button type="text" size="small" @click="emit('close')">×</Button>` 之前插入：

```vue
<Button size="small" @click="jsonModalOpen = true">
  <template #icon><ImportOutlined /></template>
  从 JSON 填充
</Button>
```

在整个 `<template>` 的最后一个 `</Transition>` 之前（`</div>` 关闭 `.node-attrs-panel` 之后）追加 Modal 挂载：

```vue
<JsonFillValuesModal
  v-model:open="jsonModalOpen"
  :fields="fields"
  :current-values="formData"
  @apply="handleJsonApply"
/>
```

**注意 `panel-header` 布局调整**：原来是 `justify-content: space-between` 两端撑开，插入按钮后变成三个子元素。修改 `.panel-header` 的 CSS 让按钮组自然放在标题右侧、"×"关闭按钮再右：

在 `<style scoped>` 里替换：

```css
.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid #e8e8e8;
}
```

为：

```css
.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid #e8e8e8;
  gap: 8px;
}
.panel-header .panel-title { flex: 1; }
```

- [ ] **Step 2: 修改 `NodeAttrsModal.vue` 加"从 JSON 填充"入口**

在文件顶部 import 处追加：

```typescript
import { Button } from 'ant-design-vue'
import { ImportOutlined } from '@ant-design/icons-vue'
import JsonFillValuesModal from '@/components/shared/JsonFillValuesModal.vue'
```

在 `<script setup>` 末尾追加：

```typescript
const jsonModalOpen = ref(false)

function handleJsonApply(values: Record<string, string>) {
  for (const [k, v] of Object.entries(values)) {
    setFieldValue(k, v)
  }
}
```

在 template 的 `<div class="node-type-name">{{ nodeTypeName }}</div>` **之后** 插入：

```vue
<div class="json-fill-toolbar">
  <Button size="small" @click="jsonModalOpen = true">
    <template #icon><ImportOutlined /></template>
    从 JSON 填充
  </Button>
</div>
```

在 template 的 `</Modal>` 之前挂载 Modal：

```vue
<JsonFillValuesModal
  v-model:open="jsonModalOpen"
  :fields="fields"
  :current-values="formData"
  @apply="handleJsonApply"
/>
```

在 `<style scoped>` 末尾追加：

```css
.json-fill-toolbar {
  margin-bottom: 12px;
}
```

- [ ] **Step 3: Smoke test —— tsc 通过**

```bash
cd /c/Users/benerlord/Desktop/InterfaceTest/frontend && npx tsc --noEmit
```

Expected: exit 0

- [ ] **Step 4: Commit**

```bash
cd /c/Users/benerlord/Desktop/InterfaceTest && git add frontend/src/components/canvas/NodeAttrsPanel.vue frontend/src/components/canvas/NodeAttrsModal.vue && git commit -m "$(cat <<'EOF'
feat(canvas): 节点属性面板 / 创建节点弹窗接入"从 JSON 填充"

Mode A · 复用 JsonFillValuesModal，一次性填 formData。
- NodeAttrsPanel 按钮加在 header 里
- NodeAttrsModal 按钮加在类型名下方

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: 告警页面入口集成（Mode A · Collapse.Panel 内锁 alarmId）

**Files:**
- Modify: `frontend/src/components/canvas/NodeAlarmsTab.vue`

- [ ] **Step 1: 加"从 JSON 填充"入口 + Modal 挂载**

在文件顶部 import 处追加：

```typescript
import { ImportOutlined } from '@ant-design/icons-vue'
import JsonFillValuesModal from '@/components/shared/JsonFillValuesModal.vue'
```

在 `<script setup>` 末尾、`defineExpose({ saveDirty })` 之前追加：

```typescript
const jsonModalOpen = ref(false)
const jsonTargetAlarmId = ref<string | null>(null)

const jsonTargetAlarm = computed(() =>
  alarms.value.find((a) => a.id === jsonTargetAlarmId.value) ?? null,
)

const jsonCurrentValues = computed<Record<string, string>>(() => {
  const src = jsonTargetAlarm.value?.attrs ?? {}
  const r: Record<string, string> = {}
  for (const k in src) r[k] = src[k] ?? ''
  return r
})

function openJsonModal(alarmId: string) {
  jsonTargetAlarmId.value = alarmId
  jsonModalOpen.value = true
}

function handleJsonApply(values: Record<string, string>) {
  const a = jsonTargetAlarm.value
  if (!a) return
  for (const [k, v] of Object.entries(values)) {
    a.attrs[k] = v
  }
  markDirty(a.id)
}
```

在 template 的 `<Collapse.Panel>` 内部、`<Form layout="vertical">` **之前**插入按钮工具栏：

```vue
<div class="alarm-json-toolbar">
  <Button size="small" @click="openJsonModal(a.id)">
    <template #icon><ImportOutlined /></template>
    从 JSON 填充
  </Button>
</div>
```

在 template 最外层（`<div v-else class="alarms-list">` 关闭之后、根 `</template>` 之前）追加 Modal 挂载：

```vue
<JsonFillValuesModal
  v-model:open="jsonModalOpen"
  :fields="schemaFields"
  :current-values="jsonCurrentValues"
  @apply="handleJsonApply"
/>
```

在 `<style scoped>` 末尾追加：

```css
.alarm-json-toolbar {
  margin-bottom: 8px;
}
```

- [ ] **Step 2: Smoke test —— tsc 通过**

```bash
cd /c/Users/benerlord/Desktop/InterfaceTest/frontend && npx tsc --noEmit
```

Expected: exit 0

- [ ] **Step 3: Commit**

```bash
cd /c/Users/benerlord/Desktop/InterfaceTest && git add frontend/src/components/canvas/NodeAlarmsTab.vue && git commit -m "$(cat <<'EOF'
feat(canvas): 告警页每条 Collapse 内接入"从 JSON 填充"

Mode A · 用 jsonTargetAlarmId 状态锁定目标告警，避免相互串扰。
- 按钮放在每条 Collapse.Panel 内 Form 之前，点击时携带该告警 id
- 应用后回写 alarm.attrs 并 markDirty

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: 三个字段编辑器入口集成（Mode B · Node/Edge/AlarmSchema）

**Files:**
- Modify: `frontend/src/components/types/NodeTypeFieldEditor.vue`
- Modify: `frontend/src/components/types/EdgeTypeFieldEditor.vue`
- Modify: `frontend/src/components/alarmSchemas/AlarmSchemaFieldEditor.vue`

三个编辑器改动模式完全一致，都是"toolbar-top 加按钮 + template 末尾挂 Modal + `handleJsonGenerate` 把 `FieldLike[]` append 到 `localFields`"。字段类型 shape 相同（AlarmSchemaFieldInput 多的 `mappingTarget` 是可选字段，自动为 undefined），FieldLike 直接作为 `NodeTypeFieldInput / EdgeTypeFieldInput / AlarmSchemaFieldInput` 使用即可，无需额外转换。

- [ ] **Step 1: 修改 `NodeTypeFieldEditor.vue`**

在文件顶部 import 处追加：

```typescript
import { ref } from 'vue'
import { ImportOutlined } from '@ant-design/icons-vue'
import JsonGenerateFieldsModal from '@/components/shared/JsonGenerateFieldsModal.vue'
import type { FieldLike } from '@/utils/jsonFieldMatch'
```

在 `<script setup>` 末尾追加：

```typescript
const jsonModalOpen = ref(false)

function handleJsonGenerate(newFields: FieldLike[]) {
  emit('update:fields', [...localFields.value, ...newFields])
}
```

在 template 的 `.toolbar.toolbar-top` 里、`<span class="hint">{{ localFields.length }} 个字段</span>` **之前**插入：

```vue
<Button size="small" @click="jsonModalOpen = true">
  <ImportOutlined /> 从 JSON 生成字段
</Button>
```

在 template 最后一个 `</div>` 关闭前追加 Modal 挂载：

```vue
<JsonGenerateFieldsModal
  v-model:open="jsonModalOpen"
  :existing-fields="localFields"
  :sort-order-start="localFields.length"
  @apply="handleJsonGenerate"
/>
```

- [ ] **Step 2: 修改 `EdgeTypeFieldEditor.vue`**

同 Step 1，全部三段代码都完全相同（EdgeTypeFieldInput 与 NodeTypeFieldInput 结构一致，FieldLike[] 可直接 append）。为避免"Similar to Task N"陷阱，明确重复：

在文件顶部 import 处追加：

```typescript
import { ref } from 'vue'
import { ImportOutlined } from '@ant-design/icons-vue'
import JsonGenerateFieldsModal from '@/components/shared/JsonGenerateFieldsModal.vue'
import type { FieldLike } from '@/utils/jsonFieldMatch'
```

在 `<script setup>` 末尾追加：

```typescript
const jsonModalOpen = ref(false)

function handleJsonGenerate(newFields: FieldLike[]) {
  emit('update:fields', [...localFields.value, ...newFields])
}
```

在 template 的 `.toolbar.toolbar-top` 里、`<span class="hint">{{ localFields.length }} 个字段</span>` **之前**插入：

```vue
<Button size="small" @click="jsonModalOpen = true">
  <ImportOutlined /> 从 JSON 生成字段
</Button>
```

在 template 最后一个 `</div>` 关闭前追加 Modal 挂载：

```vue
<JsonGenerateFieldsModal
  v-model:open="jsonModalOpen"
  :existing-fields="localFields"
  :sort-order-start="localFields.length"
  @apply="handleJsonGenerate"
/>
```

- [ ] **Step 3: 修改 `AlarmSchemaFieldEditor.vue`**

在文件顶部 import 处追加：

```typescript
import { ImportOutlined } from '@ant-design/icons-vue'
import JsonGenerateFieldsModal from '@/components/shared/JsonGenerateFieldsModal.vue'
import type { FieldLike } from '@/utils/jsonFieldMatch'
```

（若 `ref` 已在 import 里就不用再加）

在 `<script setup>` 末尾追加：

```typescript
const jsonModalOpen = ref(false)

function handleJsonGenerate(newFields: FieldLike[]) {
  emit('update:fields', [...localFields.value, ...newFields])
}
```

在 template 的 `.toolbar.toolbar-top` 里、`<span class="hint">` **之前**插入（AlarmSchemaFieldEditor 的 toolbar 结构一致）：

```vue
<Button size="small" @click="jsonModalOpen = true">
  <ImportOutlined /> 从 JSON 生成字段
</Button>
```

在 template 最后一个 `</div>` 关闭前追加 Modal 挂载：

```vue
<JsonGenerateFieldsModal
  v-model:open="jsonModalOpen"
  :existing-fields="localFields"
  :sort-order-start="localFields.length"
  @apply="handleJsonGenerate"
/>
```

**注意**：AlarmSchemaFieldInput 有一个额外的 `mappingTarget?: string | null` 字段，FieldLike[] append 后该字段自动为 `undefined`，Vue 表格里显示为空，用户可后续在字段行手工设置。

- [ ] **Step 4: Smoke test —— tsc 通过**

```bash
cd /c/Users/benerlord/Desktop/InterfaceTest/frontend && npx tsc --noEmit
```

Expected: exit 0

- [ ] **Step 5: Commit**

```bash
cd /c/Users/benerlord/Desktop/InterfaceTest && git add frontend/src/components/types/NodeTypeFieldEditor.vue frontend/src/components/types/EdgeTypeFieldEditor.vue frontend/src/components/alarmSchemas/AlarmSchemaFieldEditor.vue && git commit -m "$(cat <<'EOF'
feat(types,alarm): 三个字段编辑器接入"从 JSON 生成字段"

Mode B · 复用 JsonGenerateFieldsModal，把生成的 FieldLike[] append 到 localFields。
- NodeTypeFieldEditor / EdgeTypeFieldEditor / AlarmSchemaFieldEditor
- FieldLike shape 与三个 FieldInput 类型兼容，无需额外转换

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: 手工联调验收 + 更新 CLAUDE.md

**Files:** 无代码改动，纯手工验收 + CLAUDE.md 更新

- [ ] **Step 1: 启动前后端**

```bash
cd /c/Users/benerlord/Desktop/InterfaceTest/backend && python -m app.main
```

（后台运行）

```bash
cd /c/Users/benerlord/Desktop/InterfaceTest/frontend && npm run dev
```

- [ ] **Step 2: 用例 1 —— 画布编辑节点填值 (golden path)**

前置：有一个节点类型带 `deviceName / ipAddress / portCount / enabled` 四个字段，且拓扑上有一个该类型节点。

操作：打开画布 → 点节点 → 属性面板打开 → 点顶部"从 JSON 填充" → 粘贴：

```json
{"deviceName":"sw-01","ipAddress":"10.0.0.1","portCount":24,"enabled":true}
```

→ 点"解析预览" → 四条都在"将填充" → 点"确定填充(4)"

预期：面板 4 字段被写入正确值；点"保存"落库成功。

- [ ] **Step 3: 用例 2 —— 宽松匹配命中**

字段名 `device_name`，JSON `{"deviceName": "sw-01"}` → 预览显示命中 `device_name`，label 显示中文名。

- [ ] **Step 4: 用例 3 —— 覆盖已有值**

节点当前 `ipAddress = "1.1.1.1"`，粘贴 `{"ipAddress": "10.0.0.1"}` → 预览"将覆盖已有值"分组显示 `当前: 1.1.1.1 → 新值: 10.0.0.1`。

- [ ] **Step 5: 用例 4 —— 类型不兼容跳过**

`portCount` 是 number 类型，粘贴 `{"portCount": "not-a-num"}` → 预览"类型不兼容跳过"，reason 里显示"值无法解析为数字"。

- [ ] **Step 6: 用例 5 —— 未匹配 JSON key**

字段只有 `deviceName`，粘贴 `{"deviceName":"x","unknownKey":"y"}` → 预览"未匹配"分组显示 `unknownKey` 标签。

- [ ] **Step 7: 用例 6 —— 画布新建节点填值**

从左侧类型面板拖节点到画布 → `NodeAttrsModal` 弹出 → 点类型名下方"从 JSON 填充" → 粘贴 JSON → 确定 → 创建成功。

- [ ] **Step 8: 用例 7 —— 告警字段填值 (每条 Collapse 内)**

拓扑绑告警模板 → 展开告警 Tab → 新增一条告警 → 展开该 Collapse → 点内部"从 JSON 填充" → 粘贴 JSON → 只影响这条告警（其他告警不受影响）→ 保存告警成功。

- [ ] **Step 9: 用例 8 —— 节点类型建字段 (golden path)**

类型管理页面 → 新建节点类型 → 弹窗字段配置 toolbar 点"从 JSON 生成字段" → 粘贴：

```json
{"deviceName":"sw-01","portCount":24,"enabled":true,"tags":["core","prod"]}
```

→ 预览 Table 显示 4 条新建（text / number / boolean / array），Type 列推断正确 → 确定 → 字段表新增 4 行；填其他必要项后保存类型成功。

- [ ] **Step 10: 用例 9 —— 已存在跳过**

字段表已有 `deviceName` → 粘贴 `{"deviceName":"x","new_field":"y"}` → 预览"已存在跳过"分组显示 `deviceName` 标签，`new_field` 进"将新建" → 确定后只新增 `new_field` 一行。

- [ ] **Step 11: 用例 10 —— 无法推断类型跳过**

粘贴 `{"foo": null, "bar": {"nested": 1}, "baz": "abc"}` → `foo` 和 `bar` 进"无法推断类型跳过"，只有 `baz` 进"将新建"。

- [ ] **Step 12: 用例 11 —— 边类型建字段**

类型管理 → 编辑边类型 → 弹窗字段配置 → 粘贴 JSON → 生成成功 → 保存边类型成功。

- [ ] **Step 13: 用例 12 —— 告警模板建字段**

告警模板管理 → 编辑告警模板 → 字段配置 → 粘贴 JSON → 生成成功 → 保存告警模板成功。

- [ ] **Step 14: 用例 13 —— JSON 语法错误**

任一 Mode 的 Modal 里粘贴 `{deviceName: sw-01}`（缺引号）→ 显示"解析失败: Unexpected token ..."，"确定"按钮禁用。

- [ ] **Step 15: 用例 14 —— JSON 顶层非对象**

粘贴 `[1,2,3]` → 显示"JSON 顶层必须是对象 {}"。

- [ ] **Step 16: 用例 15 —— 空对象**

粘贴 `{}` → 显示"未从 JSON 提取到任何字段"。

- [ ] **Step 17: 关闭进程释放端口**

按 CLAUDE.md 约定，测试完成后关掉后端和前端 dev server：

```bash
netstat -ano | grep :8080 | grep LISTENING
# 找到 PID 后 taskkill /F /PID <pid>
netstat -ano | grep :5173 | grep LISTENING
# 找到 PID 后 taskkill /F /PID <pid>
```

- [ ] **Step 18: 更新 CLAUDE.md 开发进度**

在 CLAUDE.md 的"已完成"章节末尾追加一条：

```markdown
- ✅ JSON 一键填字段值 / 生成字段定义（6 处入口）：
  - 新增 `utils/jsonFieldMatch.ts` 纯函数库（keyMatch 三级宽松匹配 + buildFillPreview / buildGeneratePreview）
  - 新增 `components/shared/JsonFillValuesModal.vue`（Mode A · 填值预览四分组）
  - 新增 `components/shared/JsonGenerateFieldsModal.vue`（Mode B · 建字段预览三分组）
  - Mode A 3 处入口：NodeAttrsPanel（编辑节点） / NodeAttrsModal（新建节点） / NodeAlarmsTab（每条告警 Collapse 内锁 alarmId）
  - Mode B 3 处入口：NodeTypeFieldEditor / EdgeTypeFieldEditor / AlarmSchemaFieldEditor（toolbar-top +按钮 + append 到 localFields）
  - 设计方案：`docs/superpowers/specs/2026-07-03-json-to-node-fields-design.md`；实施计划：`docs/superpowers/plans/2026-07-03-json-to-node-fields.md`
```

（注意 CLAUDE.md 在仓库里是 `claude.md` 小写，git add 时用小写路径）

- [ ] **Step 19: Commit**

```bash
cd /c/Users/benerlord/Desktop/InterfaceTest && git add claude.md && git commit -m "$(cat <<'EOF'
docs(claude): 记录 JSON 一键填字段值 / 生成字段定义功能完成

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## 完成标准

- ✅ Task 1-7 所有 checkbox 全打勾
- ✅ Task 7 的 15 个用例（含 5 个边缘用例）全部通过
- ✅ `git log` 有 7 条对应 commit（T1-T6 + T7 CLAUDE.md）
- ✅ `netstat` 确认后端 / 前端端口已释放
