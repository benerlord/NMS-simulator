# 节点组告警 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让节点组能配置告警模板（新 CRUD + Modal 第 4 步），CTE 展开时按虚拟节点数 × 模板条数生成告警行，materialize 时把模板 copy 到每个物理节点。同时打通"编辑现有节点组"入口。

**Architecture:** 新建两张镜像表 `node_group_alarms` / `node_group_alarm_attrs`（跟 `node_alarms` / `node_alarm_attrs` 对称）；新 router `node_group_alarm.py` 复用 `_alarm_utils.build_alarm_attrs`；CTE 层扩展 `_build_alarms_cte` 走 UNION ALL；前端 `NodeAlarmsTab.vue` 加 `context: 'node' | 'group'` prop 复用；`GroupCreateModal.vue` 加第 4 步 + 编辑模式。

**Tech Stack:** Python 3.9 / FastAPI / SQLite / Vue 3.5 / Ant Design Vue 4

**Spec:** `docs/superpowers/specs/2026-07-04-node-group-alarms-design.md`

---

## 文件清单

**新增：**
- `backend/app/admin/node_group_alarm.py` — 新 router，CRUD 4 端点
- `backend/tests/test_node_group_alarm_router.py` — CRUD 单测
- `backend/tests/test_migrations_node_group_alarms.py` — 迁移单测

**修改：**
- `backend/app/db/migrations.py` — SCHEMA_SQL 加两张表
- `backend/app/admin/schemas/alarm.py` — 加 3 个 pydantic 模型
- `backend/app/admin/schemas/__init__.py` — 导出新模型
- `backend/app/main.py` — `include_router`
- `backend/app/core/cte_builder.py::_build_alarms_cte` — UNION ALL 虚拟告警
- `backend/tests/test_cte_alarms.py` — 追加 5 组 CTE 测试
- `backend/app/admin/node_group.py::materialize_node_group` — 用组模板替代"1 条默认告警"
- `backend/tests/test_materialize_alarms.py` — 追加 3 组 materialize 测试
- `frontend/src/api/nodeGroup.ts` — 加 alarm CRUD
- `frontend/src/components/canvas/NodeAlarmsTab.vue` — 加 `context` prop
- `frontend/src/components/canvas/GroupCreateModal.vue` — 4th step + 编辑模式
- `frontend/src/views/CanvasView.vue` — 接入 `editingGroupId`

**不改：**
- `backend/app/admin/node_alarm.py`
- `backend/app/admin/_alarm_utils.py`
- `backend/app/admin/schemas/__init__.py` 里的 `NodeAlarm*` 定义
- 前端 `NodeAlarmsPanel`（单节点用）

---

## 行为变更（重要）

**Materialize 目前"每节点自动插 1 条默认告警"（`node_group.py:452-463`）**——本次改成"每节点按组的告警模板列表插 M 条"。即：

- 组配 3 条模板 → materialize 后每节点有 3 条告警
- 组配 0 条模板 → materialize 后每节点 **0 条告警**（跟今天的"自动 1 条"不同！）
- 想保留"1 条默认告警"的用户需要显式在组里加 1 条模板

这是有意的语义收敛：组说了算，无隐式魔法。

---

## Task 1: DB 迁移 — 新增 node_group_alarms + node_group_alarm_attrs

**Files:**
- Modify: `backend/app/db/migrations.py`
- Create: `backend/tests/test_migrations_node_group_alarms.py`

- [ ] **Step 1: 写失败测试**

Create `backend/tests/test_migrations_node_group_alarms.py`:

```python
import sqlite3

from app.db.migrations import run_migrations


def _fresh_conn(tmp_path):
    c = sqlite3.connect(str(tmp_path / "t.db"), isolation_level=None)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    return c


def _table_columns(conn, table):
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def test_migration_creates_node_group_alarms_table(tmp_path):
    conn = _fresh_conn(tmp_path)
    run_migrations(conn)
    cols = _table_columns(conn, "node_group_alarms")
    assert cols == {"id", "node_group_id", "alarm_index", "created_at", "updated_at"}
    conn.close()


def test_migration_creates_node_group_alarm_attrs_table(tmp_path):
    conn = _fresh_conn(tmp_path)
    run_migrations(conn)
    cols = _table_columns(conn, "node_group_alarm_attrs")
    assert cols == {"alarm_id", "field_key", "value"}
    conn.close()


def test_migration_cascade_delete_group_removes_alarms(tmp_path):
    """删除 node_group 应级联删除其 alarms + alarm_attrs。"""
    conn = _fresh_conn(tmp_path)
    run_migrations(conn)
    # 造种子数据
    conn.execute("INSERT INTO topologies (id, name) VALUES ('topo_t', 'T')")
    conn.execute("INSERT INTO node_types (id, code, name, category) VALUES ('nt_t', 'dev', 'D', 'switch')")
    conn.execute(
        "INSERT INTO node_groups (id, topology_id, node_type_id, group_name, node_count) "
        "VALUES ('grp_t', 'topo_t', 'nt_t', 'G', 3)"
    )
    conn.execute(
        "INSERT INTO node_group_alarms (id, node_group_id, alarm_index) VALUES ('ga_1', 'grp_t', 1)"
    )
    conn.execute(
        "INSERT INTO node_group_alarm_attrs (alarm_id, field_key, value) VALUES ('ga_1', 'severity', 'critical')"
    )

    conn.execute("DELETE FROM node_groups WHERE id = 'grp_t'")

    alarms = conn.execute("SELECT COUNT(*) c FROM node_group_alarms").fetchone()
    attrs = conn.execute("SELECT COUNT(*) c FROM node_group_alarm_attrs").fetchone()
    assert alarms["c"] == 0
    assert attrs["c"] == 0
    conn.close()


def test_migration_cascade_delete_alarm_removes_attrs(tmp_path):
    """删除 node_group_alarms 行应级联删除其 attrs。"""
    conn = _fresh_conn(tmp_path)
    run_migrations(conn)
    conn.execute("INSERT INTO topologies (id, name) VALUES ('topo_t', 'T')")
    conn.execute("INSERT INTO node_types (id, code, name, category) VALUES ('nt_t', 'dev', 'D', 'switch')")
    conn.execute(
        "INSERT INTO node_groups (id, topology_id, node_type_id, group_name, node_count) "
        "VALUES ('grp_t', 'topo_t', 'nt_t', 'G', 3)"
    )
    conn.execute("INSERT INTO node_group_alarms (id, node_group_id, alarm_index) VALUES ('ga_1', 'grp_t', 1)")
    conn.execute(
        "INSERT INTO node_group_alarm_attrs (alarm_id, field_key, value) VALUES ('ga_1', 'severity', 'critical')"
    )

    conn.execute("DELETE FROM node_group_alarms WHERE id = 'ga_1'")

    attrs = conn.execute("SELECT COUNT(*) c FROM node_group_alarm_attrs").fetchone()
    assert attrs["c"] == 0
    conn.close()


def test_migration_is_idempotent(tmp_path):
    conn = _fresh_conn(tmp_path)
    run_migrations(conn)
    run_migrations(conn)  # 二次跑不应报错
    assert _table_columns(conn, "node_group_alarms") == {
        "id", "node_group_id", "alarm_index", "created_at", "updated_at"
    }
    conn.close()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_migrations_node_group_alarms.py -v`
Expected: 5 tests FAIL — 表不存在

- [ ] **Step 3: 加 SCHEMA_SQL**

Edit `backend/app/db/migrations.py`. 找到 `CREATE TABLE IF NOT EXISTS node_alarm_attrs`（约 277 行附近）后面，追加两条 CREATE 语句（在 SCHEMA_SQL 字符串里）：

```sql
CREATE TABLE IF NOT EXISTS node_group_alarms (
  id              TEXT PRIMARY KEY,
  node_group_id   TEXT NOT NULL,
  alarm_index     INTEGER NOT NULL,
  created_at      TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (node_group_id) REFERENCES node_groups(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_group_alarms_grp ON node_group_alarms(node_group_id);

CREATE TABLE IF NOT EXISTS node_group_alarm_attrs (
  alarm_id        TEXT NOT NULL,
  field_key       TEXT NOT NULL,
  value           TEXT,
  PRIMARY KEY (alarm_id, field_key),
  FOREIGN KEY (alarm_id) REFERENCES node_group_alarms(id) ON DELETE CASCADE
);
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_migrations_node_group_alarms.py -v`
Expected: 5 tests PASS

- [ ] **Step 5: 跑全套确认无回归**

Run: `cd backend && python -m pytest -q 2>&1 | tail -5`
Expected: 全部 PASS

- [ ] **Step 6: 提交**

```bash
git add backend/app/db/migrations.py backend/tests/test_migrations_node_group_alarms.py
git commit -m "$(cat <<'EOF'
feat(db): 新建 node_group_alarms + node_group_alarm_attrs 表

- 镜像 node_alarms / node_alarm_attrs，外键改指 node_groups(id) ON DELETE CASCADE
- +5 单测覆盖建表 / 级联删（组→告警、告警→attrs） / 幂等

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Pydantic schemas

**Files:**
- Modify: `backend/app/admin/schemas/alarm.py`
- Modify: `backend/app/admin/schemas/__init__.py`

- [ ] **Step 1: 加 pydantic 模型**

Edit `backend/app/admin/schemas/alarm.py`. 在文件末尾追加：

```python
# --- node group alarms ---

class NodeGroupAlarmAttrSet(CamelModel):
    attrs: dict[str, Optional[str]]


class NodeGroupAlarmCreate(CamelModel):
    attrs: Optional[dict[str, Optional[str]]] = None  # 未传 = 用 default_value 填


class NodeGroupAlarmItem(CamelModel):
    id: str
    node_group_id: str
    alarm_index: int
    attrs: dict[str, Optional[str]] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
```

- [ ] **Step 2: 导出**

Edit `backend/app/admin/schemas/__init__.py`. 找到现有 `NodeAlarm*` 的 import 段（约 116 行）追加：

```python
    NodeGroupAlarmAttrSet,
    NodeGroupAlarmCreate,
    NodeGroupAlarmItem,
```

同时在 `__all__` 列表里加：

```python
    "NodeGroupAlarmAttrSet",
    "NodeGroupAlarmCreate",
    "NodeGroupAlarmItem",
```

- [ ] **Step 3: 验证 import 无报错**

Run: `cd backend && python -c "from app.admin.schemas import NodeGroupAlarmAttrSet, NodeGroupAlarmCreate, NodeGroupAlarmItem; print('ok')"`
Expected: `ok`

- [ ] **Step 4: 跑全套确认无回归**

Run: `cd backend && python -m pytest -q 2>&1 | tail -3`
Expected: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/admin/schemas/alarm.py backend/app/admin/schemas/__init__.py
git commit -m "$(cat <<'EOF'
feat(schemas): NodeGroupAlarm{Create,Item,AttrSet} 三兄弟

- 完全镜像 NodeAlarm 系列，只是把 node_id 换成 node_group_id
- 导出到 admin.schemas 顶层

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: node_group_alarm.py router + CRUD 单测

**Files:**
- Create: `backend/app/admin/node_group_alarm.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_node_group_alarm_router.py`

- [ ] **Step 1: 写失败测试**

Create `backend/tests/test_node_group_alarm_router.py`:

```python
"""节点组告警 CRUD 端到端测试。"""


def _make_topo_group(client, with_schema=True):
    """造 topology + alarm_schema（可选） + node_type + node_group，返回 (tid, gid, sid|None)。"""
    r = client.post("/admin/api/topologies", json={"name": "T"})
    tid = r.json()["data"]["id"]

    sid = None
    if with_schema:
        r = client.post("/admin/api/alarm-schemas", json={
            "code": "sch1", "name": "S1",
            "fields": [
                {"fieldKey": "severity", "fieldLabel": "级别", "fieldType": "text",
                 "maxLength": 20, "defaultValue": "minor"},
                {"fieldKey": "node_dn", "fieldLabel": "设备DN", "fieldType": "text",
                 "maxLength": 100, "mappingTarget": "dn"},
            ],
        })
        sid = r.json()["data"]["id"]
        # 手动绑到拓扑（跟 test_node_alarm_router 一致的路径）
        import sqlite3
        from app.core.config import settings as app_settings
        with sqlite3.connect(str(app_settings.db_path), isolation_level=None) as c:
            c.execute("UPDATE topologies SET alarm_schema_id = ? WHERE id = ?", (sid, tid))

    r = client.post("/admin/api/node-types", json={"code": "dev", "name": "Dev", "category": "switch"})
    ntid = r.json()["data"]["id"]
    r = client.post(f"/admin/api/topologies/{tid}/node-groups", json={
        "nodeTypeId": ntid, "groupName": "G", "nodeCount": 3,
    })
    gid = r.json()["data"]["id"]
    return tid, gid, sid


def test_list_alarms_empty(client):
    _, gid, _ = _make_topo_group(client)
    r = client.get(f"/admin/api/node-groups/{gid}/alarms")
    assert r.status_code == 200
    assert r.json()["data"] == []


def test_create_alarm_success_first_index_is_1(client):
    _, gid, _ = _make_topo_group(client)
    r = client.post(f"/admin/api/node-groups/{gid}/alarms", json={
        "attrs": {"severity": "critical"},
    })
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["id"].startswith("grp_alm_")
    assert d["alarmIndex"] == 1
    assert d["attrs"]["severity"] == "critical"
    # mapping_target 字段（node_dn）不该出现在模板 attrs 里
    assert "node_dn" not in d["attrs"]


def test_create_alarm_fills_default_value(client):
    _, gid, _ = _make_topo_group(client)
    r = client.post(f"/admin/api/node-groups/{gid}/alarms", json={})
    d = r.json()["data"]
    assert d["attrs"]["severity"] == "minor"  # default_value


def test_second_alarm_gets_index_2(client):
    _, gid, _ = _make_topo_group(client)
    client.post(f"/admin/api/node-groups/{gid}/alarms", json={})
    r = client.post(f"/admin/api/node-groups/{gid}/alarms", json={})
    assert r.json()["data"]["alarmIndex"] == 2


def test_update_alarm_attrs(client):
    _, gid, _ = _make_topo_group(client)
    aid = client.post(f"/admin/api/node-groups/{gid}/alarms", json={}).json()["data"]["id"]
    r = client.put(f"/admin/api/node-group-alarms/{aid}/attrs", json={
        "attrs": {"severity": "major"},
    })
    assert r.status_code == 200
    assert r.json()["data"]["attrs"]["severity"] == "major"


def test_delete_alarm(client):
    _, gid, _ = _make_topo_group(client)
    aid = client.post(f"/admin/api/node-groups/{gid}/alarms", json={}).json()["data"]["id"]
    r = client.delete(f"/admin/api/node-group-alarms/{aid}")
    assert r.status_code == 200
    r2 = client.get(f"/admin/api/node-groups/{gid}/alarms")
    assert r2.json()["data"] == []


def test_create_alarm_without_schema_rejected(client):
    """拓扑未绑 alarm_schema 时 POST 应 409 + 40901。"""
    _, gid, _ = _make_topo_group(client, with_schema=False)
    r = client.post(f"/admin/api/node-groups/{gid}/alarms", json={})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == 40901


def test_delete_group_cascades_alarms(client):
    """DELETE 节点组时，告警 + attrs 应一并清（DB 层级联）。"""
    _, gid, _ = _make_topo_group(client)
    client.post(f"/admin/api/node-groups/{gid}/alarms", json={})
    client.delete(f"/admin/api/node-groups/{gid}")
    # 无法直接查告警是否还在——但 GET 已经找不到 group 了；用 SQL 验
    import sqlite3
    from app.core.config import settings as app_settings
    with sqlite3.connect(str(app_settings.db_path), isolation_level=None) as c:
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys = ON")
        rows = c.execute(
            "SELECT COUNT(*) c FROM node_group_alarms WHERE node_group_id = ?", (gid,)
        ).fetchone()
        assert rows["c"] == 0
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_node_group_alarm_router.py -v`
Expected: 8 tests FAIL — 端点不存在（404）

- [ ] **Step 3: 建 router 文件**

Create `backend/app/admin/node_group_alarm.py`:

```python
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException

from app.db.connection import connect, transaction
from app.admin._alarm_utils import build_alarm_attrs
from app.admin.schemas import (
    NodeGroupAlarmAttrSet,
    NodeGroupAlarmCreate,
    NodeGroupAlarmItem,
)

router = APIRouter(prefix="/admin/api", tags=["节点组告警"])


def _new_alarm_id() -> str:
    return f"grp_alm_{uuid.uuid4().hex[:12]}"


def _get_alarm_schema_for_group(conn, group_id: str):
    """Return (alarm_schema_id, [field rows]); (None, []) if topology has no schema."""
    row = conn.execute(
        "SELECT t.alarm_schema_id AS sid FROM node_groups g "
        "JOIN topologies t ON t.id = g.topology_id "
        "WHERE g.id = ?",
        (group_id,),
    ).fetchone()
    if not row or not row["sid"]:
        return None, []
    fields = conn.execute(
        "SELECT field_key, field_type, max_length, default_value, required, mapping_target "
        "FROM alarm_schema_fields WHERE alarm_schema_id = ? ORDER BY sort_order, id",
        (row["sid"],),
    ).fetchall()
    return row["sid"], fields


def _load_attrs(conn, alarm_id: str) -> dict[str, Any]:
    rows = conn.execute(
        "SELECT field_key, value FROM node_group_alarm_attrs WHERE alarm_id = ?",
        (alarm_id,),
    ).fetchall()
    return {r["field_key"]: r["value"] for r in rows}


def _row_to_item(conn, row) -> NodeGroupAlarmItem:
    return NodeGroupAlarmItem(
        id=row["id"],
        node_group_id=row["node_group_id"],
        alarm_index=row["alarm_index"],
        attrs=_load_attrs(conn, row["id"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _next_alarm_index(conn, group_id: str) -> int:
    row = conn.execute(
        "SELECT COALESCE(MAX(alarm_index), 0) + 1 AS n "
        "FROM node_group_alarms WHERE node_group_id = ?",
        (group_id,),
    ).fetchone()
    return int(row["n"])


def _validate_attr_lengths(fields, attrs: dict) -> None:
    field_map = {f["field_key"]: f for f in fields}
    for k, v in attrs.items():
        f = field_map.get(k)
        if not f:
            continue
        if f["field_type"] == "text" and f["max_length"] and v and len(str(v)) > f["max_length"]:
            raise HTTPException(
                status_code=400,
                detail={"code": 40001, "message": f"字段 {k} 超过最大长度 {f['max_length']}"},
            )


def _strip_mapping_target_fields(fields, attrs: dict) -> dict:
    """mapping_target 字段的值在 CTE 展开时从虚拟节点取，不该存到模板 attrs 里。"""
    mapped = {f["field_key"] for f in fields if f["mapping_target"]}
    return {k: v for k, v in attrs.items() if k not in mapped}


@router.get("/node-groups/{group_id}/alarms")
def list_group_alarms(group_id: str) -> dict:
    with connect() as conn:
        grp = conn.execute("SELECT id FROM node_groups WHERE id = ?", (group_id,)).fetchone()
        if not grp:
            raise HTTPException(status_code=404, detail={"code": 40404, "message": "节点组不存在"})
        rows = conn.execute(
            "SELECT * FROM node_group_alarms WHERE node_group_id = ? ORDER BY alarm_index",
            (group_id,),
        ).fetchall()
        items = [_row_to_item(conn, r).model_dump(mode="json", by_alias=True) for r in rows]
    return {"code": 0, "data": items, "message": "ok"}


@router.post("/node-groups/{group_id}/alarms")
def create_group_alarm(group_id: str, data: NodeGroupAlarmCreate) -> dict:
    with transaction() as conn:
        grp = conn.execute("SELECT id FROM node_groups WHERE id = ?", (group_id,)).fetchone()
        if not grp:
            raise HTTPException(status_code=404, detail={"code": 40404, "message": "节点组不存在"})

        sid, fields = _get_alarm_schema_for_group(conn, group_id)
        if not sid:
            raise HTTPException(
                status_code=409,
                detail={"code": 40901, "message": "本拓扑未配置告警模板"},
            )

        # build_alarm_attrs 会自动 apply default_value；这里 node_id=None
        # 让 mapping_target 跳过（组模板不需要 map，运行时再取）
        user = data.attrs or {}
        # 用 default 补齐，但不 apply mapping（node_id=None）
        merged = {}
        for f in fields:
            key = f["field_key"]
            if key in user and user[key] is not None:
                merged[key] = user[key]
            elif f["default_value"] is not None:
                merged[key] = f["default_value"]
            # mapping_target / 没值 → 跳过（不入模板）
        merged = _strip_mapping_target_fields(fields, merged)
        _validate_attr_lengths(fields, merged)

        aid = _new_alarm_id()
        idx = _next_alarm_index(conn, group_id)
        conn.execute(
            "INSERT INTO node_group_alarms (id, node_group_id, alarm_index) VALUES (?, ?, ?)",
            (aid, group_id, idx),
        )
        for k, v in merged.items():
            conn.execute(
                "INSERT INTO node_group_alarm_attrs (alarm_id, field_key, value) VALUES (?, ?, ?)",
                (aid, k, v),
            )

        row = conn.execute("SELECT * FROM node_group_alarms WHERE id = ?", (aid,)).fetchone()
        item = _row_to_item(conn, row)
    return {"code": 0, "data": item.model_dump(mode="json", by_alias=True), "message": "ok"}


@router.put("/node-group-alarms/{alarm_id}/attrs")
def update_group_alarm_attrs(alarm_id: str, data: NodeGroupAlarmAttrSet) -> dict:
    with transaction() as conn:
        row = conn.execute("SELECT * FROM node_group_alarms WHERE id = ?", (alarm_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail={"code": 40404, "message": "告警不存在"})

        _, fields = _get_alarm_schema_for_group(conn, row["node_group_id"])
        attrs = _strip_mapping_target_fields(fields, data.attrs)
        _validate_attr_lengths(fields, attrs)

        for k, v in attrs.items():
            if v is None:
                conn.execute(
                    "DELETE FROM node_group_alarm_attrs WHERE alarm_id = ? AND field_key = ?",
                    (alarm_id, k),
                )
            else:
                conn.execute(
                    "INSERT INTO node_group_alarm_attrs (alarm_id, field_key, value) VALUES (?, ?, ?) "
                    "ON CONFLICT(alarm_id, field_key) DO UPDATE SET value = excluded.value",
                    (alarm_id, k, v),
                )
        conn.execute(
            "UPDATE node_group_alarms SET updated_at = datetime('now') WHERE id = ?",
            (alarm_id,),
        )

        row = conn.execute("SELECT * FROM node_group_alarms WHERE id = ?", (alarm_id,)).fetchone()
        item = _row_to_item(conn, row)
    return {"code": 0, "data": item.model_dump(mode="json", by_alias=True), "message": "ok"}


@router.delete("/node-group-alarms/{alarm_id}")
def delete_group_alarm(alarm_id: str) -> dict:
    with transaction() as conn:
        row = conn.execute("SELECT id FROM node_group_alarms WHERE id = ?", (alarm_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail={"code": 40404, "message": "告警不存在"})
        conn.execute("DELETE FROM node_group_alarms WHERE id = ?", (alarm_id,))
    return {"code": 0, "data": None, "message": "ok"}
```

- [ ] **Step 4: 注册 router 到 main.py**

Edit `backend/app/main.py`. 在现有的 `from app.admin.node_alarm import router as node_alarm_router` 后面加：

```python
from app.admin.node_group_alarm import router as node_group_alarm_router
```

在 `include_router` 调用块里加：

```python
app.include_router(node_group_alarm_router)
```

- [ ] **Step 5: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_node_group_alarm_router.py -v`
Expected: 8 tests PASS

- [ ] **Step 6: 跑全套确认无回归**

Run: `cd backend && python -m pytest -q 2>&1 | tail -3`
Expected: 全部 PASS

- [ ] **Step 7: 提交**

```bash
git add backend/app/admin/node_group_alarm.py backend/app/main.py backend/tests/test_node_group_alarm_router.py
git commit -m "$(cat <<'EOF'
feat(node-groups): 告警模板 CRUD 端点

- 新 router node_group_alarm.py：GET/POST/PUT/DELETE 4 端点
- 镜像 node_alarm 行为：alarm_schema 未绑 → 409+40901
- 未传 attrs 自动用 default_value 填；mapping_target 字段静默丢弃（模板不存）
- alarm_index 自增；删除中间不重排
- +8 单测覆盖列表/创建/默认填充/index 递增/更新/删除/无 schema 拦截/级联删

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: CTE 扩展 — alarms 视图 UNION 虚拟组告警

**Files:**
- Modify: `backend/app/core/cte_builder.py`
- Modify: `backend/tests/test_cte_alarms.py`

- [ ] **Step 1: 写失败测试**

Append to `backend/tests/test_cte_alarms.py`:

```python
def test_alarms_cte_includes_group_virtual_alarms(client):
    """一个组 2 虚拟节点 + 3 条告警模板 → alarms 视图返回 6 行。"""
    # topology + schema
    r = client.post("/admin/api/topologies", json={"name": "T"})
    tid = r.json()["data"]["id"]
    r = client.post("/admin/api/alarm-schemas", json={
        "code": "gsch", "name": "GS",
        "fields": [
            {"fieldKey": "severity", "fieldLabel": "级别", "fieldType": "text",
             "maxLength": 20, "defaultValue": "minor"},
        ],
    })
    sid = r.json()["data"]["id"]

    import sqlite3
    from app.core.config import settings as app_settings
    with sqlite3.connect(str(app_settings.db_path), isolation_level=None) as c:
        c.execute("UPDATE topologies SET alarm_schema_id = ? WHERE id = ?", (sid, tid))

    r = client.post("/admin/api/node-types", json={"code": "sw", "name": "Switch", "category": "switch"})
    ntid = r.json()["data"]["id"]
    r = client.post(f"/admin/api/topologies/{tid}/node-groups", json={
        "nodeTypeId": ntid, "groupName": "G", "nodeCount": 2,
    })
    gid = r.json()["data"]["id"]

    # 加 3 条模板
    for sev in ["critical", "major", "minor"]:
        client.post(f"/admin/api/node-groups/{gid}/alarms", json={"attrs": {"severity": sev}})

    # 用 SQL runner 查 alarms 视图
    r = client.post("/admin/api/sql/preview", json={
        "topologyId": tid,
        "sqlText": "SELECT COUNT(*) AS c FROM alarms",
    })
    assert r.status_code == 200, r.text
    rows = r.json()["data"]["rows"]
    assert rows[0]["c"] == 6  # 2 虚拟节点 × 3 模板


def test_alarms_cte_group_ids_unique_across_union(client):
    """物理告警和虚拟告警的 id 应各自唯一，UNION 里不冲突。"""
    r = client.post("/admin/api/topologies", json={"name": "T"})
    tid = r.json()["data"]["id"]
    r = client.post("/admin/api/alarm-schemas", json={
        "code": "usch", "name": "US",
        "fields": [{"fieldKey": "severity", "fieldLabel": "级别", "fieldType": "text",
                    "maxLength": 20, "defaultValue": "minor"}],
    })
    sid = r.json()["data"]["id"]
    import sqlite3
    from app.core.config import settings as app_settings
    with sqlite3.connect(str(app_settings.db_path), isolation_level=None) as c:
        c.execute("UPDATE topologies SET alarm_schema_id = ? WHERE id = ?", (sid, tid))

    r = client.post("/admin/api/node-types", json={"code": "sw", "name": "SW", "category": "switch"})
    ntid = r.json()["data"]["id"]
    # 1 物理节点 + 1 告警
    r = client.post(f"/admin/api/topologies/{tid}/nodes", json={"nodeTypeId": ntid, "name": "n1"})
    nid = r.json()["data"]["id"]
    client.post(f"/admin/api/nodes/{nid}/alarms", json={})
    # 1 组 2 虚拟节点 + 1 告警模板
    r = client.post(f"/admin/api/topologies/{tid}/node-groups", json={
        "nodeTypeId": ntid, "groupName": "G", "nodeCount": 2,
    })
    gid = r.json()["data"]["id"]
    client.post(f"/admin/api/node-groups/{gid}/alarms", json={})

    r = client.post("/admin/api/sql/preview", json={
        "topologyId": tid,
        "sqlText": "SELECT COUNT(*) c, COUNT(DISTINCT id) d FROM alarms",
    })
    rows = r.json()["data"]["rows"]
    assert rows[0]["c"] == 3  # 1 物理 + 2 虚拟
    assert rows[0]["d"] == 3  # id 全部唯一


def test_alarms_cte_mapping_target_takes_from_virtual_node(client):
    """告警字段配 mapping_target='name' → 每行 name 来自各自虚拟节点。"""
    r = client.post("/admin/api/topologies", json={"name": "T"})
    tid = r.json()["data"]["id"]
    r = client.post("/admin/api/alarm-schemas", json={
        "code": "msch", "name": "MS",
        "fields": [
            {"fieldKey": "device_name", "fieldLabel": "设备名", "fieldType": "text",
             "maxLength": 100, "mappingTarget": "name"},
        ],
    })
    sid = r.json()["data"]["id"]
    import sqlite3
    from app.core.config import settings as app_settings
    with sqlite3.connect(str(app_settings.db_path), isolation_level=None) as c:
        c.execute("UPDATE topologies SET alarm_schema_id = ? WHERE id = ?", (sid, tid))

    r = client.post("/admin/api/node-types", json={"code": "sw", "name": "SW", "category": "switch"})
    ntid = r.json()["data"]["id"]
    r = client.post(f"/admin/api/topologies/{tid}/node-groups", json={
        "nodeTypeId": ntid, "groupName": "Sw", "nodeCount": 2,
        "nameTemplate": "{group}-{i:02d}",
    })
    gid = r.json()["data"]["id"]
    client.post(f"/admin/api/node-groups/{gid}/alarms", json={})

    r = client.post("/admin/api/sql/preview", json={
        "topologyId": tid,
        "sqlText": "SELECT device_name FROM alarms ORDER BY device_name",
    })
    rows = r.json()["data"]["rows"]
    names = sorted(r["device_name"] for r in rows)
    assert names == ["Sw-01", "Sw-02"]  # 各自虚拟节点的 name


def test_alarms_cte_no_schema_still_no_cte(client):
    """拓扑无 alarm_schema → alarms CTE 不存在（跟现有一致）。"""
    r = client.post("/admin/api/topologies", json={"name": "T"})
    tid = r.json()["data"]["id"]
    r = client.post("/admin/api/sql/preview", json={
        "topologyId": tid,
        "sqlText": "SELECT * FROM alarms LIMIT 1",
    })
    # 应报 SQL 错（表不存在）
    assert r.status_code != 200 or "no such table" in r.text.lower() or r.json().get("code", 0) != 0


def test_alarms_cte_group_alarm_index_preserved(client):
    """组模板的 alarm_index 应体现在虚拟告警行的 alarm_index 列。"""
    r = client.post("/admin/api/topologies", json={"name": "T"})
    tid = r.json()["data"]["id"]
    r = client.post("/admin/api/alarm-schemas", json={
        "code": "isch", "name": "IS",
        "fields": [{"fieldKey": "severity", "fieldLabel": "级别", "fieldType": "text",
                    "maxLength": 20, "defaultValue": "minor"}],
    })
    sid = r.json()["data"]["id"]
    import sqlite3
    from app.core.config import settings as app_settings
    with sqlite3.connect(str(app_settings.db_path), isolation_level=None) as c:
        c.execute("UPDATE topologies SET alarm_schema_id = ? WHERE id = ?", (sid, tid))

    r = client.post("/admin/api/node-types", json={"code": "sw", "name": "SW", "category": "switch"})
    ntid = r.json()["data"]["id"]
    r = client.post(f"/admin/api/topologies/{tid}/node-groups", json={
        "nodeTypeId": ntid, "groupName": "G", "nodeCount": 1,
    })
    gid = r.json()["data"]["id"]
    client.post(f"/admin/api/node-groups/{gid}/alarms", json={"attrs": {"severity": "critical"}})
    client.post(f"/admin/api/node-groups/{gid}/alarms", json={"attrs": {"severity": "major"}})

    r = client.post("/admin/api/sql/preview", json={
        "topologyId": tid,
        "sqlText": "SELECT alarm_index, severity FROM alarms ORDER BY alarm_index",
    })
    rows = r.json()["data"]["rows"]
    assert [(r["alarm_index"], r["severity"]) for r in rows] == [(1, "critical"), (2, "major")]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_cte_alarms.py -v -k "group\|union\|mapping\|no_schema\|index_preserved"`
Expected: 5 tests FAIL — alarms CTE 只覆盖物理告警

- [ ] **Step 3: 改 `_build_alarms_cte`**

Edit `backend/app/core/cte_builder.py`. 找到 `_build_alarms_cte` 函数（约 482 行），把整个函数体替换为下面这份新版（多返回一个 UNION 子句）：

```python
def _build_alarms_cte(conn: sqlite3.Connection, topology_id: str) -> Optional[dict[str, Any]]:
    """Alarms CTE — UNION 物理节点告警 + 节点组虚拟告警。

    对使用方透明：同一张 alarms 表既能查到物理告警也能查到虚拟告警，字段列一致。
    """
    row = conn.execute(
        "SELECT alarm_schema_id FROM topologies WHERE id = ?", (topology_id,)
    ).fetchone()
    if not row or not row["alarm_schema_id"]:
        return None
    sid = row["alarm_schema_id"]

    field_rows = conn.execute(
        "SELECT field_key, mapping_target FROM alarm_schema_fields WHERE alarm_schema_id = ? "
        "ORDER BY sort_order, id",
        (sid,),
    ).fetchall()

    columns = list(ALARM_FIXED_COLUMNS)

    # --- 物理节点告警 SELECT ---
    phys_fixed = [
        "a.id",
        "a.node_id",
        "n.name AS node_name",
        "n.dn AS node_dn",
        "a.alarm_index",
        "a.created_at",
        "a.updated_at",
    ]
    phys_pivots: list[str] = []
    # --- 虚拟组告警 SELECT ---
    virt_fixed = [
        "('gna_' || gn.id || '_' || ga.alarm_index) AS id",
        "gn.id AS node_id",
        "gn.name AS node_name",
        "gn.dn AS node_dn",
        "ga.alarm_index",
        "ga.created_at",
        "ga.updated_at",
    ]
    virt_pivots: list[str] = []

    for r in field_rows:
        key = r["field_key"]
        if not is_valid_ident(key):
            continue
        if key in columns:
            continue
        columns.append(key)

        if r["mapping_target"]:
            # mapping_target 字段：物理侧走 attr 表，虚拟侧从虚拟节点 attr 取
            mt = r["mapping_target"]
            if is_valid_ident(mt):
                # 物理告警：从 node_alarm_attrs pivot（用户配了值就用值，没配就 NULL）
                phys_pivots.append(f"MAX(CASE WHEN aa.field_key = '{key}' THEN aa.value END) AS {key}")
                # 虚拟告警：直接从虚拟节点的 mapping_target 列/属性取
                # 系统字段（name/dn/id/status）用 gn.<col>，自定义属性用 gna_map.value（需 join）
                # 简化实现：只支持系统字段直接映射；自定义属性映射先不支持（跟现有 CTE 一致：只 pivot，不 map）
                if mt in {"name", "dn", "id", "status"}:
                    virt_pivots.append(f"gn.{mt} AS {key}")
                else:
                    virt_pivots.append(f"NULL AS {key}")  # 自定义属性映射在虚拟侧留空
            else:
                phys_pivots.append(f"MAX(CASE WHEN aa.field_key = '{key}' THEN aa.value END) AS {key}")
                virt_pivots.append(f"NULL AS {key}")
        else:
            # 无 mapping_target：两侧都从 pivot 取
            phys_pivots.append(f"MAX(CASE WHEN aa.field_key = '{key}' THEN aa.value END) AS {key}")
            virt_pivots.append(f"MAX(CASE WHEN gaa.field_key = '{key}' THEN gaa.value END) AS {key}")

    phys_select_body = ",\n         ".join(phys_fixed + phys_pivots)
    virt_select_body = ",\n         ".join(virt_fixed + virt_pivots)

    physical_sql = (
        f"SELECT {phys_select_body}\n"
        "  FROM main.node_alarms a\n"
        "  JOIN main.nodes n ON n.id = a.node_id\n"
        "  LEFT JOIN main.node_alarm_attrs aa ON aa.alarm_id = a.id\n"
        "  WHERE n.topology_id = :__tid__\n"
        "  GROUP BY a.id"
    )
    virtual_sql = (
        f"SELECT {virt_select_body}\n"
        "  FROM group_nodes gn\n"
        "  JOIN main.node_groups g ON g.id = gn.group_id\n"
        "  JOIN main.node_group_alarms ga ON ga.node_group_id = g.id\n"
        "  LEFT JOIN main.node_group_alarm_attrs gaa ON gaa.alarm_id = ga.id\n"
        "  WHERE g.topology_id = :__tid__\n"
        "  GROUP BY gn.id, ga.id"
    )
    sql = f"{physical_sql}\nUNION ALL\n{virtual_sql}"

    return {"name": "alarms", "columns": columns, "sql": sql}
```

**注意点：**
- `group_nodes` 已是 generic CTE（`_RESERVED_NAMES` 里有）—— 直接引用
- `virtual_sql` 里 `gn.group_id` 假设 `group_nodes` 视图有 `group_id` 列——校验 `build_generic_ctes` 里 `group_nodes` 的定义包含此列，若无需先加。跑测试会暴露

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_cte_alarms.py -v`
Expected: 全部 PASS（新 5 + 原有）

如果 `group_nodes` 视图缺 `group_id` 列，需要在 `build_generic_ctes` 里的 `group_nodes_sql` 加上 `node_groups.id AS group_id`，具体位置在 `cte_builder.py` 里搜 `"group_nodes"` + `"columns"`。

- [ ] **Step 5: 跑全套确认无回归**

Run: `cd backend && python -m pytest -q 2>&1 | tail -3`
Expected: 全部 PASS

- [ ] **Step 6: 提交**

```bash
git add backend/app/core/cte_builder.py backend/tests/test_cte_alarms.py
git commit -m "$(cat <<'EOF'
feat(cte): alarms 视图 UNION 虚拟组告警

- _build_alarms_cte 生成 physical + virtual 两段 SELECT，UNION ALL 组合
- 虚拟告警 id 合成：'gna_' || group_node_id || '_' || alarm_index，保证唯一
- mapping_target 系统字段（name/dn/id/status）在虚拟侧直接从虚拟节点取；
  自定义属性映射暂不支持（跟现有虚拟节点 attr 逻辑一致）
- +5 CTE 单测覆盖：虚拟告警行数 / id 唯一 / mapping_target / 无 schema / index 保留

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Materialize 用组告警模板替代"1 条默认"

**Files:**
- Modify: `backend/app/admin/node_group.py::materialize_node_group`
- Modify: `backend/tests/test_materialize_alarms.py`

- [ ] **Step 1: 写失败测试**

Append to `backend/tests/test_materialize_alarms.py`:

```python
def test_materialize_uses_group_alarm_templates(client):
    """组 3 虚拟节点 + 2 条告警模板 → materialize 后 3 nodes × 2 alarms = 6 条 node_alarms。"""
    r = client.post("/admin/api/topologies", json={"name": "T"})
    tid = r.json()["data"]["id"]
    r = client.post("/admin/api/alarm-schemas", json={
        "code": "msch", "name": "MS",
        "fields": [
            {"fieldKey": "severity", "fieldLabel": "级别", "fieldType": "text",
             "maxLength": 20, "defaultValue": "minor"},
        ],
    })
    sid = r.json()["data"]["id"]

    import sqlite3
    from app.core.config import settings as app_settings
    with sqlite3.connect(str(app_settings.db_path), isolation_level=None) as c:
        c.execute("UPDATE topologies SET alarm_schema_id = ? WHERE id = ?", (sid, tid))

    r = client.post("/admin/api/node-types", json={"code": "sw", "name": "SW", "category": "switch"})
    ntid = r.json()["data"]["id"]
    r = client.post(f"/admin/api/topologies/{tid}/node-groups", json={
        "nodeTypeId": ntid, "groupName": "G", "nodeCount": 3,
    })
    gid = r.json()["data"]["id"]

    client.post(f"/admin/api/node-groups/{gid}/alarms", json={"attrs": {"severity": "critical"}})
    client.post(f"/admin/api/node-groups/{gid}/alarms", json={"attrs": {"severity": "major"}})

    r = client.post(f"/admin/api/node-groups/{gid}/materialize")
    assert r.status_code == 200, r.text

    with sqlite3.connect(str(app_settings.db_path), isolation_level=None) as c:
        c.row_factory = sqlite3.Row
        alarms = c.execute(
            "SELECT COUNT(*) c FROM node_alarms a JOIN nodes n ON n.id = a.node_id "
            "WHERE n.group_id = ?", (gid,),
        ).fetchone()
    assert alarms["c"] == 6


def test_materialize_zero_templates_inserts_zero_alarms(client):
    """组 0 条模板 → materialize 后 每节点 0 告警（跟旧的"自动 1 条"不同）。"""
    r = client.post("/admin/api/topologies", json={"name": "T"})
    tid = r.json()["data"]["id"]
    r = client.post("/admin/api/alarm-schemas", json={
        "code": "zsch", "name": "ZS",
        "fields": [{"fieldKey": "severity", "fieldLabel": "级别", "fieldType": "text",
                    "maxLength": 20, "defaultValue": "minor"}],
    })
    sid = r.json()["data"]["id"]
    import sqlite3
    from app.core.config import settings as app_settings
    with sqlite3.connect(str(app_settings.db_path), isolation_level=None) as c:
        c.execute("UPDATE topologies SET alarm_schema_id = ? WHERE id = ?", (sid, tid))

    r = client.post("/admin/api/node-types", json={"code": "sw", "name": "SW", "category": "switch"})
    ntid = r.json()["data"]["id"]
    r = client.post(f"/admin/api/topologies/{tid}/node-groups", json={
        "nodeTypeId": ntid, "groupName": "G", "nodeCount": 3,
    })
    gid = r.json()["data"]["id"]

    r = client.post(f"/admin/api/node-groups/{gid}/materialize")
    assert r.status_code == 200

    with sqlite3.connect(str(app_settings.db_path), isolation_level=None) as c:
        c.row_factory = sqlite3.Row
        alarms = c.execute(
            "SELECT COUNT(*) c FROM node_alarms a JOIN nodes n ON n.id = a.node_id "
            "WHERE n.group_id = ?", (gid,),
        ).fetchone()
    assert alarms["c"] == 0


def test_materialize_alarm_mapping_target_uses_new_node_value(client):
    """告警字段 mapping_target='name' → materialize 后每节点告警的 attrs 里该字段 = 节点 name。"""
    r = client.post("/admin/api/topologies", json={"name": "T"})
    tid = r.json()["data"]["id"]
    r = client.post("/admin/api/alarm-schemas", json={
        "code": "mmsch", "name": "MMS",
        "fields": [
            {"fieldKey": "device_name", "fieldLabel": "设备名", "fieldType": "text",
             "maxLength": 100, "mappingTarget": "name"},
            {"fieldKey": "severity", "fieldLabel": "级别", "fieldType": "text",
             "maxLength": 20, "defaultValue": "minor"},
        ],
    })
    sid = r.json()["data"]["id"]
    import sqlite3
    from app.core.config import settings as app_settings
    with sqlite3.connect(str(app_settings.db_path), isolation_level=None) as c:
        c.execute("UPDATE topologies SET alarm_schema_id = ? WHERE id = ?", (sid, tid))

    r = client.post("/admin/api/node-types", json={"code": "sw", "name": "SW", "category": "switch"})
    ntid = r.json()["data"]["id"]
    r = client.post(f"/admin/api/topologies/{tid}/node-groups", json={
        "nodeTypeId": ntid, "groupName": "Sw", "nodeCount": 2,
        "nameTemplate": "{group}-{i:02d}",
    })
    gid = r.json()["data"]["id"]

    client.post(f"/admin/api/node-groups/{gid}/alarms", json={"attrs": {"severity": "major"}})

    r = client.post(f"/admin/api/node-groups/{gid}/materialize")
    assert r.status_code == 200

    with sqlite3.connect(str(app_settings.db_path), isolation_level=None) as c:
        c.row_factory = sqlite3.Row
        rows = c.execute(
            "SELECT n.name, aa.value FROM node_alarms a "
            "JOIN nodes n ON n.id = a.node_id "
            "JOIN node_alarm_attrs aa ON aa.alarm_id = a.id AND aa.field_key = 'device_name' "
            "WHERE n.group_id = ? ORDER BY n.name", (gid,),
        ).fetchall()
    pairs = [(r["name"], r["value"]) for r in rows]
    assert pairs == [("Sw-01", "Sw-01"), ("Sw-02", "Sw-02")]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_materialize_alarms.py -v -k "templates\|zero_templates\|new_node_value"`
Expected: 至少 2 个新测试 FAIL — 现有 materialize 每节点插 1 条默认告警

- [ ] **Step 3: 改 materialize 的告警插入逻辑**

Edit `backend/app/admin/node_group.py`. 找到 `materialize_node_group` 里 pre-query alarm schema 那段（约 413-428 行）：

```python
        # Pre-query alarm schema for the topology (used per-node in flush)
        alarm_schema_id: Optional[str] = None
        alarm_fields: list[dict] = []
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

替换为（同段增加读取组告警模板）：

```python
        # Pre-query alarm schema for the topology (used per-node in flush)
        alarm_schema_id: Optional[str] = None
        alarm_fields: list[dict] = []
        # 组告警模板：[(template_alarm_index, {field_key: value}), ...]
        group_alarm_templates: list[tuple[int, dict]] = []
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

                # 拉当前组的所有告警模板 + attrs
                _tpl_rows = _ac.execute(
                    "SELECT id, alarm_index FROM node_group_alarms "
                    "WHERE node_group_id = ? ORDER BY alarm_index",
                    (group_id,),
                ).fetchall()
                for _tr in _tpl_rows:
                    _attr_rows = _ac.execute(
                        "SELECT field_key, value FROM node_group_alarm_attrs WHERE alarm_id = ?",
                        (_tr["id"],),
                    ).fetchall()
                    group_alarm_templates.append(
                        (_tr["alarm_index"], {a["field_key"]: a["value"] for a in _attr_rows})
                    )
```

找到 `_flush_nodes` 里"Auto-insert 1 default alarm per node"那块（约 451-463 行）：

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

替换为（改成"遍历组模板批量插"）：

```python
                # 按组的告警模板批量插入告警（0 模板 = 0 告警）
                if alarm_schema_id and group_alarm_templates:
                    for tpl_idx, tpl_attrs in group_alarm_templates:
                        aid = f"alm_{uuid.uuid4().hex[:12]}"
                        conn.execute(
                            "INSERT INTO node_alarms (id, node_id, alarm_index) VALUES (?, ?, ?)",
                            (aid, nid, tpl_idx),
                        )
                        # 合并：模板显式值 > mapping_target > default_value
                        # 用 build_alarm_attrs 走 mapping/default 优先级；再用模板值覆盖
                        base_attrs = build_alarm_attrs(conn, nid, alarm_fields)
                        for k, v in tpl_attrs.items():
                            if v is not None:
                                base_attrs[k] = v
                        for k, v in base_attrs.items():
                            conn.execute(
                                "INSERT INTO node_alarm_attrs (alarm_id, field_key, value) VALUES (?, ?, ?)",
                                (aid, k, v),
                            )
```

**注意优先级：**
- 有 mapping_target 的字段：从新物理节点取值（模板不存这些字段的值，跳过覆盖）
- 用户显式配了值（模板 attrs 里有）：优先用模板值
- 未配、无 mapping：走 default_value

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_materialize_alarms.py -v`
Expected: 全部 PASS

- [ ] **Step 5: 跑全套确认无回归**

Run: `cd backend && python -m pytest -q 2>&1 | tail -3`
Expected: 全部 PASS

如果原有 `test_materialize_alarms.py` 里有依赖"自动 1 条默认告警"的旧测试失败，是本次有意的行为变更（spec 里明确了），把旧测试的期望改为"0 告警"或改造成"用户先加 1 条模板再 materialize"。

- [ ] **Step 6: 提交**

```bash
git add backend/app/admin/node_group.py backend/tests/test_materialize_alarms.py
git commit -m "$(cat <<'EOF'
feat(node-groups): materialize 用组告警模板替代"1 条默认"

- 预拉组的所有告警模板 (alarm_index, attrs)
- 每个新建物理节点按模板批量插 M 条 node_alarms + attrs
- 优先级：模板显式值 > mapping_target（从新节点取）> default_value
- 0 模板 = 0 告警（跟旧的"自动 1 条"行为不同，是有意的语义收敛）
- +3 单测覆盖：模板数量 × 节点数 / 0 模板 0 告警 / mapping_target 代入新节点值

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: 前端 API 层 — nodeGroup.ts 加 alarm CRUD

**Files:**
- Modify: `frontend/src/api/nodeGroup.ts`

- [ ] **Step 1: 加 alarm 相关类型 + 方法**

Edit `frontend/src/api/nodeGroup.ts`. 在文件末尾（现有导出对象之前）追加类型：

```typescript
export interface NodeGroupAlarmItem {
  id: string
  nodeGroupId: string
  alarmIndex: number
  attrs: Record<string, string | null>
  createdAt: string
  updatedAt: string
}

export interface NodeGroupAlarmCreate {
  attrs?: Record<string, string | null>
}

export interface NodeGroupAlarmAttrSet {
  attrs: Record<string, string | null>
}
```

在现有的 `nodeGroupApi` 对象里追加 alarm 方法（保持跟 nodeAlarmApi 的命名对齐）：

```typescript
  listAlarms: (groupId: string): Promise<NodeGroupAlarmItem[]> =>
    apiGet(`/node-groups/${groupId}/alarms`),

  createAlarm: (groupId: string, data: NodeGroupAlarmCreate = {}): Promise<NodeGroupAlarmItem> =>
    apiPost(`/node-groups/${groupId}/alarms`, data),

  updateAlarmAttrs: (alarmId: string, data: NodeGroupAlarmAttrSet): Promise<NodeGroupAlarmItem> =>
    apiPut(`/node-group-alarms/${alarmId}/attrs`, data),

  deleteAlarm: (alarmId: string): Promise<null> =>
    apiDelete(`/node-group-alarms/${alarmId}`),
```

- [ ] **Step 2: 类型检查**

Run: `cd frontend && npx vue-tsc --noEmit`
Expected: 无错

- [ ] **Step 3: 提交**

```bash
git add frontend/src/api/nodeGroup.ts
git commit -m "$(cat <<'EOF'
feat(api): nodeGroup.ts 加 alarm CRUD 4 方法

- listAlarms / createAlarm / updateAlarmAttrs / deleteAlarm
- 类型 NodeGroupAlarmItem/Create/AttrSet 镜像后端 pydantic

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: NodeAlarmsTab.vue 加 context prop 复用

**Files:**
- Modify: `frontend/src/components/canvas/NodeAlarmsTab.vue`

- [ ] **Step 1: 先读文件了解结构**

Read `frontend/src/components/canvas/NodeAlarmsTab.vue` — 找到 props 定义、API 调用位置（`nodeAlarmApi.list/create/updateAttrs/delete`）以及"nodeId"作为主参的地方。

- [ ] **Step 2: 加 context prop 并按 context 分流 API**

在 props 里追加：

```typescript
interface Props {
  nodeId?: string        // 现有 prop（context='node' 时用）
  nodeGroupId?: string   // 新 prop（context='group' 时用）
  context?: 'node' | 'group'  // 新 prop，默认 'node' 保持兼容
}
```

在 `<script setup>` 头部加：

```typescript
import { nodeGroupApi } from '@/api/nodeGroup'
```

改所有 `nodeAlarmApi.xxx` 调用为分支：

```typescript
const ctx = computed(() => props.context ?? 'node')

async function loadAlarms() {
  if (ctx.value === 'group' && props.nodeGroupId) {
    return await nodeGroupApi.listAlarms(props.nodeGroupId)
  }
  if (props.nodeId) {
    return await nodeAlarmApi.list(props.nodeId)
  }
  return []
}

async function createOne(attrs: Record<string, string | null>) {
  if (ctx.value === 'group' && props.nodeGroupId) {
    return await nodeGroupApi.createAlarm(props.nodeGroupId, { attrs })
  }
  return await nodeAlarmApi.create(props.nodeId!, { attrs })
}

async function updateOne(alarmId: string, attrs: Record<string, string | null>) {
  if (ctx.value === 'group') {
    return await nodeGroupApi.updateAlarmAttrs(alarmId, { attrs })
  }
  return await nodeAlarmApi.updateAttrs(alarmId, { attrs })
}

async function deleteOne(alarmId: string) {
  if (ctx.value === 'group') {
    return await nodeGroupApi.deleteAlarm(alarmId)
  }
  return await nodeAlarmApi.delete(alarmId)
}
```

组件里所有 `nodeAlarmApi.*` 的调用点替换为上面 4 个包装函数。

- [ ] **Step 3: 类型检查**

Run: `cd frontend && npx vue-tsc --noEmit`
Expected: 无错

- [ ] **Step 4: 提交**

```bash
git add frontend/src/components/canvas/NodeAlarmsTab.vue
git commit -m "$(cat <<'EOF'
feat(canvas): NodeAlarmsTab 加 context prop，复用给节点组

- 新增 context: 'node' | 'group' 默认 'node'（保持兼容）
- 新增 nodeGroupId prop 供组场景传入
- 所有 API 调用点包装为 loadAlarms / createOne / updateOne / deleteOne
  分别按 context 分流到 nodeAlarmApi 或 nodeGroupApi

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: GroupCreateModal 加第 4 步"告警"

**Files:**
- Modify: `frontend/src/components/canvas/GroupCreateModal.vue`

- [ ] **Step 1: Steps 组件加第 4 步**

Read the file first to locate the Steps declaration and step content sections.

在 template 里找到 `<Steps>` 组件，加一个新 Step：

```vue
<Step title="告警" />
```

`currentStep === 3` 时渲染新内容：

```vue
<div v-if="currentStep === 3" class="step-content">
  <div v-if="!alarmSchemaBound" class="alarm-empty-hint">
    当前拓扑未绑定告警模板。请先到拓扑管理页面绑定，或提交后再补配告警。
  </div>
  <NodeAlarmsTab
    v-else-if="mode === 'edit' && editingGroupId"
    context="group"
    :node-group-id="editingGroupId"
  />
  <div v-else class="alarm-create-note">
    创建成功后可在"编辑组定义"里继续配置告警。
  </div>
</div>
```

**说明：**
- **create 模式：** 组还未创建，`editingGroupId` 为空，`NodeAlarmsTab` 不能直接工作（它 create/update 都需要现成 groupId）。所以 create 模式下只显示提示"创建后再配"，用户 submit 后打开编辑模式配。
- **edit 模式：** `editingGroupId` 已知，直接挂载 `NodeAlarmsTab` context=group。

这样保证 Task 7 的 NodeAlarmsTab 无变更（无"attrs 数组待提交"暂存概念）。

- [ ] **Step 2: 加 `alarmSchemaBound` 计算属性**

在 `<script setup>` 里加：

```typescript
import { getTopology } from '@/api/topology'  // 或已有的相应方法

const alarmSchemaBound = ref(false)

async function checkAlarmSchema(topologyId: string) {
  try {
    const topo = await getTopology(topologyId)
    alarmSchemaBound.value = !!topo.alarmSchemaId
  } catch {
    alarmSchemaBound.value = false
  }
}

// Modal 打开时调用一次
watch(() => props.open, async (v) => {
  if (v && props.topologyId) {
    await checkAlarmSchema(props.topologyId)
  }
})
```

- [ ] **Step 3: 现有"下一步"按钮的启用逻辑扩展到 step 3**

找到现有的 next-button `disabled` 计算属性；step 3 允许通过（无强校验）。找到"完成"（提交）按钮的显示条件：改成 `currentStep === 3` 时显示"确定"，之前显示"下一步"。

- [ ] **Step 4: 类型检查 + 提交**

Run: `cd frontend && npx vue-tsc --noEmit`
Expected: 无错

```bash
git add frontend/src/components/canvas/GroupCreateModal.vue
git commit -m "$(cat <<'EOF'
feat(canvas): GroupCreateModal 加第 4 步"告警"

- Steps 从 3 步变 4 步
- 拓扑未绑 alarm_schema 时告警 step 显示提示，允许直接提交
- 创建模式下不挂 NodeAlarmsTab（因为 groupId 未生成）；提示用户创建后编辑
- 编辑模式下直接挂 NodeAlarmsTab context=group
- step 3 无强校验；"完成"按钮在 step 3 显示

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: GroupCreateModal 编辑模式 + CanvasView 打通

**Files:**
- Modify: `frontend/src/components/canvas/GroupCreateModal.vue`
- Modify: `frontend/src/views/CanvasView.vue`

- [ ] **Step 1: GroupCreateModal 加 mode/editingGroupId props**

在 props 里追加：

```typescript
interface Props {
  open: boolean
  topologyId: string
  mode?: 'create' | 'edit'          // 新
  editingGroupId?: string | null    // 新
}
```

在 `<script setup>` 里加载现有组数据：

```typescript
async function loadExistingGroup(gid: string) {
  const group = await nodeGroupApi.get(gid)  // 假设 API 有 get 方法；无则用 listGroups + find
  // 填充 step1
  step1.value.nodeTypeId = group.nodeTypeId
  step1.value.groupName = group.groupName
  step1.value.nodeCount = group.nodeCount
  step1.value.nameTemplate = group.nameTemplate ?? '{group}-{i:05d}'
  // 填充 step2 attrs
  attrStrategies.value = group.attrStrategies ?? []
  // 填充 step3 edges
  edgeStrategies.value = group.edgeStrategies ?? []
}

watch(() => props.open, async (v) => {
  if (v && props.mode === 'edit' && props.editingGroupId) {
    await loadExistingGroup(props.editingGroupId)
  }
})
```

**Node type 只读锁定：** 找到 Node type 选择器 UI，在 edit 模式下加 `:disabled="mode === 'edit'"`。

**Modal 标题：**

```vue
<template #title>
  {{ mode === 'edit' ? '编辑节点组' : '创建节点组' }}
</template>
```

**提交按钮分流：**

```typescript
async function handleSubmit() {
  if (props.mode === 'edit' && props.editingGroupId) {
    await nodeGroupApi.update(props.editingGroupId, buildUpdatePayload())
  } else {
    await nodeGroupApi.create(props.topologyId, buildCreatePayload())
  }
  emit('submitted')
}
```

**Materialize 警告 banner（edit 模式）：**

```vue
<div v-if="mode === 'edit' && groupMaterialized" class="warning-banner">
  ⚠️ 该组已展开，编辑不会影响已生成的实体节点。
</div>
```

- [ ] **Step 2: CanvasView 接入 editingGroupId**

Edit `frontend/src/views/CanvasView.vue`. 找到 `GroupCreateModal` 挂载点：

```vue
<GroupCreateModal
  v-model:open="showGroupCreate"
  :topology-id="currentTopologyId"
  :mode="groupModalMode"
  :editing-group-id="editingGroupId"
  @submitted="onGroupSubmitted"
/>
```

在 `<script setup>` 加：

```typescript
const groupModalMode = ref<'create' | 'edit'>('create')
const editingGroupId = ref<string | null>(null)

function handleEditGroup(gid: string) {
  editingGroupId.value = gid
  groupModalMode.value = 'edit'
  showGroupCreate.value = true
}

function handleCreateGroup() {
  editingGroupId.value = null
  groupModalMode.value = 'create'
  showGroupCreate.value = true
}
```

找到 GroupPalette / TopologyCanvas 上"编辑组定义"的 emit 事件绑定，替换处理器为 `handleEditGroup`。

**关闭 Modal 时清 state：**

```typescript
watch(() => showGroupCreate.value, (v) => {
  if (!v) {
    editingGroupId.value = null
    groupModalMode.value = 'create'
  }
})
```

- [ ] **Step 3: 类型检查**

Run: `cd frontend && npx vue-tsc --noEmit`
Expected: 无错

- [ ] **Step 4: 提交**

```bash
git add frontend/src/components/canvas/GroupCreateModal.vue frontend/src/views/CanvasView.vue
git commit -m "$(cat <<'EOF'
feat(canvas): GroupCreateModal 编辑模式打通

- Modal 加 mode / editingGroupId prop；edit 载入现有 attrs/edges/step1
- Node type 在编辑模式下只读（改了会破坏 attr_strategies 语义）
- 提交时按 mode 走 create 或 update
- Materialize 已展开的组：Modal 顶部 warning banner
- CanvasView 接入 handleEditGroup / handleCreateGroup，切换 mode
- 关闭 Modal 时清 editingGroupId

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: 手动集成验证

**Files:** 无代码修改

- [ ] **Step 1: 重启前后端**

```bash
# 关掉当前的旧后端进程（Ctrl+C 或结束进程）
cd backend && python -m app.main
# 前端另开终端
cd frontend && npm run dev
```

- [ ] **Step 2: 验证新建节点组走 4 步流程**

1. 画布上从左侧组面板拖一个节点类型到画布，触发 GroupCreateModal
2. Step 1-3 走完（跟以前一样）
3. Step 4："告警" 显示提示"创建成功后可在编辑组定义里继续配置告警"
4. 点"确定"创建；组出现在画布

- [ ] **Step 3: 验证编辑组打通告警**

1. 右键宏节点 → "编辑组定义"
2. Modal 打开，标题"编辑节点组"，Node type 只读
3. 切到 step 4"告警"
4. 如果拓扑绑了 alarm_schema：显示 NodeAlarmsTab 界面，能添加告警条目、mapping_target 字段灰置
5. 如果拓扑未绑：显示提示"当前拓扑未绑定告警模板"

- [ ] **Step 4: 验证 CTE 查询能查到虚拟告警**

1. 上一步给组加了 2 条告警模板（severity=critical / severity=major）
2. 在 SQL 数据源接口里用 `SELECT * FROM alarms WHERE node_name LIKE '<组名>%'`
3. 应该看到 `虚拟节点数 × 2` 行

- [ ] **Step 5: 验证 materialize 用模板**

1. 前面步骤的组还没 materialize
2. 右键组 → materialize
3. 展开后每个物理节点在 NodeAlarmsPanel 里应有 2 条告警（跟模板一致）
4. mapping_target 字段（如 device_name）应等于 各节点自己的 name

- [ ] **Step 6: 关闭进程**

Ctrl+C 前后端；`netstat -ano | findstr :8080` 应无输出。

- [ ] **Step 7: 无代码变更，不提交**

---

## Self-Review Checklist（写完 plan 后自查）

- [x] **Spec 覆盖：**
  - 数据模型（两张镜像表 + CASCADE）→ Task 1
  - Pydantic schemas → Task 2
  - CRUD 端点 → Task 3
  - CTE 视图 UNION 虚拟告警 + mapping_target → Task 4
  - Materialize 用模板替代自动 1 条 → Task 5
  - 前端 API 层 → Task 6
  - NodeAlarmsTab 复用（context prop）→ Task 7
  - GroupCreateModal 4th step → Task 8
  - 编辑现有组入口 → Task 9

- [x] **占位扫描：** 每步含实际代码/命令；无 "TODO/TBD/appropriate error handling"

- [x] **类型一致性：**
  - `NodeGroupAlarmCreate / Item / AttrSet` 在 Task 2 定义，Task 3 使用
  - `NodeGroupAlarmItem` 前端类型 (Task 6) 跟后端字段一一对应（含 alarmIndex camelCase）
  - `context: 'node' | 'group'` 在 Task 7 定义，Task 8 使用
  - `mode / editingGroupId` prop 在 Task 9 前后一致
  - CTE 里 `gna_` 前缀 vs `alm_` 前缀跟 spec 一致
  - `grp_alm_` id 前缀在 Task 3 生成，Task 5 不再引用（materialize 生成的是 `alm_`）

- **已知取舍：**
  - Task 4 里 mapping_target 到"自定义节点属性"（非系统字段）的虚拟侧展开返回 NULL——跟现有虚拟节点属性生成的能力对齐；如后续需要，可在 group_nodes 视图里 pivot 属性再 join
  - Task 8 里 create 模式的告警配置延后到用户创建完组后走编辑模式——避免引入"客户端暂存 → 提交时批量写"的额外复杂度；用户体验成本可接受
