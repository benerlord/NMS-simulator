# 告警模板增强 — 设计方案

> **状态：** 设计稿 / 待实施
> **日期：** 2026-06-12
> **前序：** `docs/superpowers/specs/2026-06-10-node-alarms-design.md`（V1 节点告警系统已交付）
> **关联：** `docs/superpowers/plans/2026-06-10-node-alarms.md`（V1 实施计划，commit `ab48ab3`）

---

## 1. 背景

V1 节点告警系统上线后，3 个 UX / 功能痛点暴露：

1. **字段编辑器卡片占空间** — `AlarmSchemaFieldEditor.vue` 每字段一张约 200px 高的卡片，10+ 字段时垂直空间爆炸；"+ 新增字段"按钮在最上面，加完几个再加要滚到顶部
2. **告警字段值需要与节点字段联动** — 真实 NMS 场景下，告警里的"网元名称"、"网元 IP"等字段应自动从对应节点取值，而不是手填或写死 default_value
3. **告警卡片标题固定取第一个字段** — `NodeAlarmsTab.vue` 用 sort_order 最小的字段作为 Collapse 头部，用户无法配置展示哪个字段更有信息量

---

## 2. 关键设计决策（已对齐）

| # | 决策点 | 选择 | 理由 |
|---|--------|------|------|
| 1 | Mapping 自动填值时机 | **Snapshot 模式** | 与现有 default_value 语义一致；告警代表"发生时刻快照"符合真实 NMS |
| 2 | Mapping 目标字段范围 | **节点系统字段 + 节点自定义字段（C 方案）** | 兼顾稳健（5 个系统字段始终可用）与灵活（自定义字段覆盖业务字段） |
| 3 | Mapping / default_value / 用户传值优先级 | **用户传值 > Mapping > default_value > NULL（A 方案）** | 符合"用户显式 > 系统智能 > 兜底"直觉 |
| 4 | 字段编辑器布局 | **紧凑 Antd Table + 内联编辑（A 方案）** | 一行 ~40px，符合"管理界面"直觉；配合 sticky 顶部 + 底部双"+新增"按钮 |
| 5 | 告警卡片标题字段 | **模板配置单字段下拉（A 方案）** | YAGNI；模板字符串/多字段拼接是潜在未来需求，不在当前痛点 |

---

## 3. 数据模型

### 3.1 `alarm_schema_fields` 新增 1 列

| 列 | 类型 | 说明 |
|----|------|------|
| `mapping_target` | TEXT NULL | 映射到节点字段的标识符。可空（不映射）。值为系统字段（`name`/`dn`/`id`/`status`/`group_id`）或自定义字段 key（如 `ip`） |

幂等迁移：

```python
try:
    conn.execute("ALTER TABLE alarm_schema_fields ADD COLUMN mapping_target TEXT")
except sqlite3.OperationalError:
    pass
```

### 3.2 `alarm_schemas` 新增 1 列

| 列 | 类型 | 说明 |
|----|------|------|
| `display_field_key` | TEXT NULL | 指定告警卡片头部展示的字段 key。引用本模板下某个 `field_key`。未配置或字段被删 → fallback 到 sort_order 最小字段 |

幂等迁移：

```python
try:
    conn.execute("ALTER TABLE alarm_schemas ADD COLUMN display_field_key TEXT")
except sqlite3.OperationalError:
    pass
```

### 3.3 系统字段常量

后端 `backend/app/admin/_alarm_utils.py`：

```python
NODE_SYSTEM_FIELDS = {"name", "dn", "id", "status", "group_id"}
```

前端对应常量供分组下拉使用，由 `GET /admin/api/node-fields/available` 端点返回。

### 3.4 不变量

- `mapping_target` 是 TEXT 字符串，不做强外键校验（不同 node_type 字段可能不一致；找不到就 NULL 兜底）
- `display_field_key` 软引用，模板字段被删后值保留，前端 fallback
- 现有 `default_value` 语义不变
- 现有 `alarms` CTE 结构不变 —— mapping 只是创建时填值来源，存储后就是普通 attr

---

## 4. 后端

### 4.1 Pydantic Schemas 改动

`backend/app/admin/schemas/alarm.py`：

- `AlarmSchemaFieldCreate` / `AlarmSchemaFieldItem` 新增 `mapping_target: Optional[str] = None`
- `AlarmSchemaFieldCreate` 加 validator：若 `mapping_target` 非空，必须匹配 `^[A-Za-z_][A-Za-z0-9_]*$`
- `AlarmSchemaCreate` / `AlarmSchemaUpdate` / `AlarmSchemaItem` / `AlarmSchemaDetail` 新增 `display_field_key: Optional[str] = None`

### 4.2 公共工具 `_alarm_utils.py`（新文件）

```python
# backend/app/admin/_alarm_utils.py
NODE_SYSTEM_FIELDS = {"name", "dn", "id", "status", "group_id"}


def build_alarm_attrs(conn, node_id, fields, user_provided=None):
    """
    Resolve attr values for an alarm. Precedence: user > mapping > default > NULL.
    fields: iterable of dict-like with keys (field_key, mapping_target, default_value)
    Returns: dict[field_key -> value]
    """
    user_provided = user_provided or {}
    result = {}
    for f in fields:
        key = f["field_key"]
        # 1. user explicit value
        if key in user_provided and user_provided[key] is not None:
            result[key] = user_provided[key]
            continue
        # 2. mapping_target
        mapping = f["mapping_target"]
        if mapping:
            val = resolve_mapping(conn, node_id, mapping)
            if val is not None:
                result[key] = val
                continue
        # 3. default_value
        if f["default_value"] is not None:
            result[key] = f["default_value"]
        # 4. else skip (NULL)
    return result


def resolve_mapping(conn, node_id, mapping_target):
    if mapping_target in NODE_SYSTEM_FIELDS:
        row = conn.execute(
            f"SELECT {mapping_target} AS v FROM nodes WHERE id = ?", (node_id,)
        ).fetchone()
        return row["v"] if row else None
    # custom: node_attrs lookup
    row = conn.execute(
        "SELECT value FROM node_attrs WHERE node_id = ? AND field_key = ?",
        (node_id, mapping_target),
    ).fetchone()
    return row["value"] if row else None
```

**SQL 注入安全**：`mapping_target` 在 Pydantic 层校验为 `^[A-Za-z_][A-Za-z0-9_]*$`，DB 层进 SELECT 列名拼接安全（系统字段集合也是固定的 5 个白名单，内联拼接前已过 set 比对）。

### 4.3 三处调用点改造

| 文件 | 函数 | 改动 |
|------|------|------|
| `admin/node.py` | `create_node` | 把当前手写 default_value 循环替换为 `build_alarm_attrs(conn, node_id, fields)`，SELECT fields 时加上 `mapping_target` 列 |
| `admin/node_group.py` | materialize 的 `_flush_nodes` | 同上，每个物化节点调用；预查询 fields 列表加 `mapping_target` 列 |
| `admin/node_alarm.py` | `create_node_alarm` | 把当前 merged 逻辑替换为 `build_alarm_attrs(conn, node_id, fields, user_provided=data.attrs)` |

### 4.4 alarm_schema router 改动

`admin/alarm_schema.py`：

- POST / PUT 写入 `mapping_target`（field 级）和 `display_field_key`（schema 级）
- GET 详情返回新字段
- 现有 `_validate_field_keys` 不变；额外校验 `mapping_target` 仅做 `is_valid_ident` 检查（不强制存在性）
- 现有 `_FIXED_COLS` 冲突检查与新增的 `mapping_target` 校验不冲突（field_key 不能冲突，mapping_target 可以指向 fixed col）

### 4.5 新增端点 `GET /admin/api/node-fields/available`

放在哪个 router？放在新文件 `admin/node_fields.py`（独立模块）或追加到 `admin/node_type.py`。**选择独立模块** —— 该端点不属于 node_type CRUD 语义。

```python
# backend/app/admin/node_fields.py
from fastapi import APIRouter
from app.db.connection import connect
from app.admin._alarm_utils import NODE_SYSTEM_FIELDS

router = APIRouter(prefix="/admin/api", tags=["节点字段"])


@router.get("/node-fields/available")
def list_available_node_fields() -> dict:
    with connect() as conn:
        rows = conn.execute(
            "SELECT DISTINCT field_key FROM node_type_fields ORDER BY field_key"
        ).fetchall()
        custom = [r["field_key"] for r in rows]
    return {
        "code": 0,
        "data": {
            "systemFields": sorted(NODE_SYSTEM_FIELDS),
            "customFields": custom,
        },
        "message": "ok",
    }
```

`main.py` 挂载该 router。

### 4.6 CTE 不变

`cte_builder.py` 的 `_build_alarms_cte` 完全不动 —— mapping 只是创建时填值来源，存储后就是普通 attr，pivot 行为不变。

---

## 5. 前端

### 5.1 `AlarmSchemaFieldEditor.vue` 重写 — 紧凑表格

**布局：** Antd `Table` 渲染字段列表。列：

| 列 | 编辑控件 | 宽度 |
|----|----------|------|
| Key | `<Input>` | 100px |
| Label | `<Input>` | 120px |
| Type | `<Select>` (text/number/select/boolean) | 90px |
| MaxLen | `<InputNumber>` (type=text 启用，其他禁用) | 80px |
| Default | `<Input>` | 100px |
| Options | `<Input>` (type=select 启用) + tooltip | 120px |
| Required | `<Switch>` | 60px |
| Mapping | `<Select show-search allow-clear>` 分组：系统字段/自定义字段 | 140px |
| Sort | `<InputNumber>` | 60px |
| 操作 | 上移↑ / 下移↓ / 删除 icon | 80px |

**工具栏：**
- 表格顶部：`<Affix :offset-top="0">` 包裹"+ 新增字段"按钮（modal 内表格滚动时按钮跟随固定）
- 表格底部：再放一个"+ 新增字段"按钮（新增后自动滚到底）

**Mapping 下拉**：组件级 ref 缓存。首次打开任一行的 mapping 单元格时调 `nodeFieldsApi.available()` 一次。Modal 关闭重开时重新拉取（避免缓存陈旧）。

**字段验证**：用单元格内 `<Form.Item validate-status>` 标红，无需破坏行布局。

**移除：** 当前的卡片包裹、`<Collapse>` 折叠、上下大段 `<Form.Item>` 都不要。

### 5.2 `AlarmSchemaModal.vue` 加 `displayFieldKey` 下拉

在 Form 中"告警字段"上方加：

```vue
<Form.Item label="卡片标题字段">
  <Select
    v-model:value="form.displayFieldKey"
    allow-clear
    placeholder="默认：sort_order 最小的字段"
  >
    <Select.Option v-for="f in fields" :key="f.fieldKey" :value="f.fieldKey">
      {{ f.fieldLabel }} ({{ f.fieldKey }})
    </Select.Option>
  </Select>
</Form.Item>
```

选项实时由 `fields` ref 生成（字段增删时下拉项联动）。提交时 `displayFieldKey` 随其他字段一起 POST/PUT。

### 5.3 `NodeAlarmsTab.vue` Collapse 头部用 displayFieldKey

新增 ref `schema = ref<AlarmSchemaDetail | null>(null)`。`loadAll()` 在 `alarmSchemaApi.get(sid)` 之后 `schema.value = d`。

修改 `getCollapseHeader`：

```typescript
function getCollapseHeader(alarm: NodeAlarmItem): string {
  const displayKey = schema.value?.displayFieldKey
  let field = displayKey
    ? schemaFields.value.find(f => f.fieldKey === displayKey)
    : null
  if (!field) field = schemaFields.value[0]
  if (!field) return `告警 #${alarm.alarmIndex}`
  const v = alarm.attrs[field.fieldKey] || ''
  return `${v || '(空)'}  #${alarm.alarmIndex}`
}
```

### 5.4 API SDK 改动

**`api/alarmSchema.ts`：**
- `AlarmSchemaFieldItem` / `AlarmSchemaFieldInput` 加 `mappingTarget?: string | null`
- `AlarmSchemaItem` / `AlarmSchemaDetail` / `AlarmSchemaCreate` / `AlarmSchemaUpdate` 加 `displayFieldKey?: string | null`

**`api/nodeFields.ts`（新文件）：**

```typescript
import { apiGet } from './http'

export interface AvailableNodeFields {
  systemFields: string[]
  customFields: string[]
}

export const nodeFieldsApi = {
  available: () => apiGet<AvailableNodeFields>('/node-fields/available'),
}
```

### 5.5 影响范围

| 文件 | 改动 |
|------|------|
| `components/alarmSchemas/AlarmSchemaFieldEditor.vue` | **全量重写**为 Table 布局 |
| `components/alarmSchemas/AlarmSchemaModal.vue` | 加 `displayFieldKey` 下拉 + 在 fields 上方 |
| `components/canvas/NodeAlarmsTab.vue` | 加 `schema` ref + 改 `getCollapseHeader` |
| `api/alarmSchema.ts` | 加 2 个字段（mappingTarget / displayFieldKey） |
| `api/nodeFields.ts` | **新文件** |

---

## 6. 错误处理

| 场景 | 后端响应 | 前端体验 |
|------|----------|----------|
| `mapping_target` 非法标识符（特殊字符） | 400 + 中文说明 | 单元格 validate-status="error" 标红 |
| `display_field_key` 指向不存在的字段 | 不报错 | 前端 fallback 到第一个字段 |
| `mapping_target` 指向节点上不存在的 attr | 不报错 | NULL 兜底，转 default_value，再转 NULL |
| 节点字段未设但 mapping 引用 | 不报错 | 同上 |

---

## 7. 测试策略

### 7.1 后端 pytest 新增用例

- `_build_alarm_utils` 单测：用户传值 / mapping / default 三层优先级
- `resolve_mapping` 单测：系统字段查 nodes 列；自定义字段查 node_attrs；都不存在返 NULL
- POST `/alarm-schemas` 接收 mapping_target + display_field_key 写入正确
- POST `/alarm-schemas` mapping_target 非法字符返 400
- PUT `/alarm-schemas/{id}` 全量替换 fields 时 mapping_target / display_field_key 正确刷新
- 节点创建（拓扑挂模板）自动告警的 attrs 按"mapping > default"填充（验证一个有 mapping 的字段被节点值填充）
- 节点组 materialize 同上
- POST `/nodes/{id}/alarms` 手动创建：用户传值 > mapping > default 优先级正确
- `GET /node-fields/available` 返回 5 个系统字段 + DISTINCT 自定义字段

### 7.2 前端手动 smoke

按 CLAUDE.md "测试完成后关闭进程"原则执行：

1. 类型管理 → 告警模板 → 新建/编辑 → 字段编辑器是表格布局，"+ 新增字段"按钮顶部 sticky + 底部双放
2. 字段编辑器加 10 个字段，垂直空间 ≤ 500px 可见，无需翻滚才能加新字段
3. 模板编辑界面有"卡片标题字段"下拉，选某个字段
4. 字段的 Mapping 下拉显示「系统字段」（5 个）+「自定义字段」（按 DB 实际 distinct）分组
5. 节点类型先建 `mgmt_ip` 字段；告警模板 `alarm_ip` 字段映射到 `mgmt_ip`
6. 拓扑绑该模板 → 拖一个节点设 `mgmt_ip=192.168.1.1` → 创建告警 → 看到 `alarm_ip=192.168.1.1`
7. 节点设 `mgmt_ip=空` → 创建告警 → `alarm_ip` 走 default_value 或 NULL
8. 模板配置 displayFieldKey=`alarm_id` → NodeAlarmsTab Collapse 标题显示 alarm_id 的值
9. 删除 displayFieldKey 指向的字段 → 标题 fallback 到 sort_order 最小字段
10. 用户手动 POST 告警传 `alarm_ip=10.0.0.1` → 告警值是 10.0.0.1（不被 mapping 覆盖）

---

## 8. 实施顺序（建议 4 步）

1. **后端 DB + Schema** — 2 个 ALTER TABLE；Pydantic 字段 + 校验
2. **后端逻辑** — `_alarm_utils.py` 工具 + 3 个调用点接入 + alarm_schema router 写入新字段 + `node_fields.py` 新 router
3. **前端 API SDK** — `alarmSchema.ts` 加字段 + `nodeFields.ts` 新文件
4. **前端 UI** — `AlarmSchemaFieldEditor.vue` 重写 + `AlarmSchemaModal.vue` 加下拉 + `NodeAlarmsTab.vue` Collapse 头部改造

---

## 9. 受影响文件清单

**后端：**
- `backend/app/db/migrations.py` — 2 个新 ALTER TABLE
- `backend/app/admin/_alarm_utils.py` — **新文件**（build_alarm_attrs / resolve_mapping / NODE_SYSTEM_FIELDS）
- `backend/app/admin/node_fields.py` — **新文件**（/node-fields/available）
- `backend/app/admin/schemas/alarm.py` — 加 mapping_target / display_field_key 字段 + 校验
- `backend/app/admin/alarm_schema.py` — POST/PUT/GET 处理新字段
- `backend/app/admin/node.py` — 用 build_alarm_attrs 替代手写循环
- `backend/app/admin/node_group.py` — 同上
- `backend/app/admin/node_alarm.py` — 同上
- `backend/app/main.py` — 挂 node_fields_router

**前端：**
- `frontend/src/api/alarmSchema.ts` — 加 mappingTarget / displayFieldKey
- `frontend/src/api/nodeFields.ts` — **新文件**
- `frontend/src/components/alarmSchemas/AlarmSchemaFieldEditor.vue` — **全量重写**为 Table
- `frontend/src/components/alarmSchemas/AlarmSchemaModal.vue` — 加 displayFieldKey 下拉
- `frontend/src/components/canvas/NodeAlarmsTab.vue` — Collapse header 用 displayFieldKey

---

## 10. 后续可扩展点（不在本期范围）

- 模板字符串方式的 display（如 `{alarm_id} - {severity}`）
- 多字段拼接 display
- 拓扑级 mapping override
- mapping 实时联动模式（Live link）
- mapping target 强存在性校验
