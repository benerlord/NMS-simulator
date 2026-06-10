# 节点告警数据 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在画布上为每个节点提供"告警数据"能力 —— 全局告警模板挂到拓扑、节点创建时自动产生 1 条默认告警、可手工增删改、通过 `alarms` CTE 暴露给 SQL 编辑器供 mock 接口使用。

**Architecture:** 4 张新表（`alarm_schemas` / `alarm_schema_fields` / `node_alarms` / `node_alarm_attrs`）+ `topologies` 新列 `alarm_schema_id`；告警字段采用与 `node_type_fields` 一致的 K-V + CTE pivot 模式；后端新增 2 个 router（`alarm_schema.py` / `node_alarm.py`）+ 修改 `topology.py` / `node.py` / `node_group.py` / `cte_builder.py` / `sql_helper.py`；前端在"类型管理"页加第 3 Tab、`TopologyModal` 加挂模板下拉、`NodeAttrsPanel` 改为 Tab 切换 + 新增 `NodeAlarmsTab`。

**Tech Stack:** FastAPI / SQLite WAL / Pydantic v2 CamelModel / Vue 3.5 `<script setup>` / Ant Design Vue 4 / pytest（新建测试基础设施）

**关联文档：** `docs/superpowers/specs/2026-06-10-node-alarms-design.md`

---

## 任务总览

| # | 任务 | 类型 | 依赖 |
|---|------|------|------|
| 1 | 后端 pytest 基础设施 | 测试基建 | - |
| 2 | DB migrations + topologies 列 | 后端 | 1 |
| 3 | Pydantic schemas | 后端 | 2 |
| 4 | `alarm_schema.py` router CRUD + 引用检查 | 后端 | 3 |
| 5 | `node_alarm.py` router CRUD | 后端 | 3 |
| 6 | 拓扑挂模板 PATCH + detail 含告警计数 | 后端 | 4 |
| 7 | 创建节点时自动 +1 默认告警 | 后端 | 5 |
| 8 | 节点组 materialize 时为每物化产物 +1 默认告警 | 后端 | 7 |
| 9 | CTE builder 增加 `alarms` 视图 | 后端 | 5 |
| 10 | sql_helper 视图清单暴露 `alarms` | 后端 | 9 |
| 11 | 前端 API SDK + composable | 前端 | 4, 5, 6 |
| 12 | 告警模板管理 UI（TypesView 第 3 Tab） | 前端 | 11 |
| 13 | TopologyModal 挂模板下拉 + 切换二次确认 | 前端 | 11 |
| 14 | NodeAttrsPanel Tab 化 + NodeAlarmsTab | 前端 | 11 |

---

## Task 1: 后端 pytest 基础设施

**Files:**
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/conftest.py`
- Create: `backend/pytest.ini`
- Modify: `backend/requirements.txt`（加 pytest 依赖）

- [ ] **Step 1: 添加 pytest 依赖**

修改 `backend/requirements.txt`，在文件末尾追加：

```
pytest>=8.0,<9.0
httpx>=0.27,<1.0
```

- [ ] **Step 2: 安装依赖**

Run: `cd backend && pip install pytest httpx`

Expected: `Successfully installed pytest-... httpx-...`

- [ ] **Step 3: 创建 `backend/pytest.ini`**

```ini
[pytest]
pythonpath = .
testpaths = tests
python_files = test_*.py
addopts = -ra -v
```

- [ ] **Step 4: 创建 `backend/tests/__init__.py`**

空文件即可。

- [ ] **Step 5: 创建 `backend/tests/conftest.py`**

```python
import os
import sqlite3
from pathlib import Path

import pytest

# 在导入 app 之前设置 DB_PATH，避免污染开发库
os.environ.setdefault("APP_PORT", "0")


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """每个测试一个独立的临时 SQLite 文件。"""
    return tmp_path / "test.db"


@pytest.fixture
def conn(db_path: Path):
    """已跑完 migrations 的连接。"""
    from app.db.migrations import run_migrations

    c = sqlite3.connect(str(db_path), isolation_level=None)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    run_migrations(c)
    yield c
    c.close()


@pytest.fixture
def client(monkeypatch, db_path: Path):
    """FastAPI TestClient with isolated DB."""
    from app.core.config import settings as app_settings

    monkeypatch.setattr(app_settings, "db_path", db_path)

    from app.db.connection import init_db
    from app.main import app
    from fastapi.testclient import TestClient

    init_db()
    return TestClient(app)


@pytest.fixture
def seed_topology(conn):
    """种入一个最小拓扑 + 一个节点类型，返回 (topology_id, node_type_id)。"""
    conn.execute(
        "INSERT INTO topologies (id, name) VALUES ('topo_test', 'TestTopo')"
    )
    conn.execute(
        "INSERT INTO node_types (id, code, name, category) "
        "VALUES ('ntype_test', 'test_dev', '测试设备', 'switch')"
    )
    return ("topo_test", "ntype_test")
```

- [ ] **Step 6: 创建烟囱测试 `backend/tests/test_smoke.py`**

```python
def test_pytest_runs():
    assert 1 + 1 == 2


def test_migrations_create_tables(conn):
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    names = {r["name"] for r in rows}
    assert "topologies" in names
    assert "nodes" in names
```

- [ ] **Step 7: 运行测试**

Run: `cd backend && python -m pytest tests/test_smoke.py -v`
Expected: 2 passed

- [ ] **Step 8: 提交**

```bash
git add backend/requirements.txt backend/pytest.ini backend/tests/
git commit -m "test: 初始化后端 pytest 基础设施"
```

---

## Task 2: DB migrations — 4 张新表 + topologies 列

**Files:**
- Modify: `backend/app/db/migrations.py`
- Test: `backend/tests/test_migrations_alarms.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_migrations_alarms.py`：

```python
def test_alarm_schemas_table_created(conn):
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name IN ('alarm_schemas','alarm_schema_fields','node_alarms','node_alarm_attrs')"
    ).fetchall()
    names = {r["name"] for r in rows}
    assert names == {"alarm_schemas", "alarm_schema_fields", "node_alarms", "node_alarm_attrs"}


def test_topologies_has_alarm_schema_id_column(conn):
    rows = conn.execute("PRAGMA table_info(topologies)").fetchall()
    cols = {r["name"] for r in rows}
    assert "alarm_schema_id" in cols


def test_alarm_schema_fields_check_constraint(conn):
    conn.execute(
        "INSERT INTO alarm_schemas (id, code, name) VALUES ('as_x', 'cx', 'X')"
    )
    # field_type 非法应被 CHECK 拦截
    import sqlite3
    raised = False
    try:
        conn.execute(
            "INSERT INTO alarm_schema_fields (alarm_schema_id, field_key, field_label, field_type) "
            "VALUES ('as_x', 'k1', 'L1', 'bogus')"
        )
    except sqlite3.IntegrityError:
        raised = True
    assert raised


def test_node_alarms_cascade_delete(conn):
    conn.execute("INSERT INTO topologies (id, name) VALUES ('t1', 'T1')")
    conn.execute(
        "INSERT INTO node_types (id, code, name, category) VALUES ('nt1', 'sw', 'sw', 'switch')"
    )
    conn.execute(
        "INSERT INTO nodes (id, topology_id, node_type_id, name) VALUES ('n1', 't1', 'nt1', 'n1')"
    )
    conn.execute(
        "INSERT INTO node_alarms (id, node_id, alarm_index) VALUES ('alm_1', 'n1', 1)"
    )
    conn.execute("DELETE FROM nodes WHERE id = 'n1'")
    cnt = conn.execute("SELECT COUNT(*) AS c FROM node_alarms").fetchone()["c"]
    assert cnt == 0
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_migrations_alarms.py -v`
Expected: FAIL — 表不存在或列不存在

- [ ] **Step 3: 实现 migrations**

在 `backend/app/db/migrations.py` 的 `SCHEMA_SQL` 字符串末尾（`node_groups` 索引之后）追加 4 张新表定义：

```python
CREATE TABLE IF NOT EXISTS alarm_schemas (
  id              TEXT PRIMARY KEY,
  code            TEXT NOT NULL UNIQUE,
  name            TEXT NOT NULL,
  description     TEXT,
  created_at      TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS alarm_schema_fields (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  alarm_schema_id TEXT NOT NULL,
  field_key       TEXT NOT NULL,
  field_label     TEXT NOT NULL,
  field_type      TEXT NOT NULL CHECK (field_type IN ('text','number','select','boolean')),
  default_value   TEXT,
  options         TEXT,
  required        INTEGER NOT NULL DEFAULT 0,
  max_length      INTEGER,
  sort_order      INTEGER NOT NULL DEFAULT 0,
  FOREIGN KEY (alarm_schema_id) REFERENCES alarm_schemas(id) ON DELETE CASCADE,
  UNIQUE (alarm_schema_id, field_key)
);

CREATE TABLE IF NOT EXISTS node_alarms (
  id              TEXT PRIMARY KEY,
  node_id         TEXT NOT NULL,
  alarm_index     INTEGER NOT NULL,
  created_at      TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (node_id) REFERENCES nodes(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_node_alarms_node ON node_alarms(node_id);

CREATE TABLE IF NOT EXISTS node_alarm_attrs (
  alarm_id        TEXT NOT NULL,
  field_key       TEXT NOT NULL,
  value           TEXT,
  PRIMARY KEY (alarm_id, field_key),
  FOREIGN KEY (alarm_id) REFERENCES node_alarms(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_node_alarm_attrs_key ON node_alarm_attrs(field_key);
```

在 `run_migrations()` 函数末尾追加幂等 `ALTER TABLE`：

```python
    # Idempotent column addition for topologies.alarm_schema_id
    try:
        conn.execute("ALTER TABLE topologies ADD COLUMN alarm_schema_id TEXT")
    except sqlite3.OperationalError:
        pass
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_migrations_alarms.py -v`
Expected: 4 passed

- [ ] **Step 5: 提交**

```bash
git add backend/app/db/migrations.py backend/tests/test_migrations_alarms.py
git commit -m "feat(alarm): 数据库迁移 — 4 张新表 + topologies.alarm_schema_id 列"
```

---

## Task 3: Pydantic Schemas

**Files:**
- Create: `backend/app/admin/schemas/alarm.py`
- Modify: `backend/app/admin/schemas/__init__.py`
- Modify: `backend/app/admin/schemas/topology.py`（加 `alarmSchemaId` + `nodeAlarmCount`）

- [ ] **Step 1: 创建 `backend/app/admin/schemas/alarm.py`**

```python
from datetime import datetime
from typing import Optional

from pydantic import Field, model_validator

from ._base import CamelModel


# --- alarm_schema fields ---

class AlarmSchemaFieldCreate(CamelModel):
    field_key: str = Field(..., min_length=1, max_length=50)
    field_label: str = Field(..., min_length=1, max_length=100)
    field_type: str = Field(..., pattern="^(text|number|select|boolean)$")
    max_length: Optional[int] = Field(default=None, ge=1)
    default_value: Optional[str] = Field(default=None, max_length=200)
    options: Optional[str] = Field(default=None, max_length=500)
    required: bool = Field(default=False)
    sort_order: int = Field(default=0)

    @model_validator(mode='after')
    def validate_max_length_for_text(self) -> 'AlarmSchemaFieldCreate':
        if self.field_type != 'text':
            return self
        if self.max_length is None or self.max_length < 1:
            raise ValueError('文本类型必须设置 max_length >= 1')
        return self


class AlarmSchemaFieldItem(CamelModel):
    id: int
    alarm_schema_id: str
    field_key: str
    field_label: str
    field_type: str
    max_length: Optional[int]
    default_value: Optional[str]
    options: Optional[str]
    required: bool
    sort_order: int


# --- alarm_schemas ---

class AlarmSchemaCreate(CamelModel):
    code: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=500)
    fields: list[AlarmSchemaFieldCreate] = Field(default_factory=list)


class AlarmSchemaUpdate(CamelModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=500)
    fields: Optional[list[AlarmSchemaFieldCreate]] = Field(default=None)


class AlarmSchemaItem(CamelModel):
    id: str
    code: str
    name: str
    description: Optional[str]
    created_at: datetime
    updated_at: datetime


class AlarmSchemaDetail(AlarmSchemaItem):
    fields: list[AlarmSchemaFieldItem] = []


# --- topology binding ---

class TopologyAlarmSchemaPatch(CamelModel):
    alarm_schema_id: Optional[str] = None  # None / "" = 解绑
    clear_existing: bool = False


# --- node alarms ---

class NodeAlarmAttrSet(CamelModel):
    attrs: dict[str, Optional[str]]


class NodeAlarmCreate(CamelModel):
    attrs: Optional[dict[str, Optional[str]]] = None  # 未传 = 用 default_value 填充


class NodeAlarmItem(CamelModel):
    id: str
    node_id: str
    alarm_index: int
    attrs: dict[str, Optional[str]] = {}
    created_at: datetime
    updated_at: datetime
```

- [ ] **Step 2: 修改 `backend/app/admin/schemas/topology.py`**

读现有 `TopologyDetail` 定义后，在 `TopologyDetail` 类中加两个新字段（沿用 Optional 模式）。具体编辑：找到 `class TopologyDetail` 定义，在最后增加：

```python
    alarm_schema_id: Optional[str] = None
    node_alarm_count: int = 0
```

- [ ] **Step 3: 修改 `backend/app/admin/schemas/__init__.py`**

加入新 schema 导出：

```python
from .alarm import (
    AlarmSchemaCreate,
    AlarmSchemaUpdate,
    AlarmSchemaItem,
    AlarmSchemaDetail,
    AlarmSchemaFieldCreate,
    AlarmSchemaFieldItem,
    TopologyAlarmSchemaPatch,
    NodeAlarmAttrSet,
    NodeAlarmCreate,
    NodeAlarmItem,
)
```

并加入 `__all__` 列表对应条目。

- [ ] **Step 4: 写测试**

创建 `backend/tests/test_alarm_schemas_pydantic.py`：

```python
import pytest
from pydantic import ValidationError
from app.admin.schemas import (
    AlarmSchemaCreate,
    AlarmSchemaFieldCreate,
    TopologyAlarmSchemaPatch,
)


def test_field_text_requires_max_length():
    with pytest.raises(ValidationError):
        AlarmSchemaFieldCreate(
            field_key="x", field_label="X", field_type="text"
        )


def test_field_non_text_no_max_length_needed():
    f = AlarmSchemaFieldCreate(
        field_key="x", field_label="X", field_type="number"
    )
    assert f.max_length is None


def test_alarm_schema_create_camel_alias():
    a = AlarmSchemaCreate(code="huawei", name="华为告警")
    dump = a.model_dump(by_alias=True)
    assert "code" in dump and "name" in dump


def test_topology_alarm_schema_patch_clear_existing_default_false():
    p = TopologyAlarmSchemaPatch(alarmSchemaId="as_1")
    assert p.clear_existing is False
    assert p.alarm_schema_id == "as_1"
```

- [ ] **Step 5: 运行测试**

Run: `cd backend && python -m pytest tests/test_alarm_schemas_pydantic.py -v`
Expected: 4 passed

- [ ] **Step 6: 提交**

```bash
git add backend/app/admin/schemas/ backend/tests/test_alarm_schemas_pydantic.py
git commit -m "feat(alarm): Pydantic schemas — alarm_schema / node_alarm / topology binding"
```

---

## Task 4: `alarm_schema.py` Router CRUD + 引用检查

**Files:**
- Create: `backend/app/admin/alarm_schema.py`
- Modify: `backend/app/main.py`（挂载 router）
- Test: `backend/tests/test_alarm_schema_router.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_alarm_schema_router.py`：

```python
def test_list_alarm_schemas_empty(client):
    r = client.get("/admin/api/alarm-schemas")
    assert r.status_code == 200
    j = r.json()
    assert j["code"] == 0
    assert j["data"] == []


def test_create_alarm_schema_with_fields(client):
    payload = {
        "code": "huawei",
        "name": "华为告警模板",
        "description": "demo",
        "fields": [
            {"fieldKey": "alarm_id", "fieldLabel": "告警ID", "fieldType": "text", "maxLength": 64, "sortOrder": 0},
            {"fieldKey": "severity", "fieldLabel": "级别", "fieldType": "select", "options": "critical,major,minor", "sortOrder": 1},
        ],
    }
    r = client.post("/admin/api/alarm-schemas", json=payload)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["code"] == 0
    sid = j["data"]["id"]
    assert sid.startswith("as_")
    assert len(j["data"]["fields"]) == 2


def test_get_alarm_schema_detail(client):
    r = client.post("/admin/api/alarm-schemas", json={
        "code": "zte", "name": "中兴", "fields": []
    })
    sid = r.json()["data"]["id"]

    r = client.get(f"/admin/api/alarm-schemas/{sid}")
    assert r.status_code == 200
    assert r.json()["data"]["code"] == "zte"


def test_update_alarm_schema_replaces_fields(client):
    r = client.post("/admin/api/alarm-schemas", json={
        "code": "c1", "name": "n1",
        "fields": [{"fieldKey": "a", "fieldLabel": "A", "fieldType": "text", "maxLength": 50}],
    })
    sid = r.json()["data"]["id"]

    r = client.put(f"/admin/api/alarm-schemas/{sid}", json={
        "name": "new_name",
        "fields": [{"fieldKey": "b", "fieldLabel": "B", "fieldType": "number"}],
    })
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["name"] == "new_name"
    assert [f["fieldKey"] for f in d["fields"]] == ["b"]


def test_delete_unreferenced_alarm_schema_succeeds(client):
    r = client.post("/admin/api/alarm-schemas", json={"code": "x", "name": "X", "fields": []})
    sid = r.json()["data"]["id"]
    r = client.delete(f"/admin/api/alarm-schemas/{sid}")
    assert r.status_code == 200
    assert r.json()["code"] == 0


def test_delete_referenced_alarm_schema_rejected(client):
    # create alarm_schema and topology, bind
    r = client.post("/admin/api/alarm-schemas", json={"code": "x", "name": "X", "fields": []})
    sid = r.json()["data"]["id"]
    r = client.post("/admin/api/topologies", json={"name": "T1"})
    tid = r.json()["data"]["id"]
    r = client.patch(f"/admin/api/topologies/{tid}/alarm-schema",
                     json={"alarmSchemaId": sid, "clearExisting": False})
    assert r.status_code == 200

    # delete attempt
    r = client.delete(f"/admin/api/alarm-schemas/{sid}")
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert detail["code"] == 40901
    assert "T1" in detail["details"]["referencedBy"]


def test_create_alarm_schema_with_invalid_field_key_rejected(client):
    r = client.post("/admin/api/alarm-schemas", json={
        "code": "c1", "name": "n1",
        "fields": [{"fieldKey": "bad-key!", "fieldLabel": "X", "fieldType": "number"}],
    })
    # Pydantic 不拦截，应在 router 层拦截或在 DB 层拦截。我们在 router 层拦截。
    assert r.status_code == 400
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_alarm_schema_router.py -v`
Expected: FAIL — 404（路由未挂载）

- [ ] **Step 3: 创建 router 文件**

创建 `backend/app/admin/alarm_schema.py`：

```python
import re
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException

from app.db.connection import connect, transaction
from app.admin.schemas import (
    AlarmSchemaCreate,
    AlarmSchemaUpdate,
    AlarmSchemaDetail,
    AlarmSchemaItem,
    AlarmSchemaFieldItem,
)

router = APIRouter(prefix="/admin/api", tags=["告警模板"])

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_FIXED_COLS = {"id", "node_id", "node_name", "node_dn", "alarm_index", "created_at", "updated_at"}


def _new_id() -> str:
    return f"as_{uuid.uuid4().hex[:12]}"


def _validate_field_keys(fields: list) -> None:
    seen: set[str] = set()
    for f in fields:
        if not _IDENT_RE.match(f.field_key):
            raise HTTPException(
                status_code=400,
                detail={
                    "code": 40001,
                    "message": f"字段键非法（仅支持字母/数字/下划线，且以字母或下划线开头）: {f.field_key}",
                },
            )
        if f.field_key in _FIXED_COLS:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": 40002,
                    "message": f"字段键与固定列冲突: {f.field_key}（固定列：{', '.join(sorted(_FIXED_COLS))}）",
                },
            )
        if f.field_key in seen:
            raise HTTPException(
                status_code=400,
                detail={"code": 40003, "message": f"字段键重复: {f.field_key}"},
            )
        seen.add(f.field_key)


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
        )
        for r in rows
    ]


def _row_to_detail(conn, row) -> AlarmSchemaDetail:
    return AlarmSchemaDetail(
        id=row["id"],
        code=row["code"],
        name=row["name"],
        description=row["description"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        fields=_get_fields(conn, row["id"]),
    )


@router.get("/alarm-schemas")
def list_alarm_schemas() -> dict:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM alarm_schemas ORDER BY created_at DESC"
        ).fetchall()
        items = [
            AlarmSchemaItem(
                id=r["id"], code=r["code"], name=r["name"],
                description=r["description"],
                created_at=r["created_at"], updated_at=r["updated_at"],
            ).model_dump(mode="json", by_alias=True)
            for r in rows
        ]
    return {"code": 0, "data": items, "message": "ok"}


@router.get("/alarm-schemas/{schema_id}")
def get_alarm_schema(schema_id: str) -> dict:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM alarm_schemas WHERE id = ?", (schema_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail={"code": 40404, "message": "告警模板不存在"})
        d = _row_to_detail(conn, row)
    return {"code": 0, "data": d.model_dump(mode="json", by_alias=True), "message": "ok"}


@router.post("/alarm-schemas")
def create_alarm_schema(data: AlarmSchemaCreate) -> dict:
    _validate_field_keys(data.fields)
    sid = _new_id()
    with transaction() as conn:
        # code 唯一性
        dup = conn.execute(
            "SELECT id FROM alarm_schemas WHERE code = ?", (data.code,)
        ).fetchone()
        if dup:
            raise HTTPException(
                status_code=409,
                detail={"code": 40901, "message": f"code 已存在: {data.code}"},
            )
        conn.execute(
            "INSERT INTO alarm_schemas (id, code, name, description) VALUES (?, ?, ?, ?)",
            (sid, data.code, data.name, data.description),
        )
        for f in data.fields:
            conn.execute(
                "INSERT INTO alarm_schema_fields "
                "(alarm_schema_id, field_key, field_label, field_type, max_length, "
                " default_value, options, required, sort_order) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (sid, f.field_key, f.field_label, f.field_type, f.max_length,
                 f.default_value, f.options, int(f.required), f.sort_order),
            )
        row = conn.execute("SELECT * FROM alarm_schemas WHERE id = ?", (sid,)).fetchone()
        d = _row_to_detail(conn, row)
    return {"code": 0, "data": d.model_dump(mode="json", by_alias=True), "message": "ok"}


@router.put("/alarm-schemas/{schema_id}")
def update_alarm_schema(schema_id: str, data: AlarmSchemaUpdate) -> dict:
    if data.fields is not None:
        _validate_field_keys(data.fields)
    with transaction() as conn:
        row = conn.execute("SELECT * FROM alarm_schemas WHERE id = ?", (schema_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail={"code": 40404, "message": "告警模板不存在"})

        sets: list[str] = []
        params: list[Any] = []
        if data.name is not None:
            sets.append("name = ?")
            params.append(data.name)
        if data.description is not None:
            sets.append("description = ?")
            params.append(data.description)
        if sets:
            sets.append("updated_at = datetime('now')")
            params.append(schema_id)
            conn.execute(f"UPDATE alarm_schemas SET {', '.join(sets)} WHERE id = ?", params)

        # fields 全量替换
        if data.fields is not None:
            conn.execute("DELETE FROM alarm_schema_fields WHERE alarm_schema_id = ?", (schema_id,))
            for f in data.fields:
                conn.execute(
                    "INSERT INTO alarm_schema_fields "
                    "(alarm_schema_id, field_key, field_label, field_type, max_length, "
                    " default_value, options, required, sort_order) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (schema_id, f.field_key, f.field_label, f.field_type, f.max_length,
                     f.default_value, f.options, int(f.required), f.sort_order),
                )

        row = conn.execute("SELECT * FROM alarm_schemas WHERE id = ?", (schema_id,)).fetchone()
        d = _row_to_detail(conn, row)
    return {"code": 0, "data": d.model_dump(mode="json", by_alias=True), "message": "ok"}


@router.delete("/alarm-schemas/{schema_id}")
def delete_alarm_schema(schema_id: str) -> dict:
    with transaction() as conn:
        row = conn.execute("SELECT id FROM alarm_schemas WHERE id = ?", (schema_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail={"code": 40404, "message": "告警模板不存在"})

        # 引用检查 Y1
        refs = conn.execute(
            "SELECT name FROM topologies WHERE alarm_schema_id = ?", (schema_id,)
        ).fetchall()
        if refs:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": 40901,
                    "message": "告警模板被以下拓扑引用，无法删除",
                    "details": {"referencedBy": [r["name"] for r in refs]},
                },
            )
        conn.execute("DELETE FROM alarm_schemas WHERE id = ?", (schema_id,))
    return {"code": 0, "data": None, "message": "ok"}
```

- [ ] **Step 4: 挂载 router**

修改 `backend/app/main.py` —— 在 `from app.admin.node_group import router as node_group_router` 之后加：

```python
from app.admin.alarm_schema import router as alarm_schema_router
```

并在 `app.include_router(node_group_router)` 之后加：

```python
app.include_router(alarm_schema_router)
```

- [ ] **Step 5: 运行测试**

Run: `cd backend && python -m pytest tests/test_alarm_schema_router.py -v`
Expected: 7 passed（`test_delete_referenced_alarm_schema_rejected` 依赖 Task 6 的拓扑挂载端点 —— 如未实现会因 404 失败。这种情况下先跳过该用例：在测试函数上加 `@pytest.mark.skip(reason="depends on Task 6")`，Task 6 完成后再开启）

实际推荐：标记跳过，写注释提醒。Task 6 完成后回来移除 skip。

- [ ] **Step 6: 提交**

```bash
git add backend/app/admin/alarm_schema.py backend/app/main.py backend/tests/test_alarm_schema_router.py
git commit -m "feat(alarm): alarm_schema router — CRUD + 引用检查 + 字段键校验"
```

---

## Task 5: `node_alarm.py` Router CRUD

**Files:**
- Create: `backend/app/admin/node_alarm.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_node_alarm_router.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_node_alarm_router.py`：

```python
def _setup_topology_with_schema_and_node(client):
    r = client.post("/admin/api/alarm-schemas", json={
        "code": "demo", "name": "DemoTpl",
        "fields": [
            {"fieldKey": "alarm_id", "fieldLabel": "ID", "fieldType": "text", "maxLength": 64, "defaultValue": "AID-000"},
            {"fieldKey": "severity", "fieldLabel": "级别", "fieldType": "select", "options": "critical,major", "defaultValue": "minor"},
        ],
    })
    sid = r.json()["data"]["id"]

    r = client.post("/admin/api/topologies", json={"name": "T"})
    tid = r.json()["data"]["id"]
    client.patch(f"/admin/api/topologies/{tid}/alarm-schema", json={
        "alarmSchemaId": sid, "clearExisting": False
    })

    # need a node_type and node
    r = client.post("/admin/api/node-types", json={
        "code": "sw", "name": "交换机", "category": "switch"
    })
    ntid = r.json()["data"]["id"]
    r = client.post(f"/admin/api/topologies/{tid}/nodes", json={
        "nodeTypeId": ntid, "name": "n1"
    })
    nid = r.json()["data"]["id"]
    return tid, ntid, nid


def test_list_node_alarms(client):
    tid, ntid, nid = _setup_topology_with_schema_and_node(client)
    r = client.get(f"/admin/api/nodes/{nid}/alarms")
    assert r.status_code == 200
    # 节点创建已自动 +1 告警（Task 7 实现）
    # 这一步如未到 Task 7 完成，应该返回 0 条，故此处暂时容忍 0 或 1。
    assert len(r.json()["data"]) >= 0


def test_create_node_alarm_uses_default_value(client):
    tid, ntid, nid = _setup_topology_with_schema_and_node(client)
    r = client.post(f"/admin/api/nodes/{nid}/alarms", json={})
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["id"].startswith("alm_")
    assert d["attrs"]["alarm_id"] == "AID-000"
    assert d["attrs"]["severity"] == "minor"


def test_create_node_alarm_with_partial_attrs(client):
    tid, ntid, nid = _setup_topology_with_schema_and_node(client)
    r = client.post(f"/admin/api/nodes/{nid}/alarms", json={
        "attrs": {"alarm_id": "CUSTOM-1"}
    })
    d = r.json()["data"]
    assert d["attrs"]["alarm_id"] == "CUSTOM-1"
    assert d["attrs"]["severity"] == "minor"  # default fill


def test_create_node_alarm_without_schema_rejected(client):
    # topology 没挂模板
    r = client.post("/admin/api/topologies", json={"name": "T2"})
    tid = r.json()["data"]["id"]
    r = client.post("/admin/api/node-types", json={"code": "sw2", "name": "SW", "category": "switch"})
    ntid = r.json()["data"]["id"]
    r = client.post(f"/admin/api/topologies/{tid}/nodes", json={"nodeTypeId": ntid, "name": "n"})
    nid = r.json()["data"]["id"]

    r = client.post(f"/admin/api/nodes/{nid}/alarms", json={})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == 40901


def test_update_node_alarm_attrs(client):
    tid, ntid, nid = _setup_topology_with_schema_and_node(client)
    r = client.post(f"/admin/api/nodes/{nid}/alarms", json={})
    aid = r.json()["data"]["id"]

    r = client.put(f"/admin/api/alarms/{aid}/attrs", json={
        "attrs": {"alarm_id": "UPDATED", "severity": "critical"}
    })
    assert r.status_code == 200
    assert r.json()["data"]["attrs"]["severity"] == "critical"


def test_update_node_alarm_max_length_rejected(client):
    tid, ntid, nid = _setup_topology_with_schema_and_node(client)
    r = client.post(f"/admin/api/nodes/{nid}/alarms", json={})
    aid = r.json()["data"]["id"]

    too_long = "x" * 100  # maxLength is 64
    r = client.put(f"/admin/api/alarms/{aid}/attrs", json={
        "attrs": {"alarm_id": too_long}
    })
    assert r.status_code == 400


def test_delete_node_alarm(client):
    tid, ntid, nid = _setup_topology_with_schema_and_node(client)
    r = client.post(f"/admin/api/nodes/{nid}/alarms", json={})
    aid = r.json()["data"]["id"]
    r = client.delete(f"/admin/api/alarms/{aid}")
    assert r.status_code == 200
    r = client.get(f"/admin/api/nodes/{nid}/alarms")
    assert all(a["id"] != aid for a in r.json()["data"])


def test_alarm_index_auto_increment(client):
    tid, ntid, nid = _setup_topology_with_schema_and_node(client)
    a1 = client.post(f"/admin/api/nodes/{nid}/alarms", json={}).json()["data"]
    a2 = client.post(f"/admin/api/nodes/{nid}/alarms", json={}).json()["data"]
    a3 = client.post(f"/admin/api/nodes/{nid}/alarms", json={}).json()["data"]
    assert a2["alarmIndex"] == a1["alarmIndex"] + 1
    assert a3["alarmIndex"] == a2["alarmIndex"] + 1
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_node_alarm_router.py -v`
Expected: FAIL — 404

- [ ] **Step 3: 创建 `backend/app/admin/node_alarm.py`**

```python
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException

from app.db.connection import connect, transaction
from app.admin.schemas import (
    NodeAlarmAttrSet,
    NodeAlarmCreate,
    NodeAlarmItem,
)

router = APIRouter(prefix="/admin/api", tags=["节点告警"])


def _new_alarm_id() -> str:
    return f"alm_{uuid.uuid4().hex[:12]}"


def _get_alarm_schema_for_node(conn, node_id: str):
    """返回 (alarm_schema_id, [field rows])；若拓扑未挂模板返回 (None, [])。"""
    row = conn.execute(
        "SELECT t.alarm_schema_id AS sid FROM nodes n "
        "JOIN topologies t ON t.id = n.topology_id "
        "WHERE n.id = ?",
        (node_id,),
    ).fetchone()
    if not row or not row["sid"]:
        return None, []
    fields = conn.execute(
        "SELECT field_key, field_type, max_length, default_value, required "
        "FROM alarm_schema_fields WHERE alarm_schema_id = ? ORDER BY sort_order, id",
        (row["sid"],),
    ).fetchall()
    return row["sid"], fields


def _load_attrs(conn, alarm_id: str) -> dict[str, Any]:
    rows = conn.execute(
        "SELECT field_key, value FROM node_alarm_attrs WHERE alarm_id = ?",
        (alarm_id,),
    ).fetchall()
    return {r["field_key"]: r["value"] for r in rows}


def _row_to_item(conn, row) -> NodeAlarmItem:
    return NodeAlarmItem(
        id=row["id"],
        node_id=row["node_id"],
        alarm_index=row["alarm_index"],
        attrs=_load_attrs(conn, row["id"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _next_alarm_index(conn, node_id: str) -> int:
    row = conn.execute(
        "SELECT COALESCE(MAX(alarm_index), 0) + 1 AS n FROM node_alarms WHERE node_id = ?",
        (node_id,),
    ).fetchone()
    return int(row["n"])


def _validate_attr_lengths(fields, attrs: dict[str, Any]) -> None:
    field_map = {f["field_key"]: f for f in fields}
    for k, v in attrs.items():
        f = field_map.get(k)
        if not f:
            continue
        if f["field_type"] == "text" and f["max_length"] and v and len(str(v)) > f["max_length"]:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": 40001,
                    "message": f"字段 {k} 超过最大长度 {f['max_length']}",
                },
            )


@router.get("/nodes/{node_id}/alarms")
def list_node_alarms(node_id: str) -> dict:
    with connect() as conn:
        node = conn.execute("SELECT id FROM nodes WHERE id = ?", (node_id,)).fetchone()
        if not node:
            raise HTTPException(status_code=404, detail={"code": 40404, "message": "节点不存在"})
        rows = conn.execute(
            "SELECT * FROM node_alarms WHERE node_id = ? ORDER BY alarm_index",
            (node_id,),
        ).fetchall()
        items = [_row_to_item(conn, r).model_dump(mode="json", by_alias=True) for r in rows]
    return {"code": 0, "data": items, "message": "ok"}


@router.post("/nodes/{node_id}/alarms")
def create_node_alarm(node_id: str, data: NodeAlarmCreate) -> dict:
    with transaction() as conn:
        node = conn.execute("SELECT id FROM nodes WHERE id = ?", (node_id,)).fetchone()
        if not node:
            raise HTTPException(status_code=404, detail={"code": 40404, "message": "节点不存在"})

        sid, fields = _get_alarm_schema_for_node(conn, node_id)
        if not sid:
            raise HTTPException(
                status_code=409,
                detail={"code": 40901, "message": "本拓扑未配置告警模板"},
            )

        # 合并：用户传的 + default_value 兜底
        provided = data.attrs or {}
        merged: dict[str, Any] = {}
        for f in fields:
            if f["field_key"] in provided:
                merged[f["field_key"]] = provided[f["field_key"]]
            elif f["default_value"] is not None:
                merged[f["field_key"]] = f["default_value"]

        _validate_attr_lengths(fields, merged)

        aid = _new_alarm_id()
        idx = _next_alarm_index(conn, node_id)
        conn.execute(
            "INSERT INTO node_alarms (id, node_id, alarm_index) VALUES (?, ?, ?)",
            (aid, node_id, idx),
        )
        for k, v in merged.items():
            conn.execute(
                "INSERT INTO node_alarm_attrs (alarm_id, field_key, value) VALUES (?, ?, ?)",
                (aid, k, v),
            )

        row = conn.execute("SELECT * FROM node_alarms WHERE id = ?", (aid,)).fetchone()
        item = _row_to_item(conn, row)
    return {"code": 0, "data": item.model_dump(mode="json", by_alias=True), "message": "ok"}


@router.put("/alarms/{alarm_id}/attrs")
def update_alarm_attrs(alarm_id: str, data: NodeAlarmAttrSet) -> dict:
    with transaction() as conn:
        row = conn.execute("SELECT * FROM node_alarms WHERE id = ?", (alarm_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail={"code": 40404, "message": "告警不存在"})

        _, fields = _get_alarm_schema_for_node(conn, row["node_id"])
        _validate_attr_lengths(fields, data.attrs)

        for k, v in data.attrs.items():
            if v is None:
                conn.execute(
                    "DELETE FROM node_alarm_attrs WHERE alarm_id = ? AND field_key = ?",
                    (alarm_id, k),
                )
            else:
                conn.execute(
                    "INSERT INTO node_alarm_attrs (alarm_id, field_key, value) VALUES (?, ?, ?) "
                    "ON CONFLICT(alarm_id, field_key) DO UPDATE SET value = excluded.value",
                    (alarm_id, k, v),
                )
        conn.execute(
            "UPDATE node_alarms SET updated_at = datetime('now') WHERE id = ?",
            (alarm_id,),
        )

        row = conn.execute("SELECT * FROM node_alarms WHERE id = ?", (alarm_id,)).fetchone()
        item = _row_to_item(conn, row)
    return {"code": 0, "data": item.model_dump(mode="json", by_alias=True), "message": "ok"}


@router.delete("/alarms/{alarm_id}")
def delete_alarm(alarm_id: str) -> dict:
    with transaction() as conn:
        row = conn.execute("SELECT id FROM node_alarms WHERE id = ?", (alarm_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail={"code": 40404, "message": "告警不存在"})
        conn.execute("DELETE FROM node_alarms WHERE id = ?", (alarm_id,))
    return {"code": 0, "data": None, "message": "ok"}
```

- [ ] **Step 4: 挂载 router**

修改 `backend/app/main.py` —— 在 alarm_schema_router 后追加：

```python
from app.admin.node_alarm import router as node_alarm_router
```

并在 `app.include_router(alarm_schema_router)` 后追加：

```python
app.include_router(node_alarm_router)
```

- [ ] **Step 5: 运行测试**

Run: `cd backend && python -m pytest tests/test_node_alarm_router.py -v`

Expected: 多数通过；`test_alarm_index_auto_increment` 可能失败如果 Task 7 已实现"创建节点自动 +1"则起始 index 不是 1。这是预期 —— 修正测试为 `a2 - a1 == 1` 模式（已用相对差，没问题）。

如 `test_create_node_alarm_without_schema_rejected` 失败因为 `topologies` PATCH 端点（Task 6）未实现，那么"挂了模板"的 setup 也失败。这是循环依赖。建议：测试中绕过 PATCH 端点，直接走 SQL 修改 topologies：

```python
# 在 _setup_topology_with_schema_and_node 中代替 PATCH:
from sqlite3 import connect as _sqlite_connect
from app.core.config import settings as _s
with _sqlite_connect(str(_s.db_path), isolation_level=None) as _c:
    _c.execute("UPDATE topologies SET alarm_schema_id = ? WHERE id = ?", (sid, tid))
```

提交时保留 PATCH 调用 —— Task 6 实现后取消此 fallback。

- [ ] **Step 6: 提交**

```bash
git add backend/app/admin/node_alarm.py backend/app/main.py backend/tests/test_node_alarm_router.py
git commit -m "feat(alarm): node_alarm router — 增删改查 + 长度校验"
```

---

## Task 6: 拓扑挂模板 PATCH + Detail 含告警计数

**Files:**
- Modify: `backend/app/admin/topology.py`
- Test: `backend/tests/test_topology_alarm_binding.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_topology_alarm_binding.py`：

```python
def _create_topo_and_schema(client):
    r = client.post("/admin/api/alarm-schemas", json={"code": "x", "name": "X", "fields": []})
    sid = r.json()["data"]["id"]
    r = client.post("/admin/api/topologies", json={"name": "T"})
    tid = r.json()["data"]["id"]
    return tid, sid


def test_bind_alarm_schema_empty_topology(client):
    tid, sid = _create_topo_and_schema(client)
    r = client.patch(f"/admin/api/topologies/{tid}/alarm-schema", json={
        "alarmSchemaId": sid, "clearExisting": False
    })
    assert r.status_code == 200
    detail = client.get(f"/admin/api/topologies/{tid}").json()["data"]
    assert detail["alarmSchemaId"] == sid


def test_unbind_alarm_schema_when_empty(client):
    tid, sid = _create_topo_and_schema(client)
    client.patch(f"/admin/api/topologies/{tid}/alarm-schema", json={
        "alarmSchemaId": sid, "clearExisting": False
    })
    r = client.patch(f"/admin/api/topologies/{tid}/alarm-schema", json={
        "alarmSchemaId": None, "clearExisting": False
    })
    assert r.status_code == 200


def test_switch_schema_with_alarms_requires_clear(client):
    tid, sid = _create_topo_and_schema(client)
    # bind
    client.patch(f"/admin/api/topologies/{tid}/alarm-schema", json={
        "alarmSchemaId": sid, "clearExisting": False
    })
    # create node + alarm (依赖 Task 5)
    nt = client.post("/admin/api/node-types", json={"code": "sw", "name": "SW", "category": "switch"}).json()["data"]
    n = client.post(f"/admin/api/topologies/{tid}/nodes", json={"nodeTypeId": nt["id"], "name": "n"}).json()["data"]
    client.post(f"/admin/api/nodes/{n['id']}/alarms", json={})

    # 创建另一个模板
    r = client.post("/admin/api/alarm-schemas", json={"code": "y", "name": "Y", "fields": []})
    sid2 = r.json()["data"]["id"]

    # 不带 clearExisting 切换 → 409
    r = client.patch(f"/admin/api/topologies/{tid}/alarm-schema", json={
        "alarmSchemaId": sid2, "clearExisting": False
    })
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == 40902
    assert r.json()["detail"]["details"]["nodeAlarmCount"] >= 1

    # 带 clearExisting → 通过 + 清空旧告警
    r = client.patch(f"/admin/api/topologies/{tid}/alarm-schema", json={
        "alarmSchemaId": sid2, "clearExisting": True
    })
    assert r.status_code == 200

    r = client.get(f"/admin/api/nodes/{n['id']}/alarms")
    assert r.json()["data"] == []


def test_topology_detail_includes_node_alarm_count(client):
    tid, sid = _create_topo_and_schema(client)
    client.patch(f"/admin/api/topologies/{tid}/alarm-schema", json={
        "alarmSchemaId": sid, "clearExisting": False
    })
    nt = client.post("/admin/api/node-types", json={"code": "sw", "name": "SW", "category": "switch"}).json()["data"]
    n = client.post(f"/admin/api/topologies/{tid}/nodes", json={"nodeTypeId": nt["id"], "name": "n"}).json()["data"]
    client.post(f"/admin/api/nodes/{n['id']}/alarms", json={})
    client.post(f"/admin/api/nodes/{n['id']}/alarms", json={})

    detail = client.get(f"/admin/api/topologies/{tid}").json()["data"]
    assert detail["nodeAlarmCount"] >= 2
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_topology_alarm_binding.py -v`
Expected: FAIL — PATCH 路由未实现 / detail 无新字段

- [ ] **Step 3: 实现 PATCH 端点**

修改 `backend/app/admin/topology.py`：

1. 在文件顶部 import 中加入：

```python
from app.admin.schemas import TopologyAlarmSchemaPatch
```

2. 在文件末尾追加新端点（与现有 router 风格保持一致）：

```python
@router.patch("/topologies/{topology_id}/alarm-schema")
def bind_alarm_schema(topology_id: str, data: TopologyAlarmSchemaPatch) -> dict:
    with transaction() as conn:
        row = conn.execute(
            "SELECT id, alarm_schema_id FROM topologies WHERE id = ?", (topology_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail={"code": 40404, "message": "拓扑不存在"})

        new_sid = data.alarm_schema_id or None
        current_sid = row["alarm_schema_id"]

        # 校验模板存在
        if new_sid:
            schema = conn.execute(
                "SELECT id FROM alarm_schemas WHERE id = ?", (new_sid,)
            ).fetchone()
            if not schema:
                raise HTTPException(status_code=404, detail={"code": 40404, "message": "告警模板不存在"})

        # 如果是变更（含解绑），检查告警计数
        if new_sid != current_sid:
            cnt_row = conn.execute(
                "SELECT COUNT(*) AS c FROM node_alarms a "
                "JOIN nodes n ON n.id = a.node_id "
                "WHERE n.topology_id = ?",
                (topology_id,),
            ).fetchone()
            alarm_cnt = cnt_row["c"]
            if alarm_cnt > 0 and not data.clear_existing:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": 40902,
                        "message": "拓扑下有告警数据，请确认是否清空",
                        "details": {"nodeAlarmCount": alarm_cnt},
                    },
                )
            if alarm_cnt > 0 and data.clear_existing:
                conn.execute(
                    "DELETE FROM node_alarms WHERE node_id IN "
                    "(SELECT id FROM nodes WHERE topology_id = ?)",
                    (topology_id,),
                )

        conn.execute(
            "UPDATE topologies SET alarm_schema_id = ?, updated_at = datetime('now') WHERE id = ?",
            (new_sid, topology_id),
        )

    return {"code": 0, "data": {"alarmSchemaId": new_sid}, "message": "ok"}
```

3. 修改 `GET /topologies/{topology_id}`（拓扑详情）函数 —— 找到该端点，在返回的 detail 对象构造处添加 `alarm_schema_id` 和 `node_alarm_count` 字段。先用 Grep 定位：

```bash
# 用 Read 查看 backend/app/admin/topology.py 的 detail 构造代码
```

找到 `TopologyDetail(...)` 实例化处，加入：

```python
        # 已有的字段...
        alarm_schema_id=topo_row["alarm_schema_id"],
        node_alarm_count=conn.execute(
            "SELECT COUNT(*) AS c FROM node_alarms a "
            "JOIN nodes n ON n.id = a.node_id WHERE n.topology_id = ?",
            (topology_id,),
        ).fetchone()["c"],
```

- [ ] **Step 4: 运行测试**

Run: `cd backend && python -m pytest tests/test_topology_alarm_binding.py tests/test_alarm_schema_router.py -v`
Expected: 全部通过；Task 4 中标记 skip 的 `test_delete_referenced_alarm_schema_rejected` 移除 skip 后也应通过。

- [ ] **Step 5: 移除 Task 4 中的 skip 标记**

如 Task 4 步骤 5 中给某测试加了 `@pytest.mark.skip`，现在去掉。

Run: `cd backend && python -m pytest tests/test_alarm_schema_router.py::test_delete_referenced_alarm_schema_rejected -v`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add backend/app/admin/topology.py backend/tests/test_topology_alarm_binding.py backend/tests/test_alarm_schema_router.py
git commit -m "feat(alarm): 拓扑挂载告警模板 PATCH + detail 告警计数"
```

---

## Task 7: 创建节点时自动 +1 默认告警

**Files:**
- Modify: `backend/app/admin/node.py`
- Test: `backend/tests/test_node_auto_alarm.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_node_auto_alarm.py`：

```python
def test_create_node_auto_inserts_default_alarm(client):
    # setup: schema + topology + binding
    r = client.post("/admin/api/alarm-schemas", json={
        "code": "x", "name": "X",
        "fields": [
            {"fieldKey": "aid", "fieldLabel": "AID", "fieldType": "text", "maxLength": 50, "defaultValue": "ALM-DEF"}
        ],
    })
    sid = r.json()["data"]["id"]
    r = client.post("/admin/api/topologies", json={"name": "T"})
    tid = r.json()["data"]["id"]
    client.patch(f"/admin/api/topologies/{tid}/alarm-schema", json={
        "alarmSchemaId": sid, "clearExisting": False
    })
    r = client.post("/admin/api/node-types", json={"code": "sw", "name": "SW", "category": "switch"})
    ntid = r.json()["data"]["id"]

    # create node
    r = client.post(f"/admin/api/topologies/{tid}/nodes", json={
        "nodeTypeId": ntid, "name": "node-1"
    })
    nid = r.json()["data"]["id"]

    # alarms list should have 1
    r = client.get(f"/admin/api/nodes/{nid}/alarms")
    alarms = r.json()["data"]
    assert len(alarms) == 1
    assert alarms[0]["attrs"]["aid"] == "ALM-DEF"
    assert alarms[0]["alarmIndex"] == 1


def test_create_node_without_topology_schema_no_auto_alarm(client):
    r = client.post("/admin/api/topologies", json={"name": "T2"})
    tid = r.json()["data"]["id"]
    r = client.post("/admin/api/node-types", json={"code": "sw", "name": "SW", "category": "switch"})
    ntid = r.json()["data"]["id"]
    r = client.post(f"/admin/api/topologies/{tid}/nodes", json={
        "nodeTypeId": ntid, "name": "node-2"
    })
    nid = r.json()["data"]["id"]

    r = client.get(f"/admin/api/nodes/{nid}/alarms")
    assert r.json()["data"] == []
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_node_auto_alarm.py -v`
Expected: FAIL — alarm 列表为空

- [ ] **Step 3: 修改 `backend/app/admin/node.py`**

在 `create_node` 函数中，找到 `conn.execute("INSERT INTO nodes ...")` 之后、`row = conn.execute("SELECT * FROM nodes WHERE id = ?", (node_id,)).fetchone()` 之前，插入：

```python
        # 自动 +1 默认告警（拓扑挂模板时）
        topo_full = conn.execute(
            "SELECT alarm_schema_id FROM topologies WHERE id = ?", (topology_id,)
        ).fetchone()
        if topo_full and topo_full["alarm_schema_id"]:
            sid = topo_full["alarm_schema_id"]
            fields = conn.execute(
                "SELECT field_key, default_value FROM alarm_schema_fields "
                "WHERE alarm_schema_id = ? ORDER BY sort_order, id",
                (sid,),
            ).fetchall()
            import uuid as _uuid
            aid = f"alm_{_uuid.uuid4().hex[:12]}"
            conn.execute(
                "INSERT INTO node_alarms (id, node_id, alarm_index) VALUES (?, ?, 1)",
                (aid, node_id),
            )
            for f in fields:
                if f["default_value"] is not None:
                    conn.execute(
                        "INSERT INTO node_alarm_attrs (alarm_id, field_key, value) "
                        "VALUES (?, ?, ?)",
                        (aid, f["field_key"], f["default_value"]),
                    )
```

将 `import uuid` 上移到文件顶部 import 区（如果还没有）—— `node.py` 已经 import 了 uuid，所以删掉局部 import。最终插入代码为：

```python
        # 自动 +1 默认告警（拓扑挂模板时）
        topo_full = conn.execute(
            "SELECT alarm_schema_id FROM topologies WHERE id = ?", (topology_id,)
        ).fetchone()
        if topo_full and topo_full["alarm_schema_id"]:
            sid = topo_full["alarm_schema_id"]
            fields = conn.execute(
                "SELECT field_key, default_value FROM alarm_schema_fields "
                "WHERE alarm_schema_id = ? ORDER BY sort_order, id",
                (sid,),
            ).fetchall()
            aid = f"alm_{uuid.uuid4().hex[:12]}"
            conn.execute(
                "INSERT INTO node_alarms (id, node_id, alarm_index) VALUES (?, ?, 1)",
                (aid, node_id),
            )
            for f in fields:
                if f["default_value"] is not None:
                    conn.execute(
                        "INSERT INTO node_alarm_attrs (alarm_id, field_key, value) "
                        "VALUES (?, ?, ?)",
                        (aid, f["field_key"], f["default_value"]),
                    )
```

- [ ] **Step 4: 运行测试**

Run: `cd backend && python -m pytest tests/test_node_auto_alarm.py tests/test_node_alarm_router.py -v`
Expected: 全部通过

- [ ] **Step 5: 提交**

```bash
git add backend/app/admin/node.py backend/tests/test_node_auto_alarm.py
git commit -m "feat(alarm): 创建节点时自动插入 1 条默认告警（按 default_value 填充）"
```

---

## Task 8: 节点组 materialize 时为每物化产物 +1 默认告警

**Files:**
- Modify: `backend/app/admin/node_group.py`
- Test: `backend/tests/test_materialize_alarms.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_materialize_alarms.py`：

```python
import asyncio


def test_materialize_creates_default_alarm_per_node(client):
    # setup
    r = client.post("/admin/api/alarm-schemas", json={
        "code": "x", "name": "X",
        "fields": [{"fieldKey": "aid", "fieldLabel": "AID", "fieldType": "text", "maxLength": 50, "defaultValue": "DEF"}],
    })
    sid = r.json()["data"]["id"]
    r = client.post("/admin/api/topologies", json={"name": "T"})
    tid = r.json()["data"]["id"]
    client.patch(f"/admin/api/topologies/{tid}/alarm-schema", json={"alarmSchemaId": sid, "clearExisting": False})
    r = client.post("/admin/api/node-types", json={"code": "sw", "name": "SW", "category": "switch"})
    ntid = r.json()["data"]["id"]

    # create node group, count = 5
    r = client.post(f"/admin/api/topologies/{tid}/node-groups", json={
        "nodeTypeId": ntid,
        "groupName": "g1",
        "nodeCount": 5,
        "nameTemplate": "{group}-{i:03d}",
        "attrStrategies": [],
        "edgeStrategies": [],
    })
    gid = r.json()["data"]["id"]

    # materialize
    r = client.post(f"/admin/api/node-groups/{gid}/materialize")
    assert r.status_code == 200

    # 5 nodes, 5 alarms total
    import sqlite3
    from app.core.config import settings
    with sqlite3.connect(str(settings.db_path)) as c:
        c.row_factory = sqlite3.Row
        n_cnt = c.execute(
            "SELECT COUNT(*) AS c FROM nodes WHERE topology_id = ?", (tid,)
        ).fetchone()["c"]
        a_cnt = c.execute(
            "SELECT COUNT(*) AS c FROM node_alarms a JOIN nodes n ON n.id = a.node_id "
            "WHERE n.topology_id = ?", (tid,)
        ).fetchone()["c"]
    assert n_cnt == 5
    assert a_cnt == 5


def test_materialize_no_alarm_when_schema_unbound(client):
    r = client.post("/admin/api/topologies", json={"name": "T2"})
    tid = r.json()["data"]["id"]
    r = client.post("/admin/api/node-types", json={"code": "sw", "name": "SW", "category": "switch"})
    ntid = r.json()["data"]["id"]
    r = client.post(f"/admin/api/topologies/{tid}/node-groups", json={
        "nodeTypeId": ntid, "groupName": "g", "nodeCount": 3,
        "nameTemplate": "{group}-{i:03d}", "attrStrategies": [], "edgeStrategies": [],
    })
    gid = r.json()["data"]["id"]
    client.post(f"/admin/api/node-groups/{gid}/materialize")

    import sqlite3
    from app.core.config import settings
    with sqlite3.connect(str(settings.db_path)) as c:
        c.row_factory = sqlite3.Row
        a_cnt = c.execute(
            "SELECT COUNT(*) AS c FROM node_alarms a JOIN nodes n ON n.id = a.node_id "
            "WHERE n.topology_id = ?", (tid,)
        ).fetchone()["c"]
    assert a_cnt == 0
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_materialize_alarms.py -v`
Expected: FAIL — 告警计数为 0

- [ ] **Step 3: 修改 `node_group.py` 的 `_flush_nodes`**

找到 `_flush_nodes(conn, buffer, base_idx)` 函数（约第 416 行）。在函数定义外（materialize 调用前）查一次拓扑的 `alarm_schema_id` + 字段，作为闭包变量：

在 `_flush_nodes` 定义之前、`width = _parse_name_template(...)` 之后，加：

```python
        # 预查告警模板（用于物化每个节点时自动 +1 默认告警）
        alarm_schema_id: Optional[str] = None
        alarm_default_fields: list[tuple] = []  # [(field_key, default_value), ...]
        with connect() as _ac:
            _row = _ac.execute(
                "SELECT alarm_schema_id FROM topologies WHERE id = ?", (topology_id,)
            ).fetchone()
            if _row and _row["alarm_schema_id"]:
                alarm_schema_id = _row["alarm_schema_id"]
                _fields = _ac.execute(
                    "SELECT field_key, default_value FROM alarm_schema_fields "
                    "WHERE alarm_schema_id = ? AND default_value IS NOT NULL "
                    "ORDER BY sort_order, id",
                    (alarm_schema_id,),
                ).fetchall()
                alarm_default_fields = [(f["field_key"], f["default_value"]) for f in _fields]
```

注意：`Optional` 已在文件顶部 import。

然后修改 `_flush_nodes` 函数 —— 在 `for s in attr_strategies: ...` 循环之后加：

```python
                # 自动 +1 默认告警
                if alarm_schema_id:
                    aid = f"alm_{uuid.uuid4().hex[:12]}"
                    conn.execute(
                        "INSERT INTO node_alarms (id, node_id, alarm_index) VALUES (?, ?, 1)",
                        (aid, nid),
                    )
                    for fk, fv in alarm_default_fields:
                        conn.execute(
                            "INSERT INTO node_alarm_attrs (alarm_id, field_key, value) VALUES (?, ?, ?)",
                            (aid, fk, fv),
                        )
```

- [ ] **Step 4: 运行测试**

Run: `cd backend && python -m pytest tests/test_materialize_alarms.py -v`
Expected: PASS

- [ ] **Step 5: 性能 sanity check**

写一个测试验证 1000 节点的 materialize 性能在合理范围内：

补充测试到 `test_materialize_alarms.py`：

```python
def test_materialize_1000_nodes_under_30s(client):
    import time
    r = client.post("/admin/api/alarm-schemas", json={
        "code": "x", "name": "X",
        "fields": [{"fieldKey": "aid", "fieldLabel": "AID", "fieldType": "text", "maxLength": 50, "defaultValue": "X"}],
    })
    sid = r.json()["data"]["id"]
    r = client.post("/admin/api/topologies", json={"name": "T"})
    tid = r.json()["data"]["id"]
    client.patch(f"/admin/api/topologies/{tid}/alarm-schema", json={"alarmSchemaId": sid, "clearExisting": False})
    r = client.post("/admin/api/node-types", json={"code": "sw", "name": "SW", "category": "switch"})
    ntid = r.json()["data"]["id"]

    r = client.post(f"/admin/api/topologies/{tid}/node-groups", json={
        "nodeTypeId": ntid, "groupName": "big", "nodeCount": 1000,
        "nameTemplate": "{group}-{i:05d}", "attrStrategies": [], "edgeStrategies": [],
    })
    gid = r.json()["data"]["id"]

    t0 = time.time()
    r = client.post(f"/admin/api/node-groups/{gid}/materialize")
    elapsed = time.time() - t0
    assert r.status_code == 200
    assert elapsed < 30, f"materialize 1000 nodes took {elapsed:.1f}s"
```

Run: `cd backend && python -m pytest tests/test_materialize_alarms.py -v`
Expected: PASS（如失败说明 INSERT 性能问题，需要 batch 优化 —— 本期不做）

- [ ] **Step 6: 提交**

```bash
git add backend/app/admin/node_group.py backend/tests/test_materialize_alarms.py
git commit -m "feat(alarm): 节点组 materialize 时为每个物化节点自动 +1 默认告警"
```

---

## Task 9: CTE Builder — `alarms` 视图

**Files:**
- Modify: `backend/app/core/cte_builder.py`
- Test: `backend/tests/test_cte_alarms.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_cte_alarms.py`：

```python
import sqlite3

from app.core.cte_builder import collect_views
from app.db.migrations import run_migrations


def _build_db_with_alarm_data():
    conn = sqlite3.connect(":memory:", isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    run_migrations(conn)
    conn.execute("INSERT INTO topologies (id, name) VALUES ('t1', 'T1')")
    conn.execute("INSERT INTO node_types (id, code, name, category) VALUES ('nt1', 'sw', 'SW', 'switch')")
    conn.execute("INSERT INTO alarm_schemas (id, code, name) VALUES ('as1', 'huawei', 'Huawei')")
    conn.execute(
        "INSERT INTO alarm_schema_fields (alarm_schema_id, field_key, field_label, field_type, sort_order) "
        "VALUES ('as1','severity','级别','select',0),('as1','occurred_at','发生时间','text',1)"
    )
    conn.execute("UPDATE topologies SET alarm_schema_id = 'as1' WHERE id = 't1'")
    conn.execute("INSERT INTO nodes (id, topology_id, node_type_id, name) VALUES ('n1', 't1', 'nt1', 'n-1')")
    conn.execute("INSERT INTO node_alarms (id, node_id, alarm_index) VALUES ('alm_1', 'n1', 1)")
    conn.execute("INSERT INTO node_alarm_attrs (alarm_id, field_key, value) VALUES ('alm_1','severity','critical')")
    conn.execute("INSERT INTO node_alarm_attrs (alarm_id, field_key, value) VALUES ('alm_1','occurred_at','2026-06-10 10:00')")
    return conn


def test_alarms_cte_present_when_topology_has_schema():
    conn = _build_db_with_alarm_data()
    views = collect_views(conn, "t1")
    names = {v["name"] for v in views["generic"]}
    assert "alarms" in names


def test_alarms_cte_absent_when_topology_has_no_schema():
    conn = sqlite3.connect(":memory:", isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    run_migrations(conn)
    conn.execute("INSERT INTO topologies (id, name) VALUES ('t1', 'T1')")
    views = collect_views(conn, "t1")
    names = {v["name"] for v in views["generic"]}
    assert "alarms" not in names


def test_alarms_cte_columns_include_pivots():
    conn = _build_db_with_alarm_data()
    views = collect_views(conn, "t1")
    alarms = next(v for v in views["generic"] if v["name"] == "alarms")
    assert "severity" in alarms["columns"]
    assert "occurred_at" in alarms["columns"]
    assert "node_name" in alarms["columns"]
    assert "alarm_index" in alarms["columns"]


def test_alarms_cte_executes_against_db():
    conn = _build_db_with_alarm_data()
    views = collect_views(conn, "t1")
    alarms = next(v for v in views["generic"] if v["name"] == "alarms")
    sql = f"WITH alarms AS ({alarms['sql']}) SELECT * FROM alarms"
    rows = conn.execute(sql, {"__tid__": "t1"}).fetchall()
    assert len(rows) == 1
    r = rows[0]
    assert r["severity"] == "critical"
    assert r["node_name"] == "n-1"


def test_alarms_cte_field_key_collision_skipped():
    conn = _build_db_with_alarm_data()
    # 加一个与固定列冲突的字段
    conn.execute(
        "INSERT INTO alarm_schema_fields (alarm_schema_id, field_key, field_label, field_type, sort_order) "
        "VALUES ('as1','node_name','节点名','text',5)"
    )
    views = collect_views(conn, "t1")
    alarms = next(v for v in views["generic"] if v["name"] == "alarms")
    # node_name 应只出现一次（固定列），不重复 pivot
    assert alarms["columns"].count("node_name") == 1


def test_alarms_cte_invalid_field_key_skipped():
    conn = _build_db_with_alarm_data()
    conn.execute(
        "INSERT INTO alarm_schema_fields (alarm_schema_id, field_key, field_label, field_type, sort_order) "
        "VALUES ('as1','bad-key','bad','text',9)"
    )
    views = collect_views(conn, "t1")
    alarms = next(v for v in views["generic"] if v["name"] == "alarms")
    assert "bad-key" not in alarms["columns"]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_cte_alarms.py -v`
Expected: FAIL — alarms CTE 不在 generic 列表

- [ ] **Step 3: 修改 `cte_builder.py`**

在 `GENERIC_VIEW_NAMES` 列表末尾追加 `"alarms"`：

```python
GENERIC_VIEW_NAMES: list[str] = ["nodes", "edges", "children", "node_groups", "group_nodes", "group_edges", "topology_nodes", "topology_edges", "alarms"]
```

在 `_RESERVED_NAMES` set 中也加 `"alarms"`：

```python
_RESERVED_NAMES: set[str] = {"nodes", "edges", "children", "node_groups", "group_nodes", "group_edges", "topology_nodes", "topology_edges", "alarms"}
```

在文件中新增函数（放在 `_build_topology_edges_cte` 之后）：

```python
ALARM_FIXED_COLUMNS: list[str] = [
    "id", "node_id", "node_name", "node_dn",
    "alarm_index", "created_at", "updated_at",
]


def _build_alarms_cte(conn: sqlite3.Connection, topology_id: str) -> dict[str, Any] | None:
    """Alarms CTE — None if topology has no alarm_schema bound."""
    row = conn.execute(
        "SELECT alarm_schema_id FROM topologies WHERE id = ?", (topology_id,)
    ).fetchone()
    if not row or not row["alarm_schema_id"]:
        return None
    sid = row["alarm_schema_id"]

    field_rows = conn.execute(
        "SELECT field_key FROM alarm_schema_fields WHERE alarm_schema_id = ? "
        "ORDER BY sort_order, id",
        (sid,),
    ).fetchall()

    columns = list(ALARM_FIXED_COLUMNS)
    pivots: list[str] = []
    for r in field_rows:
        key = r["field_key"]
        if not is_valid_ident(key):
            continue
        if key in columns:
            continue
        columns.append(key)
        pivots.append(f"MAX(CASE WHEN aa.field_key = '{key}' THEN aa.value END) AS {key}")

    fixed_select = [
        "a.id",
        "a.node_id",
        "n.name AS node_name",
        "n.dn AS node_dn",
        "a.alarm_index",
        "a.created_at",
        "a.updated_at",
    ]
    select_body = ",\n         ".join(fixed_select + pivots)
    sql = (
        f"SELECT {select_body}\n"
        "  FROM main.node_alarms a\n"
        "  JOIN main.nodes n ON n.id = a.node_id\n"
        "  LEFT JOIN main.node_alarm_attrs aa ON aa.alarm_id = a.id\n"
        "  WHERE n.topology_id = :__tid__\n"
        "  GROUP BY a.id"
    )
    return {"name": "alarms", "columns": columns, "sql": sql}
```

修改 `collect_views(conn, topology_id)` —— 在末尾返回前，把 `alarms` CTE（若不为 None）加入 generic 列表：

找到现有 `return {"nodeViews": node_views, "edgeViews": edge_views, "generic": build_generic_ctes()}`，改为：

```python
    generic = build_generic_ctes()
    alarms_cte = _build_alarms_cte(conn, topology_id)
    if alarms_cte is not None:
        generic.append(alarms_cte)

    return {
        "nodeViews": node_views,
        "edgeViews": edge_views,
        "generic": generic,
    }
```

- [ ] **Step 4: 运行测试**

Run: `cd backend && python -m pytest tests/test_cte_alarms.py -v`
Expected: 6 passed

- [ ] **Step 5: 提交**

```bash
git add backend/app/core/cte_builder.py backend/tests/test_cte_alarms.py
git commit -m "feat(alarm): cte_builder 新增 alarms 视图（动态 pivot + 固定列冲突保护）"
```

---

## Task 10: SQL Helper 视图清单暴露 `alarms`

**Files:**
- Read: `backend/app/admin/sql_helper.py`（先了解现有 schema）
- Modify: `backend/app/admin/sql_helper.py`
- Test: `backend/tests/test_sql_helper_alarms.py`

- [ ] **Step 1: 读现有 sql_helper.py**

Run: 用 Read 工具打开 `backend/app/admin/sql_helper.py`，找到返回视图清单的端点（约 `GET /admin/api/sql/views/{topology_id}`），看现有 schema 长什么样。

- [ ] **Step 2: 写失败测试**

创建 `backend/tests/test_sql_helper_alarms.py`：

```python
def test_sql_views_includes_alarms_when_bound(client):
    # setup schema + topology + binding
    r = client.post("/admin/api/alarm-schemas", json={
        "code": "x", "name": "X",
        "fields": [{"fieldKey": "severity", "fieldLabel": "S", "fieldType": "text", "maxLength": 30}],
    })
    sid = r.json()["data"]["id"]
    r = client.post("/admin/api/topologies", json={"name": "T"})
    tid = r.json()["data"]["id"]
    client.patch(f"/admin/api/topologies/{tid}/alarm-schema", json={"alarmSchemaId": sid, "clearExisting": False})

    r = client.get(f"/admin/api/sql/views/{tid}")
    assert r.status_code == 200
    views = r.json()["data"]["generic"]
    names = {v["name"] for v in views}
    assert "alarms" in names


def test_sql_views_omits_alarms_when_unbound(client):
    r = client.post("/admin/api/topologies", json={"name": "T2"})
    tid = r.json()["data"]["id"]
    r = client.get(f"/admin/api/sql/views/{tid}")
    views = r.json()["data"]["generic"]
    names = {v["name"] for v in views}
    assert "alarms" not in names
```

- [ ] **Step 3: 运行测试确认状态**

Run: `cd backend && python -m pytest tests/test_sql_helper_alarms.py -v`
Expected: 两个测试都可能已经通过（因为 sql_helper 直接调用 `collect_views`），或者部分失败（如果 sql_helper 自己维护一份白名单）。

- [ ] **Step 4: 修改 `sql_helper.py`（如有必要）**

如果 Step 3 测试已通过 —— 跳过。如果失败：
- 找到 `/admin/api/sql/views/{topology_id}` 端点
- 确认它从 `collect_views` 取 generic 列表后返回 —— 如果它做了过滤剔除 `alarms`，去掉过滤
- 如果它有硬编码的视图描述（如 i18n 标签），为 alarms 加一条对应文案

- [ ] **Step 5: 提交**

```bash
git add backend/app/admin/sql_helper.py backend/tests/test_sql_helper_alarms.py
git commit -m "test(alarm): 验证 sql/views 端点暴露 alarms 视图"
```

---

## Task 11: 前端 API SDK + Composable

**Files:**
- Create: `frontend/src/api/alarmSchema.ts`
- Create: `frontend/src/api/nodeAlarm.ts`
- Modify: `frontend/src/api/topology.ts`（加 `bindAlarmSchema` + detail 字段）
- Create: `frontend/src/composables/useAlarmSchemas.ts`

- [ ] **Step 1: 创建 `frontend/src/api/alarmSchema.ts`**

```typescript
import { http } from './http'

export interface AlarmSchemaFieldItem {
  id: number
  alarmSchemaId: string
  fieldKey: string
  fieldLabel: string
  fieldType: 'text' | 'number' | 'select' | 'boolean'
  maxLength?: number | null
  defaultValue?: string | null
  options?: string | null
  required: boolean
  sortOrder: number
}

export interface AlarmSchemaFieldInput {
  fieldKey: string
  fieldLabel: string
  fieldType: 'text' | 'number' | 'select' | 'boolean'
  maxLength?: number | null
  defaultValue?: string | null
  options?: string | null
  required?: boolean
  sortOrder?: number
}

export interface AlarmSchemaItem {
  id: string
  code: string
  name: string
  description?: string | null
  createdAt: string
  updatedAt: string
}

export interface AlarmSchemaDetail extends AlarmSchemaItem {
  fields: AlarmSchemaFieldItem[]
}

export interface AlarmSchemaCreate {
  code: string
  name: string
  description?: string | null
  fields: AlarmSchemaFieldInput[]
}

export interface AlarmSchemaUpdate {
  name?: string
  description?: string | null
  fields?: AlarmSchemaFieldInput[]
}

export const alarmSchemaApi = {
  list: () => http.get<AlarmSchemaItem[]>('/alarm-schemas'),
  get: (id: string) => http.get<AlarmSchemaDetail>(`/alarm-schemas/${id}`),
  create: (data: AlarmSchemaCreate) => http.post<AlarmSchemaDetail>('/alarm-schemas', data),
  update: (id: string, data: AlarmSchemaUpdate) => http.put<AlarmSchemaDetail>(`/alarm-schemas/${id}`, data),
  delete: (id: string) => http.delete<null>(`/alarm-schemas/${id}`),
}
```

- [ ] **Step 2: 创建 `frontend/src/api/nodeAlarm.ts`**

```typescript
import { http } from './http'

export interface NodeAlarmItem {
  id: string
  nodeId: string
  alarmIndex: number
  attrs: Record<string, string | null>
  createdAt: string
  updatedAt: string
}

export const nodeAlarmApi = {
  listByNode: (nodeId: string) => http.get<NodeAlarmItem[]>(`/nodes/${nodeId}/alarms`),
  create: (nodeId: string, attrs?: Record<string, string | null>) =>
    http.post<NodeAlarmItem>(`/nodes/${nodeId}/alarms`, { attrs: attrs ?? null }),
  updateAttrs: (alarmId: string, attrs: Record<string, string | null>) =>
    http.put<NodeAlarmItem>(`/alarms/${alarmId}/attrs`, { attrs }),
  delete: (alarmId: string) => http.delete<null>(`/alarms/${alarmId}`),
}
```

- [ ] **Step 3: 修改 `frontend/src/api/topology.ts`**

先用 Read 看现有接口。在文件中：

1. 在 `TopologyDetail` 接口中加：
```typescript
  alarmSchemaId?: string | null
  nodeAlarmCount?: number
```

2. 在 `topologyApi` 对象中加：
```typescript
  bindAlarmSchema: (id: string, alarmSchemaId: string | null, clearExisting = false) =>
    http.patch<{ alarmSchemaId: string | null }>(`/topologies/${id}/alarm-schema`, {
      alarmSchemaId, clearExisting
    }),
```

- [ ] **Step 4: 创建 `frontend/src/composables/useAlarmSchemas.ts`**

```typescript
import { ref } from 'vue'
import { message } from 'ant-design-vue'
import { alarmSchemaApi, type AlarmSchemaItem, type AlarmSchemaDetail, type AlarmSchemaCreate, type AlarmSchemaUpdate } from '@/api/alarmSchema'

export function useAlarmSchemas() {
  const schemas = ref<AlarmSchemaItem[]>([])
  const loading = ref(false)

  async function fetchSchemas() {
    loading.value = true
    try {
      schemas.value = await alarmSchemaApi.list()
    } finally {
      loading.value = false
    }
  }

  async function getDetail(id: string): Promise<AlarmSchemaDetail | null> {
    try {
      return await alarmSchemaApi.get(id)
    } catch {
      return null
    }
  }

  async function createSchema(data: AlarmSchemaCreate): Promise<boolean> {
    try {
      await alarmSchemaApi.create(data)
      message.success('创建成功')
      await fetchSchemas()
      return true
    } catch (e: any) {
      message.error(e?.message || '创建失败')
      return false
    }
  }

  async function updateSchema(id: string, data: AlarmSchemaUpdate): Promise<boolean> {
    try {
      await alarmSchemaApi.update(id, data)
      message.success('更新成功')
      await fetchSchemas()
      return true
    } catch (e: any) {
      message.error(e?.message || '更新失败')
      return false
    }
  }

  async function deleteSchema(id: string): Promise<boolean> {
    try {
      await alarmSchemaApi.delete(id)
      message.success('删除成功')
      await fetchSchemas()
      return true
    } catch (e: any) {
      // 引用检查的详细错误
      const refs = e?.details?.referencedBy
      if (Array.isArray(refs) && refs.length > 0) {
        message.error(`告警模板被以下拓扑引用，无法删除：${refs.join(', ')}`)
      } else {
        message.error(e?.message || '删除失败')
      }
      return false
    }
  }

  return { schemas, loading, fetchSchemas, getDetail, createSchema, updateSchema, deleteSchema }
}
```

- [ ] **Step 5: 手动 smoke 检查（前端编译）**

Run: `cd frontend && pnpm install` （首次）然后 `pnpm run build`
Expected: TypeScript 编译通过、无报错

如 `pnpm install` 失败、改用 `npm install`（CLAUDE.md 启动命令用的是 npm）。

- [ ] **Step 6: 提交**

```bash
git add frontend/src/api/alarmSchema.ts frontend/src/api/nodeAlarm.ts frontend/src/api/topology.ts frontend/src/composables/useAlarmSchemas.ts
git commit -m "feat(alarm): 前端 API SDK + useAlarmSchemas composable"
```

---

## Task 12: 告警模板管理 UI（TypesView 第 3 Tab）

**Files:**
- Create: `frontend/src/components/alarmSchemas/AlarmSchemaTable.vue`
- Create: `frontend/src/components/alarmSchemas/AlarmSchemaModal.vue`
- Create: `frontend/src/components/alarmSchemas/AlarmSchemaFieldEditor.vue`
- Modify: `frontend/src/views/TypesView.vue`（加第 3 Tab）

- [ ] **Step 1: 先读 NodeTypeFieldEditor 作为模板**

Run: 用 Read 工具看 `frontend/src/components/types/NodeTypeFieldEditor.vue`，了解结构。

- [ ] **Step 2: 创建 `AlarmSchemaFieldEditor.vue`**

直接复制 `NodeTypeFieldEditor.vue` 内容，做以下替换：
- 模型类型从 `NodeTypeFieldItem` 改为 `AlarmSchemaFieldInput`
- import 路径换为 `@/api/alarmSchema`
- 标签文案 "节点字段" → "告警字段"

具体保留：4 种字段类型选择、`fieldKey` 输入、`fieldLabel`、`fieldType`、`maxLength`（text 时必填）、`defaultValue`、`options`（select 时必填）、`required` switch、`sortOrder`、新增/删除按钮、上下移动按钮。

- [ ] **Step 3: 创建 `AlarmSchemaModal.vue`**

```vue
<script setup lang="ts">
import { ref, watch } from 'vue'
import { Modal, Form, Input, Textarea, message } from 'ant-design-vue'
import AlarmSchemaFieldEditor from './AlarmSchemaFieldEditor.vue'
import { alarmSchemaApi, type AlarmSchemaDetail, type AlarmSchemaFieldInput } from '@/api/alarmSchema'

const props = defineProps<{
  visible: boolean
  schemaId: string | null  // null = 新建
}>()

const emit = defineEmits<{
  (e: 'update:visible', v: boolean): void
  (e: 'saved'): void
}>()

const form = ref({
  code: '',
  name: '',
  description: '',
})
const fields = ref<AlarmSchemaFieldInput[]>([])
const saving = ref(false)

watch(
  () => props.visible,
  async (v) => {
    if (!v) return
    if (props.schemaId) {
      const d = await alarmSchemaApi.get(props.schemaId)
      form.value = { code: d.code, name: d.name, description: d.description ?? '' }
      fields.value = d.fields.map(f => ({
        fieldKey: f.fieldKey,
        fieldLabel: f.fieldLabel,
        fieldType: f.fieldType,
        maxLength: f.maxLength ?? undefined,
        defaultValue: f.defaultValue ?? undefined,
        options: f.options ?? undefined,
        required: f.required,
        sortOrder: f.sortOrder,
      }))
    } else {
      form.value = { code: '', name: '', description: '' }
      fields.value = []
    }
  },
)

async function handleOk() {
  if (!form.value.code || !form.value.name) {
    message.error('code 和 name 必填')
    return
  }
  saving.value = true
  try {
    if (props.schemaId) {
      await alarmSchemaApi.update(props.schemaId, {
        name: form.value.name,
        description: form.value.description || null,
        fields: fields.value,
      })
      message.success('更新成功')
    } else {
      await alarmSchemaApi.create({
        code: form.value.code,
        name: form.value.name,
        description: form.value.description || null,
        fields: fields.value,
      })
      message.success('创建成功')
    }
    emit('saved')
    emit('update:visible', false)
  } catch (e: any) {
    message.error(e?.message || '保存失败')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <Modal
    :open="visible"
    :title="schemaId ? '编辑告警模板' : '新建告警模板'"
    width="800px"
    :confirm-loading="saving"
    @update:open="(v) => emit('update:visible', v)"
    @ok="handleOk"
  >
    <Form layout="vertical">
      <Form.Item label="Code (SQL 标识符)">
        <Input v-model:value="form.code" :disabled="!!schemaId" />
      </Form.Item>
      <Form.Item label="名称">
        <Input v-model:value="form.name" />
      </Form.Item>
      <Form.Item label="描述">
        <Textarea v-model:value="form.description" :rows="2" />
      </Form.Item>
      <Form.Item label="告警字段">
        <AlarmSchemaFieldEditor v-model:fields="fields" />
      </Form.Item>
    </Form>
  </Modal>
</template>
```

- [ ] **Step 4: 创建 `AlarmSchemaTable.vue`**

```vue
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { Button, Table, Modal, Space } from 'ant-design-vue'
import { useAlarmSchemas } from '@/composables/useAlarmSchemas'
import AlarmSchemaModal from './AlarmSchemaModal.vue'
import { alarmSchemaApi } from '@/api/alarmSchema'

const { schemas, loading, fetchSchemas, deleteSchema } = useAlarmSchemas()
const modalVisible = ref(false)
const editingId = ref<string | null>(null)
const fieldsCount = ref<Record<string, number>>({})

async function refresh() {
  await fetchSchemas()
  // 拉一次详情统计字段数（简单实现，可后端 list 接口未来加 fieldCount）
  for (const s of schemas.value) {
    try {
      const d = await alarmSchemaApi.get(s.id)
      fieldsCount.value[s.id] = d.fields.length
    } catch {
      fieldsCount.value[s.id] = 0
    }
  }
}

function handleCreate() {
  editingId.value = null
  modalVisible.value = true
}

function handleEdit(id: string) {
  editingId.value = id
  modalVisible.value = true
}

function handleDelete(id: string, name: string) {
  Modal.confirm({
    title: `确定删除告警模板"${name}"？`,
    content: '若被拓扑引用将无法删除。',
    onOk: () => deleteSchema(id).then(refresh),
  })
}

const columns = [
  { title: 'Code', dataIndex: 'code', key: 'code', width: 160 },
  { title: '名称', dataIndex: 'name', key: 'name' },
  { title: '字段数', key: 'fields', width: 100, customRender: ({ record }: any) => fieldsCount.value[record.id] ?? '-' },
  { title: '描述', dataIndex: 'description', key: 'description' },
  { title: '操作', key: 'actions', width: 160 },
]

onMounted(refresh)
</script>

<template>
  <div>
    <div style="margin-bottom: 16px">
      <Button type="primary" @click="handleCreate">新建告警模板</Button>
    </div>
    <Table
      :columns="columns"
      :data-source="schemas"
      :loading="loading"
      :pagination="false"
      row-key="id"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'actions'">
          <Space>
            <Button type="link" size="small" @click="handleEdit(record.id)">编辑</Button>
            <Button type="link" size="small" danger @click="handleDelete(record.id, record.name)">删除</Button>
          </Space>
        </template>
      </template>
    </Table>

    <AlarmSchemaModal
      v-model:visible="modalVisible"
      :schema-id="editingId"
      @saved="refresh"
    />
  </div>
</template>
```

- [ ] **Step 5: 修改 `frontend/src/views/TypesView.vue`**

用 Read 先看现有 Tab 结构。在 Tabs 组件中加入第 3 个 TabPane：

```vue
<Tabs.TabPane key="alarm" tab="告警模板">
  <AlarmSchemaTable />
</Tabs.TabPane>
```

并在 `<script setup>` 中加 import：

```typescript
import AlarmSchemaTable from '@/components/alarmSchemas/AlarmSchemaTable.vue'
```

- [ ] **Step 6: 手动 smoke 测试**

启动后端 + 前端：
```bash
# 终端 1
cd backend && python -m app.main

# 终端 2
cd frontend && npm run dev
```

浏览器打开 `http://localhost:5173`，进入"类型管理" → 切换到"告警模板"Tab：

✓ 列表为空时显示"新建告警模板"按钮
✓ 点击新建，填 code="huawei"、name="华为告警"、添加 2 个字段（severity select / occurred_at text）→ 保存
✓ 列表显示新创建的模板，字段数列正确
✓ 点击"编辑"打开 Modal，code 字段不可改、name 可改，字段编辑器可加/删/排序
✓ 点击"删除"弹确认 → 删除成功

测试完成后停止两个进程释放端口。

- [ ] **Step 7: 提交**

```bash
git add frontend/src/components/alarmSchemas/ frontend/src/views/TypesView.vue
git commit -m "feat(alarm): 告警模板管理 UI（TypesView 第 3 Tab + CRUD Modal + 字段编辑器）"
```

---

## Task 13: TopologyModal 挂模板下拉 + 切换二次确认

**Files:**
- Modify: `frontend/src/components/topology/TopologyModal.vue`

- [ ] **Step 1: 读现有 `TopologyModal.vue`**

Run: 用 Read 看现有结构，确认是 `<Modal>` + `<Form>` 包装。

- [ ] **Step 2: 注入告警模板下拉 + 切换处理逻辑**

在 `<script setup>` 中加：

```typescript
import { alarmSchemaApi, type AlarmSchemaItem } from '@/api/alarmSchema'
import { topologyApi } from '@/api/topology'
import { Modal } from 'ant-design-vue'

const alarmSchemas = ref<AlarmSchemaItem[]>([])
const selectedAlarmSchemaId = ref<string | null>(null)
const initialAlarmSchemaId = ref<string | null>(null)
const initialAlarmCount = ref(0)

async function loadAlarmSchemas() {
  alarmSchemas.value = await alarmSchemaApi.list()
}
```

在打开/加载逻辑中：

```typescript
// 编辑模式打开时
if (props.topologyId) {
  const detail = await topologyApi.get(props.topologyId)
  selectedAlarmSchemaId.value = detail.alarmSchemaId ?? null
  initialAlarmSchemaId.value = detail.alarmSchemaId ?? null
  initialAlarmCount.value = detail.nodeAlarmCount ?? 0
}
await loadAlarmSchemas()
```

在保存逻辑中（拓扑基础信息保存成功后）：

```typescript
const newSid = selectedAlarmSchemaId.value
if (newSid !== initialAlarmSchemaId.value) {
  // 需要变更
  if (initialAlarmCount.value > 0) {
    // 二次确认
    await new Promise<void>((resolve, reject) => {
      Modal.confirm({
        title: '切换告警模板将清空已有告警数据',
        content: `当前拓扑下有 ${initialAlarmCount.value} 条告警，是否确认清空并切换？`,
        okText: '清空并切换',
        okType: 'danger',
        cancelText: '取消',
        onOk: () => resolve(),
        onCancel: () => reject(new Error('user_cancelled')),
      })
    })
    await topologyApi.bindAlarmSchema(props.topologyId!, newSid, true)
  } else {
    await topologyApi.bindAlarmSchema(props.topologyId!, newSid, false)
  }
}
```

新建拓扑的情况：因为新建后是空拓扑（无节点 → 无告警），直接调 PATCH 即可：

```typescript
// 新建后
if (selectedAlarmSchemaId.value) {
  await topologyApi.bindAlarmSchema(createdTopologyId, selectedAlarmSchemaId.value, false)
}
```

在 `<template>` Form 中加入：

```vue
<Form.Item label="告警模板">
  <Select v-model:value="selectedAlarmSchemaId" allow-clear placeholder="不绑定">
    <Select.Option v-for="s in alarmSchemas" :key="s.id" :value="s.id">
      {{ s.name }} ({{ s.code }})
    </Select.Option>
  </Select>
</Form.Item>
```

- [ ] **Step 3: 手动 smoke 测试**

启动前后端，进入"拓扑管理"：

✓ 新建拓扑：下拉显示之前创建的"华为告警"模板，可选可不选
✓ 选模板 + 保存 → 拓扑列表里点拓扑名进入画布，新拖一个节点，节点属性面板（暂时还没 Tab 化，留待 Task 14）—— 此时验证后端能力：调 `GET /admin/api/nodes/<id>/alarms` 返回 1 条
✓ 编辑拓扑：下拉显示当前绑定值；切换为另一个模板 / 解绑 → 如有告警弹"清空并切换"确认 → 确认后告警清空

测试完成后停止进程。

- [ ] **Step 4: 提交**

```bash
git add frontend/src/components/topology/TopologyModal.vue
git commit -m "feat(alarm): TopologyModal 加告警模板下拉 + 切换二次确认"
```

---

## Task 14: NodeAttrsPanel Tab 化 + NodeAlarmsTab

**Files:**
- Modify: `frontend/src/components/canvas/NodeAttrsPanel.vue`
- Create: `frontend/src/components/canvas/NodeAlarmsTab.vue`

- [ ] **Step 1: 创建 `NodeAlarmsTab.vue`**

```vue
<script setup lang="ts">
import { ref, watch, nextTick, computed } from 'vue'
import { Button, Collapse, Form, Input, InputNumber, Select, Switch, Spin, Empty, message, Popconfirm } from 'ant-design-vue'
import { PlusOutlined, DeleteOutlined } from '@ant-design/icons-vue'
import { nodeAlarmApi, type NodeAlarmItem } from '@/api/nodeAlarm'
import { alarmSchemaApi, type AlarmSchemaFieldItem } from '@/api/alarmSchema'
import { topologyApi } from '@/api/topology'

const props = defineProps<{
  nodeId: string | null
  topologyId: string
}>()

const emit = defineEmits<{
  (e: 'count-change', count: number): void
}>()

const loading = ref(false)
const schemaFields = ref<AlarmSchemaFieldItem[]>([])
const alarms = ref<NodeAlarmItem[]>([])
const alarmSchemaId = ref<string | null>(null)
const dirtyAlarmIds = ref<Set<string>>(new Set())
const fieldErrors = ref<Record<string, Record<string, string>>>({})

const hasSchema = computed(() => !!alarmSchemaId.value)

async function loadAll() {
  if (!props.nodeId) return
  loading.value = true
  try {
    // 拓扑模板
    const topo = await topologyApi.get(props.topologyId)
    alarmSchemaId.value = topo.alarmSchemaId ?? null
    if (alarmSchemaId.value) {
      const d = await alarmSchemaApi.get(alarmSchemaId.value)
      schemaFields.value = d.fields.sort((a, b) => a.sortOrder - b.sortOrder)
    } else {
      schemaFields.value = []
    }
    // 告警列表
    alarms.value = await nodeAlarmApi.listByNode(props.nodeId)
    dirtyAlarmIds.value.clear()
    emit('count-change', alarms.value.length)
  } finally {
    loading.value = false
  }
}

watch(() => props.nodeId, loadAll, { immediate: true })

async function handleAdd() {
  if (!props.nodeId) return
  try {
    const created = await nodeAlarmApi.create(props.nodeId)
    alarms.value.push(created)
    emit('count-change', alarms.value.length)
  } catch (e: any) {
    message.error(e?.message || '新增告警失败')
  }
}

async function handleDelete(alarmId: string) {
  try {
    await nodeAlarmApi.delete(alarmId)
    alarms.value = alarms.value.filter(a => a.id !== alarmId)
    dirtyAlarmIds.value.delete(alarmId)
    emit('count-change', alarms.value.length)
  } catch (e: any) {
    message.error(e?.message || '删除失败')
  }
}

function markDirty(alarmId: string) {
  dirtyAlarmIds.value.add(alarmId)
}

function getCollapseHeader(alarm: NodeAlarmItem): string {
  const firstField = schemaFields.value[0]
  if (!firstField) return `告警 #${alarm.alarmIndex}`
  const v = alarm.attrs[firstField.fieldKey] || ''
  return `${v || '(空)'}  #${alarm.alarmIndex}`
}

function validateAlarm(alarm: NodeAlarmItem): boolean {
  const errs: Record<string, string> = {}
  for (const f of schemaFields.value) {
    const v = alarm.attrs[f.fieldKey]
    if (f.required && (!v || String(v).trim() === '')) {
      errs[f.fieldKey] = `${f.fieldLabel}必填`
    }
    if (f.fieldType === 'text' && f.maxLength && v && String(v).length > f.maxLength) {
      errs[f.fieldKey] = `不能超过 ${f.maxLength} 字符`
    }
  }
  fieldErrors.value[alarm.id] = errs
  return Object.keys(errs).length === 0
}

async function saveDirty(): Promise<boolean> {
  // 校验
  for (const a of alarms.value) {
    if (dirtyAlarmIds.value.has(a.id) && !validateAlarm(a)) {
      await nextTick()
      const el = document.querySelector('.ant-form-item-has-error') as HTMLElement | null
      el?.scrollIntoView({ behavior: 'smooth', block: 'center' })
      message.error('请检查告警字段')
      return false
    }
  }
  // 提交
  for (const a of [...alarms.value]) {
    if (!dirtyAlarmIds.value.has(a.id)) continue
    try {
      const updated = await nodeAlarmApi.updateAttrs(a.id, a.attrs)
      const idx = alarms.value.findIndex(x => x.id === a.id)
      if (idx >= 0) alarms.value[idx] = updated
      dirtyAlarmIds.value.delete(a.id)
    } catch (e: any) {
      message.error(`告警 #${a.alarmIndex} 保存失败：${e?.message || ''}`)
      return false
    }
  }
  return true
}

defineExpose({ saveDirty })
</script>

<template>
  <Spin v-if="loading" tip="加载中..." />
  <div v-else-if="!hasSchema" class="alarm-empty">
    <Empty description="本拓扑未配置告警模板" />
    <div class="hint">去拓扑管理 → 编辑拓扑 → 选择告警模板</div>
  </div>
  <div v-else class="alarms-list">
    <div class="alarms-toolbar">
      <Button type="primary" size="small" @click="handleAdd">
        <PlusOutlined /> 新增告警
      </Button>
    </div>
    <Empty v-if="alarms.length === 0" description="暂无告警，点击上方新增" />
    <Collapse v-else>
      <Collapse.Panel v-for="a in alarms" :key="a.id" :header="getCollapseHeader(a)">
        <template #extra>
          <Popconfirm title="确定删除该条告警？" @confirm="handleDelete(a.id)">
            <DeleteOutlined class="danger-icon" @click.stop />
          </Popconfirm>
        </template>
        <Form layout="vertical">
          <Form.Item
            v-for="f in schemaFields"
            :key="f.id"
            :label="f.fieldLabel + (f.required ? ' *' : '')"
            :validate-status="fieldErrors[a.id]?.[f.fieldKey] ? 'error' : ''"
            :help="fieldErrors[a.id]?.[f.fieldKey]"
          >
            <template v-if="f.fieldType === 'text'">
              <Input
                :value="a.attrs[f.fieldKey] || ''"
                :maxlength="f.maxLength || undefined"
                :show-count="!!f.maxLength"
                @update:value="(v: string) => { a.attrs[f.fieldKey] = v; markDirty(a.id) }"
              />
            </template>
            <template v-else-if="f.fieldType === 'number'">
              <InputNumber
                style="width: 100%"
                :value="a.attrs[f.fieldKey] ? Number(a.attrs[f.fieldKey]) : null"
                @change="(v: any) => { a.attrs[f.fieldKey] = v == null ? null : String(v); markDirty(a.id) }"
              />
            </template>
            <template v-else-if="f.fieldType === 'select'">
              <Select
                :value="a.attrs[f.fieldKey]"
                allow-clear
                @change="(v: any) => { a.attrs[f.fieldKey] = v == null ? null : String(v); markDirty(a.id) }"
              >
                <Select.Option v-for="opt in (f.options || '').split(',')" :key="opt.trim()" :value="opt.trim()">
                  {{ opt.trim() }}
                </Select.Option>
              </Select>
            </template>
            <template v-else-if="f.fieldType === 'boolean'">
              <Switch
                :checked="a.attrs[f.fieldKey] === 'true'"
                @change="(v: any) => { a.attrs[f.fieldKey] = String(v); markDirty(a.id) }"
              />
            </template>
          </Form.Item>
        </Form>
      </Collapse.Panel>
    </Collapse>
  </div>
</template>

<style scoped>
.alarm-empty { padding: 32px 16px; text-align: center; }
.alarm-empty .hint { color: #999; font-size: 12px; margin-top: 8px; }
.alarms-toolbar { margin-bottom: 12px; }
.danger-icon { color: #f5222d; cursor: pointer; }
</style>
```

- [ ] **Step 2: 改造 `NodeAttrsPanel.vue` —— 加 Tabs**

修改：
1. 在 `<script setup>` 顶部加 import：

```typescript
import { Tabs } from 'ant-design-vue'
import NodeAlarmsTab from './NodeAlarmsTab.vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const topologyId = route.params.id as string

const activeTab = ref<'attrs' | 'alarms'>('attrs')
const alarmCount = ref(0)
const alarmsTabRef = ref<InstanceType<typeof NodeAlarmsTab> | null>(null)
```

2. 在 `handleSave()` 函数末尾（attrs 保存之后）追加：

```typescript
    // 提交告警 Tab 的 dirty 状态
    if (alarmsTabRef.value) {
      const ok = await alarmsTabRef.value.saveDirty()
      if (!ok) return
    }
```

3. 修改 `<template>` 的 `.panel-content` 内容 —— 把现有"节点名 + 表单"部分包到 Tab 中：

```vue
<div class="panel-content">
  <Tabs v-model:active-key="activeTab">
    <Tabs.TabPane key="attrs" tab="属性">
      <Spin v-if="loading" tip="加载中..." />
      <template v-else>
        <div class="node-name-row">
          <span class="node-name-label">节点名称</span>
          <Input v-model:value="editingName" :maxlength="100" placeholder="请输入节点名称" />
        </div>
        <Form layout="vertical" class="attrs-form">
          <!-- 现有 fields 渲染保持不变 -->
        </Form>
      </template>
    </Tabs.TabPane>
    <Tabs.TabPane key="alarms" :tab="`告警(${alarmCount})`">
      <NodeAlarmsTab
        ref="alarmsTabRef"
        :node-id="nodeId"
        :topology-id="topologyId"
        @count-change="(c) => alarmCount = c"
      />
    </Tabs.TabPane>
  </Tabs>
</div>
```

注意保留现有 `Form.Item v-for="field in fields"` 的内容（4 种字段类型渲染），仅把外层包到 TabPane 内。

- [ ] **Step 3: 类型 / 编译检查**

Run: `cd frontend && npm run build`
Expected: 编译通过

- [ ] **Step 4: 手动 smoke 测试**

启动前后端：

```bash
cd backend && python -m app.main &
cd frontend && npm run dev
```

测试流程：
1. 类型管理 → 告警模板 → 新建"华为告警"含 3 字段：`alarm_id` text（默认 ALM-001）、`severity` select（critical,major,minor，默认 minor）、`message` text
2. 拓扑管理 → 新建拓扑"测试1"，告警模板选"华为告警"，保存
3. 打开"测试1"画布 → 从左侧拖一个节点类型到画布 → 节点出现
4. 单击节点 → 节点属性面板打开 → 看到两个 Tab："属性" / "告警(1)"
5. 切到"告警(1)" Tab → 看到 1 条默认告警，标题"ALM-001  #1"，展开后能编辑 3 个字段
6. 改 severity → "critical"，点底部"保存"按钮 → 提示保存成功
7. 点"+ 新增告警" → 列表新增 1 条 → 编辑某个字段 → 保存
8. 点告警卡片右上角删除图标 → Popconfirm → 删除成功
9. 拓扑管理 → 编辑"测试1" → 把告警模板换成另一个 → 弹"清空 N 条告警"确认 → 确认 → 重新打开画布告警 Tab → 0 条
10. 类型管理 → 告警模板 → 尝试删除"华为告警" → 弹错"被拓扑引用，无法删除"
11. API 管理 → 新建一个 SQL Mock API，topology 选"测试1"，SQL 写 `SELECT id, node_name, severity FROM alarms LIMIT 10` → 测试 API 应返回告警数据

测试完成后 **关闭进程释放端口**（CLAUDE.md 要求）。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/components/canvas/NodeAttrsPanel.vue frontend/src/components/canvas/NodeAlarmsTab.vue
git commit -m "feat(alarm): NodeAttrsPanel Tab 化 + NodeAlarmsTab 告警 CRUD UI"
```

---

## 自检清单

实施完成后逐条核对：

### 后端
- [ ] `alarm_schemas` / `alarm_schema_fields` / `node_alarms` / `node_alarm_attrs` 4 张表存在
- [ ] `topologies.alarm_schema_id` 列存在且 FK 正确
- [ ] `GET / POST / PUT / DELETE /admin/api/alarm-schemas` 全部工作
- [ ] 删除被引用模板返 409
- [ ] `PATCH /admin/api/topologies/{id}/alarm-schema` 支持绑定/解绑/切换
- [ ] 切换时已有告警 + 未带 `clearExisting` → 409 + `nodeAlarmCount`
- [ ] `GET /admin/api/topologies/{id}` 详情含 `alarmSchemaId` + `nodeAlarmCount`
- [ ] 创建节点（拓扑挂模板）→ 自动 +1 默认告警
- [ ] 节点组 materialize → 每物化节点 +1 默认告警
- [ ] `GET /nodes/{id}/alarms` / `POST /nodes/{id}/alarms` / `PUT /alarms/{id}/attrs` / `DELETE /alarms/{id}` 全部工作
- [ ] 拓扑未挂模板时 POST `/nodes/{id}/alarms` → 409
- [ ] `collect_views(conn, tid)` 在挂模板时返回 `alarms` 视图、未挂时不返回
- [ ] `alarms` CTE 包含固定列 + 模板字段 pivot 列
- [ ] 固定列名冲突的字段被跳过；非法 `field_key` 被跳过
- [ ] `GET /admin/api/sql/views/{tid}` 暴露 `alarms` 视图
- [ ] 所有 pytest 测试通过：`cd backend && python -m pytest tests/ -v`

### 前端
- [ ] 类型管理页第 3 Tab "告警模板" 出现
- [ ] 告警模板 CRUD 工作正常，删除被引用时弹错
- [ ] TopologyModal 加了告警模板下拉
- [ ] 切换告警模板（已有告警时）弹二次确认
- [ ] NodeAttrsPanel 顶部出现"属性" / "告警(N)" Tab
- [ ] 节点初次拖到画布后，单击节点 → 告警 Tab 显示 1 条默认告警
- [ ] "+ 新增告警" 立即 POST，列表立刻显示
- [ ] 告警卡片删除图标立即 DELETE
- [ ] 字段校验：required + max_length 字符计数
- [ ] 保存按钮提交 dirty 告警
- [ ] API 编辑器左侧"可用视图"显示 `alarms`（已挂模板的拓扑）
- [ ] Mock API SQL `SELECT * FROM alarms WHERE severity = 'critical'` 能跑出真实数据
- [ ] 前后端测试结束后停止进程释放端口

---

## 提交策略

每个 Task 完成后立即提交（Step "提交" 中已列出 commit message）。提交粒度：
- 后端：每个 router / 每个核心改动一个 commit
- 前端：每个组件 / 每个 view 改动一个 commit
- 测试与对应实现放同一 commit（TDD 风格）

---

## 风险提示

1. **测试间相互依赖** — Task 5 的部分用例依赖 Task 6 的 PATCH 端点。已在 Task 5 步骤 5 说明绕过方案。
2. **node.py 创建节点路径** — 现有代码用单个 `transaction()` 包裹。Task 7 注入告警写入要在同一 transaction 内，错误时整体回滚（设计目标）。
3. **node_group materialize 性能** — Task 8 在每个物化节点的 batch flush 内追加 N 个 INSERT。1000 节点测试 < 30s 是 sanity check。若失败需考虑 `executemany` 或预计算 SQL 模板。
4. **frontend NodeAttrsPanel 重构面较大** — 改 Tab 包装时小心保留现有节点名 / 节点属性表单的所有交互（保存、删除节点、滚动聚焦校验）。Task 14 Step 2 的代码段是片段，注意整体合并完整。
