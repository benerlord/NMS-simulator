# 节点/边类型字段编辑器紧凑化 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把节点类型 / 边类型的字段定义编辑改造为与告警模板一致的"Modal 内嵌紧凑表格 + 整批同步"模式，并把画布上节点/边的字段值编辑改造为更紧凑的布局（Modal 双列 720px / 抽屉水平 label 380px）。

**Architecture:** 后端从"每字段独立 API"切换为"父表单整批同步"模式（POST/PUT 节点类型时一并传 `fields[]`，服务端按 `field_key` diff insert/update/delete）；删字段时先调用 `delete-impact` 端点统计 `node_attrs/edge_attrs` 影响，再让前端弹确认。前端类型管理页删除表格展开行，字段编辑搬进 Modal；画布属性编辑用 Antd Row+Col / horizontal Form 提升信息密度。

**Tech Stack:** FastAPI + SQLite WAL + Pydantic v2 CamelModel；Vue 3.5 `<script setup>` + Ant Design Vue 4；pytest（后端）；前端无自动化测试，靠人工 smoke。

**Spec:** `docs/superpowers/specs/2026-06-14-node-type-field-editor-compact-design.md`

**Worktree note:** 实施前如需隔离环境，使用 `superpowers:using-git-worktrees` 在执行时创建独立 worktree（分支名建议 `worktree-node-type-field-compact`）。

---

## Task 1: 后端 Pydantic schemas

**Files:**
- Modify: `backend/app/admin/schemas/node_type.py`

新增 4 个 schema（`NodeTypeFieldInput` / `EdgeTypeFieldInput` / `FieldDeleteImpactRequest` / `FieldDeleteImpactItem`），并在 `NodeTypeCreate` / `NodeTypeUpdate` / `EdgeTypeCreate` / `EdgeTypeUpdate` 加 `fields: Optional[list[...]]`。这是纯结构改动，没有运行时逻辑，不写单测。

- [ ] **Step 1: 阅读 spec §3.5 确认 schema 设计**

设计要点：
- `NodeTypeFieldInput` 不含 `id`（diff 用 `field_key`）；和 `NodeTypeFieldCreate` 几乎一致但作为整批同步专用类型，命名上区分
- `fields` 字段在 `Create` / `Update` 都是 `Optional[list[...]] = None`：`None` = 不动字段（PUT 兼容性），`[]` = 清空字段
- `field_key` 必须可选地允许重复 → 由服务端 diff 阶段校验

- [ ] **Step 2: 在 `schemas/node_type.py` 添加 NodeTypeFieldInput**

在 `NodeTypeFieldItem` 类之前（约第 73 行）添加：

```python
class NodeTypeFieldInput(CamelModel):
    """整批同步用 — 无 id；field_key 是稳定主键。"""
    field_key: str = Field(..., min_length=1, max_length=50)
    field_label: str = Field(..., min_length=1, max_length=100)
    field_type: str = Field(..., pattern="^(text|number|select|boolean)$")
    max_length: Optional[int] = Field(default=None, ge=1)
    default_value: Optional[str] = Field(default=None, max_length=200)
    options: Optional[str] = Field(default=None, max_length=500)
    required: bool = Field(default=False)
    sort_order: int = Field(default=0)

    @model_validator(mode='after')
    def validate_max_length_for_text(self) -> 'NodeTypeFieldInput':
        if self.field_type != 'text':
            return self
        if self.max_length is None:
            raise ValueError('文本类型必须设置 max_length')
        if self.max_length < 1:
            raise ValueError('max_length 必须 >= 1')
        return self
```

- [ ] **Step 3: 在 NodeTypeCreate / NodeTypeUpdate 加 fields 字段**

修改 `NodeTypeCreate`（约第 11 行）和 `NodeTypeUpdate`（约第 23 行），在末尾各加一行：

```python
# NodeTypeCreate 末尾
    fields: Optional[list[NodeTypeFieldInput]] = Field(default=None)

# NodeTypeUpdate 末尾
    fields: Optional[list[NodeTypeFieldInput]] = Field(default=None)
```

注：因为 `NodeTypeFieldInput` 在 `NodeTypeCreate` 之后定义，需将其声明移到 `NodeTypeCreate` 之前；或者保持 Python 用字符串形式 `Optional[list["NodeTypeFieldInput"]]` 并写 `model_rebuild()`。**最简方案：** 把 `NodeTypeFieldInput` 类移到文件顶部（在 `NodeTypeCreate` 之前）。

- [ ] **Step 4: 添加 EdgeTypeFieldInput**

镜像 `NodeTypeFieldInput`，放在 `EdgeTypeFieldItem` 之前（约第 215 行）。同样把它移到 `EdgeTypeCreate` 之前。

```python
class EdgeTypeFieldInput(CamelModel):
    """整批同步用 — 无 id；field_key 是稳定主键。"""
    field_key: str = Field(..., min_length=1, max_length=50)
    field_label: str = Field(..., min_length=1, max_length=100)
    field_type: str = Field(..., pattern="^(text|number|select|boolean)$")
    max_length: Optional[int] = Field(default=None, ge=1)
    default_value: Optional[str] = Field(default=None, max_length=200)
    options: Optional[str] = Field(default=None, max_length=500)
    required: bool = Field(default=False)
    sort_order: int = Field(default=0)

    @model_validator(mode='after')
    def validate_max_length_for_text(self) -> 'EdgeTypeFieldInput':
        if self.field_type != 'text':
            return self
        if self.max_length is None:
            raise ValueError('文本类型必须设置 max_length')
        if self.max_length < 1:
            raise ValueError('max_length 必须 >= 1')
        return self
```

- [ ] **Step 5: 在 EdgeTypeCreate / EdgeTypeUpdate 加 fields**

末尾各加：

```python
    fields: Optional[list[EdgeTypeFieldInput]] = Field(default=None)
```

- [ ] **Step 6: 添加 FieldDeleteImpact schemas**

在文件末尾（共用，节点/边都用）：

```python
class FieldDeleteImpactRequest(CamelModel):
    field_keys: list[str] = Field(..., min_length=1, max_length=200)


class FieldDeleteImpactItem(CamelModel):
    field_key: str
    affected_node_count: int = 0  # 节点类型用；边类型在响应里会复用同结构（语义为 affected_edge_count）


class FieldDeleteImpactResponse(CamelModel):
    items: list[FieldDeleteImpactItem]
```

注：响应字段名为 `affected_node_count` — 即使边类型复用同结构（语义为受影响"边"数），保持字段名简化前端逻辑。spec §3.4 显示 `affected_node_count` 是约定名。

- [ ] **Step 7: 验证 import 顺序**

运行：

```bash
cd backend && python -c "from app.admin.schemas.node_type import NodeTypeFieldInput, NodeTypeCreate, EdgeTypeFieldInput, EdgeTypeCreate, FieldDeleteImpactRequest, FieldDeleteImpactItem, FieldDeleteImpactResponse; print('ok')"
```

预期输出：`ok`

- [ ] **Step 8: 提交**

```bash
cd backend && git add app/admin/schemas/node_type.py
cd .. && git commit -m "$(cat <<'EOF'
feat(types): 加 NodeTypeFieldInput/EdgeTypeFieldInput 整批同步 schema

新增：
- NodeTypeFieldInput / EdgeTypeFieldInput — 不含 id，field_key 作 diff 主键
- FieldDeleteImpactRequest / FieldDeleteImpactItem / FieldDeleteImpactResponse
- NodeTypeCreate / NodeTypeUpdate / EdgeTypeCreate / EdgeTypeUpdate 加可选 fields[]

为下游 Task 2/3 的整批同步端点准备 schema 基础。
EOF
)"
```

---

## Task 2: 后端 node_type 整批同步 + delete-impact + 移除旧端点

**Files:**
- Modify: `backend/app/admin/node_type.py`
- Create: `backend/tests/test_node_type_field_sync.py`

### TDD 顺序：先写测试再改实现。

- [ ] **Step 1: 创建测试文件骨架并写第 1 个失败用例**

创建 `backend/tests/test_node_type_field_sync.py`：

```python
"""节点类型字段整批同步测试。

覆盖 §3.3 diff 算法（insert/update/delete）+ §3.4 delete-impact +
旧 3 个单字段端点已移除。
"""


def test_create_node_type_with_fields(client):
    """POST /node-types body 含 fields[] → 类型 + 字段一次性落库。"""
    payload = {
        "code": "router_v2",
        "name": "路由器V2",
        "category": "physical",
        "fields": [
            {"fieldKey": "ip", "fieldLabel": "IP", "fieldType": "text", "maxLength": 15},
            {"fieldKey": "ports", "fieldLabel": "端口数", "fieldType": "number"},
        ],
    }
    r = client.post("/admin/api/node-types", json=payload)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["code"] == 0
    type_id = j["data"]["id"]

    # 验证字段已落库
    r = client.get(f"/admin/api/node-types/{type_id}")
    assert r.status_code == 200
    fields = r.json()["data"]["fields"]
    assert [f["fieldKey"] for f in fields] == ["ip", "ports"]
    assert fields[0]["maxLength"] == 15
```

- [ ] **Step 2: 跑这个测试，确认失败**

```bash
cd backend && python -m pytest tests/test_node_type_field_sync.py::test_create_node_type_with_fields -xvs
```

预期失败原因：POST 端点忽略 fields → GET 返回 `fields: []`。

- [ ] **Step 3: 实现 _sync_node_type_fields helper + 修改 create_node_type**

打开 `backend/app/admin/node_type.py`，在 `_get_node_type_fields` 之后（约第 102 行后）插入辅助函数：

```python
def _sync_node_type_fields(conn, node_type_id: str, incoming: list) -> None:
    """整批同步 node_type_fields，按 field_key 做 diff。

    incoming: list[NodeTypeFieldInput]
    事务内顺序：delete → update → insert
    删除字段时一并清理同类型节点的孤儿 node_attrs 行。
    """
    # 校验 incoming 内 field_key 不重复
    seen_keys = set()
    for f in incoming:
        if f.field_key in seen_keys:
            raise HTTPException(
                status_code=400,
                detail={"code": 40206, "message": f"字段 Key 重复: {f.field_key}"},
            )
        seen_keys.add(f.field_key)

    existing_keys = {
        r["field_key"]
        for r in conn.execute(
            "SELECT field_key FROM node_type_fields WHERE node_type_id = ?",
            (node_type_id,),
        ).fetchall()
    }

    incoming_keys = {f.field_key for f in incoming}
    to_delete = existing_keys - incoming_keys
    to_update = [f for f in incoming if f.field_key in existing_keys]
    to_insert = [f for f in incoming if f.field_key not in existing_keys]

    # DELETE：先删字段定义，再清理孤儿 node_attrs（仅同类型节点）
    for k in to_delete:
        conn.execute(
            "DELETE FROM node_type_fields WHERE node_type_id = ? AND field_key = ?",
            (node_type_id, k),
        )
        conn.execute(
            """DELETE FROM node_attrs
               WHERE field_key = ?
                 AND node_id IN (SELECT id FROM nodes WHERE node_type_id = ?)""",
            (k, node_type_id),
        )

    # UPDATE：按 sort_order = 数组下标重写
    for idx, f in enumerate(incoming):
        if f.field_key not in existing_keys:
            continue
        conn.execute(
            """UPDATE node_type_fields
               SET field_label = ?, field_type = ?, max_length = ?,
                   default_value = ?, options = ?, required = ?, sort_order = ?
               WHERE node_type_id = ? AND field_key = ?""",
            (f.field_label, f.field_type, f.max_length, f.default_value,
             f.options, int(f.required), idx,
             node_type_id, f.field_key),
        )

    # INSERT：sort_order = 数组下标
    for idx, f in enumerate(incoming):
        if f.field_key in existing_keys:
            continue
        conn.execute(
            """INSERT INTO node_type_fields
               (node_type_id, field_key, field_label, field_type, max_length,
                default_value, options, required, sort_order)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (node_type_id, f.field_key, f.field_label, f.field_type,
             f.max_length, f.default_value, f.options, int(f.required), idx),
        )
```

修改 `create_node_type`（约第 205-220 行）：

```python
@router.post("/node-types")
def create_node_type(data: NodeTypeCreate) -> dict:
    type_id = _new_id()
    with transaction() as conn:
        existing = conn.execute(
            "SELECT id FROM node_types WHERE code = ?", (data.code,)
        ).fetchone()
        if existing:
            raise HTTPException(status_code=409, detail={"code": 40202, "message": "类型代码已存在"})
        conn.execute(
            """INSERT INTO node_types (id, code, name, category, icon, color, shape, render_mode, dn_template, description)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (type_id, data.code, data.name, data.category, data.icon, data.color,
             data.shape, data.render_mode, data.dn_template, data.description),
        )
        if data.fields is not None:
            _sync_node_type_fields(conn, type_id, data.fields)
    return {"code": 0, "data": {"id": type_id}, "message": "ok"}
```

记得在文件顶部 import 中加入 `NodeTypeFieldInput, FieldDeleteImpactRequest, FieldDeleteImpactResponse, FieldDeleteImpactItem`（约第 11 行 schema import 处）。

- [ ] **Step 4: 跑测试确认通过**

```bash
cd backend && python -m pytest tests/test_node_type_field_sync.py::test_create_node_type_with_fields -xvs
```

预期：PASS

- [ ] **Step 5: 写 update 同步用例**

继续在 `test_node_type_field_sync.py` 末尾追加：

```python
def test_update_sync_fields_insert_only(client):
    """PUT 加新字段 → 旧字段保留，新字段加入。"""
    r = client.post("/admin/api/node-types", json={
        "code": "sw", "name": "交换机", "category": "physical",
        "fields": [{"fieldKey": "old_f", "fieldLabel": "旧", "fieldType": "number"}],
    })
    tid = r.json()["data"]["id"]

    r = client.put(f"/admin/api/node-types/{tid}", json={
        "fields": [
            {"fieldKey": "old_f", "fieldLabel": "旧", "fieldType": "number"},
            {"fieldKey": "new_f", "fieldLabel": "新", "fieldType": "number"},
        ],
    })
    assert r.status_code == 200, r.text

    r = client.get(f"/admin/api/node-types/{tid}")
    keys = [f["fieldKey"] for f in r.json()["data"]["fields"]]
    assert keys == ["old_f", "new_f"]


def test_update_sync_fields_update_only(client):
    """PUT 改字段 label / sort → field_key 不变，UPDATE 生效。"""
    r = client.post("/admin/api/node-types", json={
        "code": "sw2", "name": "S2", "category": "physical",
        "fields": [
            {"fieldKey": "a", "fieldLabel": "Old A", "fieldType": "number"},
            {"fieldKey": "b", "fieldLabel": "Old B", "fieldType": "number"},
        ],
    })
    tid = r.json()["data"]["id"]

    r = client.put(f"/admin/api/node-types/{tid}", json={
        "fields": [
            {"fieldKey": "b", "fieldLabel": "New B", "fieldType": "number"},  # 调到前
            {"fieldKey": "a", "fieldLabel": "New A", "fieldType": "number"},  # 调到后
        ],
    })
    assert r.status_code == 200, r.text

    fields = client.get(f"/admin/api/node-types/{tid}").json()["data"]["fields"]
    assert [f["fieldKey"] for f in fields] == ["b", "a"]
    assert [f["fieldLabel"] for f in fields] == ["New B", "New A"]
```

- [ ] **Step 6: 跑测试确认 update 端点失败**

```bash
cd backend && python -m pytest tests/test_node_type_field_sync.py::test_update_sync_fields_insert_only -xvs
```

预期失败原因：PUT 端点没处理 fields。

- [ ] **Step 7: 修改 update_node_type 支持 fields 同步**

找到 `update_node_type`（约第 267-283 行）并改写：

```python
@router.put("/node-types/{type_id}")
def update_node_type(type_id: str, data: NodeTypeUpdate) -> dict:
    raw = data.model_dump(exclude_unset=True)
    fields_payload = data.fields  # 取出 fields 单独处理
    raw.pop("fields", None)  # 不放进 UPDATE SQL

    with transaction() as conn:
        existing = conn.execute(
            "SELECT id FROM node_types WHERE id = ?", (type_id,)
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail={"code": 40201, "message": "类型不存在"})

        if raw:
            set_clause = ", ".join(f"{k} = ?" for k in raw.keys())
            conn.execute(
                f"UPDATE node_types SET {set_clause}, updated_at = datetime('now') WHERE id = ?",
                (*raw.values(), type_id),
            )

        if fields_payload is not None:
            _sync_node_type_fields(conn, type_id, fields_payload)

    return {"code": 0, "data": {"id": type_id}, "message": "ok"}
```

注意：原版若 `not fields` 抛 400 — 现在去掉这个保护，因为只传 fields 也是合法的更新。

- [ ] **Step 8: 跑测试确认通过**

```bash
cd backend && python -m pytest tests/test_node_type_field_sync.py -xvs
```

预期：前 3 个 test 通过。

- [ ] **Step 9: 写 delete + orphan-cleanup 用例**

```python
def test_update_sync_fields_delete_cleans_orphan_attrs(conn, client):
    """PUT 删字段 + 该字段在 node_attrs 有数据 → node_attrs 中同类型节点的孤儿一并清理。"""
    r = client.post("/admin/api/node-types", json={
        "code": "ap", "name": "AP", "category": "physical",
        "fields": [
            {"fieldKey": "ip", "fieldLabel": "IP", "fieldType": "text", "maxLength": 15},
            {"fieldKey": "vendor", "fieldLabel": "厂家", "fieldType": "text", "maxLength": 50},
        ],
    })
    tid = r.json()["data"]["id"]

    # 创建拓扑 + 节点 + 灌 attrs
    r = client.post("/admin/api/topologies", json={"name": "T1"})
    topo_id = r.json()["data"]["id"]
    r = client.post(f"/admin/api/topologies/{topo_id}/nodes", json={
        "nodeTypeId": tid, "name": "ap-01",
    })
    node_id = r.json()["data"]["id"]
    r = client.put(f"/admin/api/nodes/{node_id}/attrs", json={
        "attrs": {"ip": "10.0.0.1", "vendor": "huawei"},
    })
    assert r.status_code == 200, r.text

    # PUT 删除 vendor 字段
    r = client.put(f"/admin/api/node-types/{tid}", json={
        "fields": [{"fieldKey": "ip", "fieldLabel": "IP", "fieldType": "text", "maxLength": 15}],
    })
    assert r.status_code == 200, r.text

    # 验证 ip 还在，vendor 已清
    from app.db.connection import connect
    with connect() as c:
        rows = c.execute(
            "SELECT field_key FROM node_attrs WHERE node_id = ?", (node_id,)
        ).fetchall()
    keys = sorted(r["field_key"] for r in rows)
    assert keys == ["ip"]


def test_update_sync_fields_delete_keeps_other_type_attrs(client):
    """同名 field_key 在不同 node_type 的节点 attrs 不受波及。"""
    # 两个类型都有 fieldKey="ip"
    r = client.post("/admin/api/node-types", json={
        "code": "type_a", "name": "A", "category": "physical",
        "fields": [{"fieldKey": "ip", "fieldLabel": "IP", "fieldType": "text", "maxLength": 15}],
    })
    type_a = r.json()["data"]["id"]
    r = client.post("/admin/api/node-types", json={
        "code": "type_b", "name": "B", "category": "physical",
        "fields": [{"fieldKey": "ip", "fieldLabel": "IP", "fieldType": "text", "maxLength": 15}],
    })
    type_b = r.json()["data"]["id"]

    r = client.post("/admin/api/topologies", json={"name": "T2"})
    topo_id = r.json()["data"]["id"]
    r = client.post(f"/admin/api/topologies/{topo_id}/nodes", json={
        "nodeTypeId": type_b, "name": "b-01",
    })
    node_b = r.json()["data"]["id"]
    client.put(f"/admin/api/nodes/{node_b}/attrs", json={"attrs": {"ip": "192.168.1.1"}})

    # 删 type_a 的 ip 字段
    r = client.put(f"/admin/api/node-types/{type_a}", json={"fields": []})
    assert r.status_code == 200

    # type_b 节点的 ip attr 必须还在
    from app.db.connection import connect
    with connect() as c:
        row = c.execute(
            "SELECT value FROM node_attrs WHERE node_id = ? AND field_key = 'ip'",
            (node_b,),
        ).fetchone()
    assert row is not None
    assert row["value"] == "192.168.1.1"


def test_update_sync_fields_duplicate_field_key_rejected(client):
    """incoming 重复 field_key → 400。"""
    r = client.post("/admin/api/node-types", json={
        "code": "dup_test", "name": "D", "category": "physical",
        "fields": [],
    })
    tid = r.json()["data"]["id"]

    r = client.put(f"/admin/api/node-types/{tid}", json={
        "fields": [
            {"fieldKey": "same", "fieldLabel": "A", "fieldType": "number"},
            {"fieldKey": "same", "fieldLabel": "B", "fieldType": "number"},
        ],
    })
    assert r.status_code == 400


def test_update_omit_fields_preserves_existing(client):
    """PUT body 不含 fields → 字段不变。"""
    r = client.post("/admin/api/node-types", json={
        "code": "keep_test", "name": "K", "category": "physical",
        "fields": [{"fieldKey": "x", "fieldLabel": "X", "fieldType": "number"}],
    })
    tid = r.json()["data"]["id"]

    r = client.put(f"/admin/api/node-types/{tid}", json={"name": "K2"})
    assert r.status_code == 200, r.text

    fields = client.get(f"/admin/api/node-types/{tid}").json()["data"]["fields"]
    assert [f["fieldKey"] for f in fields] == ["x"]
```

- [ ] **Step 10: 跑测试**

```bash
cd backend && python -m pytest tests/test_node_type_field_sync.py -xvs
```

预期：全部 PASS（实现已支持 delete + orphan-cleanup + duplicate 校验）。

- [ ] **Step 11: 写 delete-impact 端点测试**

```python
def test_delete_impact_returns_affected_counts(client):
    """POST delete-impact → 每个 field_key 受影响节点数正确。"""
    r = client.post("/admin/api/node-types", json={
        "code": "impact_test", "name": "I", "category": "physical",
        "fields": [
            {"fieldKey": "ip", "fieldLabel": "IP", "fieldType": "text", "maxLength": 15},
            {"fieldKey": "mac", "fieldLabel": "MAC", "fieldType": "text", "maxLength": 17},
        ],
    })
    tid = r.json()["data"]["id"]

    r = client.post("/admin/api/topologies", json={"name": "T3"})
    topo_id = r.json()["data"]["id"]
    for i in range(3):
        rr = client.post(f"/admin/api/topologies/{topo_id}/nodes", json={
            "nodeTypeId": tid, "name": f"n{i}",
        })
        nid = rr.json()["data"]["id"]
        client.put(f"/admin/api/nodes/{nid}/attrs", json={
            "attrs": {"ip": f"10.0.0.{i}", "mac": f"aa:bb:cc:00:00:0{i}"},
        })

    r = client.post(
        f"/admin/api/node-types/{tid}/fields/delete-impact",
        json={"fieldKeys": ["ip", "mac"]},
    )
    assert r.status_code == 200
    items = r.json()["data"]["items"]
    counts = {it["fieldKey"]: it["affectedNodeCount"] for it in items}
    assert counts == {"ip": 3, "mac": 3}


def test_delete_impact_empty_for_unused_field(client):
    """未引用字段 → affectedNodeCount=0。"""
    r = client.post("/admin/api/node-types", json={
        "code": "unused", "name": "U", "category": "physical",
        "fields": [{"fieldKey": "unused_field", "fieldLabel": "U", "fieldType": "number"}],
    })
    tid = r.json()["data"]["id"]

    r = client.post(
        f"/admin/api/node-types/{tid}/fields/delete-impact",
        json={"fieldKeys": ["unused_field"]},
    )
    assert r.status_code == 200
    items = r.json()["data"]["items"]
    assert items == [{"fieldKey": "unused_field", "affectedNodeCount": 0}]
```

- [ ] **Step 12: 跑测试确认失败**

```bash
cd backend && python -m pytest tests/test_node_type_field_sync.py::test_delete_impact_returns_affected_counts -xvs
```

预期 404：端点未实现。

- [ ] **Step 13: 实现 delete-impact 端点**

在 `node_type.py` 中 `delete_node_type` 之后（约第 615 行后）插入：

```python
@router.post("/node-types/{type_id}/fields/delete-impact")
def get_node_type_field_delete_impact(
    type_id: str, payload: FieldDeleteImpactRequest
) -> dict:
    """统计若删除 fieldKeys 中的字段，会影响多少同类型节点的 node_attrs。"""
    with connect() as conn:
        existing = conn.execute(
            "SELECT id FROM node_types WHERE id = ?", (type_id,)
        ).fetchone()
        if not existing:
            raise HTTPException(
                status_code=404, detail={"code": 40201, "message": "类型不存在"}
            )
        items = []
        for k in payload.field_keys:
            count = conn.execute(
                """SELECT COUNT(*) AS cnt FROM node_attrs a
                   JOIN nodes n ON a.node_id = n.id
                   WHERE n.node_type_id = ? AND a.field_key = ?""",
                (type_id, k),
            ).fetchone()["cnt"]
            items.append(
                FieldDeleteImpactItem(field_key=k, affected_node_count=count)
            )
        resp = FieldDeleteImpactResponse(items=items)
    return {"code": 0, "data": resp.model_dump(mode="json", by_alias=True), "message": "ok"}
```

- [ ] **Step 14: 跑 delete-impact 测试**

```bash
cd backend && python -m pytest tests/test_node_type_field_sync.py::test_delete_impact_returns_affected_counts tests/test_node_type_field_sync.py::test_delete_impact_empty_for_unused_field -xvs
```

预期：PASS。

- [ ] **Step 15: 写"旧端点已移除"测试**

```python
def test_legacy_single_field_endpoints_removed(client):
    """旧 3 个单字段端点应已删除，返回 404 或 405。"""
    r = client.post("/admin/api/node-types", json={
        "code": "legacy_test", "name": "L", "category": "physical",
    })
    tid = r.json()["data"]["id"]

    r = client.post(f"/admin/api/node-types/{tid}/fields", json={
        "fieldKey": "x", "fieldLabel": "X", "fieldType": "number",
    })
    assert r.status_code in (404, 405), f"POST /fields 应已移除，实际 {r.status_code}"

    r = client.put(f"/admin/api/node-types/{tid}/fields/1", json={
        "fieldLabel": "Y",
    })
    assert r.status_code in (404, 405)

    r = client.delete(f"/admin/api/node-types/{tid}/fields/1")
    assert r.status_code in (404, 405)
```

- [ ] **Step 16: 跑测试确认旧端点还在**

```bash
cd backend && python -m pytest tests/test_node_type_field_sync.py::test_legacy_single_field_endpoints_removed -xvs
```

预期失败：旧端点返回 200。

- [ ] **Step 17: 移除旧 3 个单字段端点**

在 `node_type.py` 中删除以下三个函数及其装饰器（spec §3.1 列出，约第 624-685 行）：
- `create_node_type_field` （`@router.post("/node-types/{type_id}/fields")`）
- `update_node_type_field` （`@router.put("/node-types/{type_id}/fields/{field_id}")`）
- `delete_node_type_field` （`@router.delete("/node-types/{type_id}/fields/{field_id}")`）

连同上方 `# ============== node_type_fields ==============` 注释一起删除。

- [ ] **Step 18: 跑全部测试确认通过**

```bash
cd backend && python -m pytest tests/test_node_type_field_sync.py -xvs
```

预期：全部 PASS。

- [ ] **Step 19: 跑全套既有测试确认无回归**

```bash
cd backend && python -m pytest -x
```

预期：全部 PASS。如有失败，应是其它测试用了被删除的 3 个旧端点 — 删除/改写相应测试。

- [ ] **Step 20: 提交**

```bash
cd backend && git add app/admin/node_type.py tests/test_node_type_field_sync.py
cd .. && git commit -m "$(cat <<'EOF'
feat(node-type): 字段编辑改为整批同步 + delete-impact 端点

- POST /node-types / PUT /node-types/{id} 支持 fields[] 整批同步
- _sync_node_type_fields 按 field_key diff insert/update/delete
- 删字段时同步清理同类型节点的 node_attrs 孤儿
- 新增 POST /node-types/{id}/fields/delete-impact 预扫描受影响节点数
- 移除 POST/PUT/DELETE /node-types/{id}/fields/... 3 个旧端点
- field_key 重复 → 400；sort_order 服务端按下标重写
EOF
)"
```

---

## Task 3: 后端 edge_type 整批同步 + delete-impact + 移除旧端点

**Files:**
- Modify: `backend/app/admin/node_type.py`
- Create: `backend/tests/test_edge_type_field_sync.py`

镜像 Task 2，把 `node_*` 换成 `edge_*`。

- [ ] **Step 1: 创建测试文件并写第一个用例**

创建 `backend/tests/test_edge_type_field_sync.py`：

```python
"""边类型字段整批同步测试（镜像 node_type 测试）。"""


def test_create_edge_type_with_fields(client):
    payload = {
        "code": "link_v2",
        "name": "链路V2",
        "fields": [
            {"fieldKey": "bandwidth", "fieldLabel": "带宽", "fieldType": "text", "maxLength": 20},
            {"fieldKey": "latency", "fieldLabel": "时延", "fieldType": "number"},
        ],
    }
    r = client.post("/admin/api/edge-types", json=payload)
    assert r.status_code == 200, r.text
    type_id = r.json()["data"]["id"]

    r = client.get(f"/admin/api/edge-types/{type_id}")
    fields = r.json()["data"]["fields"]
    assert [f["fieldKey"] for f in fields] == ["bandwidth", "latency"]


def test_update_edge_sync_fields_insert_only(client):
    r = client.post("/admin/api/edge-types", json={
        "code": "et_a", "name": "A",
        "fields": [{"fieldKey": "old_f", "fieldLabel": "旧", "fieldType": "number"}],
    })
    tid = r.json()["data"]["id"]

    r = client.put(f"/admin/api/edge-types/{tid}", json={
        "fields": [
            {"fieldKey": "old_f", "fieldLabel": "旧", "fieldType": "number"},
            {"fieldKey": "new_f", "fieldLabel": "新", "fieldType": "number"},
        ],
    })
    assert r.status_code == 200, r.text

    keys = [f["fieldKey"] for f in client.get(f"/admin/api/edge-types/{tid}").json()["data"]["fields"]]
    assert keys == ["old_f", "new_f"]


def test_update_edge_sync_fields_update_only(client):
    r = client.post("/admin/api/edge-types", json={
        "code": "et_b", "name": "B",
        "fields": [
            {"fieldKey": "a", "fieldLabel": "Old A", "fieldType": "number"},
            {"fieldKey": "b", "fieldLabel": "Old B", "fieldType": "number"},
        ],
    })
    tid = r.json()["data"]["id"]

    r = client.put(f"/admin/api/edge-types/{tid}", json={
        "fields": [
            {"fieldKey": "b", "fieldLabel": "New B", "fieldType": "number"},
            {"fieldKey": "a", "fieldLabel": "New A", "fieldType": "number"},
        ],
    })
    assert r.status_code == 200

    fields = client.get(f"/admin/api/edge-types/{tid}").json()["data"]["fields"]
    assert [f["fieldKey"] for f in fields] == ["b", "a"]
    assert [f["fieldLabel"] for f in fields] == ["New B", "New A"]
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd backend && python -m pytest tests/test_edge_type_field_sync.py::test_create_edge_type_with_fields -xvs
```

预期：PASS for code path or fail because fields not handled. If POST doesn't reject extra fields, the test will fail on GET assertion.

- [ ] **Step 3: 实现 _sync_edge_type_fields helper + 修改 create/update**

在 `node_type.py` 的 `_sync_node_type_fields` 之后添加：

```python
def _sync_edge_type_fields(conn, edge_type_id: str, incoming: list) -> None:
    """整批同步 edge_type_fields（与 _sync_node_type_fields 对称）。"""
    seen_keys = set()
    for f in incoming:
        if f.field_key in seen_keys:
            raise HTTPException(
                status_code=400,
                detail={"code": 40306, "message": f"字段 Key 重复: {f.field_key}"},
            )
        seen_keys.add(f.field_key)

    existing_keys = {
        r["field_key"]
        for r in conn.execute(
            "SELECT field_key FROM edge_type_fields WHERE edge_type_id = ?",
            (edge_type_id,),
        ).fetchall()
    }

    incoming_keys = {f.field_key for f in incoming}
    to_delete = existing_keys - incoming_keys

    for k in to_delete:
        conn.execute(
            "DELETE FROM edge_type_fields WHERE edge_type_id = ? AND field_key = ?",
            (edge_type_id, k),
        )
        conn.execute(
            """DELETE FROM edge_attrs
               WHERE field_key = ?
                 AND edge_id IN (SELECT id FROM edges WHERE edge_type_id = ?)""",
            (k, edge_type_id),
        )

    for idx, f in enumerate(incoming):
        if f.field_key not in existing_keys:
            continue
        conn.execute(
            """UPDATE edge_type_fields
               SET field_label = ?, field_type = ?, max_length = ?,
                   default_value = ?, options = ?, required = ?, sort_order = ?
               WHERE edge_type_id = ? AND field_key = ?""",
            (f.field_label, f.field_type, f.max_length, f.default_value,
             f.options, int(f.required), idx,
             edge_type_id, f.field_key),
        )

    for idx, f in enumerate(incoming):
        if f.field_key in existing_keys:
            continue
        conn.execute(
            """INSERT INTO edge_type_fields
               (edge_type_id, field_key, field_label, field_type, max_length,
                default_value, options, required, sort_order)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (edge_type_id, f.field_key, f.field_label, f.field_type,
             f.max_length, f.default_value, f.options, int(f.required), idx),
        )
```

修改 `create_edge_type`（约第 745-763 行）末尾，在事务里加：

```python
        if data.fields is not None:
            _sync_edge_type_fields(conn, type_id, data.fields)
```

修改 `update_edge_type`（约第 766-782 行）：

```python
@router.put("/edge-types/{type_id}")
def update_edge_type(type_id: str, data: EdgeTypeUpdate) -> dict:
    raw = data.model_dump(exclude_unset=True)
    fields_payload = data.fields
    raw.pop("fields", None)

    with transaction() as conn:
        existing = conn.execute(
            "SELECT id FROM edge_types WHERE id = ?", (type_id,)
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail={"code": 40301, "message": "类型不存在"})

        if raw:
            set_clause = ", ".join(f"{k} = ?" for k in raw.keys())
            conn.execute(
                f"UPDATE edge_types SET {set_clause}, updated_at = datetime('now') WHERE id = ?",
                (*raw.values(), type_id),
            )

        if fields_payload is not None:
            _sync_edge_type_fields(conn, type_id, fields_payload)

    return {"code": 0, "data": {"id": type_id}, "message": "ok"}
```

`EdgeTypeFieldInput` import 加入 schema import 块。

- [ ] **Step 4: 跑测试确认前三用例通过**

```bash
cd backend && python -m pytest tests/test_edge_type_field_sync.py -xvs
```

- [ ] **Step 5: 添加 delete + orphan-cleanup + duplicate + omit 用例**

继续在 `test_edge_type_field_sync.py` 末尾追加：

```python
def test_update_edge_sync_fields_delete_cleans_orphan_attrs(client):
    """删边字段 + 该字段在 edge_attrs 有数据 → edge_attrs 孤儿清理。"""
    r = client.post("/admin/api/edge-types", json={
        "code": "et_link", "name": "L",
        "fields": [
            {"fieldKey": "bandwidth", "fieldLabel": "B", "fieldType": "text", "maxLength": 20},
            {"fieldKey": "vendor", "fieldLabel": "V", "fieldType": "text", "maxLength": 50},
        ],
    })
    tid = r.json()["data"]["id"]

    # 创建拓扑 + 2 节点 + 1 条边
    r = client.post("/admin/api/topologies", json={"name": "ET1"})
    topo_id = r.json()["data"]["id"]
    r = client.post("/admin/api/node-types", json={"code": "nt_e", "name": "N", "category": "physical"})
    ntype = r.json()["data"]["id"]
    n1 = client.post(f"/admin/api/topologies/{topo_id}/nodes", json={"nodeTypeId": ntype, "name": "n1"}).json()["data"]["id"]
    n2 = client.post(f"/admin/api/topologies/{topo_id}/nodes", json={"nodeTypeId": ntype, "name": "n2"}).json()["data"]["id"]
    r = client.post(f"/admin/api/topologies/{topo_id}/edges", json={
        "edgeTypeId": tid, "sourceId": n1, "targetId": n2,
    })
    eid = r.json()["data"]["id"]
    client.put(f"/admin/api/edges/{eid}/attrs", json={
        "attrs": {"bandwidth": "1G", "vendor": "huawei"},
    })

    # 删 vendor 字段
    r = client.put(f"/admin/api/edge-types/{tid}", json={
        "fields": [{"fieldKey": "bandwidth", "fieldLabel": "B", "fieldType": "text", "maxLength": 20}],
    })
    assert r.status_code == 200

    from app.db.connection import connect
    with connect() as c:
        rows = c.execute(
            "SELECT field_key FROM edge_attrs WHERE edge_id = ?", (eid,)
        ).fetchall()
    keys = sorted(r["field_key"] for r in rows)
    assert keys == ["bandwidth"]


def test_update_edge_sync_fields_duplicate_field_key_rejected(client):
    r = client.post("/admin/api/edge-types", json={"code": "et_dup", "name": "D", "fields": []})
    tid = r.json()["data"]["id"]
    r = client.put(f"/admin/api/edge-types/{tid}", json={
        "fields": [
            {"fieldKey": "same", "fieldLabel": "A", "fieldType": "number"},
            {"fieldKey": "same", "fieldLabel": "B", "fieldType": "number"},
        ],
    })
    assert r.status_code == 400


def test_update_edge_omit_fields_preserves_existing(client):
    r = client.post("/admin/api/edge-types", json={
        "code": "et_keep", "name": "K",
        "fields": [{"fieldKey": "x", "fieldLabel": "X", "fieldType": "number"}],
    })
    tid = r.json()["data"]["id"]
    r = client.put(f"/admin/api/edge-types/{tid}", json={"name": "K2"})
    assert r.status_code == 200
    fields = client.get(f"/admin/api/edge-types/{tid}").json()["data"]["fields"]
    assert [f["fieldKey"] for f in fields] == ["x"]
```

- [ ] **Step 6: 跑测试**

```bash
cd backend && python -m pytest tests/test_edge_type_field_sync.py -xvs
```

预期：全部 PASS。

- [ ] **Step 7: 写 delete-impact 测试**

```python
def test_edge_delete_impact_returns_affected_counts(client):
    r = client.post("/admin/api/edge-types", json={
        "code": "et_impact", "name": "I",
        "fields": [
            {"fieldKey": "bandwidth", "fieldLabel": "B", "fieldType": "text", "maxLength": 20},
        ],
    })
    tid = r.json()["data"]["id"]

    # 准备拓扑 + 节点 + 2 条边
    r = client.post("/admin/api/topologies", json={"name": "EI1"})
    topo_id = r.json()["data"]["id"]
    r = client.post("/admin/api/node-types", json={"code": "nt_ei", "name": "N", "category": "physical"})
    ntype = r.json()["data"]["id"]
    nodes = [
        client.post(f"/admin/api/topologies/{topo_id}/nodes", json={"nodeTypeId": ntype, "name": f"n{i}"}).json()["data"]["id"]
        for i in range(3)
    ]
    for i in range(2):
        rr = client.post(f"/admin/api/topologies/{topo_id}/edges", json={
            "edgeTypeId": tid, "sourceId": nodes[i], "targetId": nodes[i + 1],
        })
        eid = rr.json()["data"]["id"]
        client.put(f"/admin/api/edges/{eid}/attrs", json={"attrs": {"bandwidth": "1G"}})

    r = client.post(
        f"/admin/api/edge-types/{tid}/fields/delete-impact",
        json={"fieldKeys": ["bandwidth"]},
    )
    assert r.status_code == 200
    items = r.json()["data"]["items"]
    counts = {it["fieldKey"]: it["affectedNodeCount"] for it in items}
    assert counts == {"bandwidth": 2}  # 复用 affectedNodeCount 字段名


def test_edge_delete_impact_empty_for_unused_field(client):
    r = client.post("/admin/api/edge-types", json={
        "code": "et_unused", "name": "U",
        "fields": [{"fieldKey": "unused", "fieldLabel": "U", "fieldType": "number"}],
    })
    tid = r.json()["data"]["id"]
    r = client.post(
        f"/admin/api/edge-types/{tid}/fields/delete-impact",
        json={"fieldKeys": ["unused"]},
    )
    assert r.status_code == 200
    assert r.json()["data"]["items"] == [{"fieldKey": "unused", "affectedNodeCount": 0}]
```

- [ ] **Step 8: 跑测试，预期失败**

- [ ] **Step 9: 实现 edge_type 的 delete-impact 端点**

在 `delete_edge_type` 之后（搜索 `@router.delete("/edge-types/{type_id}")`）插入：

```python
@router.post("/edge-types/{type_id}/fields/delete-impact")
def get_edge_type_field_delete_impact(
    type_id: str, payload: FieldDeleteImpactRequest
) -> dict:
    """统计若删除 fieldKeys 中的字段，会影响多少同类型边的 edge_attrs。"""
    with connect() as conn:
        existing = conn.execute(
            "SELECT id FROM edge_types WHERE id = ?", (type_id,)
        ).fetchone()
        if not existing:
            raise HTTPException(
                status_code=404, detail={"code": 40301, "message": "类型不存在"}
            )
        items = []
        for k in payload.field_keys:
            count = conn.execute(
                """SELECT COUNT(*) AS cnt FROM edge_attrs a
                   JOIN edges e ON a.edge_id = e.id
                   WHERE e.edge_type_id = ? AND a.field_key = ?""",
                (type_id, k),
            ).fetchone()["cnt"]
            items.append(
                FieldDeleteImpactItem(field_key=k, affected_node_count=count)
            )
        resp = FieldDeleteImpactResponse(items=items)
    return {"code": 0, "data": resp.model_dump(mode="json", by_alias=True), "message": "ok"}
```

- [ ] **Step 10: 跑测试通过**

```bash
cd backend && python -m pytest tests/test_edge_type_field_sync.py -xvs
```

- [ ] **Step 11: 写"旧端点已移除"测试**

```python
def test_edge_legacy_single_field_endpoints_removed(client):
    r = client.post("/admin/api/edge-types", json={"code": "et_leg", "name": "L"})
    tid = r.json()["data"]["id"]

    r = client.post(f"/admin/api/edge-types/{tid}/fields", json={
        "fieldKey": "x", "fieldLabel": "X", "fieldType": "number",
    })
    assert r.status_code in (404, 405)

    r = client.put(f"/admin/api/edge-types/{tid}/fields/1", json={"fieldLabel": "Y"})
    assert r.status_code in (404, 405)

    r = client.delete(f"/admin/api/edge-types/{tid}/fields/1")
    assert r.status_code in (404, 405)
```

- [ ] **Step 12: 跑测试确认失败**

- [ ] **Step 13: 移除 edge_type 的 3 个旧单字段端点**

搜索文件中 `edge_type_fields` 装饰器（在 `node_type.py` 末尾，约第 850 行后）：
- `create_edge_type_field` （`@router.post("/edge-types/{type_id}/fields")`）
- `update_edge_type_field` （`@router.put("/edge-types/{type_id}/fields/{field_id}")`）
- `delete_edge_type_field` （`@router.delete("/edge-types/{type_id}/fields/{field_id}")`）

连同注释一起删除。

- [ ] **Step 14: 跑全部测试**

```bash
cd backend && python -m pytest tests/test_edge_type_field_sync.py -xvs
cd backend && python -m pytest -x
```

预期：全部 PASS。

- [ ] **Step 15: 提交**

```bash
cd backend && git add app/admin/node_type.py tests/test_edge_type_field_sync.py
cd .. && git commit -m "$(cat <<'EOF'
feat(edge-type): 字段编辑改为整批同步 + delete-impact 端点（镜像 node_type）

对称改造 Task 2 的 node_type 端点：
- POST/PUT /edge-types 支持 fields[] 整批同步
- _sync_edge_type_fields 按 field_key diff + 清理 edge_attrs 孤儿
- 新增 POST /edge-types/{id}/fields/delete-impact
- 移除 3 个旧单字段端点
EOF
)"
```

---

## Task 4: 前端 API 层 (types.ts)

**Files:**
- Modify: `frontend/src/api/types.ts`

更新 TypeScript 接口和 API 方法集，匹配后端整批同步形态。

- [ ] **Step 1: 加 FieldDeleteImpact 类型定义**

在 `types.ts` 文件顶部（约第 5 行 `NodeTypeFieldItem` 之前）插入：

```ts
// ============ 整批同步用字段输入（无 id） ============

export interface NodeTypeFieldInput {
  fieldKey: string
  fieldLabel: string
  fieldType: 'text' | 'number' | 'select' | 'boolean'
  maxLength?: number | null
  defaultValue?: string | null
  options?: string | null
  required?: boolean
  sortOrder?: number
}

export interface EdgeTypeFieldInput {
  fieldKey: string
  fieldLabel: string
  fieldType: 'text' | 'number' | 'select' | 'boolean'
  maxLength?: number | null
  defaultValue?: string | null
  options?: string | null
  required?: boolean
  sortOrder?: number
}

export interface FieldDeleteImpactItem {
  fieldKey: string
  affectedNodeCount: number  // 节点类型/边类型共用，边类型语义为"受影响的边数"
}

export interface FieldDeleteImpactResponse {
  items: FieldDeleteImpactItem[]
}
```

- [ ] **Step 2: 给 NodeTypeCreate / NodeTypeUpdate 加 fields**

修改 `NodeTypeCreate`（约第 40 行）末尾加：

```ts
  fields?: NodeTypeFieldInput[] | null
```

修改 `NodeTypeUpdate`（约第 52 行）末尾加：

```ts
  fields?: NodeTypeFieldInput[] | null
```

- [ ] **Step 3: 给 EdgeTypeCreate / EdgeTypeUpdate 加 fields**

同上，分别在 `EdgeTypeCreate`（约第 118 行）和 `EdgeTypeUpdate`（约第 131 行）末尾加：

```ts
  fields?: EdgeTypeFieldInput[] | null
```

- [ ] **Step 4: 从 nodeTypeApi 移除单字段方法 + 加 getFieldDeleteImpact**

修改 `nodeTypeApi` 对象（约第 190-242 行）：

**移除：** `createField`, `updateField`, `deleteField`（3 个方法）

**新增：**
```ts
  getFieldDeleteImpact: (typeId: string, fieldKeys: string[]): Promise<FieldDeleteImpactResponse> =>
    apiPost(`/node-types/${typeId}/fields/delete-impact`, { fieldKeys }),
```

- [ ] **Step 5: 从 edgeTypeApi 移除单字段方法 + 加 getFieldDeleteImpact**

修改 `edgeTypeApi` 对象（约第 244-274 行）：

**移除：** `createField`, `updateField`, `deleteField`

**新增：**
```ts
  getFieldDeleteImpact: (typeId: string, fieldKeys: string[]): Promise<FieldDeleteImpactResponse> =>
    apiPost(`/edge-types/${typeId}/fields/delete-impact`, { fieldKeys }),
```

- [ ] **Step 6: 删除已过时的 NodeTypeFieldCreate / NodeTypeFieldUpdate / EdgeTypeFieldCreate / EdgeTypeFieldUpdate 接口**

它们仅被旧单字段 API 使用，整批同步用 `NodeTypeFieldInput` 替代。直接删除这 4 个接口定义（约第 62-81 行和第 143-162 行）。

如果还有别处 import 它们（grep 确认），删除对应 import。下游 Task 5 的 useTypes.ts 会同步清理。

- [ ] **Step 7: 验证 TypeScript 编译**

```bash
cd frontend && npx tsc --noEmit
```

预期：可能有 error，因为 `useTypes.ts` / `NodeTypeFieldEditor.vue` 等还在引用被删除的类型 — 这些会在 Task 5+ 修复。**临时把那些下游文件的 import 注释掉以验证 types.ts 本身正确**，验证后恢复。

- [ ] **Step 8: 提交**

```bash
git add frontend/src/api/types.ts
git commit -m "$(cat <<'EOF'
feat(types-api): 类型 API 层切换到整批同步

- 新增 NodeTypeFieldInput / EdgeTypeFieldInput（无 id）
- 新增 FieldDeleteImpactItem / FieldDeleteImpactResponse
- NodeTypeCreate/Update + EdgeTypeCreate/Update 加 fields?: ...[]
- 新增 getFieldDeleteImpact() 到 nodeTypeApi / edgeTypeApi
- 移除 createField/updateField/deleteField 旧方法
- 移除 NodeTypeFieldCreate/Update + EdgeTypeFieldCreate/Update 接口
EOF
)"
```

注：此提交可能会让 useTypes.ts 等下游文件暂时编译失败 — 紧接着 Task 5 会修复。

---

## Task 5: 前端 useTypes.ts 清理

**Files:**
- Modify: `frontend/src/composables/useTypes.ts`

删除 6 个字段级方法（createNodeTypeField/updateNodeTypeField/deleteNodeTypeField + edge 3 个）和它们对应的 import / return。

- [ ] **Step 1: 删除 import 中的 4 个已废类型**

修改文件顶部 import（约第 3-14 行），删除：
- `NodeTypeFieldCreate`
- `NodeTypeFieldUpdate`
- `EdgeTypeFieldCreate`
- `EdgeTypeFieldUpdate`

- [ ] **Step 2: 从 useNodeTypes 删除 3 个方法**

删除：
- `createNodeTypeField` 函数（约第 60-64 行）
- `updateNodeTypeField` 函数（约第 66-70 行）
- `deleteNodeTypeField` 函数（约第 72-76 行）

从 return 对象（约第 87-100 行）删除：
- `createNodeTypeField`
- `updateNodeTypeField`
- `deleteNodeTypeField`

- [ ] **Step 3: 从 useEdgeTypes 删除 3 个方法**

删除：
- `createEdgeTypeField`（约第 147-151 行）
- `updateEdgeTypeField`（约第 153-157 行）
- `deleteEdgeTypeField`（约第 159-163 行）

从 return（约第 165-177 行）删除三者。

- [ ] **Step 4: 验证 TypeScript（仍可能因 vue 组件而失败，但 useTypes.ts 本身应通过）**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep useTypes.ts
```

预期：useTypes.ts 无错误。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/composables/useTypes.ts
git commit -m "$(cat <<'EOF'
refactor(useTypes): 移除 6 个单字段方法

字段编辑改走整批同步：父表单提交时一并传 fields[]，
不再需要 createField/updateField/deleteField 三组对（节点+边）。
EOF
)"
```

---

## Task 6: 重写 NodeTypeFieldEditor.vue（紧凑表格 + 受控）

**Files:**
- Modify: `frontend/src/components/types/NodeTypeFieldEditor.vue`（完全重写）

参考 `frontend/src/components/alarmSchemas/AlarmSchemaFieldEditor.vue` 结构，去 Mapping 列。

- [ ] **Step 1: 完全重写文件内容**

把 `NodeTypeFieldEditor.vue` 内容整体替换为：

```vue
<script setup lang="ts">
import { computed } from 'vue'
import {
  Table, Input, InputNumber, Select, Switch, Button, Tooltip, Affix,
} from 'ant-design-vue'
import {
  PlusOutlined, DeleteOutlined, ArrowUpOutlined, ArrowDownOutlined,
} from '@ant-design/icons-vue'
import type { NodeTypeFieldInput } from '@/api/types'

const props = defineProps<{
  fields: NodeTypeFieldInput[]
}>()

const emit = defineEmits<{
  (e: 'update:fields', v: NodeTypeFieldInput[]): void
}>()

const localFields = computed({
  get: () => props.fields,
  set: (v) => emit('update:fields', v),
})

function addField() {
  const newField: NodeTypeFieldInput = {
    fieldKey: '',
    fieldLabel: '',
    fieldType: 'text',
    maxLength: 50,
    defaultValue: undefined,
    options: undefined,
    required: false,
    sortOrder: localFields.value.length,
  }
  emit('update:fields', [...localFields.value, newField])
}

function removeField(index: number) {
  emit('update:fields', localFields.value.filter((_, i) => i !== index))
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

function updateField(index: number, key: keyof NodeTypeFieldInput, value: any) {
  const next = [...localFields.value]
  next[index] = { ...next[index], [key]: value }
  emit('update:fields', next)
}

// 已存在字段的 fieldKey 不可改 — 通过判断"原始 fields 是否包含此 key"
// 由父组件追踪；这里简化为：所有非空 fieldKey 都 disabled
function isFieldKeyLocked(field: NodeTypeFieldInput, originalIndex: number): boolean {
  // 简化规则：新行（空 fieldKey）可编辑；已填的不能改
  // 实际由 Modal 在 originalFields 中记录"哪些 key 已落库"，但 prop 受控模式下也可仅靠"非空"判断
  return !!field.fieldKey && field.fieldKey.length > 0
}

const columns = [
  { title: 'Key', dataIndex: 'fieldKey', key: 'fieldKey', width: 120 },
  { title: 'Label', dataIndex: 'fieldLabel', key: 'fieldLabel', width: 140 },
  { title: 'Type', dataIndex: 'fieldType', key: 'fieldType', width: 100 },
  { title: 'MaxLen', dataIndex: 'maxLength', key: 'maxLength', width: 80 },
  { title: 'Default', dataIndex: 'defaultValue', key: 'defaultValue', width: 100 },
  { title: 'Options', dataIndex: 'options', key: 'options', width: 120 },
  { title: 'Required', dataIndex: 'required', key: 'required', width: 70 },
  { title: '操作', key: 'actions', width: 100, fixed: 'right' as const },
]
</script>

<template>
  <div class="node-type-field-editor">
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
      :row-key="(_record: NodeTypeFieldInput, index?: number) => `row-${index}`"
      size="small"
      :scroll="{ x: 900 }"
    >
      <template #bodyCell="{ column, index, record }">
        <template v-if="column.key === 'fieldKey'">
          <Input
            :value="record.fieldKey"
            size="small"
            placeholder="key"
            :disabled="isFieldKeyLocked(record, index)"
            @update:value="(v: string) => updateField(index, 'fieldKey', v)"
          />
        </template>
        <template v-else-if="column.key === 'fieldLabel'">
          <Input
            :value="record.fieldLabel"
            size="small"
            placeholder="标签"
            @update:value="(v: string) => updateField(index, 'fieldLabel', v)"
          />
        </template>
        <template v-else-if="column.key === 'fieldType'">
          <Select
            :value="record.fieldType"
            size="small"
            style="width: 100%"
            @change="(v: any) => updateField(index, 'fieldType', v)"
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
            @change="(v: any) => updateField(index, 'maxLength', v)"
          />
        </template>
        <template v-else-if="column.key === 'defaultValue'">
          <Input
            :value="record.defaultValue || ''"
            size="small"
            placeholder="默认值"
            @update:value="(v: string) => updateField(index, 'defaultValue', v || null)"
          />
        </template>
        <template v-else-if="column.key === 'options'">
          <Tooltip :title="record.options">
            <Input
              :value="record.options || ''"
              size="small"
              placeholder="opt1,opt2"
              :disabled="record.fieldType !== 'select'"
              @update:value="(v: string) => updateField(index, 'options', v || null)"
            />
          </Tooltip>
        </template>
        <template v-else-if="column.key === 'required'">
          <Switch
            :checked="!!record.required"
            size="small"
            @change="(v: any) => updateField(index, 'required', v)"
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
.node-type-field-editor { display: flex; flex-direction: column; }
.toolbar { display: flex; align-items: center; gap: 12px; padding: 8px 0; background: #fff; z-index: 10; }
.toolbar-top { border-bottom: 1px solid #f0f0f0; }
.toolbar-bottom { border-top: 1px solid #f0f0f0; margin-top: 8px; }
.hint { color: #999; font-size: 12px; }
.action-buttons { display: flex; gap: 2px; }
</style>
```

- [ ] **Step 2: 验证 TypeScript**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep NodeTypeFieldEditor
```

预期：无错误。

- [ ] **Step 3: 提交**

```bash
git add frontend/src/components/types/NodeTypeFieldEditor.vue
git commit -m "$(cat <<'EOF'
refactor(NodeTypeFieldEditor): 重写为受控紧凑表格

- 行内编辑（Input/Select/Switch/InputNumber 嵌在表格单元格里）
- Affix 粘顶 + 底部"新增字段"按钮
- ↑↓ 按钮排序（移除 sort_order 数字输入）
- field_key 已填则禁止编辑（不可变约束）
- v-model:fields 受控模式，与告警模板编辑器一致
EOF
)"
```

---

## Task 7: 重写 EdgeTypeFieldEditor.vue

**Files:**
- Modify: `frontend/src/components/types/EdgeTypeFieldEditor.vue`（完全重写）

镜像 Task 6 的 NodeTypeFieldEditor.vue，把 `NodeTypeFieldInput` 换成 `EdgeTypeFieldInput`、类名换成 `edge-type-field-editor`。

- [ ] **Step 1: 完全重写文件**

复制 Task 6 的最终内容，做以下替换：
- `import type { NodeTypeFieldInput }` → `import type { EdgeTypeFieldInput }`
- 所有 `NodeTypeFieldInput` → `EdgeTypeFieldInput`
- `class="node-type-field-editor"` → `class="edge-type-field-editor"`
- 样式块 `.node-type-field-editor` → `.edge-type-field-editor`

其余代码完全一致。

- [ ] **Step 2: 验证 TypeScript**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep EdgeTypeFieldEditor
```

- [ ] **Step 3: 提交**

```bash
git add frontend/src/components/types/EdgeTypeFieldEditor.vue
git commit -m "$(cat <<'EOF'
refactor(EdgeTypeFieldEditor): 重写为受控紧凑表格（镜像 NodeTypeFieldEditor）
EOF
)"
```

---

## Task 8: 重写 NodeTypeModal.vue（内嵌字段编辑器 + delete-impact 流程）

**Files:**
- Modify: `frontend/src/components/types/NodeTypeModal.vue`

- [ ] **Step 1: 完全重写**

```vue
<script setup lang="ts">
import { ref, computed, watch, h } from 'vue'
import { Modal } from 'ant-design-vue'
import NodeTypeFieldEditor from './NodeTypeFieldEditor.vue'
import { nodeTypeApi } from '@/api/types'
import type {
  NodeTypeCreate, NodeTypeUpdate, NodeTypeDetail, NodeTypeFieldInput,
} from '@/api/types'

const CATEGORIES = ['physical', 'virtual', 'cloud', 'application']
const RENDER_MODES = [
  { value: 'none', label: '无' },
  { value: 'flat', label: '扁平' },
]
const SHAPES = [
  { value: 'rect', label: '矩形' },
  { value: 'circle', label: '圆形' },
  { value: 'ellipse', label: '椭圆' },
  { value: 'polygon', label: '多边形' },
]

interface NodeTypeForm {
  code: string
  name: string
  category: string
  icon: string
  color: string
  shape: string
  renderMode: string
  dnTemplate: string
  description: string
  fields: NodeTypeFieldInput[]
}

const props = defineProps<{
  open: boolean
  editing?: NodeTypeDetail | null
  loading?: boolean
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
  create: [data: NodeTypeCreate]
  update: [id: string, data: NodeTypeUpdate]
}>()

const isEdit = computed(() => !!props.editing)

const defaultForm = (): NodeTypeForm => ({
  code: '',
  name: '',
  category: 'physical',
  icon: '',
  color: '',
  shape: '',
  renderMode: 'none',
  dnTemplate: '',
  description: '',
  fields: [],
})

const form = ref<NodeTypeForm>(defaultForm())
const originalFieldKeys = ref<Set<string>>(new Set())

watch(() => props.open, (open) => {
  if (!open) return
  if (props.editing) {
    form.value = {
      code: props.editing.code,
      name: props.editing.name,
      category: props.editing.category,
      icon: props.editing.icon ?? '',
      color: props.editing.color ?? '',
      shape: props.editing.shape ?? '',
      renderMode: props.editing.renderMode,
      dnTemplate: props.editing.dnTemplate ?? '',
      description: props.editing.description ?? '',
      fields: (props.editing.fields ?? []).map(f => ({
        fieldKey: f.fieldKey,
        fieldLabel: f.fieldLabel,
        fieldType: f.fieldType,
        maxLength: f.maxLength,
        defaultValue: f.defaultValue,
        options: f.options,
        required: f.required,
        sortOrder: f.sortOrder,
      })),
    }
    originalFieldKeys.value = new Set(form.value.fields.map(f => f.fieldKey))
  } else {
    form.value = defaultForm()
    originalFieldKeys.value = new Set()
  }
})

function close() {
  emit('update:open', false)
}

function buildImpactContent(items: Array<{ fieldKey: string; affectedNodeCount: number }>) {
  return h('div', { style: { lineHeight: '1.8' } }, [
    h('div', { style: { marginBottom: '8px' } }, '以下字段将被删除，相关节点的属性值会被清除：'),
    ...items.map(it =>
      h('div', { style: { paddingLeft: '12px', color: '#fa541c' } },
        `• ${it.fieldKey}：清除 ${it.affectedNodeCount} 个节点的数据`),
    ),
    h('div', { style: { marginTop: '8px', color: '#999' } }, '此操作不可撤销，确定继续？'),
  ])
}

async function confirmDeleteImpactIfAny(): Promise<boolean> {
  if (!props.editing) return true
  const currentKeys = new Set(form.value.fields.map(f => f.fieldKey))
  const deletedKeys = [...originalFieldKeys.value].filter(k => !currentKeys.has(k))
  if (deletedKeys.length === 0) return true

  try {
    const resp = await nodeTypeApi.getFieldDeleteImpact(props.editing.id, deletedKeys)
    const nonEmpty = resp.items.filter(it => it.affectedNodeCount > 0)
    if (nonEmpty.length === 0) return true

    return await new Promise<boolean>((resolve) => {
      Modal.confirm({
        title: '确认删除字段',
        content: buildImpactContent(nonEmpty),
        okText: '确认删除',
        cancelText: '取消',
        okType: 'danger',
        width: 480,
        onOk: () => resolve(true),
        onCancel: () => resolve(false),
      })
    })
  } catch {
    return false
  }
}

async function submit() {
  const ok = await confirmDeleteImpactIfAny()
  if (!ok) return

  if (isEdit.value && props.editing) {
    emit('update', props.editing.id, {
      name: form.value.name,
      icon: form.value.icon || null,
      color: form.value.color || null,
      shape: form.value.shape || null,
      renderMode: form.value.renderMode,
      dnTemplate: form.value.dnTemplate || null,
      description: form.value.description || null,
      fields: form.value.fields,
    })
  } else {
    emit('create', {
      code: form.value.code,
      name: form.value.name,
      category: form.value.category,
      icon: form.value.icon || null,
      color: form.value.color || null,
      shape: form.value.shape || null,
      renderMode: form.value.renderMode,
      dnTemplate: form.value.dnTemplate || null,
      description: form.value.description || null,
      fields: form.value.fields,
    })
  }
}
</script>

<template>
  <a-modal
    :open="open"
    :title="isEdit ? '编辑节点类型' : '新建节点类型'"
    :confirm-loading="loading"
    @ok="submit"
    @cancel="close"
    ok-text="确定"
    cancel-text="取消"
    width="880px"
    :styles="{ body: { maxHeight: 'calc(100vh - 200px)', overflowY: 'auto' } }"
  >
    <a-form layout="vertical">
      <a-row :gutter="16">
        <a-col :span="12">
          <a-form-item label="类型代码" required>
            <a-input
              v-model:value="form.code"
              placeholder="如: switch"
              :disabled="isEdit"
            />
          </a-form-item>
        </a-col>
        <a-col :span="12">
          <a-form-item label="类型名称" required>
            <a-input v-model:value="form.name" placeholder="如: 交换机" />
          </a-form-item>
        </a-col>
      </a-row>

      <a-row :gutter="16">
        <a-col :span="12">
          <a-form-item label="分类">
            <a-select v-model:value="form.category">
              <a-select-option v-for="cat in CATEGORIES" :key="cat" :value="cat">
                {{ cat }}
              </a-select-option>
            </a-select>
          </a-form-item>
        </a-col>
        <a-col :span="12">
          <a-form-item label="渲染模式">
            <a-select v-model:value="form.renderMode">
              <a-select-option v-for="m in RENDER_MODES" :key="m.value" :value="m.value">
                {{ m.label }}
              </a-select-option>
            </a-select>
          </a-form-item>
        </a-col>
      </a-row>

      <a-row :gutter="16">
        <a-col :span="12">
          <a-form-item label="图标">
            <a-input v-model:value="form.icon" placeholder="可选" />
          </a-form-item>
        </a-col>
        <a-col :span="12">
          <a-form-item label="颜色">
            <a-input v-model:value="form.color" placeholder="如: #1890ff" />
          </a-form-item>
        </a-col>
      </a-row>

      <a-row :gutter="16">
        <a-col :span="12">
          <a-form-item label="形状">
            <a-select v-model:value="form.shape" allowClear placeholder="可选">
              <a-select-option v-for="s in SHAPES" :key="s.value" :value="s.value">
                {{ s.label }}
              </a-select-option>
            </a-select>
          </a-form-item>
        </a-col>
        <a-col :span="12">
          <a-form-item label="DN 模板">
            <a-input v-model:value="form.dnTemplate" placeholder="可选，如: /dev/{{ '{{name}}' }}" />
          </a-form-item>
        </a-col>
      </a-row>

      <a-form-item label="描述">
        <a-textarea v-model:value="form.description" :rows="2" placeholder="可选" />
      </a-form-item>
    </a-form>

    <a-divider style="margin: 16px 0">字段配置</a-divider>

    <NodeTypeFieldEditor v-model:fields="form.fields" />
  </a-modal>
</template>
```

- [ ] **Step 2: 验证 TypeScript + 视觉**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep NodeTypeModal
```

启动前端 + 后端，打开类型管理页 → 新建节点类型 → 验证：
- Modal 宽度 880px
- 字段编辑器显示在基础信息下方
- 加字段、改字段、排序、删字段都在 Modal 内完成

- [ ] **Step 3: 提交**

```bash
git add frontend/src/components/types/NodeTypeModal.vue
git commit -m "$(cat <<'EOF'
refactor(NodeTypeModal): 内嵌 FieldEditor + delete-impact 弹窗确认

- Modal 宽度 560 → 880px，max-height 限制 + 字段区独立滚动
- 内嵌 NodeTypeFieldEditor（受控 v-model:fields）
- 提交前若有字段被删 → 调 delete-impact 端点 → 弹窗显示影响节点数 → 用户确认
- 同 POST/PUT 一并提交 fields[]，不再走单字段 API
EOF
)"
```

---

## Task 9: 重写 EdgeTypeModal.vue（镜像 NodeTypeModal）

**Files:**
- Modify: `frontend/src/components/types/EdgeTypeModal.vue`

- [ ] **Step 1: 读取现有 EdgeTypeModal.vue 了解基础字段**

```bash
```

读 `frontend/src/components/types/EdgeTypeModal.vue`，记下它的基础字段（code/name/semantic/directed/...）。

- [ ] **Step 2: 重写 EdgeTypeModal.vue**

基础结构同 Task 8，区别：
- `import EdgeTypeFieldEditor`
- 类型导入 `EdgeTypeCreate / EdgeTypeUpdate / EdgeTypeDetail / EdgeTypeFieldInput`
- 用 `edgeTypeApi.getFieldDeleteImpact`
- 基础信息表单字段按 EdgeTypeCreate 字段（`code`, `name`, `semantic`, `directed`, `exclusiveTarget`, `allowSourceTypeCodes`, `allowTargetTypeCodes`, `lineStyle`, `color`, `description`）
- delete-impact 弹窗文案：把"节点"改为"边"

主要逻辑代码（script setup）几乎完全一致，只需把：
- `NodeTypeCreate` → `EdgeTypeCreate`
- `NodeTypeUpdate` → `EdgeTypeUpdate`
- `NodeTypeDetail` → `EdgeTypeDetail`
- `NodeTypeFieldInput` → `EdgeTypeFieldInput`
- `nodeTypeApi` → `edgeTypeApi`
- 弹窗内"节点"→"边"，"affectedNodeCount" 字段名不变（后端约定）

template 部分按 EdgeType 现有基础字段重组：

```vue
    <a-form layout="vertical">
      <a-row :gutter="16">
        <a-col :span="12">
          <a-form-item label="类型代码" required>
            <a-input v-model:value="form.code" placeholder="如: link" :disabled="isEdit" />
          </a-form-item>
        </a-col>
        <a-col :span="12">
          <a-form-item label="类型名称" required>
            <a-input v-model:value="form.name" placeholder="如: 链路" />
          </a-form-item>
        </a-col>
      </a-row>

      <a-row :gutter="16">
        <a-col :span="12">
          <a-form-item label="语义">
            <a-select v-model:value="form.semantic">
              <a-select-option value="connect">connect</a-select-option>
              <a-select-option value="contain">contain</a-select-option>
            </a-select>
          </a-form-item>
        </a-col>
        <a-col :span="12">
          <a-form-item label="线条样式">
            <a-input v-model:value="form.lineStyle" placeholder="可选" />
          </a-form-item>
        </a-col>
      </a-row>

      <a-row :gutter="16">
        <a-col :span="12">
          <a-form-item label="颜色">
            <a-input v-model:value="form.color" placeholder="如: #1890ff" />
          </a-form-item>
        </a-col>
        <a-col :span="12">
          <a-form-item label="选项">
            <a-space>
              <a-switch v-model:checked="form.directed" /> <span style="font-size: 12px">有向</span>
              <a-switch v-model:checked="form.exclusiveTarget" /> <span style="font-size: 12px">唯一目标</span>
            </a-space>
          </a-form-item>
        </a-col>
      </a-row>

      <a-form-item label="允许的源类型代码">
        <a-input v-model:value="form.allowSourceTypeCodes" placeholder="可选，多个用逗号分隔" />
      </a-form-item>

      <a-form-item label="允许的目标类型代码">
        <a-input v-model:value="form.allowTargetTypeCodes" placeholder="可选，多个用逗号分隔" />
      </a-form-item>

      <a-form-item label="描述">
        <a-textarea v-model:value="form.description" :rows="2" placeholder="可选" />
      </a-form-item>
    </a-form>

    <a-divider style="margin: 16px 0">字段配置</a-divider>

    <EdgeTypeFieldEditor v-model:fields="form.fields" />
```

弹窗文案：

```ts
  return h('div', { style: { lineHeight: '1.8' } }, [
    h('div', { style: { marginBottom: '8px' } }, '以下字段将被删除，相关边的属性值会被清除：'),
    ...items.map(it =>
      h('div', { style: { paddingLeft: '12px', color: '#fa541c' } },
        `• ${it.fieldKey}：清除 ${it.affectedNodeCount} 条边的数据`),
    ),
    h('div', { style: { marginTop: '8px', color: '#999' } }, '此操作不可撤销，确定继续？'),
  ])
```

- [ ] **Step 3: 验证 + 提交**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep EdgeTypeModal
git add frontend/src/components/types/EdgeTypeModal.vue
git commit -m "$(cat <<'EOF'
refactor(EdgeTypeModal): 内嵌 FieldEditor + delete-impact 弹窗（镜像 NodeTypeModal）
EOF
)"
```

---

## Task 10: 清理 NodeTypeTable.vue（删除展开行）

**Files:**
- Modify: `frontend/src/components/types/NodeTypeTable.vue`

- [ ] **Step 1: 删除展开行相关 import**

修改顶部 import（约第 11 行）：

**移除：** `NodeTypeFieldCreate, NodeTypeFieldUpdate`

不需要保留它们，因为 FieldEditor 调用已删除。

- [ ] **Step 2: 删除字段相关 handler 函数**

删除以下 4 个函数（约第 71-90 行）：
- `handleCreateField`
- `handleUpdateField`
- `handleDeleteField`

并从 useNodeTypes 解构里删除 `createNodeTypeField/updateNodeTypeField/deleteNodeTypeField`（约第 21-23 行）。

- [ ] **Step 3: 删除 expandedRowKeys 状态**

删除（约第 93 行）：
```ts
const expandedRowKeys = ref<string[]>([])
```

- [ ] **Step 4: 删除 a-table 上的 expand 相关 props**

修改 `<a-table>` 元素，删除：
- `:expandedRowKeys="expandedRowKeys"`
- `@expand="(expanded: boolean, record: NodeTypeDetail) => ..."`

- [ ] **Step 5: 删除 expandedRowRender template slot**

删除 `<template #expandedRowRender="{ record }">...</template>` 整段（约第 423-431 行）。

- [ ] **Step 6: 验证 + smoke**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep NodeTypeTable
```

打开类型管理 → 节点类型 Tab → 确认：
- 表格行尾没有展开图标
- "字段数"列仍显示数字
- 点编辑按钮打开 Modal，字段在 Modal 内编辑

- [ ] **Step 7: 提交**

```bash
git add frontend/src/components/types/NodeTypeTable.vue
git commit -m "$(cat <<'EOF'
refactor(NodeTypeTable): 移除展开行（字段编辑搬进 Modal）
EOF
)"
```

---

## Task 11: 清理 EdgeTypeTable.vue（删除展开行）

**Files:**
- Modify: `frontend/src/components/types/EdgeTypeTable.vue`

镜像 Task 10。

- [ ] **Step 1: 删除 import 中的 EdgeTypeFieldCreate/Update**

- [ ] **Step 2: 删除 handleCreateField / handleUpdateField / handleDeleteField 函数**

- [ ] **Step 3: 删除 useEdgeTypes 解构里的 createEdgeTypeField/updateEdgeTypeField/deleteEdgeTypeField**

- [ ] **Step 4: 删除 expandedRowKeys ref + a-table 上的 expand props + expandedRowRender template**

- [ ] **Step 5: 验证 + 提交**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep EdgeTypeTable
git add frontend/src/components/types/EdgeTypeTable.vue
git commit -m "refactor(EdgeTypeTable): 移除展开行（镜像 NodeTypeTable）"
```

---

## Task 12: 画布 NodeAttrsModal.vue 改为 720px + 双列网格

**Files:**
- Modify: `frontend/src/components/canvas/NodeAttrsModal.vue`

- [ ] **Step 1: 修改 Modal 宽度**

找到 `<Modal>` 元素（约第 129 行），加 `:width="720"`：

```vue
  <Modal
    :open="visible"
    title="创建节点"
    :width="720"
    :confirm-loading="creating"
    @cancel="emit('close')"
    @ok="handleCreate"
    ok-text="创建"
    :styles="{ body: { maxHeight: 'calc(100vh - 200px)', overflowY: 'auto' } }"
  >
```

- [ ] **Step 2: 字段区改双列网格**

修改 template 内的字段循环（约第 155-198 行），把 `<Form.Item v-for="field in fields" ...>` 包到 `<a-row :gutter="16">` 里，每个 `<Form.Item>` 包到 `<a-col :xs="24" :md="12">`：

```vue
      <Form layout="vertical" class="attrs-form">
        <Form.Item
          label="节点名称"
          required
          :validate-status="nodeNameError ? 'error' : ''"
          :help="nodeNameError"
        >
          <Input
            v-model:value="nodeName"
            placeholder="请输入节点名称，如 core-switch-01"
            @focus="onNameFocus"
          />
        </Form.Item>

        <a-row :gutter="16">
          <a-col
            v-for="field in fields"
            :key="field.id"
            :xs="24"
            :md="12"
          >
            <Form.Item
              :label="field.fieldLabel"
              :required="field.required"
              :validate-status="fieldErrors[field.fieldKey] ? 'error' : ''"
              :help="fieldErrors[field.fieldKey]"
            >
              <template v-if="field.fieldType === 'text'">
                <Input
                  :value="getFieldValue(field.fieldKey)"
                  @input="(e: any) => setFieldValue(field.fieldKey, e.target.value)"
                  :maxlength="field.maxLength || undefined"
                  :showCount="!!field.maxLength"
                />
              </template>
              <template v-else-if="field.fieldType === 'number'">
                <InputNumber
                  :value="Number(getFieldValue(field.fieldKey))"
                  @change="(v: any) => setFieldValue(field.fieldKey, String(v ?? ''))"
                  style="width: 100%"
                />
              </template>
              <template v-else-if="field.fieldType === 'select'">
                <Select
                  :value="getFieldValue(field.fieldKey)"
                  @change="(v: any) => setFieldValue(field.fieldKey, String(v))"
                >
                  <Select.Option
                    v-for="opt in (field.options || '').split(',')"
                    :key="opt.trim()"
                    :value="opt.trim()"
                  >
                    {{ opt.trim() }}
                  </Select.Option>
                </Select>
              </template>
              <template v-else-if="field.fieldType === 'boolean'">
                <Switch
                  :checked="getFieldValue(field.fieldKey) === 'true'"
                  @change="(v: any) => setFieldValue(field.fieldKey, String(v))"
                />
              </template>
            </Form.Item>
          </a-col>
        </a-row>
      </Form>
```

- [ ] **Step 3: 紧凑间距 CSS**

修改 `<style scoped>` 部分，加上：

```css
.attrs-form :deep(.ant-form-item) {
  margin-bottom: 16px;
}
```

- [ ] **Step 4: smoke 测试**

启动前后端，画布 → 拖一个有 6+ 字段的节点类型 → 验证：
- Modal 宽度 720px
- 字段两列摆放
- 节点名称单行不进双列
- 改字段后 scroll-to-error 仍生效
- 窗口缩到 < 768 时降级单列

- [ ] **Step 5: 提交**

```bash
git add frontend/src/components/canvas/NodeAttrsModal.vue
git commit -m "$(cat <<'EOF'
feat(canvas): NodeAttrsModal 紧凑化（720px + 双列网格 + 紧凑间距）

- Modal 宽度 520 → 720px
- 字段区改 Antd Row+Col 双列网格（xs:24 md:12 响应式降级）
- 节点名称仍单行突出
- Form.Item margin-bottom 24 → 16px
EOF
)"
```

---

## Task 13: 画布 NodeAttrsPanel.vue 改为 380px + 水平 label

**Files:**
- Modify: `frontend/src/components/canvas/NodeAttrsPanel.vue`

- [ ] **Step 1: 修改面板宽度 CSS**

找到 `.node-attrs-panel` 样式（约第 236 行），把 `width: 320px;` 改为 `width: 380px;`。

- [ ] **Step 2: 字段 Form 改 horizontal layout**

找到字段循环外的 `<Form layout="vertical" class="attrs-form">`（约第 166 行），改为：

```vue
<Form
  layout="horizontal"
  class="attrs-form"
  :label-col="{ flex: '100px' }"
  :wrapper-col="{ flex: 'auto' }"
>
```

- [ ] **Step 3: Form.Item label 加 tooltip + 截断**

把字段 Form.Item 的 label 改为模板形式以支持 Tooltip：

```vue
                <Form.Item
                  v-for="field in fields"
                  :key="field.id"
                >
                  <template #label>
                    <Tooltip :title="field.fieldLabel" placement="left">
                      <span class="attr-label-text">{{ field.fieldLabel }}</span>
                    </Tooltip>
                  </template>
                  <!-- ... 控件不变 ... -->
                </Form.Item>
```

import Tooltip：

```ts
import { Form, Input, InputNumber, Select, Switch, Button, Spin, Tabs, Tooltip } from 'ant-design-vue'
```

- [ ] **Step 4: 紧凑间距 + label 截断 CSS**

修改 `<style scoped>`：

```css
.node-attrs-panel {
  width: 380px;  /* 已在 Step 1 改 */
  /* ... 其余不变 */
}

.attrs-form :deep(.ant-form-item) {
  margin-bottom: 12px;
}

.attr-label-text {
  display: inline-block;
  max-width: 100px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  vertical-align: bottom;
}
```

- [ ] **Step 5: smoke 测试**

启动前后端，画布 → 双击节点打开抽屉 → 验证：
- 抽屉宽度 380px
- 字段 label 在左、input 在右
- 长 label（如手动加一个 fieldLabel="非常长的标签文字"）出现 ellipsis + 悬停 tooltip
- 告警 Tab 切换不受影响
- 底部"删除/保存"按钮位置不变

- [ ] **Step 6: 提交**

```bash
git add frontend/src/components/canvas/NodeAttrsPanel.vue
git commit -m "$(cat <<'EOF'
feat(canvas): NodeAttrsPanel 紧凑化（380px + 水平 label + tooltip）

- 抽屉宽度 320 → 380px
- 字段 Form layout: vertical → horizontal（label-col 100px）
- Form.Item margin-bottom 24 → 12px
- 长 label 截断 + Tooltip 显示完整文本
- 节点名称行保持原"label 上、input 下"独立块（关键信息突出）
- 告警 Tab 完全不动
EOF
)"
```

---

## Task 14: 画布 EdgeAttrsPanel.vue 镜像改造

**Files:**
- Modify: `frontend/src/components/canvas/EdgeAttrsPanel.vue`

- [ ] **Step 1: 读取现有 EdgeAttrsPanel 了解结构**

读 `frontend/src/components/canvas/EdgeAttrsPanel.vue`，对照 `NodeAttrsPanel.vue` 找出对应字段循环段。

- [ ] **Step 2: 应用与 Task 13 相同的修改**

- 面板 `.edge-attrs-panel` width: 320px → 380px
- Form layout="vertical" → layout="horizontal" + label-col flex:100px + wrapper-col flex:auto
- 字段 Form.Item label 改用 template + Tooltip 截断
- import Tooltip
- 紧凑间距 CSS + label 截断 CSS

如果 EdgeAttrsPanel 没有 Tab 结构（只是属性面板），更简单。

- [ ] **Step 3: smoke 测试**

启动前后端，画布 → 双击边打开抽屉 → 验证视觉与节点抽屉一致。

- [ ] **Step 4: 提交**

```bash
git add frontend/src/components/canvas/EdgeAttrsPanel.vue
git commit -m "$(cat <<'EOF'
feat(canvas): EdgeAttrsPanel 紧凑化（380px + 水平 label + tooltip）

镜像 NodeAttrsPanel 改造，保持视觉一致。
EOF
)"
```

---

## 完成检查清单

- [ ] 后端测试：`cd backend && python -m pytest -x` 全过
- [ ] 前端 TS 编译：`cd frontend && npx tsc --noEmit` 无错误
- [ ] 前端 smoke 测试（spec §6.2 + §11.6 共 17 步）：
  - 1-10 类型管理页面（节点类型 + 边类型 + 告警模板不动）
  - 11-17 画布（创建 Modal 双列 + 编辑抽屉水平 label）
- [ ] 后端启动后没遇到 schema 加载错误
- [ ] 把分支 push 到 origin 前确认 `git log --oneline origin/main..HEAD` 14+ 个干净 commit

---

## 自审记录

**Spec coverage:**
- §3.1 节点类型端点：Task 2 ✓
- §3.2 边类型端点：Task 3 ✓
- §3.3 diff 算法：Task 2 Step 3 + Task 3 Step 3 ✓
- §3.4 delete-impact：Task 2 Step 13 + Task 3 Step 9 ✓
- §3.5 Pydantic schema：Task 1 ✓
- §4.1 组件树：Task 6-11 ✓
- §4.2 受控数据流：Task 6 ✓
- §4.3 紧凑表格列：Task 6 Step 1 ✓
- §4.4 删字段预扫描流程：Task 8 ✓
- §4.5 边类型对称：Task 7 + 9 + 11 ✓
- §5 文件清单：14 task 全覆盖 ✓
- §6.1 后端测试：Task 2 + Task 3 ✓
- §6.2 前端 smoke：完成检查清单 ✓
- §11 画布紧凑化：Task 12-14 ✓

**Placeholder scan:** 无 TBD/TODO。

**Type 一致性：**
- `NodeTypeFieldInput` 在 Task 1 / 4 / 6 / 8 统一使用 ✓
- `getFieldDeleteImpact` 在 Task 4 / 8 / 9 命名一致 ✓
- `_sync_node_type_fields` / `_sync_edge_type_fields` 在 Task 2 / 3 一致 ✓
- 端点路径 `/fields/delete-impact` 在 spec / Task 2 / Task 3 / Task 4 一致 ✓
