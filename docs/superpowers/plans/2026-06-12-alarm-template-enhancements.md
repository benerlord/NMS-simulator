# 告警模板增强 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在已交付的 V1 节点告警系统基础上叠加 3 个 UX/功能增强 —— 字段编辑器紧凑化、告警字段↔节点字段 snapshot 映射、告警卡片标题字段可在模板中配置。

**Architecture:** 数据模型增量：`alarm_schema_fields` 加 `mapping_target` 列、`alarm_schemas` 加 `display_field_key` 列；新建 `backend/app/admin/_alarm_utils.py` 公共工具承载"用户传值 > mapping > default > NULL"的填值逻辑，3 个调用点（`node.py` create / `node_group.py` materialize / `node_alarm.py` POST）统一接入；新增 `GET /admin/api/node-fields/available` 端点供前端 mapping 下拉用；前端字段编辑器全量重写为 Antd Table 紧凑布局，Modal 加 displayFieldKey 下拉，NodeAlarmsTab Collapse 头部按 displayFieldKey + fallback 渲染。

**Tech Stack:** FastAPI / SQLite WAL / Pydantic v2 CamelModel / Vue 3.5 `<script setup>` / Ant Design Vue 4 / pytest（已配置）

**关联文档：** `docs/superpowers/specs/2026-06-12-alarm-template-enhancements-design.md`

---

## 任务总览

| # | 任务 | 类型 | 依赖 |
|---|------|------|------|
| 1 | DB migrations — `mapping_target` + `display_field_key` 2 列 | 后端 | - |
| 2 | Pydantic schemas — alarm.py 加字段 + 校验 | 后端 | 1 |
| 3 | `_alarm_utils.py` 工具 + 单测 | 后端 | 2 |
| 4 | alarm_schema router 收发新字段 | 后端 | 2 |
| 5 | 3 个调用点接入 build_alarm_attrs | 后端 | 3 |
| 6 | `node_fields.py` 新 router | 后端 | - |
| 7 | 前端 API SDK — alarmSchema 加字段 + nodeFields 新文件 | 前端 | 4, 6 |
| 8 | `AlarmSchemaFieldEditor.vue` 重写为紧凑表格 | 前端 | 7 |
| 9 | `AlarmSchemaModal.vue` 加 displayFieldKey 下拉 | 前端 | 7 |
| 10 | `NodeAlarmsTab.vue` Collapse 标题用 displayFieldKey | 前端 | 7 |

---

## Task 1: DB Migrations — 2 个新列

**Files:**
- Modify: `backend/app/db/migrations.py`
- Test: `backend/tests/test_migrations_alarm_enhancements.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_migrations_alarm_enhancements.py`：

```python
def test_alarm_schema_fields_has_mapping_target(conn):
    rows = conn.execute("PRAGMA table_info(alarm_schema_fields)").fetchall()
    cols = {r["name"] for r in rows}
    assert "mapping_target" in cols


def test_alarm_schemas_has_display_field_key(conn):
    rows = conn.execute("PRAGMA table_info(alarm_schemas)").fetchall()
    cols = {r["name"] for r in rows}
    assert "display_field_key" in cols


def test_mapping_target_can_be_null(conn):
    conn.execute(
        "INSERT INTO alarm_schemas (id, code, name) VALUES ('as_1', 'a', 'A')"
    )
    conn.execute(
        "INSERT INTO alarm_schema_fields (alarm_schema_id, field_key, field_label, field_type) "
        "VALUES ('as_1', 'k1', 'L1', 'text')"
    )
    r = conn.execute(
        "SELECT mapping_target FROM alarm_schema_fields WHERE field_key = 'k1'"
    ).fetchone()
    assert r["mapping_target"] is None


def test_display_field_key_can_be_null(conn):
    conn.execute(
        "INSERT INTO alarm_schemas (id, code, name) VALUES ('as_2', 'b', 'B')"
    )
    r = conn.execute(
        "SELECT display_field_key FROM alarm_schemas WHERE id = 'as_2'"
    ).fetchone()
    assert r["display_field_key"] is None
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_migrations_alarm_enhancements.py -v`
Expected: FAIL — 列不存在

- [ ] **Step 3: 实现 migrations**

修改 `backend/app/db/migrations.py`。在 `run_migrations()` 函数末尾（已有的 `node_type_fields.max_length` ALTER 之后）追加：

```python
    # Idempotent column addition for alarm_schema_fields.mapping_target
    try:
        conn.execute("ALTER TABLE alarm_schema_fields ADD COLUMN mapping_target TEXT")
    except sqlite3.OperationalError:
        pass
    # Idempotent column addition for alarm_schemas.display_field_key
    try:
        conn.execute("ALTER TABLE alarm_schemas ADD COLUMN display_field_key TEXT")
    except sqlite3.OperationalError:
        pass
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_migrations_alarm_enhancements.py -v`
Expected: 4 passed

- [ ] **Step 5: 全量回归**

Run: `cd backend && python -m pytest tests/ -v`
Expected: all green (existing 42 + new 4 = 46)

- [ ] **Step 6: 提交**

```bash
git add backend/app/db/migrations.py backend/tests/test_migrations_alarm_enhancements.py
git commit -m "feat(alarm-v2): 数据库迁移 — mapping_target + display_field_key 2 列"
```

---

## Task 2: Pydantic Schemas — 加字段 + 校验

**Files:**
- Modify: `backend/app/admin/schemas/alarm.py`
- Test: `backend/tests/test_alarm_enhanced_schemas.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_alarm_enhanced_schemas.py`：

```python
import pytest
from pydantic import ValidationError
from app.admin.schemas import (
    AlarmSchemaFieldCreate,
    AlarmSchemaCreate,
)


def test_field_mapping_target_accepts_valid_ident():
    f = AlarmSchemaFieldCreate(
        field_key="x", field_label="X", field_type="number",
        mapping_target="ip",
    )
    assert f.mapping_target == "ip"


def test_field_mapping_target_accepts_none():
    f = AlarmSchemaFieldCreate(
        field_key="x", field_label="X", field_type="number",
    )
    assert f.mapping_target is None


def test_field_mapping_target_rejects_invalid_chars():
    with pytest.raises(ValidationError):
        AlarmSchemaFieldCreate(
            field_key="x", field_label="X", field_type="number",
            mapping_target="bad-key!",
        )


def test_field_mapping_target_rejects_leading_digit():
    with pytest.raises(ValidationError):
        AlarmSchemaFieldCreate(
            field_key="x", field_label="X", field_type="number",
            mapping_target="1invalid",
        )


def test_alarm_schema_create_with_display_field_key():
    a = AlarmSchemaCreate(
        code="c1", name="C1", display_field_key="alarm_id",
    )
    assert a.display_field_key == "alarm_id"


def test_alarm_schema_create_display_field_key_defaults_none():
    a = AlarmSchemaCreate(code="c1", name="C1")
    assert a.display_field_key is None


def test_camel_alias_for_mapping_target_and_display_field_key():
    f = AlarmSchemaFieldCreate(
        fieldKey="x", fieldLabel="X", fieldType="number",
        mappingTarget="ip",
    )
    dump = f.model_dump(by_alias=True)
    assert "mappingTarget" in dump
    assert dump["mappingTarget"] == "ip"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_alarm_enhanced_schemas.py -v`
Expected: FAIL — fields not exist

- [ ] **Step 3: 修改 `backend/app/admin/schemas/alarm.py`**

读现有文件确认结构。在 `AlarmSchemaFieldCreate` 类中追加 `mapping_target` 字段 + 校验。完整修改：

3a. 在文件顶部 import 加入 `field_validator`（如未有）：
```python
from pydantic import Field, model_validator, field_validator
```

3b. 在 `AlarmSchemaFieldCreate` 类（现有的 `validate_max_length_for_text` 之前或之后）加：

```python
    mapping_target: Optional[str] = Field(default=None, max_length=50)

    @field_validator('mapping_target')
    @classmethod
    def validate_mapping_target(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == '':
            return None
        import re
        if not re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', v):
            raise ValueError('mapping_target 必须是合法标识符（字母/数字/下划线，以字母或下划线开头）')
        return v
```

3c. 在 `AlarmSchemaFieldItem` 类中追加：

```python
    mapping_target: Optional[str]
```

3d. 在 `AlarmSchemaCreate` 类中追加（紧跟 description 之后）：

```python
    display_field_key: Optional[str] = Field(default=None, max_length=50)
```

3e. 在 `AlarmSchemaUpdate` 类中追加：

```python
    display_field_key: Optional[str] = Field(default=None, max_length=50)
```

3f. 在 `AlarmSchemaItem` 类中追加：

```python
    display_field_key: Optional[str]
```

注意：`AlarmSchemaDetail` 继承自 `AlarmSchemaItem`，自动获得 `display_field_key`。

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_alarm_enhanced_schemas.py -v`
Expected: 7 passed

- [ ] **Step 5: 全量回归**

Run: `cd backend && python -m pytest tests/ -v`
Expected: all green (46 prior + 7 new = 53)

如有现有测试因 `AlarmSchemaFieldItem` / `AlarmSchemaItem` 多了字段而失败（不太可能，因为新字段都是 Optional 默认 None），修复后再跑。

- [ ] **Step 6: 提交**

```bash
git add backend/app/admin/schemas/alarm.py backend/tests/test_alarm_enhanced_schemas.py
git commit -m "feat(alarm-v2): Pydantic schemas — mapping_target + display_field_key + 校验"
```

---

## Task 3: `_alarm_utils.py` 工具 + 单测

**Files:**
- Create: `backend/app/admin/_alarm_utils.py`
- Test: `backend/tests/test_alarm_utils.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_alarm_utils.py`：

```python
import sqlite3
from app.db.migrations import run_migrations
from app.admin._alarm_utils import (
    NODE_SYSTEM_FIELDS,
    build_alarm_attrs,
    resolve_mapping,
)


def _make_db_with_node():
    conn = sqlite3.connect(":memory:", isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    run_migrations(conn)
    conn.execute("INSERT INTO topologies (id, name) VALUES ('t1', 'T1')")
    conn.execute("INSERT INTO node_types (id, code, name, category) VALUES ('nt1', 'sw', 'SW', 'switch')")
    conn.execute(
        "INSERT INTO nodes (id, topology_id, node_type_id, name, dn, status) "
        "VALUES ('n1', 't1', 'nt1', 'sw-001', 'dn-001', 'online')"
    )
    conn.execute(
        "INSERT INTO node_attrs (node_id, field_key, value) VALUES ('n1', 'ip', '192.168.1.1')"
    )
    return conn


def test_node_system_fields_contains_expected_columns():
    assert NODE_SYSTEM_FIELDS == {"name", "dn", "id", "status", "group_id"}


def test_resolve_mapping_system_field_name():
    conn = _make_db_with_node()
    assert resolve_mapping(conn, "n1", "name") == "sw-001"


def test_resolve_mapping_system_field_dn():
    conn = _make_db_with_node()
    assert resolve_mapping(conn, "n1", "dn") == "dn-001"


def test_resolve_mapping_system_field_status():
    conn = _make_db_with_node()
    assert resolve_mapping(conn, "n1", "status") == "online"


def test_resolve_mapping_custom_field_found():
    conn = _make_db_with_node()
    assert resolve_mapping(conn, "n1", "ip") == "192.168.1.1"


def test_resolve_mapping_custom_field_not_found():
    conn = _make_db_with_node()
    assert resolve_mapping(conn, "n1", "nonexistent") is None


def test_resolve_mapping_node_not_exist():
    conn = _make_db_with_node()
    assert resolve_mapping(conn, "node_missing", "name") is None


def test_build_alarm_attrs_user_value_wins():
    conn = _make_db_with_node()
    fields = [
        {"field_key": "node_ip", "mapping_target": "ip", "default_value": "0.0.0.0"},
    ]
    result = build_alarm_attrs(conn, "n1", fields, user_provided={"node_ip": "USER"})
    assert result == {"node_ip": "USER"}


def test_build_alarm_attrs_mapping_wins_over_default():
    conn = _make_db_with_node()
    fields = [
        {"field_key": "node_ip", "mapping_target": "ip", "default_value": "0.0.0.0"},
    ]
    result = build_alarm_attrs(conn, "n1", fields)
    assert result == {"node_ip": "192.168.1.1"}


def test_build_alarm_attrs_default_when_no_mapping():
    conn = _make_db_with_node()
    fields = [
        {"field_key": "severity", "mapping_target": None, "default_value": "minor"},
    ]
    result = build_alarm_attrs(conn, "n1", fields)
    assert result == {"severity": "minor"}


def test_build_alarm_attrs_default_when_mapping_target_missing():
    conn = _make_db_with_node()
    fields = [
        {"field_key": "node_x", "mapping_target": "nonexistent_field", "default_value": "DEF"},
    ]
    result = build_alarm_attrs(conn, "n1", fields)
    assert result == {"node_x": "DEF"}


def test_build_alarm_attrs_skip_when_all_null():
    conn = _make_db_with_node()
    fields = [
        {"field_key": "k", "mapping_target": None, "default_value": None},
    ]
    result = build_alarm_attrs(conn, "n1", fields)
    assert result == {}


def test_build_alarm_attrs_user_value_none_falls_through_to_mapping():
    conn = _make_db_with_node()
    fields = [
        {"field_key": "node_ip", "mapping_target": "ip", "default_value": "0.0.0.0"},
    ]
    # User explicitly passed None — treated as "not provided"
    result = build_alarm_attrs(conn, "n1", fields, user_provided={"node_ip": None})
    assert result == {"node_ip": "192.168.1.1"}


def test_build_alarm_attrs_mixed_fields():
    conn = _make_db_with_node()
    fields = [
        {"field_key": "node_name", "mapping_target": "name", "default_value": None},
        {"field_key": "severity", "mapping_target": None, "default_value": "minor"},
        {"field_key": "user_field", "mapping_target": None, "default_value": "FALLBACK"},
    ]
    result = build_alarm_attrs(conn, "n1", fields, user_provided={"user_field": "USER"})
    assert result == {"node_name": "sw-001", "severity": "minor", "user_field": "USER"}
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_alarm_utils.py -v`
Expected: FAIL — module not exist

- [ ] **Step 3: 创建 `backend/app/admin/_alarm_utils.py`**

```python
"""Common helpers for alarm attr value resolution.

Precedence: user-provided value > mapping_target > default_value > NULL.
"""

NODE_SYSTEM_FIELDS = {"name", "dn", "id", "status", "group_id"}


def resolve_mapping(conn, node_id, mapping_target):
    """Look up the value for a mapping_target on a node.

    System fields are read from nodes.<column>. Custom fields are read from
    node_attrs by field_key. Returns None if node or field is missing.

    mapping_target is assumed to be a validated identifier (alphanumeric + underscore,
    leading letter or underscore) — enforced by Pydantic at the schema layer.
    For system fields, the value is additionally gated by NODE_SYSTEM_FIELDS set
    membership before any SQL interpolation, so column-name interpolation is safe.
    """
    if mapping_target in NODE_SYSTEM_FIELDS:
        row = conn.execute(
            f"SELECT {mapping_target} AS v FROM nodes WHERE id = ?", (node_id,)
        ).fetchone()
        return row["v"] if row else None
    row = conn.execute(
        "SELECT value FROM node_attrs WHERE node_id = ? AND field_key = ?",
        (node_id, mapping_target),
    ).fetchone()
    return row["value"] if row else None


def build_alarm_attrs(conn, node_id, fields, user_provided=None):
    """Resolve attr values for an alarm using the precedence:
    user_provided > mapping_target > default_value > NULL (skip).

    fields: iterable of dict-like with keys (field_key, mapping_target, default_value).
    user_provided: optional dict[field_key -> value]. None values are treated as
                   "not provided" so they fall through to mapping/default.
    Returns: dict[field_key -> value], omitting fields whose final value is None.
    """
    user_provided = user_provided or {}
    result = {}
    for f in fields:
        key = f["field_key"]
        # 1. user explicit value (non-None)
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
        # 4. else skip (no entry in result)
    return result
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_alarm_utils.py -v`
Expected: 14 passed

- [ ] **Step 5: 全量回归**

Run: `cd backend && python -m pytest tests/ -v`
Expected: 67 passed (53 prior + 14 new)

- [ ] **Step 6: 提交**

```bash
git add backend/app/admin/_alarm_utils.py backend/tests/test_alarm_utils.py
git commit -m "feat(alarm-v2): _alarm_utils 公共工具 — build_alarm_attrs + resolve_mapping"
```

---

## Task 4: alarm_schema Router 收发新字段

**Files:**
- Modify: `backend/app/admin/alarm_schema.py`
- Test: `backend/tests/test_alarm_schema_router_v2.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_alarm_schema_router_v2.py`：

```python
def test_create_with_mapping_target_and_display_field_key(client):
    payload = {
        "code": "huawei",
        "name": "华为",
        "displayFieldKey": "alarm_id",
        "fields": [
            {"fieldKey": "alarm_id", "fieldLabel": "ID", "fieldType": "text", "maxLength": 64, "sortOrder": 0},
            {"fieldKey": "node_ip", "fieldLabel": "网元IP", "fieldType": "text", "maxLength": 50, "mappingTarget": "ip", "sortOrder": 1},
        ],
    }
    r = client.post("/admin/api/alarm-schemas", json=payload)
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["displayFieldKey"] == "alarm_id"
    node_ip_field = next(f for f in d["fields"] if f["fieldKey"] == "node_ip")
    assert node_ip_field["mappingTarget"] == "ip"


def test_create_with_invalid_mapping_target_returns_400(client):
    r = client.post("/admin/api/alarm-schemas", json={
        "code": "c1", "name": "n1",
        "fields": [{"fieldKey": "x", "fieldLabel": "X", "fieldType": "number", "mappingTarget": "bad-key!"}],
    })
    assert r.status_code == 422  # Pydantic validation


def test_get_alarm_schema_returns_new_fields(client):
    r = client.post("/admin/api/alarm-schemas", json={
        "code": "c2", "name": "n2",
        "displayFieldKey": "k1",
        "fields": [{"fieldKey": "k1", "fieldLabel": "L1", "fieldType": "number", "mappingTarget": "name"}],
    })
    sid = r.json()["data"]["id"]
    r = client.get(f"/admin/api/alarm-schemas/{sid}")
    d = r.json()["data"]
    assert d["displayFieldKey"] == "k1"
    assert d["fields"][0]["mappingTarget"] == "name"


def test_update_replaces_mapping_target_and_display_field_key(client):
    r = client.post("/admin/api/alarm-schemas", json={
        "code": "c3", "name": "n3",
        "displayFieldKey": "k1",
        "fields": [{"fieldKey": "k1", "fieldLabel": "L1", "fieldType": "number", "mappingTarget": "name"}],
    })
    sid = r.json()["data"]["id"]
    r = client.put(f"/admin/api/alarm-schemas/{sid}", json={
        "displayFieldKey": "k2",
        "fields": [{"fieldKey": "k2", "fieldLabel": "L2", "fieldType": "number", "mappingTarget": "status"}],
    })
    d = r.json()["data"]
    assert d["displayFieldKey"] == "k2"
    assert d["fields"][0]["mappingTarget"] == "status"


def test_create_without_new_fields_works(client):
    """Backward compatibility — schemas without mapping_target / display_field_key still work."""
    r = client.post("/admin/api/alarm-schemas", json={
        "code": "c4", "name": "n4",
        "fields": [{"fieldKey": "k", "fieldLabel": "K", "fieldType": "number"}],
    })
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["displayFieldKey"] is None
    assert d["fields"][0]["mappingTarget"] is None
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_alarm_schema_router_v2.py -v`
Expected: FAIL — DB/router doesn't handle new fields yet

- [ ] **Step 3: 修改 `backend/app/admin/alarm_schema.py`**

3a. 修改 `_get_fields()` SELECT 列表 + Pydantic 构造：

```python
def _get_fields(conn, schema_id: str) -> list[AlarmSchemaFieldItem]:
    rows = conn.execute(
        "SELECT * FROM alarm_schema_fields WHERE alarm_schema_id = ? ORDER BY sort_order, id",
        (schema_id,),
    ).fetchall()
    return [
        AlarmSchemaFieldItem(
            id=r["id"],
            alarm_schema_id=r["alarm_schema_id"],
            field_key=r["field_key"],
            field_label=r["field_label"],
            field_type=r["field_type"],
            max_length=r["max_length"],
            default_value=r["default_value"],
            options=r["options"],
            required=bool(r["required"]),
            sort_order=r["sort_order"],
            mapping_target=r["mapping_target"],
        )
        for r in rows
    ]
```

3b. 修改 `_row_to_detail()` 返回 `display_field_key`：

```python
def _row_to_detail(conn, row) -> AlarmSchemaDetail:
    return AlarmSchemaDetail(
        id=row["id"],
        code=row["code"],
        name=row["name"],
        description=row["description"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        display_field_key=row["display_field_key"],
        fields=_get_fields(conn, row["id"]),
    )
```

3c. 修改 `list_alarm_schemas()` 中构造 `AlarmSchemaItem` 时加 `display_field_key=r["display_field_key"]`。

3d. 修改 `create_alarm_schema()`：

- INSERT 主表 SQL 加 `display_field_key` 列：

```python
        conn.execute(
            "INSERT INTO alarm_schemas (id, code, name, description, display_field_key) "
            "VALUES (?, ?, ?, ?, ?)",
            (sid, data.code, data.name, data.description, data.display_field_key),
        )
```

- INSERT 字段 SQL 加 `mapping_target` 列：

```python
        for f in data.fields:
            conn.execute(
                "INSERT INTO alarm_schema_fields "
                "(alarm_schema_id, field_key, field_label, field_type, max_length, "
                " default_value, options, required, sort_order, mapping_target) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (sid, f.field_key, f.field_label, f.field_type, f.max_length,
                 f.default_value, f.options, int(f.required), f.sort_order, f.mapping_target),
            )
```

3e. 修改 `update_alarm_schema()`：

- 在 `if data.name is not None:` / `if data.description is not None:` 块之后追加：

```python
        if 'display_field_key' in data.model_fields_set:
            sets.append("display_field_key = ?")
            params.append(data.display_field_key)
```

注意：用 `model_fields_set` 判断字段是否被显式传入。这样 PUT 时传 `displayFieldKey: null` 可以清空数据库值，不传则保持原样。`data.description` 的现有逻辑用 `is not None` 不允许清空 —— 是已知限制，本期不动。

- 字段全量替换部分的 INSERT 同样加 `mapping_target` 列：

```python
            for f in data.fields:
                conn.execute(
                    "INSERT INTO alarm_schema_fields "
                    "(alarm_schema_id, field_key, field_label, field_type, max_length, "
                    " default_value, options, required, sort_order, mapping_target) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (schema_id, f.field_key, f.field_label, f.field_type, f.max_length,
                     f.default_value, f.options, int(f.required), f.sort_order, f.mapping_target),
                )
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_alarm_schema_router_v2.py tests/test_alarm_schema_router.py -v`
Expected: 5 (v2) + 7 (v1) passed

- [ ] **Step 5: 全量回归**

Run: `cd backend && python -m pytest tests/ -v`
Expected: 72 passed (67 prior + 5 new)

- [ ] **Step 6: 提交**

```bash
git add backend/app/admin/alarm_schema.py backend/tests/test_alarm_schema_router_v2.py
git commit -m "feat(alarm-v2): alarm_schema router 收发 mapping_target + display_field_key"
```

---

## Task 5: 3 个调用点接入 build_alarm_attrs

**Files:**
- Modify: `backend/app/admin/node.py`
- Modify: `backend/app/admin/node_group.py`
- Modify: `backend/app/admin/node_alarm.py`
- Test: `backend/tests/test_alarm_mapping_e2e.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_alarm_mapping_e2e.py`：

```python
import sqlite3
from app.core.config import settings


def _setup_schema_with_mapping(client):
    """Schema with: alarm_id (no mapping, default 'AID-DEF'), node_ip (maps to ip), node_name (maps to name)."""
    r = client.post("/admin/api/alarm-schemas", json={
        "code": "demo", "name": "Demo",
        "fields": [
            {"fieldKey": "alarm_id", "fieldLabel": "ID", "fieldType": "text", "maxLength": 64, "defaultValue": "AID-DEF", "sortOrder": 0},
            {"fieldKey": "node_ip", "fieldLabel": "IP", "fieldType": "text", "maxLength": 50, "mappingTarget": "ip", "sortOrder": 1},
            {"fieldKey": "node_name", "fieldLabel": "Name", "fieldType": "text", "maxLength": 100, "mappingTarget": "name", "sortOrder": 2},
        ],
    })
    return r.json()["data"]["id"]


def _setup_node_type_and_topology(client, sid):
    r = client.post("/admin/api/topologies", json={"name": "T"})
    tid = r.json()["data"]["id"]
    client.patch(f"/admin/api/topologies/{tid}/alarm-schema", json={"alarmSchemaId": sid, "clearExisting": False})
    r = client.post("/admin/api/node-types", json={"code": "sw", "name": "SW", "category": "switch"})
    ntid = r.json()["data"]["id"]
    return tid, ntid


def test_create_node_alarm_fills_mapping_from_system_field(client):
    sid = _setup_schema_with_mapping(client)
    tid, ntid = _setup_node_type_and_topology(client, sid)
    # Create node with name = "router-01"
    r = client.post(f"/admin/api/topologies/{tid}/nodes", json={
        "nodeTypeId": ntid, "name": "router-01"
    })
    nid = r.json()["data"]["id"]
    # Verify auto-alarm got node_name = "router-01" from mapping
    alarms = client.get(f"/admin/api/nodes/{nid}/alarms").json()["data"]
    assert len(alarms) == 1
    assert alarms[0]["attrs"]["node_name"] == "router-01"
    assert alarms[0]["attrs"]["alarm_id"] == "AID-DEF"  # default kicks in


def test_create_node_alarm_fills_mapping_from_custom_attr(client):
    sid = _setup_schema_with_mapping(client)
    tid, ntid = _setup_node_type_and_topology(client, sid)
    # Create node + set ip attr
    r = client.post(f"/admin/api/topologies/{tid}/nodes", json={
        "nodeTypeId": ntid, "name": "n1"
    })
    nid = r.json()["data"]["id"]
    client.put(f"/admin/api/nodes/{nid}/attrs", json={"attrs": {"ip": "10.0.0.5"}})
    # Manually create a second alarm — should pick up ip
    r = client.post(f"/admin/api/nodes/{nid}/alarms", json={})
    assert r.status_code == 200
    assert r.json()["data"]["attrs"]["node_ip"] == "10.0.0.5"


def test_manual_alarm_user_attrs_override_mapping(client):
    sid = _setup_schema_with_mapping(client)
    tid, ntid = _setup_node_type_and_topology(client, sid)
    r = client.post(f"/admin/api/topologies/{tid}/nodes", json={
        "nodeTypeId": ntid, "name": "n2"
    })
    nid = r.json()["data"]["id"]
    # User explicitly provides node_name
    r = client.post(f"/admin/api/nodes/{nid}/alarms", json={
        "attrs": {"node_name": "USER-OVERRIDE"}
    })
    assert r.json()["data"]["attrs"]["node_name"] == "USER-OVERRIDE"


def test_materialize_uses_mapping(client):
    sid = _setup_schema_with_mapping(client)
    tid, ntid = _setup_node_type_and_topology(client, sid)
    # Create node group, materialize
    r = client.post(f"/admin/api/topologies/{tid}/node-groups", json={
        "nodeTypeId": ntid, "groupName": "g", "nodeCount": 3,
        "nameTemplate": "{group}-{i:03d}",
        "attrStrategies": [], "edgeStrategies": [],
    })
    gid = r.json()["data"]["id"]
    client.post(f"/admin/api/node-groups/{gid}/materialize")

    # Verify each materialized node's alarm has node_name filled from mapping
    with sqlite3.connect(str(settings.db_path)) as c:
        c.row_factory = sqlite3.Row
        rows = c.execute(
            "SELECT n.name, aa.value AS node_name_val "
            "FROM nodes n "
            "JOIN node_alarms a ON a.node_id = n.id "
            "JOIN node_alarm_attrs aa ON aa.alarm_id = a.id AND aa.field_key = 'node_name' "
            "WHERE n.topology_id = ?",
            (tid,),
        ).fetchall()
    assert len(rows) == 3
    for r in rows:
        assert r["node_name_val"] == r["name"]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_alarm_mapping_e2e.py -v`
Expected: FAIL — mapping not applied

- [ ] **Step 3: 改 `admin/node.py` `create_node`**

定位现有自动告警注入区块（包含 `topo["alarm_schema_id"]` 检查和手写 `default_value` 循环）。替换为：

```python
        # Auto-insert 1 default alarm if topology has alarm_schema bound
        if topo["alarm_schema_id"]:
            from app.admin._alarm_utils import build_alarm_attrs
            sid = topo["alarm_schema_id"]
            fields = conn.execute(
                "SELECT field_key, mapping_target, default_value FROM alarm_schema_fields "
                "WHERE alarm_schema_id = ? ORDER BY sort_order, id",
                (sid,),
            ).fetchall()
            aid = f"alm_{uuid.uuid4().hex[:12]}"
            conn.execute(
                "INSERT INTO node_alarms (id, node_id, alarm_index) VALUES (?, ?, 1)",
                (aid, node_id),
            )
            attrs = build_alarm_attrs(conn, node_id, fields)
            for k, v in attrs.items():
                conn.execute(
                    "INSERT INTO node_alarm_attrs (alarm_id, field_key, value) VALUES (?, ?, ?)",
                    (aid, k, v),
                )
```

将 `from app.admin._alarm_utils import build_alarm_attrs` 上移到文件顶部 import 区。

- [ ] **Step 4: 改 `admin/node_group.py` materialize**

定位 `_flush_nodes` 之前的 alarm 预查询区块。改成：

```python
        # Pre-query alarm schema fields for the topology
        alarm_schema_id: Optional[str] = None
        alarm_fields: list[dict] = []  # rows used by build_alarm_attrs
        with connect() as _ac:
            _row = _ac.execute(
                "SELECT alarm_schema_id FROM topologies WHERE id = ?", (topology_id,)
            ).fetchone()
            if _row and _row["alarm_schema_id"]:
                alarm_schema_id = _row["alarm_schema_id"]
                _fields = _ac.execute(
                    "SELECT field_key, mapping_target, default_value FROM alarm_schema_fields "
                    "WHERE alarm_schema_id = ? "
                    "ORDER BY sort_order, id",
                    (alarm_schema_id,),
                ).fetchall()
                alarm_fields = [dict(f) for f in _fields]
```

注意：移除了 V1 中 `AND default_value IS NOT NULL` 过滤 —— 现在所有字段都进列表，由 `build_alarm_attrs` 内部根据 mapping/default 决定。

把 `alarm_default_fields` 重命名为 `alarm_fields`（行内可变更现有变量名以保持一致）。

在 `_flush_nodes` 内部，替换 V1 中的"alarm_index=1 + 手写 default_value 循环"为：

```python
                # Auto-insert 1 default alarm per node when topology has alarm_schema bound
                if alarm_schema_id:
                    aid = f"alm_{uuid.uuid4().hex[:12]}"
                    conn.execute(
                        "INSERT INTO node_alarms (id, node_id, alarm_index) VALUES (?, ?, 1)",
                        (aid, nid),
                    )
                    attrs = build_alarm_attrs(conn, nid, alarm_fields)
                    for k, v in attrs.items():
                        conn.execute(
                            "INSERT INTO node_alarm_attrs (alarm_id, field_key, value) VALUES (?, ?, ?)",
                            (aid, k, v),
                        )
```

加 `from app.admin._alarm_utils import build_alarm_attrs` 到 import 区。

- [ ] **Step 5: 改 `admin/node_alarm.py` create_node_alarm**

定位 `_get_alarm_schema_for_node` 返回字段后的合并逻辑（"Merge user-provided attrs with default_value fallbacks"）。替换为：

```python
        # Build attrs via shared helper: user > mapping > default > skip
        merged = build_alarm_attrs(conn, node_id, fields, user_provided=data.attrs)

        _validate_attr_lengths(fields, merged)

        aid = _new_alarm_id()
        # ... 现有 INSERT 节点告警 + 写 attrs 行为不变
```

修改 `_get_alarm_schema_for_node` 的 SELECT 列表，加上 `mapping_target`：

```python
def _get_alarm_schema_for_node(conn, node_id: str):
    """Return (alarm_schema_id, [field rows]); (None, []) if topology has no schema."""
    row = conn.execute(
        "SELECT t.alarm_schema_id AS sid FROM nodes n "
        "JOIN topologies t ON t.id = n.topology_id "
        "WHERE n.id = ?",
        (node_id,),
    ).fetchone()
    if not row or not row["sid"]:
        return None, []
    fields = conn.execute(
        "SELECT field_key, field_type, max_length, default_value, required, mapping_target "
        "FROM alarm_schema_fields WHERE alarm_schema_id = ? ORDER BY sort_order, id",
        (row["sid"],),
    ).fetchall()
    return row["sid"], fields
```

加 `from app.admin._alarm_utils import build_alarm_attrs` 到顶部 import 区。

- [ ] **Step 6: 运行新测试确认通过**

Run: `cd backend && python -m pytest tests/test_alarm_mapping_e2e.py -v`
Expected: 4 passed

- [ ] **Step 7: 全量回归**

Run: `cd backend && python -m pytest tests/ -v`
Expected: 76 passed (72 prior + 4 new)

如果旧测试（特别是 `test_node_auto_alarm.py` / `test_materialize_alarms.py` / `test_node_alarm_router.py`）有失败，检查 SELECT 列表是否漏了 `mapping_target`。

- [ ] **Step 8: 提交**

```bash
git add backend/app/admin/node.py backend/app/admin/node_group.py backend/app/admin/node_alarm.py backend/tests/test_alarm_mapping_e2e.py
git commit -m "feat(alarm-v2): 3 个告警创建路径接入 build_alarm_attrs（mapping 优先级）"
```

---

## Task 6: `node_fields.py` 新 Router

**Files:**
- Create: `backend/app/admin/node_fields.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_node_fields_router.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_node_fields_router.py`：

```python
def test_node_fields_available_returns_system_fields(client):
    r = client.get("/admin/api/node-fields/available")
    assert r.status_code == 200
    data = r.json()["data"]
    assert set(data["systemFields"]) == {"name", "dn", "id", "status", "group_id"}


def test_node_fields_available_returns_custom_fields(client):
    # Create node type with custom fields
    r = client.post("/admin/api/node-types", json={
        "code": "sw", "name": "SW", "category": "switch",
        "fields": [
            {"fieldKey": "ip", "fieldLabel": "IP", "fieldType": "text", "maxLength": 50},
            {"fieldKey": "manufacturer", "fieldLabel": "厂商", "fieldType": "text", "maxLength": 100},
        ],
    })
    if r.status_code != 200:
        # Older node-types create may not accept fields inline; try field endpoint
        ntid = client.post("/admin/api/node-types", json={"code": "sw", "name": "SW", "category": "switch"}).json()["data"]["id"]
        client.post(f"/admin/api/node-types/{ntid}/fields", json={"fieldKey": "ip", "fieldLabel": "IP", "fieldType": "text", "maxLength": 50})
        client.post(f"/admin/api/node-types/{ntid}/fields", json={"fieldKey": "manufacturer", "fieldLabel": "厂商", "fieldType": "text", "maxLength": 100})

    r = client.get("/admin/api/node-fields/available")
    data = r.json()["data"]
    assert "ip" in data["customFields"]
    assert "manufacturer" in data["customFields"]


def test_node_fields_available_dedupes_custom(client):
    """If 2 node types both have 'ip' field, custom_fields contains 'ip' only once."""
    # Create two node types with same custom field
    nt1 = client.post("/admin/api/node-types", json={"code": "sw", "name": "SW", "category": "switch"}).json()["data"]["id"]
    nt2 = client.post("/admin/api/node-types", json={"code": "rt", "name": "RT", "category": "router"}).json()["data"]["id"]
    for ntid in (nt1, nt2):
        client.post(f"/admin/api/node-types/{ntid}/fields", json={"fieldKey": "ip", "fieldLabel": "IP", "fieldType": "text", "maxLength": 50})

    r = client.get("/admin/api/node-fields/available")
    customs = r.json()["data"]["customFields"]
    assert customs.count("ip") == 1


def test_node_fields_available_empty_custom_when_no_types(client):
    r = client.get("/admin/api/node-fields/available")
    data = r.json()["data"]
    assert data["customFields"] == []
    assert len(data["systemFields"]) == 5
```

注意：测试 2 和 3 使用了 `POST /admin/api/node-types/{ntid}/fields` 路径来加字段。如果实际端点不是这个路径，需要在测试运行时调整 —— 但 Task 6 主要验证 `node_fields/available` 端点本身，custom 字段来源是 DB 直接 SELECT，所以你可以改测试用直接 SQL 插入字段：

```python
import sqlite3
from app.core.config import settings as _s
def _add_field(node_type_id, fk):
    with sqlite3.connect(str(_s.db_path), isolation_level=None) as c:
        c.execute(
            "INSERT INTO node_type_fields (node_type_id, field_key, field_label, field_type, max_length) "
            "VALUES (?, ?, ?, 'text', 50)",
            (node_type_id, fk, fk.upper()),
        )
```

然后测试 2/3 改用 `_add_field(ntid, "ip")` 等。这是更可靠的选择 —— 如果你不确定字段创建端点路径，直接走 SQL。

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_node_fields_router.py -v`
Expected: FAIL — 404 (route not mounted)

- [ ] **Step 3: 创建 `backend/app/admin/node_fields.py`**

```python
"""Endpoint to enumerate available node fields for alarm field mapping UI."""

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

- [ ] **Step 4: 挂载 router**

修改 `backend/app/main.py`，在 `from app.admin.node_alarm import router as node_alarm_router` 之后加：

```python
from app.admin.node_fields import router as node_fields_router
```

并在 `app.include_router(node_alarm_router)` 之后加：

```python
app.include_router(node_fields_router)
```

- [ ] **Step 5: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_node_fields_router.py -v`
Expected: 4 passed

- [ ] **Step 6: 全量回归**

Run: `cd backend && python -m pytest tests/ -v`
Expected: 80 passed (76 prior + 4 new)

- [ ] **Step 7: 提交**

```bash
git add backend/app/admin/node_fields.py backend/app/main.py backend/tests/test_node_fields_router.py
git commit -m "feat(alarm-v2): /node-fields/available 端点 — 系统字段 + 自定义字段去重"
```

---

## Task 7: 前端 API SDK — alarmSchema 加字段 + nodeFields 新文件

**Files:**
- Modify: `frontend/src/api/alarmSchema.ts`
- Create: `frontend/src/api/nodeFields.ts`

- [ ] **Step 1: 修改 `frontend/src/api/alarmSchema.ts`**

在 `AlarmSchemaFieldItem` 中追加：

```typescript
  mappingTarget?: string | null
```

在 `AlarmSchemaFieldInput` 中追加：

```typescript
  mappingTarget?: string | null
```

在 `AlarmSchemaItem` 中追加：

```typescript
  displayFieldKey?: string | null
```

在 `AlarmSchemaCreate` 中追加：

```typescript
  displayFieldKey?: string | null
```

在 `AlarmSchemaUpdate` 中追加：

```typescript
  displayFieldKey?: string | null
```

注意：`AlarmSchemaDetail extends AlarmSchemaItem`，自动获得 `displayFieldKey`。

- [ ] **Step 2: 创建 `frontend/src/api/nodeFields.ts`**

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

- [ ] **Step 3: TypeScript 编译**

Run: `cd frontend && npx vue-tsc --noEmit`
Expected: 零错误

- [ ] **Step 4: 提交**

```bash
git add frontend/src/api/alarmSchema.ts frontend/src/api/nodeFields.ts
git commit -m "feat(alarm-v2): 前端 SDK — alarmSchema 加 mappingTarget/displayFieldKey + nodeFields"
```

---

## Task 8: `AlarmSchemaFieldEditor.vue` 重写为紧凑表格

**Files:**
- Modify: `frontend/src/components/alarmSchemas/AlarmSchemaFieldEditor.vue`（全量重写）

- [ ] **Step 1: 读现有文件**

先用 Read 工具看现有 `AlarmSchemaFieldEditor.vue` 了解 props/emits（应该是 `v-model:fields`）。

- [ ] **Step 2: 全量重写**

替换文件内容为：

```vue
<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import {
  Table, Input, InputNumber, Select, Switch, Button, Tooltip, Affix, Form,
} from 'ant-design-vue'
import {
  PlusOutlined, DeleteOutlined, ArrowUpOutlined, ArrowDownOutlined,
} from '@ant-design/icons-vue'
import type { AlarmSchemaFieldInput } from '@/api/alarmSchema'
import { nodeFieldsApi, type AvailableNodeFields } from '@/api/nodeFields'

const props = defineProps<{
  fields: AlarmSchemaFieldInput[]
}>()

const emit = defineEmits<{
  (e: 'update:fields', v: AlarmSchemaFieldInput[]): void
}>()

const localFields = computed({
  get: () => props.fields,
  set: (v) => emit('update:fields', v),
})

const availableFields = ref<AvailableNodeFields>({ systemFields: [], customFields: [] })

onMounted(async () => {
  try {
    availableFields.value = await nodeFieldsApi.available()
  } catch {
    availableFields.value = { systemFields: [], customFields: [] }
  }
})

function addField() {
  const newField: AlarmSchemaFieldInput = {
    fieldKey: '',
    fieldLabel: '',
    fieldType: 'text',
    maxLength: 50,
    defaultValue: undefined,
    options: undefined,
    required: false,
    sortOrder: localFields.value.length,
    mappingTarget: undefined,
  }
  emit('update:fields', [...localFields.value, newField])
}

function removeField(index: number) {
  const next = localFields.value.filter((_, i) => i !== index)
  emit('update:fields', next)
}

function moveUp(index: number) {
  if (index === 0) return
  const next = [...localFields.value]
  ;[next[index - 1], next[index]] = [next[index], next[index - 1]]
  emit('update:fields', next)
}

function moveDown(index: number) {
  if (index === localFields.value.length - 1) return
  const next = [...localFields.value]
  ;[next[index], next[index + 1]] = [next[index + 1], next[index]]
  emit('update:fields', next)
}

function updateField(index: number, key: keyof AlarmSchemaFieldInput, value: any) {
  const next = [...localFields.value]
  next[index] = { ...next[index], [key]: value }
  emit('update:fields', next)
}

const columns = [
  { title: 'Key', dataIndex: 'fieldKey', key: 'fieldKey', width: 100 },
  { title: 'Label', dataIndex: 'fieldLabel', key: 'fieldLabel', width: 120 },
  { title: 'Type', dataIndex: 'fieldType', key: 'fieldType', width: 100 },
  { title: 'MaxLen', dataIndex: 'maxLength', key: 'maxLength', width: 80 },
  { title: 'Default', dataIndex: 'defaultValue', key: 'defaultValue', width: 100 },
  { title: 'Options', dataIndex: 'options', key: 'options', width: 120 },
  { title: 'Required', dataIndex: 'required', key: 'required', width: 70 },
  { title: 'Mapping', dataIndex: 'mappingTarget', key: 'mappingTarget', width: 140 },
  { title: 'Sort', dataIndex: 'sortOrder', key: 'sortOrder', width: 60 },
  { title: '操作', key: 'actions', width: 90, fixed: 'right' },
]
</script>

<template>
  <div class="alarm-field-editor">
    <Affix :offset-top="0">
      <div class="toolbar toolbar-top">
        <Button type="primary" size="small" @click="addField">
          <PlusOutlined /> 新增字段
        </Button>
        <span class="hint">{{ localFields.length }} 个字段</span>
      </div>
    </Affix>

    <Table
      :columns="columns"
      :data-source="localFields"
      :pagination="false"
      row-key="fieldKey"
      size="small"
      :scroll="{ x: 1000 }"
    >
      <template #bodyCell="{ column, index, record }">
        <template v-if="column.key === 'fieldKey'">
          <Input
            :value="record.fieldKey"
            size="small"
            placeholder="key"
            @update:value="(v) => updateField(index, 'fieldKey', v)"
          />
        </template>
        <template v-else-if="column.key === 'fieldLabel'">
          <Input
            :value="record.fieldLabel"
            size="small"
            placeholder="标签"
            @update:value="(v) => updateField(index, 'fieldLabel', v)"
          />
        </template>
        <template v-else-if="column.key === 'fieldType'">
          <Select
            :value="record.fieldType"
            size="small"
            style="width: 100%"
            @change="(v) => updateField(index, 'fieldType', v)"
          >
            <Select.Option value="text">text</Select.Option>
            <Select.Option value="number">number</Select.Option>
            <Select.Option value="select">select</Select.Option>
            <Select.Option value="boolean">boolean</Select.Option>
          </Select>
        </template>
        <template v-else-if="column.key === 'maxLength'">
          <InputNumber
            :value="record.maxLength"
            size="small"
            :min="1"
            :disabled="record.fieldType !== 'text'"
            style="width: 100%"
            @change="(v) => updateField(index, 'maxLength', v)"
          />
        </template>
        <template v-else-if="column.key === 'defaultValue'">
          <Input
            :value="record.defaultValue || ''"
            size="small"
            placeholder="默认值"
            @update:value="(v) => updateField(index, 'defaultValue', v || null)"
          />
        </template>
        <template v-else-if="column.key === 'options'">
          <Tooltip :title="record.options">
            <Input
              :value="record.options || ''"
              size="small"
              placeholder="opt1,opt2"
              :disabled="record.fieldType !== 'select'"
              @update:value="(v) => updateField(index, 'options', v || null)"
            />
          </Tooltip>
        </template>
        <template v-else-if="column.key === 'required'">
          <Switch
            :checked="!!record.required"
            size="small"
            @change="(v) => updateField(index, 'required', v)"
          />
        </template>
        <template v-else-if="column.key === 'mappingTarget'">
          <Select
            :value="record.mappingTarget || undefined"
            size="small"
            style="width: 100%"
            allow-clear
            show-search
            placeholder="不映射"
            @change="(v) => updateField(index, 'mappingTarget', v || null)"
          >
            <Select.OptGroup label="系统字段">
              <Select.Option v-for="f in availableFields.systemFields" :key="`sys-${f}`" :value="f">{{ f }}</Select.Option>
            </Select.OptGroup>
            <Select.OptGroup label="自定义字段">
              <Select.Option v-for="f in availableFields.customFields" :key="`cus-${f}`" :value="f">{{ f }}</Select.Option>
            </Select.OptGroup>
          </Select>
        </template>
        <template v-else-if="column.key === 'sortOrder'">
          <InputNumber
            :value="record.sortOrder"
            size="small"
            style="width: 100%"
            @change="(v) => updateField(index, 'sortOrder', v ?? 0)"
          />
        </template>
        <template v-else-if="column.key === 'actions'">
          <div class="action-buttons">
            <Button type="text" size="small" :disabled="index === 0" @click="moveUp(index)">
              <ArrowUpOutlined />
            </Button>
            <Button type="text" size="small" :disabled="index === localFields.length - 1" @click="moveDown(index)">
              <ArrowDownOutlined />
            </Button>
            <Button type="text" size="small" danger @click="removeField(index)">
              <DeleteOutlined />
            </Button>
          </div>
        </template>
      </template>
    </Table>

    <div class="toolbar toolbar-bottom">
      <Button type="primary" size="small" @click="addField">
        <PlusOutlined /> 新增字段
      </Button>
    </div>
  </div>
</template>

<style scoped>
.alarm-field-editor { display: flex; flex-direction: column; }
.toolbar { display: flex; align-items: center; gap: 12px; padding: 8px 0; background: #fff; z-index: 10; }
.toolbar-top { border-bottom: 1px solid #f0f0f0; }
.toolbar-bottom { border-top: 1px solid #f0f0f0; margin-top: 8px; }
.hint { color: #999; font-size: 12px; }
.action-buttons { display: flex; gap: 2px; }
</style>
```

- [ ] **Step 3: TypeScript 编译**

Run: `cd frontend && npx vue-tsc --noEmit`
Expected: 零错误

- [ ] **Step 4: 提交**

```bash
git add frontend/src/components/alarmSchemas/AlarmSchemaFieldEditor.vue
git commit -m "feat(alarm-v2): AlarmSchemaFieldEditor 重写为紧凑表格 + Mapping 下拉"
```

---

## Task 9: `AlarmSchemaModal.vue` 加 displayFieldKey 下拉

**Files:**
- Modify: `frontend/src/components/alarmSchemas/AlarmSchemaModal.vue`

- [ ] **Step 1: 读现有文件**

用 Read 工具看现有 `AlarmSchemaModal.vue` 结构。它有：
- form ref `{ code, name, description }` —— 加 `displayFieldKey`
- watch `props.visible` 初始化（编辑模式从 detail 拷字段值；新建模式 reset）
- `handleOk()` 提交时构造 `AlarmSchemaCreate` / `AlarmSchemaUpdate`

- [ ] **Step 2: 修改 form 初始化**

在 `<script setup>` 找到 `const form = ref({...})`，改为：

```typescript
const form = ref({
  code: '',
  name: '',
  description: '',
  displayFieldKey: null as string | null,
})
```

- [ ] **Step 3: 在 watch 中加载 displayFieldKey**

找到 `watch(() => props.visible, async (v) => { ... })`。在编辑分支（`if (props.schemaId)` 块内）的 `form.value = {...}` 加入 `displayFieldKey`：

```typescript
      form.value = {
        code: d.code,
        name: d.name,
        description: d.description ?? '',
        displayFieldKey: d.displayFieldKey ?? null,
      }
```

在新建分支（`else`）reset：

```typescript
      form.value = { code: '', name: '', description: '', displayFieldKey: null }
```

- [ ] **Step 4: 在 handleOk 中提交 displayFieldKey**

找到 `handleOk` 中两个分支 `alarmSchemaApi.update` / `alarmSchemaApi.create`，分别加上 `displayFieldKey: form.value.displayFieldKey`：

```typescript
      await alarmSchemaApi.update(props.schemaId, {
        name: form.value.name,
        description: form.value.description || null,
        displayFieldKey: form.value.displayFieldKey,
        fields: fields.value,
      })
```

```typescript
      await alarmSchemaApi.create({
        code: form.value.code,
        name: form.value.name,
        description: form.value.description || null,
        displayFieldKey: form.value.displayFieldKey,
        fields: fields.value,
      })
```

- [ ] **Step 5: 在模板中加 dropdown**

找到 `<Form layout="vertical">`，在"告警字段"行（含 AlarmSchemaFieldEditor）之前加：

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

在 `<script setup>` 的 import 块确认 `Select` 已 import（如果不在：`import { Modal, Form, Input, Textarea, message, Select } from 'ant-design-vue'`）。

- [ ] **Step 6: TypeScript 编译**

Run: `cd frontend && npx vue-tsc --noEmit`
Expected: 零错误

- [ ] **Step 7: 提交**

```bash
git add frontend/src/components/alarmSchemas/AlarmSchemaModal.vue
git commit -m "feat(alarm-v2): AlarmSchemaModal 加卡片标题字段下拉"
```

---

## Task 10: `NodeAlarmsTab.vue` Collapse 标题用 displayFieldKey

**Files:**
- Modify: `frontend/src/components/canvas/NodeAlarmsTab.vue`

- [ ] **Step 1: 读现有文件**

用 Read 工具看现有 `NodeAlarmsTab.vue`。当前 `getCollapseHeader` 取 `schemaFields.value[0]`。

- [ ] **Step 2: 加 schema ref + 修改 loadAll**

在 `<script setup>` 中：

```typescript
import type { AlarmSchemaDetail, AlarmSchemaFieldItem } from '@/api/alarmSchema'

// 加 ref
const schema = ref<AlarmSchemaDetail | null>(null)
```

在 `loadAll` 函数中，找到 `const d = await alarmSchemaApi.get(alarmSchemaId.value)`，在 `schemaFields.value = ...` 之前/之后加：

```typescript
      schema.value = d
```

在 `loadAll` 函数的 else 分支（拓扑未挂模板时）加：

```typescript
      schema.value = null
```

- [ ] **Step 3: 修改 getCollapseHeader**

替换函数为：

```typescript
function getCollapseHeader(alarm: NodeAlarmItem): string {
  const displayKey = schema.value?.displayFieldKey
  let field: AlarmSchemaFieldItem | null = null
  if (displayKey) {
    field = schemaFields.value.find(f => f.fieldKey === displayKey) ?? null
  }
  if (!field) field = schemaFields.value[0] ?? null
  if (!field) return `告警 #${alarm.alarmIndex}`
  const v = alarm.attrs[field.fieldKey] || ''
  return `${v || '(空)'}  #${alarm.alarmIndex}`
}
```

- [ ] **Step 4: TypeScript 编译**

Run: `cd frontend && npx vue-tsc --noEmit`
Expected: 零错误

- [ ] **Step 5: 提交**

```bash
git add frontend/src/components/canvas/NodeAlarmsTab.vue
git commit -m "feat(alarm-v2): NodeAlarmsTab Collapse 标题字段按 displayFieldKey + fallback"
```

---

## 自检清单（实施完成后）

### 后端
- [ ] `alarm_schema_fields.mapping_target` 列存在
- [ ] `alarm_schemas.display_field_key` 列存在
- [ ] `AlarmSchemaFieldCreate.mapping_target` 非法字符抛 ValidationError
- [ ] `build_alarm_attrs(conn, node_id, fields, user_provided)` 按 user > mapping > default > NULL 顺序
- [ ] `resolve_mapping` 系统字段查 nodes 列，自定义字段查 node_attrs
- [ ] `POST/PUT /admin/api/alarm-schemas` 接受 mappingTarget + displayFieldKey
- [ ] `GET /admin/api/alarm-schemas/{id}` 返回新字段
- [ ] 节点创建（拓扑挂模板）自动告警的 attrs 按 mapping 填充
- [ ] 节点组 materialize 自动告警同上
- [ ] `POST /admin/api/nodes/{id}/alarms` 手动创建：用户传值 > mapping > default
- [ ] `GET /admin/api/node-fields/available` 返回 5 个系统字段 + DISTINCT custom 字段
- [ ] 所有 pytest 通过：`cd backend && python -m pytest tests/ -v`（80+）

### 前端
- [ ] `AlarmSchemaFieldEditor` 用 Table 渲染，一行 ~40px
- [ ] "+ 新增字段"按钮顶部 sticky + 底部双放
- [ ] Mapping 下拉显示「系统字段」+「自定义字段」分组
- [ ] `AlarmSchemaModal` 有"卡片标题字段"下拉
- [ ] 选项联动当前 `fields` 数组
- [ ] `NodeAlarmsTab` Collapse 标题按 displayFieldKey 取值；fallback 到 sort_order 最小字段
- [ ] TypeScript 编译通过

---

## 受影响文件清单

**后端：**
- `backend/app/db/migrations.py` — 2 个新 ALTER TABLE（Task 1）
- `backend/app/admin/schemas/alarm.py` — 加字段 + 校验（Task 2）
- `backend/app/admin/_alarm_utils.py` — **新文件**（Task 3）
- `backend/app/admin/alarm_schema.py` — 收发新字段（Task 4）
- `backend/app/admin/node.py` — 接入 build_alarm_attrs（Task 5）
- `backend/app/admin/node_group.py` — 同上（Task 5）
- `backend/app/admin/node_alarm.py` — 同上（Task 5）
- `backend/app/admin/node_fields.py` — **新文件**（Task 6）
- `backend/app/main.py` — 挂 node_fields_router（Task 6）

**前端：**
- `frontend/src/api/alarmSchema.ts` — 加字段（Task 7）
- `frontend/src/api/nodeFields.ts` — **新文件**（Task 7）
- `frontend/src/components/alarmSchemas/AlarmSchemaFieldEditor.vue` — **全量重写**（Task 8）
- `frontend/src/components/alarmSchemas/AlarmSchemaModal.vue` — 加下拉（Task 9）
- `frontend/src/components/canvas/NodeAlarmsTab.vue` — Collapse 头部改造（Task 10）

---

## 风险提示

1. **Task 5 同时改 3 个文件** — 现有 V1 测试（`test_node_auto_alarm.py` / `test_materialize_alarms.py` / `test_node_alarm_router.py`）会跑相同代码路径。SELECT `mapping_target` 列是新的，旧字段（field_key/default_value 等）行为不变 —— 应该零回归。若失败，检查 SELECT 列表是否漏了 `mapping_target` 字段。
2. **Task 6 测试中创建 node_type fields 的端点路径** — 若 `POST /node-types/{id}/fields` 不存在或路径不对，用直接 SQL 插入（测试注释中给出替代方案）。
3. **Task 8 全量重写** — `AlarmSchemaFieldEditor.vue` 用 Affix 实现 sticky toolbar。Affix 需要在 modal 内正常工作 —— 如果不工作，回退到 CSS `position: sticky`。
4. **Mapping 下拉每次 mount 拉取一次** — 首次打开 Modal 会发 1 次请求；同 Modal 内重新打开复用 `availableFields` ref。Modal 关闭重开会触发新 mount 因而重新拉取，是预期行为。
5. **`mapping_target` SQL 注入** — `_alarm_utils.resolve_mapping` 用 f-string 拼接列名 `f"SELECT {mapping_target} FROM nodes ..."`，前提：`mapping_target` 必须先通过 `in NODE_SYSTEM_FIELDS` 白名单检查（5 个固定值），代码中已保证。第二条路径（custom）用参数化 query 处理 `field_key`。
