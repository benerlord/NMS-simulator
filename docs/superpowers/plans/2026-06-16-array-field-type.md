# 字段类型新增 array 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 系统级新增第 5 种字段类型 `array`，覆盖节点类型 / 边类型 / 告警模板字段定义、画布上 4 个属性编辑器、以及 Excel 导入导出。

**Architecture:** 后端 7 处 Pydantic `field_type` pattern 扩展为 `^(text|number|select|boolean|array)$`，新增 `validate_array_default` validator 限制 array 字段的 default_value 必须是合法 JSON array；前端 4 个 TS 类型联合扩展，3 个字段编辑器加 array Select 选项，新增独立 `ArrayJsonInput.vue` 组件（Antd `Input.TextArea` + 实时 JSON parse 校验），4 个画布属性编辑器加 array 渲染分支并复用 `fieldValidation.ts` helper。

**Tech Stack:** FastAPI + SQLite + Pydantic v2 CamelModel；Vue 3.5 `<script setup>` + Ant Design Vue 4；pytest；项目无前端单元测试，UI 改动靠人工 smoke。

**Spec:** `docs/superpowers/specs/2026-06-16-array-field-type-design.md`

**Worktree note:** 实施前如需隔离环境，使用 `superpowers:using-git-worktrees` 创建独立 worktree（建议分支名 `worktree-array-field-type`）。

---

## Task 1: 后端 Pydantic patterns + validators + 全部测试

**Files:**
- Modify: `backend/app/admin/schemas/node_type.py`
- Modify: `backend/app/admin/schemas/alarm.py`
- Create: `backend/tests/test_array_field_type.py`

### TDD 顺序：所有 14 个测试先写，然后批量改 schema，最后单一 commit

- [ ] **Step 1: 创建测试文件，写所有 14 个用例**

创建 `backend/tests/test_array_field_type.py`：

```python
"""字段类型新增 array 测试 — 覆盖 spec §3.1 / §3.2 + §3.6 Excel I/O。"""
import json

import pytest


# ============================================================
# 1. Pattern 接受 array
# ============================================================

def test_array_field_pattern_accepted(client):
    """fieldType='array' 通过 pattern 校验。"""
    r = client.post("/admin/api/node-types", json={
        "code": "arr_router", "name": "ArrRouter", "category": "physical",
        "fields": [
            {"fieldKey": "ports", "fieldLabel": "端口列表", "fieldType": "array"},
        ],
    })
    assert r.status_code == 200, r.text


def test_create_node_type_with_array_field(client):
    """POST 类型含 array 字段 → 落库 + GET 回来类型保留。"""
    r = client.post("/admin/api/node-types", json={
        "code": "arr_dev", "name": "ArrDev", "category": "physical",
        "fields": [
            {"fieldKey": "tags", "fieldLabel": "标签", "fieldType": "array"},
        ],
    })
    tid = r.json()["data"]["id"]
    r = client.get(f"/admin/api/node-types/{tid}")
    fields = r.json()["data"]["fields"]
    assert len(fields) == 1
    assert fields[0]["fieldType"] == "array"


# ============================================================
# 2. validate_array_default
# ============================================================

def test_create_with_array_default_value_valid(client):
    """defaultValue='[\"a\",\"b\"]' → 成功。"""
    r = client.post("/admin/api/node-types", json={
        "code": "arr_dv1", "name": "D1", "category": "physical",
        "fields": [
            {"fieldKey": "tags", "fieldLabel": "标签", "fieldType": "array",
             "defaultValue": '["a","b"]'},
        ],
    })
    assert r.status_code == 200, r.text
    tid = r.json()["data"]["id"]
    fields = client.get(f"/admin/api/node-types/{tid}").json()["data"]["fields"]
    assert fields[0]["defaultValue"] == '["a","b"]'


def test_create_with_array_default_value_invalid_not_list(client):
    """defaultValue='\"abc\"' → 422（不是 array）。"""
    r = client.post("/admin/api/node-types", json={
        "code": "arr_dv2", "name": "D2", "category": "physical",
        "fields": [
            {"fieldKey": "tags", "fieldLabel": "标签", "fieldType": "array",
             "defaultValue": '"abc"'},
        ],
    })
    assert r.status_code == 422
    assert "JSON array" in r.text


def test_create_with_array_default_value_invalid_json(client):
    """defaultValue='[1,2' → 422（语法错）。"""
    r = client.post("/admin/api/node-types", json={
        "code": "arr_dv3", "name": "D3", "category": "physical",
        "fields": [
            {"fieldKey": "tags", "fieldLabel": "标签", "fieldType": "array",
             "defaultValue": "[1,2"},
        ],
    })
    assert r.status_code == 422
    assert "合法 JSON" in r.text


def test_create_with_array_default_value_empty_array(client):
    """defaultValue='[]' → 成功。"""
    r = client.post("/admin/api/node-types", json={
        "code": "arr_dv4", "name": "D4", "category": "physical",
        "fields": [
            {"fieldKey": "tags", "fieldLabel": "标签", "fieldType": "array",
             "defaultValue": "[]"},
        ],
    })
    assert r.status_code == 200, r.text


def test_create_with_array_default_value_null(client):
    """defaultValue 不传 → 成功（不校验）。"""
    r = client.post("/admin/api/node-types", json={
        "code": "arr_dv5", "name": "D5", "category": "physical",
        "fields": [
            {"fieldKey": "tags", "fieldLabel": "标签", "fieldType": "array"},
        ],
    })
    assert r.status_code == 200, r.text


# ============================================================
# 3. 节点 attrs 接口接受 array JSON 字符串
# ============================================================

def test_set_attrs_with_json_array_string(client):
    """PUT node attrs value='[\"a\",\"b\"]' → GET 回来一致。"""
    r = client.post("/admin/api/node-types", json={
        "code": "arr_n", "name": "N", "category": "physical",
        "fields": [{"fieldKey": "tags", "fieldLabel": "标签", "fieldType": "array"}],
    })
    tid = r.json()["data"]["id"]
    r = client.post("/admin/api/topologies", json={"name": "T-arr"})
    topo = r.json()["data"]["id"]
    n1 = client.post(f"/admin/api/topologies/{topo}/nodes",
                     json={"nodeTypeId": tid, "name": "n1"}).json()["data"]["id"]

    r = client.put(f"/admin/api/nodes/{n1}/attrs", json=[
        {"fieldKey": "tags", "value": '["a","b","c"]'},
    ])
    assert r.status_code == 200, r.text

    attrs = client.get(f"/admin/api/nodes/{n1}").json()["data"].get("attrs", {})
    assert attrs.get("tags") == '["a","b","c"]'


# ============================================================
# 4. 改字段类型为 array
# ============================================================

def test_update_node_type_change_field_type_to_array(client):
    """已有 text 字段，PUT 改 fieldType 为 array → 成功。"""
    r = client.post("/admin/api/node-types", json={
        "code": "arr_chg", "name": "Chg", "category": "physical",
        "fields": [
            {"fieldKey": "tags", "fieldLabel": "标签", "fieldType": "text", "maxLength": 100},
        ],
    })
    tid = r.json()["data"]["id"]

    r = client.put(f"/admin/api/node-types/{tid}", json={
        "fields": [
            {"fieldKey": "tags", "fieldLabel": "标签", "fieldType": "array"},
        ],
    })
    assert r.status_code == 200, r.text

    fields = client.get(f"/admin/api/node-types/{tid}").json()["data"]["fields"]
    assert fields[0]["fieldType"] == "array"


# ============================================================
# 5. 边类型 + 告警模板对称
# ============================================================

def test_edge_type_array_field_symmetric(client):
    """边类型 fields[fieldType='array'] → 成功。"""
    r = client.post("/admin/api/edge-types", json={
        "code": "arr_edge", "name": "ArrEdge",
        "fields": [
            {"fieldKey": "subnets", "fieldLabel": "子网", "fieldType": "array",
             "defaultValue": '["10.0.0.0/24"]'},
        ],
    })
    assert r.status_code == 200, r.text
    tid = r.json()["data"]["id"]
    fields = client.get(f"/admin/api/edge-types/{tid}").json()["data"]["fields"]
    assert fields[0]["fieldType"] == "array"


def test_alarm_schema_array_field(client):
    """告警模板 fields[fieldType='array'] → 成功。"""
    r = client.post("/admin/api/alarm-schemas", json={
        "code": "arr_alarm", "name": "ArrAlarm",
        "fields": [
            {"fieldKey": "tags", "fieldLabel": "标签", "fieldType": "array",
             "defaultValue": "[]"},
        ],
    })
    assert r.status_code == 200, r.text


# ============================================================
# 6. Excel I/O
# ============================================================

def test_excel_export_array_field_default_preserved(client):
    """导出 → array 字段的默认值 JSON 字符串保留在 cell 里。"""
    from io import BytesIO
    from openpyxl import load_workbook

    r = client.post("/admin/api/node-types", json={
        "code": "arr_xl1", "name": "XL1", "category": "physical",
        "fields": [
            {"fieldKey": "tags", "fieldLabel": "标签", "fieldType": "array",
             "defaultValue": '["a","b"]'},
        ],
    })
    tid = r.json()["data"]["id"]

    r = client.post("/admin/api/node-types/export", json={"ids": [tid]})
    assert r.status_code == 200

    wb = load_workbook(BytesIO(r.content))
    sheet = wb["arr_xl1"]
    headers = {cell.value: idx for idx, cell in enumerate(sheet[1], start=1)}
    row2 = sheet[2]
    default_cell = row2[headers["默认值"] - 1]
    type_cell = row2[headers["字段类型"] - 1]
    assert type_cell.value == "array"
    assert default_cell.value == '["a","b"]'


def test_excel_import_array_field_default_parsed(client):
    """导入 cell '[\"a\",\"b\"]'（fieldType=array）→ 默认值落库。"""
    from io import BytesIO
    from openpyxl import Workbook

    wb = Workbook()
    ws1 = wb.active
    ws1.title = "类型汇总"
    ws1.append(["编码", "名称", "分类", "图标", "颜色", "形状",
                "渲染模式", "DN模板", "描述", "创建时间", "更新时间"])
    ws1.append(["xl_imp1", "ImpType", "physical", "", "", "", "none", "", "", "", ""])

    ws2 = wb.create_sheet(title="xl_imp1")
    ws2.append(["字段标识", "显示名称", "字段类型", "最大长度",
                "默认值", "选项", "必填", "排序"])
    ws2.append(["tags", "标签", "array", "", '["a","b"]', "", "否", 0])

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    r = client.post("/admin/api/node-types/import",
                    files={"file": ("t.xlsx", buf.read(),
                                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    assert r.status_code == 200, r.text

    types = client.get("/admin/api/node-types").json()["data"]["items"]
    imp = next(t for t in types if t["code"] == "xl_imp1")
    fields = imp["fields"]
    assert len(fields) == 1
    assert fields[0]["fieldType"] == "array"
    assert fields[0]["defaultValue"] == '["a","b"]'


def test_excel_import_array_invalid_default_rejected(client):
    """导入非法 array default（fieldType=array, defaultValue='abc'）→ errors 收集，该字段被跳过。"""
    from io import BytesIO
    from openpyxl import Workbook

    wb = Workbook()
    ws1 = wb.active
    ws1.title = "类型汇总"
    ws1.append(["编码", "名称", "分类", "图标", "颜色", "形状",
                "渲染模式", "DN模板", "描述", "创建时间", "更新时间"])
    ws1.append(["xl_imp2", "BadImp", "physical", "", "", "", "none", "", "", "", ""])

    ws2 = wb.create_sheet(title="xl_imp2")
    ws2.append(["字段标识", "显示名称", "字段类型", "最大长度",
                "默认值", "选项", "必填", "排序"])
    ws2.append(["tags", "标签", "array", "", "abc", "", "否", 0])

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    r = client.post("/admin/api/node-types/import",
                    files={"file": ("t.xlsx", buf.read(),
                                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    assert r.status_code == 200
    data = r.json()["data"]
    # 字段被跳过，errors 不为空
    assert len(data.get("errors", [])) > 0
```

- [ ] **Step 2: 跑测试，确认全部 FAIL（pattern 不接受 array）**

```bash
cd backend && python -m pytest tests/test_array_field_type.py -xvs 2>&1 | head -30
```

预期：全部 FAIL，错误信息含 `pattern '^(text|number|select|boolean)$'` 之类。

- [ ] **Step 3: 修改 `schemas/node_type.py` 的 6 处 pattern**

把所有 `pattern="^(text|number|select|boolean)$"` 改为 `pattern="^(text|number|select|boolean|array)$"`，涉及 6 个类（NodeTypeFieldInput、NodeTypeFieldCreate、NodeTypeFieldUpdate、EdgeTypeFieldInput、EdgeTypeFieldCreate、EdgeTypeFieldUpdate）。

可用 `sed` 一次替换：

```bash
cd backend && python -c "
import re
p = 'app/admin/schemas/node_type.py'
s = open(p, encoding='utf-8').read()
new = s.replace(
    'pattern=\"^(text|number|select|boolean)\$\"',
    'pattern=\"^(text|number|select|boolean|array)\$\"',
)
open(p, 'w', encoding='utf-8').write(new)
print('replaced count:', s.count('^(text|number|select|boolean)\$'))
"
```

预期输出：`replaced count: 6`

或手动用 Edit 工具批量替换。

- [ ] **Step 4: 修改 `schemas/alarm.py` 的 1 处 pattern**

同样将 `pattern="^(text|number|select|boolean)$"` 改为 `pattern="^(text|number|select|boolean|array)$"`（第 14 行附近的 AlarmSchemaFieldInput）。

- [ ] **Step 5: 在 NodeTypeFieldInput 添加 validate_array_default validator**

`backend/app/admin/schemas/node_type.py` 的 `NodeTypeFieldInput` 类，在现有 `validate_max_length_for_text` 之后加：

```python
    @model_validator(mode='after')
    def validate_array_default(self) -> 'NodeTypeFieldInput':
        if self.field_type != 'array' or not self.default_value:
            return self
        import json
        try:
            v = json.loads(self.default_value)
        except json.JSONDecodeError:
            raise ValueError('array 类型的 default_value 必须是合法 JSON')
        if not isinstance(v, list):
            raise ValueError('array 类型的 default_value 必须是 JSON array')
        return self
```

- [ ] **Step 6: 同样 validator 添加到另外 5 个 schema 类**

在 `schemas/node_type.py` 的 `NodeTypeFieldCreate` / `NodeTypeFieldUpdate` / `EdgeTypeFieldInput` / `EdgeTypeFieldCreate` / `EdgeTypeFieldUpdate` 5 个类中各添加同款 validator。返回类型注解相应改为 `'NodeTypeFieldCreate'` / `'NodeTypeFieldUpdate'` / `'EdgeTypeFieldInput'` / `'EdgeTypeFieldCreate'` / `'EdgeTypeFieldUpdate'`。

- [ ] **Step 7: 在 alarm.py 的 AlarmSchemaFieldInput 添加 validator**

`backend/app/admin/schemas/alarm.py`，在 AlarmSchemaFieldInput 类里加同款 validator（返回类型 `'AlarmSchemaFieldInput'`）。

- [ ] **Step 8: 跑全部测试确认通过**

```bash
cd backend && python -m pytest tests/test_array_field_type.py -xvs
```

预期：14 个全部 PASS。

- [ ] **Step 9: 跑既有测试集确认无回归**

```bash
cd backend && python -m pytest -x
```

预期：全部 PASS。

- [ ] **Step 10: 提交**

```bash
git add backend/app/admin/schemas/node_type.py backend/app/admin/schemas/alarm.py backend/tests/test_array_field_type.py
git commit -m "$(cat <<'EOF'
feat(types): 后端字段类型新增 array

- 7 处 Pydantic pattern 扩展为 ^(text|number|select|boolean|array)$
  - schemas/node_type.py 6 处（Node + Edge 的 Input / Create / Update）
  - schemas/alarm.py 1 处（AlarmSchemaFieldInput）
- 新增 validate_array_default validator：array 类型的 default_value 必须为合法 JSON array
- 14 个测试覆盖 pattern、validator、attrs 存储、跨类型对称、Excel 导入导出
EOF
)"
```

---

## Task 2: 前端 TS 类型联合扩展

**Files:**
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/api/alarmSchema.ts`

- [ ] **Step 1: 修改 types.ts 中的 4 处 fieldType 联合**

`frontend/src/api/types.ts` 中以下 4 个接口的 `fieldType` 字段：

```ts
// 原：'text' | 'number' | 'select' | 'boolean'
// 新：'text' | 'number' | 'select' | 'boolean' | 'array'
```

涉及：
- `NodeTypeFieldItem.fieldType`（约第 9 行）
- `NodeTypeFieldInput.fieldType`（约第 20 行）
- `EdgeTypeFieldItem.fieldType`（约第 44 行）
- `EdgeTypeFieldInput.fieldType`（约第 104 行）

可用 `replace_all` 一次替换：把 `'text' | 'number' | 'select' | 'boolean'` 全替换为 `'text' | 'number' | 'select' | 'boolean' | 'array'`。

- [ ] **Step 2: 修改 alarmSchema.ts 中的 fieldType 联合**

`frontend/src/api/alarmSchema.ts` 中所有 `fieldType` 字段联合（通常 1-3 处）做相同扩展。

```bash
cd frontend && grep -n "'text' | 'number'" src/api/alarmSchema.ts
```

把所有匹配项扩展为 `'text' | 'number' | 'select' | 'boolean' | 'array'`。

- [ ] **Step 3: 验证 TypeScript**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep "api/types\.ts\|api/alarmSchema\.ts"
```

预期：无错误。

- [ ] **Step 4: 提交**

```bash
git add frontend/src/api/types.ts frontend/src/api/alarmSchema.ts
git commit -m "$(cat <<'EOF'
feat(types-api): TS fieldType 联合加 'array'

NodeTypeFieldItem / NodeTypeFieldInput / EdgeTypeFieldItem / EdgeTypeFieldInput
+ AlarmSchema 相关接口的 fieldType 联合扩展 'text' | 'number' | 'select' | 'boolean' | 'array'。

为下游 Task 3-9 的字段编辑器 + 画布属性编辑器解锁 array 选项。
EOF
)"
```

---

## Task 3: 3 个字段编辑器加 array 选项 + Default 校验

**Files:**
- Modify: `frontend/src/components/types/NodeTypeFieldEditor.vue`
- Modify: `frontend/src/components/types/EdgeTypeFieldEditor.vue`
- Modify: `frontend/src/components/alarmSchemas/AlarmSchemaFieldEditor.vue`

三个文件改动几乎完全相同。

### NodeTypeFieldEditor.vue

- [ ] **Step 1: 加 array 选项**

在 `NodeTypeFieldEditor.vue` 找到字段类型 Select（搜 `<Select.Option value="boolean">boolean</Select.Option>`），在其后加：

```vue
<Select.Option value="array">array</Select.Option>
```

- [ ] **Step 2: Default 列 placeholder 区分 array**

找到 Default 列的 `<Input ... placeholder="默认值" ... />`，改为：

```vue
<Input
  :value="record.defaultValue || ''"
  size="small"
  :placeholder="record.fieldType === 'array' ? 'JSON: [\&quot;a\&quot;,\&quot;b\&quot;]' : '默认值'"
  @update:value="(v: string) => updateField(index, 'defaultValue', v || null)"
  @blur="() => validateArrayDefault(record)"
/>
```

（其中 `\&quot;` 是 Vue 模板里的转义引号。如果 prefer 简单写法可以用 `'JSON 数组，如 [a,b]'`。）

- [ ] **Step 3: 在 `<script setup>` 加 validateArrayDefault 函数**

在已有 `updateField` 函数之后加：

```ts
import { message } from 'ant-design-vue'

function validateArrayDefault(field: NodeTypeFieldInput) {
  if (field.fieldType !== 'array' || !field.defaultValue) return
  try {
    const v = JSON.parse(field.defaultValue)
    if (!Array.isArray(v)) {
      message.warning('默认值必须是 JSON array')
    }
  } catch {
    message.warning('默认值 JSON 语法错误')
  }
}
```

注意：如果 `message` 不在现有 import 中需要添加。

- [ ] **Step 4: 验证 TypeScript**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep "NodeTypeFieldEditor"
```

### EdgeTypeFieldEditor.vue

- [ ] **Step 5: 镜像 Step 1-3 改动**

把 `EdgeTypeFieldEditor.vue` 应用与 `NodeTypeFieldEditor.vue` 完全相同的改动，但是把 `NodeTypeFieldInput` 替换为 `EdgeTypeFieldInput`（在 validateArrayDefault 函数签名里）。

- [ ] **Step 6: 验证 TypeScript**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep "EdgeTypeFieldEditor"
```

### AlarmSchemaFieldEditor.vue

- [ ] **Step 7: 镜像 Step 1-3 改动**

把 `AlarmSchemaFieldEditor.vue` 应用相同改动，validateArrayDefault 函数签名用 `AlarmSchemaFieldInput`。

- [ ] **Step 8: 验证 TypeScript**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep "AlarmSchemaFieldEditor"
```

- [ ] **Step 9: 全量 tsc 确认无回归**

```bash
cd frontend && npx tsc --noEmit
```

预期：exit 0。

- [ ] **Step 10: 提交**

```bash
git add frontend/src/components/types/NodeTypeFieldEditor.vue frontend/src/components/types/EdgeTypeFieldEditor.vue frontend/src/components/alarmSchemas/AlarmSchemaFieldEditor.vue
git commit -m "$(cat <<'EOF'
feat(types-editor): 3 个字段编辑器加 array 选项 + Default 失焦校验

- NodeTypeFieldEditor / EdgeTypeFieldEditor / AlarmSchemaFieldEditor 的字段类型 Select 新增 'array' 选项
- array 字段的 Default 列 placeholder 改为 'JSON: ["a","b"]'
- Default 失焦时 JSON.parse 校验，非合法 array toast warning，但不阻止保存（后端兜底）

利用现有 MaxLen/Options 列 :disabled 写法自然让 array 落入禁用分支，无需改禁用逻辑。
EOF
)"
```

---

## Task 4: 新增 ArrayJsonInput.vue 组件

**Files:**
- Create: `frontend/src/components/canvas/ArrayJsonInput.vue`

- [ ] **Step 1: 创建组件文件**

完整内容：

```vue
<script setup lang="ts">
import { computed } from 'vue'
import { Input } from 'ant-design-vue'

const props = defineProps<{
  value: string
  placeholder?: string
}>()

const emit = defineEmits<{
  (e: 'update:value', v: string): void
}>()

const parseError = computed(() => {
  const v = props.value
  if (!v) return ''
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
.array-json-input {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.error-hint {
  font-size: 12px;
  color: #ff4d4f;
}
</style>
```

- [ ] **Step 2: 验证 TypeScript**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep "ArrayJsonInput"
```

预期：无错误（因为没人引用它）。

- [ ] **Step 3: 提交**

```bash
git add frontend/src/components/canvas/ArrayJsonInput.vue
git commit -m "$(cat <<'EOF'
feat(canvas): 新增 ArrayJsonInput 组件

Antd Input.TextArea + auto-size: { minRows: 2, maxRows: 6 } + 实时 JSON.parse 校验：
- 空字符串不报错（由 required 校验处理）
- 非 JSON array → 红边 + "必须是 JSON array"
- JSON 语法错 → 红边 + "JSON 语法错误"
- 不阻止保存，由表单整体校验 + 后端 Pydantic 兜底
- 接口 value / @update:value 与现有 Input 控件一致
EOF
)"
```

---

## Task 5: 新增 fieldValidation.ts helper

**Files:**
- Create: `frontend/src/utils/fieldValidation.ts`

- [ ] **Step 1: 创建 helper 文件**

完整内容：

```ts
import type { NodeTypeFieldItem, EdgeTypeFieldItem } from '@/api/types'
import type { AlarmSchemaFieldItem } from '@/api/alarmSchema'

type FieldLike = Pick<
  NodeTypeFieldItem | EdgeTypeFieldItem | AlarmSchemaFieldItem,
  'fieldKey' | 'fieldType' | 'required'
>

/**
 * 校验整张表单：返回 { [fieldKey]: errorMessage }。
 * - required 字段空值 → '此字段为必填项'
 * - array 字段非合法 JSON array → 'JSON 语法错误' 或 '必须是 JSON array'
 * - 其它类型暂不在前端校验（依赖后端 Pydantic + DB 约束）
 */
export function validateFields(
  fields: FieldLike[],
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
        if (!Array.isArray(parsed)) {
          errs[field.fieldKey] = '必须是 JSON array'
        }
      } catch {
        errs[field.fieldKey] = 'JSON 语法错误'
      }
    }
  }
  return errs
}
```

- [ ] **Step 2: 验证 TypeScript**

```bash
cd frontend && npx tsc --noEmit
```

预期：exit 0。

- [ ] **Step 3: 提交**

```bash
git add frontend/src/utils/fieldValidation.ts
git commit -m "$(cat <<'EOF'
feat(utils): 新增 fieldValidation.validateFields helper

接受 fields[] + formData，返回 { fieldKey: errorMessage } 字典：
- required 字段空值 → '此字段为必填项'
- array 字段非合法 JSON array → 'JSON 语法错误' 或 '必须是 JSON array'

为 4 个画布属性编辑器（NodeAttrsModal / NodeAttrsPanel / EdgeAttrsPanel / NodeAlarmsTab）
统一校验逻辑，避免 4 处复制粘贴。
EOF
)"
```

---

## Task 6: NodeAttrsModal 集成 array 渲染 + 校验 helper

**Files:**
- Modify: `frontend/src/components/canvas/NodeAttrsModal.vue`

- [ ] **Step 1: 加 ArrayJsonInput import**

在现有 `import { Modal, Form, Input, InputNumber, Select, Switch } from 'ant-design-vue'` 之后加：

```ts
import ArrayJsonInput from './ArrayJsonInput.vue'
import { validateFields } from '@/utils/fieldValidation'
```

- [ ] **Step 2: 在 fieldType 分支末尾加 array 分支**

找到 template 里 `<template v-else-if="field.fieldType === 'boolean'">` 块，在其结束 `</template>` 之后加：

```vue
<template v-else-if="field.fieldType === 'array'">
  <ArrayJsonInput
    :value="getFieldValue(field.fieldKey)"
    @update:value="(v: string) => setFieldValue(field.fieldKey, v)"
    :placeholder="field.defaultValue || '[]'"
  />
</template>
```

- [ ] **Step 3: 替换 handleCreate 中的校验逻辑**

找到 `handleCreate` 函数（约第 78-101 行）的"校验必填字段"循环：

```ts
const newErrors: Record<string, string> = {}
for (const field of fields.value) {
  if (field.required && !formData.value[field.fieldKey]) {
    newErrors[field.fieldKey] = '此字段为必填项'
  }
}
```

替换为：

```ts
const newErrors = validateFields(fields.value, formData.value)
```

后面的 `if (Object.keys(newErrors).length > 0)` 逻辑保留不变。

- [ ] **Step 4: 验证 TypeScript**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep "NodeAttrsModal"
```

- [ ] **Step 5: 提交**

```bash
git add frontend/src/components/canvas/NodeAttrsModal.vue
git commit -m "$(cat <<'EOF'
feat(canvas): NodeAttrsModal 支持 array 字段

- 加 ArrayJsonInput 分支渲染
- handleCreate 的 required 循环替换为 validateFields helper（同时校验 array JSON 合法性）
EOF
)"
```

---

## Task 7: NodeAttrsPanel 集成 array 渲染 + 校验 helper

**Files:**
- Modify: `frontend/src/components/canvas/NodeAttrsPanel.vue`

- [ ] **Step 1: 加 import**

在现有 `import { Form, Input, InputNumber, Select, Switch, Button, Spin, Tabs, Tooltip } from 'ant-design-vue'` 之后加：

```ts
import ArrayJsonInput from './ArrayJsonInput.vue'
import { validateFields } from '@/utils/fieldValidation'
```

- [ ] **Step 2: 加 fieldErrors ref（用于显示校验错误）**

如果文件里还没有 fieldErrors，在已有 ref 声明附近加：

```ts
const fieldErrors = ref<Record<string, string>>({})
```

- [ ] **Step 3: 在 Form.Item 上绑定 validate-status + help**

找到 fields 循环的 `<Form.Item v-for="field in fields" :key="field.id">`，改为：

```vue
<Form.Item
  v-for="field in fields"
  :key="field.id"
  :validate-status="fieldErrors[field.fieldKey] ? 'error' : ''"
  :help="fieldErrors[field.fieldKey]"
>
```

`#label` slot 保留不变。

- [ ] **Step 4: 在 fieldType 分支末尾加 array 分支**

找到 template 里 `<template v-else-if="field.fieldType === 'boolean'">` 块，在其结束之后加：

```vue
<template v-else-if="field.fieldType === 'array'">
  <ArrayJsonInput
    :value="getFieldValue(field.fieldKey)"
    @update:value="(v: string) => setFieldValue(field.fieldKey, v)"
    placeholder="[]"
  />
</template>
```

- [ ] **Step 5: 在 handleSave 加 array 校验**

找到 `handleSave` 函数开头，在 `saving.value = true` 之前加：

```ts
const errs = validateFields(fields.value, formData.value)
if (Object.keys(errs).length > 0) {
  fieldErrors.value = errs
  return
}
fieldErrors.value = {}
```

- [ ] **Step 6: 验证 TypeScript**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep "NodeAttrsPanel"
```

- [ ] **Step 7: 提交**

```bash
git add frontend/src/components/canvas/NodeAttrsPanel.vue
git commit -m "$(cat <<'EOF'
feat(canvas): NodeAttrsPanel 支持 array 字段

- 加 ArrayJsonInput 分支渲染
- handleSave 前用 validateFields 校验（required + array JSON）
- Form.Item 绑定 fieldErrors 显示错误状态
EOF
)"
```

---

## Task 8: EdgeAttrsPanel 集成 array 渲染 + 校验 helper

**Files:**
- Modify: `frontend/src/components/canvas/EdgeAttrsPanel.vue`

- [ ] **Step 1: 加 import**

在现有 import 中追加：

```ts
import ArrayJsonInput from './ArrayJsonInput.vue'
import { validateFields } from '@/utils/fieldValidation'
```

- [ ] **Step 2: 加 fieldErrors ref**

```ts
const fieldErrors = ref<Record<string, string>>({})
```

- [ ] **Step 3: 在 Form.Item 上绑定 validate-status + help**

找到 fields 循环的 `<Form.Item v-for="field in fields" :key="field.id" :label="field.fieldLabel">`，改为：

```vue
<Form.Item
  v-for="field in fields"
  :key="field.id"
  :label="field.fieldLabel"
  :validate-status="fieldErrors[field.fieldKey] ? 'error' : ''"
  :help="fieldErrors[field.fieldKey]"
>
```

- [ ] **Step 4: 加 array 分支**

找到 `<template v-else-if="field.fieldType === 'boolean'">` 之后加：

```vue
<template v-else-if="field.fieldType === 'array'">
  <ArrayJsonInput
    :value="getFieldValue(field.fieldKey)"
    @update:value="(v: string) => setFieldValue(field.fieldKey, v)"
    placeholder="[]"
  />
</template>
```

- [ ] **Step 5: 在 handleSave 加 array 校验**

在 `handleSave` 开头加：

```ts
const errs = validateFields(fields.value, formData.value)
if (Object.keys(errs).length > 0) {
  fieldErrors.value = errs
  return
}
fieldErrors.value = {}
```

- [ ] **Step 6: 验证 TypeScript**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep "EdgeAttrsPanel"
```

- [ ] **Step 7: 提交**

```bash
git add frontend/src/components/canvas/EdgeAttrsPanel.vue
git commit -m "feat(canvas): EdgeAttrsPanel 支持 array 字段（镜像 NodeAttrsPanel）"
```

---

## Task 9: NodeAlarmsTab 集成 array 渲染 + 校验

**Files:**
- Modify: `frontend/src/components/canvas/NodeAlarmsTab.vue`

NodeAlarmsTab 是告警卡片 Collapse 列表，每个告警卡片里有多个字段。array 字段渲染同款。

- [ ] **Step 1: 加 import**

在 import 块中加：

```ts
import ArrayJsonInput from './ArrayJsonInput.vue'
import { validateFields } from '@/utils/fieldValidation'
```

- [ ] **Step 2: 在 template 的告警字段循环里加 array 分支**

NodeAlarmsTab 现有 4 个分支（约 162-188 行）：

```vue
<template v-if="f.fieldType === 'text'">
  <Input ... />
</template>
<template v-else-if="f.fieldType === 'number'">
  <InputNumber ... />
</template>
<template v-else-if="f.fieldType === 'select'">
  <Select ...>...</Select>
</template>
<template v-else-if="f.fieldType === 'boolean'">
  <Switch ... />
</template>
```

在 `boolean` 分支之后加：

```vue
<template v-else-if="f.fieldType === 'array'">
  <ArrayJsonInput
    :value="getAlarmFieldValue(alarm, f.fieldKey)"
    @update:value="(v: string) => setAlarmFieldValue(alarm, f.fieldKey, v)"
    placeholder="[]"
  />
</template>
```

注意：变量名可能与上面伪代码不同（实际代码可能用 `alarm.attrs[f.fieldKey]` 等），按现有 text 分支的写法对照。

- [ ] **Step 3: 在 saveDirty 函数里加 array 校验**

找到 saveDirty 函数（如有 `text` 类型 maxLength 校验的位置），在保存前用 validateFields 校验告警的字段：

具体来说，找到现有的 maxLength 校验（约第 98 行 `if (f.fieldType === 'text' && f.maxLength && ...)`），在其同一循环里追加：

```ts
if (f.fieldType === 'array' && v) {
  try {
    const parsed = JSON.parse(v)
    if (!Array.isArray(parsed)) {
      // 加入 fieldErrors
      return
    }
  } catch {
    // 加入 fieldErrors
    return
  }
}
```

实际嵌入方式以现有结构为准——如果现有有完整的"字段循环 + 累积错误"结构则附加分支；如果是简单的提前 return 风格则模仿。

- [ ] **Step 4: 验证 TypeScript**

```bash
cd frontend && npx tsc --noEmit
```

- [ ] **Step 5: 提交**

```bash
git add frontend/src/components/canvas/NodeAlarmsTab.vue
git commit -m "feat(canvas): NodeAlarmsTab 告警字段支持 array"
```

---

## 完成检查清单

- [ ] 后端测试：`cd backend && python -m pytest -x` 全过
- [ ] 前端 TS 编译：`cd frontend && npx tsc --noEmit` exit 0
- [ ] 前端 smoke 测试（spec §6.2 共 17 步）：
  - 1-6 类型管理 3 个 Tab（节点 / 边 / 告警）的 array 选项 + Default 校验
  - 7-13 画布创建节点 Modal 的 array textarea 渲染 + 实时校验 + 必填校验
  - 14-17 抽屉编辑 + 边属性面板 + 告警卡片的 array 字段一致体验

---

## 自审记录

**Spec coverage:**
- §3.1 Pydantic patterns 7 处：Task 1 Step 3-4 ✓
- §3.2 validate_array_default validator：Task 1 Step 5-7 ✓
- §3.3 max_length 无需改：Task 1 隐含 ✓
- §3.4 存储 K-V 表不变：Task 1 隐含（无 DB 改动）✓
- §3.5 set_attrs 不校验：Task 1 Step 1 测试覆盖（只验证 string 存储）✓
- §3.6 Excel I/O：Task 1 Step 1 的 export/import 测试 ✓
- §4.1 TS 联合扩展：Task 2 ✓
- §4.2 Select 选项：Task 3 ✓
- §4.3 列禁用：无需改（用 Task 3 现有的 :disabled 写法）✓
- §4.4 Default placeholder + 校验：Task 3 ✓
- §5.2 ArrayJsonInput：Task 4 ✓
- §5.3 4 个组件 array 分支：Task 6-9 ✓
- §5.4 fieldValidation helper：Task 5 + Task 6-9 引用 ✓
- §5.5 默认值应用：无需改（现有 watch 块直接生效）✓
- §6.1 后端测试 14 个：Task 1 Step 1 全列 ✓
- §6.2 前端 smoke 17 步：完成检查清单引用 ✓

**Placeholder scan:** 无 TBD/TODO。Task 9 Step 3 因 NodeAlarmsTab 现有 saveDirty 函数结构不完全可控，给出"以现有结构为准"的指引，但提供了完整的校验代码。

**Type consistency:**
- `validateFields` 在 Task 5 定义，Task 6/7/8 引用 ✓
- `ArrayJsonInput` 在 Task 4 创建，Task 6/7/8/9 引用 ✓
- `placeholder="[]"` 与 ArrayJsonInput 的 placeholder prop 一致 ✓
- `validateArrayDefault` 在 Task 3 三处定义，签名按各自类型（NodeTypeFieldInput / EdgeTypeFieldInput / AlarmSchemaFieldInput）✓
- `field_type='array'` 字符串值在 Task 1/3/4/5/6-9 一致 ✓
