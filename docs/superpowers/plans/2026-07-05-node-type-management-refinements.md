# 节点类型管理体验优化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 剥离节点类型 5 个死字段（icon/color/shape/render_mode/dn_template）、统一 text max_length 兜底 255、把 3 个字段编辑器改成独立滚动去掉底部按钮、在 NodeTypeModal 里集成"所属网管/设备"多选并串通到 Excel 导入导出。

**Architecture:**
- 后端 Schema 层剥离死字段 + 三处 max_length validator 兜底；路由层事务内一次处理"类型 + 字段 + 网管关联"；Excel 导入导出的列头随之调整，用 `domains.name`（UNIQUE）作为关联匹配键
- 前端 `api/types.ts` 类型定义同步；`NodeTypeModal` 表单区瘦身、`NodeTypeTable` 删列；3 个 FieldEditor 组件统一改造为 flex 顶部 toolbar + Table `scroll.y` 独立滚动、删除底部冗余按钮
- 不做 DB migration（死字段列保留），不改画布 / Mock 流水线 / Instance 子系统

**Tech Stack:** FastAPI + SQLite + Pydantic v2 CamelModel + Vue 3.5 `<script setup>` + Ant Design Vue 4 + openpyxl + pytest

---

## File Structure

**新建：**
- `backend/tests/test_field_max_length_default.py` — 统一测试 3 处 text max_length 兜底
- `backend/tests/test_node_type_domain_binding.py` — 测试 Modal 侧 domainIds 保存
- `backend/tests/test_node_type_excel_domains.py` — 测试 Excel 导入导出的所属网管列

**修改后端：**
- `backend/app/admin/schemas/node_type.py` — 剥离 5 死字段 + 加 domain_ids + max_length 兜底
- `backend/app/admin/schemas/alarm.py` — max_length 兜底
- `backend/app/admin/node_type.py` — 读写路径剥离死字段、事务内处理 domainIds、Excel 表头调整、Excel 导入 text max_length 兜底

**修改前端：**
- `frontend/src/api/types.ts` — NodeType 接口删 5 字段、Create/Update 加 domainIds
- `frontend/src/components/types/NodeTypeModal.vue` — 表单区瘦身、加网管选择器、去除 Modal body 高度限制
- `frontend/src/components/types/NodeTypeTable.vue` — 删"图标 / 颜色 / 渲染模式"三列
- `frontend/src/components/types/NodeTypeFieldEditor.vue` — 独立滚动 + 删底部按钮 + MaxLen placeholder
- `frontend/src/components/types/EdgeTypeFieldEditor.vue` — 独立滚动 + 删底部按钮 + MaxLen placeholder
- `frontend/src/components/alarmSchemas/AlarmSchemaFieldEditor.vue` — 独立滚动 + 删底部按钮 + MaxLen placeholder

**依赖顺序：**
- Task 1 (Schema max_length 兜底) 是独立的基础改动
- Task 2 (Schema 死字段剥离 + domain_ids) 需先于 Task 3、4、5、6、7、8
- Task 3、4、5 (Route 层) 依赖 Task 2
- Task 6 (api/types.ts) 依赖 Task 2
- Task 7 (NodeTypeModal) 依赖 Task 6
- Task 8 (NodeTypeTable) 依赖 Task 6
- Task 9、10、11 (3 个 FieldEditor) 独立于 Schema/Route，可并行

---

## Task 1: Schema 层统一 text max_length 兜底 255

**Files:**
- Modify: `backend/app/admin/schemas/node_type.py:25-33, 162-170`
- Modify: `backend/app/admin/schemas/alarm.py:32-40`
- Create: `backend/tests/test_field_max_length_default.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_field_max_length_default.py`：

```python
"""三处字段 Schema 的 text max_length 兜底测试。

user story: 用户新增 text 字段忘填 MaxLen —— 应自动填 255 而不是报 400。
"""
import pytest
from pydantic import ValidationError

from app.admin.schemas.node_type import NodeTypeFieldInput, EdgeTypeFieldInput
from app.admin.schemas.alarm import AlarmSchemaFieldCreate


def test_node_type_field_text_maxlen_none_defaults_to_255():
    """NodeTypeFieldInput: text 类型 max_length=None → 255。"""
    f = NodeTypeFieldInput(fieldKey="ip", fieldLabel="IP", fieldType="text")
    assert f.max_length == 255


def test_node_type_field_text_maxlen_explicit_preserved():
    """NodeTypeFieldInput: 显式 max_length=100 → 保留 100。"""
    f = NodeTypeFieldInput(fieldKey="ip", fieldLabel="IP", fieldType="text", maxLength=100)
    assert f.max_length == 100


def test_node_type_field_text_maxlen_zero_still_rejected():
    """NodeTypeFieldInput: max_length=0 仍拒绝（Field ge=1 兜底）。"""
    with pytest.raises(ValidationError):
        NodeTypeFieldInput(fieldKey="ip", fieldLabel="IP", fieldType="text", maxLength=0)


def test_node_type_field_number_maxlen_none_stays_none():
    """NodeTypeFieldInput: number 类型 max_length=None 不动 —— 只对 text 兜底。"""
    f = NodeTypeFieldInput(fieldKey="p", fieldLabel="端口", fieldType="number")
    assert f.max_length is None


def test_edge_type_field_text_maxlen_none_defaults_to_255():
    """EdgeTypeFieldInput: text 类型 max_length=None → 255。"""
    f = EdgeTypeFieldInput(fieldKey="bw", fieldLabel="带宽", fieldType="text")
    assert f.max_length == 255


def test_alarm_schema_field_text_maxlen_none_defaults_to_255():
    """AlarmSchemaFieldCreate: text 类型 max_length=None → 255。"""
    f = AlarmSchemaFieldCreate(fieldKey="msg", fieldLabel="告警文本", fieldType="text")
    assert f.max_length == 255
```

- [ ] **Step 2: 跑测试确认 FAIL**

Run: `cd backend && python -m pytest tests/test_field_max_length_default.py -v`
Expected: 4 个 test（node_type text、edge_type text、alarm_schema text 三个 "defaults_to_255"）FAIL with `ValidationError: 文本类型必须设置 max_length`

- [ ] **Step 3: 修改 `backend/app/admin/schemas/node_type.py`**

替换第 25-33 行 `NodeTypeFieldInput.validate_max_length_for_text`：

```python
    @model_validator(mode='after')
    def validate_max_length_for_text(self) -> 'NodeTypeFieldInput':
        if self.field_type != 'text':
            return self
        if self.max_length is None:
            object.__setattr__(self, 'max_length', 255)
        return self
```

替换第 162-170 行 `EdgeTypeFieldInput.validate_max_length_for_text`：

```python
    @model_validator(mode='after')
    def validate_max_length_for_text(self) -> 'EdgeTypeFieldInput':
        if self.field_type != 'text':
            return self
        if self.max_length is None:
            object.__setattr__(self, 'max_length', 255)
        return self
```

- [ ] **Step 4: 修改 `backend/app/admin/schemas/alarm.py`**

替换第 32-40 行 `AlarmSchemaFieldCreate.validate_max_length_for_text`：

```python
    @model_validator(mode='after')
    def validate_max_length_for_text(self) -> 'AlarmSchemaFieldCreate':
        if self.field_type != 'text':
            return self
        if self.max_length is None:
            object.__setattr__(self, 'max_length', 255)
        return self
```

- [ ] **Step 5: 跑测试确认 PASS**

Run: `cd backend && python -m pytest tests/test_field_max_length_default.py -v`
Expected: 6 passed

- [ ] **Step 6: 确认既有测试未回归**

Run: `cd backend && python -m pytest tests/test_node_type_field_sync.py tests/test_edge_type_field_sync.py tests/test_alarm_enhanced_schemas.py -v`
Expected: 全部 pass

- [ ] **Step 7: Commit**

```bash
git add backend/app/admin/schemas/node_type.py backend/app/admin/schemas/alarm.py backend/tests/test_field_max_length_default.py
git commit -m "$(cat <<'EOF'
feat(schema): text max_length 三处 Schema 统一兜底 255

- NodeTypeFieldInput / EdgeTypeFieldInput / AlarmSchemaFieldCreate 的
  validate_max_length_for_text 从"必填 raise"改成"None → 255"
- 目的：新增 text 字段忘填 MaxLen 不再报错，兜底通用值 255

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Schema 剥离 NodeType 5 死字段 + 加 domain_ids

**Files:**
- Modify: `backend/app/admin/schemas/node_type.py:51-107`

- [ ] **Step 1: 写失败测试**

在 `backend/tests/test_field_max_length_default.py` 末尾追加：

```python
def test_node_type_create_no_legacy_fields():
    """NodeTypeCreate 不再接受 icon/color/shape/renderMode/dnTemplate。"""
    from app.admin.schemas.node_type import NodeTypeCreate

    # 只能传新字段
    c = NodeTypeCreate(code="sw", name="交换机", category="physical")
    dumped = c.model_dump(by_alias=True)
    for k in ("icon", "color", "shape", "renderMode", "dnTemplate"):
        assert k not in dumped, f"NodeTypeCreate 不应保留死字段 {k}"


def test_node_type_create_accepts_domain_ids():
    """NodeTypeCreate 新增 domainIds 可选字段。"""
    from app.admin.schemas.node_type import NodeTypeCreate

    c = NodeTypeCreate(code="sw", name="交换机", category="physical", domainIds=["dom_a", "dom_b"])
    assert c.domain_ids == ["dom_a", "dom_b"]

    # None 表示不改动关联
    c2 = NodeTypeCreate(code="sw2", name="交换机2", category="physical")
    assert c2.domain_ids is None

    # 空数组表示清空关联
    c3 = NodeTypeCreate(code="sw3", name="交换机3", category="physical", domainIds=[])
    assert c3.domain_ids == []


def test_node_type_update_accepts_domain_ids():
    """NodeTypeUpdate 新增 domainIds 可选字段。"""
    from app.admin.schemas.node_type import NodeTypeUpdate

    u = NodeTypeUpdate(name="新名字", domainIds=["dom_c"])
    assert u.domain_ids == ["dom_c"]
    assert "renderMode" not in u.model_dump(by_alias=True, exclude_unset=True)
```

- [ ] **Step 2: 跑测试确认 FAIL**

Run: `cd backend && python -m pytest tests/test_field_max_length_default.py -v -k "legacy or domain_ids"`
Expected: FAIL — `NodeTypeCreate` 仍带死字段 / 不认 `domainIds`

- [ ] **Step 3: 修改 `backend/app/admin/schemas/node_type.py:51-107`**

替换 `NodeTypeCreate` / `NodeTypeUpdate` / `NodeTypeItem` / `NodeTypeDetail`：

```python
# --- node_types ---

class NodeTypeCreate(CamelModel):
    code: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=100)
    category: str = Field(..., min_length=1, max_length=50)
    description: Optional[str] = Field(default=None, max_length=500)
    domain_ids: Optional[list[str]] = Field(default=None)
    fields: Optional[list[NodeTypeFieldInput]] = Field(default=None)


class NodeTypeUpdate(CamelModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=500)
    domain_ids: Optional[list[str]] = Field(default=None)
    fields: Optional[list[NodeTypeFieldInput]] = Field(default=None)


class NodeTypeFieldItem(CamelModel):
    id: int
    node_type_id: str
    field_key: str
    field_label: str
    field_type: str
    max_length: Optional[int]
    default_value: Optional[str]
    options: Optional[str]
    required: bool
    sort_order: int


class NodeTypeItem(CamelModel):
    id: str
    code: str
    name: str
    category: str
    description: Optional[str]
    domain_ids: list[str] = []
    domain_names: list[str] = []
    created_at: datetime
    updated_at: datetime


class NodeTypeDetail(NodeTypeItem):
    fields: list[NodeTypeFieldItem] = []
```

- [ ] **Step 4: 跑测试确认 PASS**

Run: `cd backend && python -m pytest tests/test_field_max_length_default.py -v`
Expected: 9 passed

- [ ] **Step 5: 确认既有 schema import 未报错**

Run: `cd backend && python -c "from app.admin.schemas import NodeTypeCreate, NodeTypeUpdate, NodeTypeItem, NodeTypeDetail; print('ok')"`
Expected: `ok`

- [ ] **Step 6: Commit（先不 commit，等 Task 3 一起 —— 因为 Route 层引用了刚删的字段，此刻 backend 是 broken 状态）**

跳过 commit。Task 3 完成后再一起 commit。

---

## Task 3: Route 层 node_type.py 读写路径剥离死字段 + 事务处理 domainIds

**Files:**
- Modify: `backend/app/admin/node_type.py:48-62, 265-361, 408-435`
- Create: `backend/tests/test_node_type_domain_binding.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_node_type_domain_binding.py`：

```python
"""NodeType Create/Update 通过 payload 一次性处理 domain_ids。"""


def _seed_domain(client, name: str) -> str:
    r = client.post("/admin/api/domains", json={"name": name})
    assert r.status_code == 200, r.text
    return r.json()["data"]["id"]


def test_create_node_type_with_domain_ids(client):
    """POST /node-types 带 domainIds → 类型创建时自动关联网管。"""
    dom_a = _seed_domain(client, "网管A")
    dom_b = _seed_domain(client, "网管B")

    r = client.post("/admin/api/node-types", json={
        "code": "sw_bind", "name": "交换机绑定", "category": "physical",
        "domainIds": [dom_a, dom_b],
    })
    assert r.status_code == 200, r.text
    type_id = r.json()["data"]["id"]

    detail = client.get(f"/admin/api/node-types/{type_id}").json()["data"]
    assert set(detail["domainIds"]) == {dom_a, dom_b}
    assert set(detail["domainNames"]) == {"网管A", "网管B"}


def test_update_node_type_domain_ids_replace(client):
    """PUT /node-types/{id} 带 domainIds 数组 → 覆盖式 replace 关联。"""
    dom_a = _seed_domain(client, "网管A")
    dom_b = _seed_domain(client, "网管B")

    r = client.post("/admin/api/node-types", json={
        "code": "sw_upd", "name": "交换机", "category": "physical",
        "domainIds": [dom_a],
    })
    type_id = r.json()["data"]["id"]

    r = client.put(f"/admin/api/node-types/{type_id}", json={"domainIds": [dom_b]})
    assert r.status_code == 200, r.text

    detail = client.get(f"/admin/api/node-types/{type_id}").json()["data"]
    assert detail["domainIds"] == [dom_b]


def test_update_node_type_domain_ids_empty_clears(client):
    """PUT /node-types/{id} 带 domainIds=[] → 清空关联。"""
    dom_a = _seed_domain(client, "网管A")
    r = client.post("/admin/api/node-types", json={
        "code": "sw_clear", "name": "交换机", "category": "physical",
        "domainIds": [dom_a],
    })
    type_id = r.json()["data"]["id"]

    r = client.put(f"/admin/api/node-types/{type_id}", json={"domainIds": []})
    assert r.status_code == 200, r.text

    detail = client.get(f"/admin/api/node-types/{type_id}").json()["data"]
    assert detail["domainIds"] == []


def test_update_node_type_without_domain_ids_leaves_binding(client):
    """PUT /node-types/{id} 不带 domainIds 只改 name → 关联保持不动。"""
    dom_a = _seed_domain(client, "网管A")
    r = client.post("/admin/api/node-types", json={
        "code": "sw_keep", "name": "交换机", "category": "physical",
        "domainIds": [dom_a],
    })
    type_id = r.json()["data"]["id"]

    r = client.put(f"/admin/api/node-types/{type_id}", json={"name": "改名"})
    assert r.status_code == 200, r.text

    detail = client.get(f"/admin/api/node-types/{type_id}").json()["data"]
    assert detail["name"] == "改名"
    assert detail["domainIds"] == [dom_a]


def test_get_node_type_no_legacy_fields(client):
    """GET /node-types/{id} 不再返回 icon/color/shape/renderMode/dnTemplate。"""
    r = client.post("/admin/api/node-types", json={
        "code": "sw_nl", "name": "交换机", "category": "physical",
    })
    type_id = r.json()["data"]["id"]

    detail = client.get(f"/admin/api/node-types/{type_id}").json()["data"]
    for k in ("icon", "color", "shape", "renderMode", "dnTemplate"):
        assert k not in detail, f"响应不应包含死字段 {k}"
```

- [ ] **Step 2: 跑测试确认 FAIL**

Run: `cd backend && python -m pytest tests/test_node_type_domain_binding.py -v`
Expected: 全部 FAIL（`domainIds` 未被处理 / 死字段还在响应里）

- [ ] **Step 3: 修改 `backend/app/admin/node_type.py:48-62`**

替换 `_row_to_node_type_item`：

```python
def _row_to_node_type_item(row) -> NodeTypeItem:
    return NodeTypeItem(
        id=row["id"],
        code=row["code"],
        name=row["name"],
        category=row["category"],
        description=row["description"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
```

- [ ] **Step 4: 修改 `list_node_types` 里的 NodeTypeDetail 构造（第 297-313 行）**

替换 `item = NodeTypeDetail(...)` 块：

```python
            item = NodeTypeDetail(
                id=r["id"],
                code=r["code"],
                name=r["name"],
                category=r["category"],
                description=r["description"],
                domain_ids=[dr["id"] for dr in dom_rows],
                domain_names=[dr["name"] for dr in dom_rows],
                created_at=r["created_at"],
                updated_at=r["updated_at"],
                fields=_get_node_type_fields(conn, r["id"]),
            )
```

- [ ] **Step 5: 修改 `get_node_type` 里的 NodeTypeDetail 构造（第 326-340 行）**

替换 `item = NodeTypeDetail(...)` 块，同时补上关联 domains 查询（原代码漏了）：

```python
        dom_rows = conn.execute("""
            SELECT d.id, d.name FROM domains d
            INNER JOIN domain_node_types dnt ON dnt.domain_id = d.id
            WHERE dnt.node_type_id = ?
        """, (type_id,)).fetchall()
        item = NodeTypeDetail(
            id=row["id"],
            code=row["code"],
            name=row["name"],
            category=row["category"],
            description=row["description"],
            domain_ids=[dr["id"] for dr in dom_rows],
            domain_names=[dr["name"] for dr in dom_rows],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            fields=_get_node_type_fields(conn, row["id"]),
        )
```

- [ ] **Step 6: 修改 `create_node_type`（第 344-361 行）**

替换整个函数：

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
            """INSERT INTO node_types (id, code, name, category, description)
               VALUES (?, ?, ?, ?, ?)""",
            (type_id, data.code, data.name, data.category, data.description),
        )
        if data.fields is not None:
            _sync_node_type_fields(conn, type_id, data.fields)
        if data.domain_ids is not None:
            conn.execute("DELETE FROM domain_node_types WHERE node_type_id = ?", (type_id,))
            for dom_id in data.domain_ids:
                conn.execute(
                    "INSERT OR IGNORE INTO domain_node_types (domain_id, node_type_id) VALUES (?, ?)",
                    (dom_id, type_id),
                )
    return {"code": 0, "data": {"id": type_id}, "message": "ok"}
```

- [ ] **Step 7: 修改 `update_node_type`（第 408-435 行）**

替换整个函数：

```python
@router.put("/node-types/{type_id}")
def update_node_type(type_id: str, data: NodeTypeUpdate) -> dict:
    raw = data.model_dump(exclude_unset=True)
    fields_payload = data.fields if "fields" in raw else None
    domain_ids_payload = data.domain_ids if "domain_ids" in raw else None
    raw.pop("fields", None)
    raw.pop("domain_ids", None)

    # 防御：空 body {} 拒绝
    if not raw and fields_payload is None and domain_ids_payload is None:
        raise HTTPException(status_code=400, detail={"code": 40203, "message": "无更新字段"})

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

        if domain_ids_payload is not None:
            conn.execute("DELETE FROM domain_node_types WHERE node_type_id = ?", (type_id,))
            for dom_id in domain_ids_payload:
                conn.execute(
                    "INSERT OR IGNORE INTO domain_node_types (domain_id, node_type_id) VALUES (?, ?)",
                    (dom_id, type_id),
                )

    return {"code": 0, "data": {"id": type_id}, "message": "ok"}
```

- [ ] **Step 8: 跑测试确认 PASS**

Run: `cd backend && python -m pytest tests/test_node_type_domain_binding.py -v`
Expected: 5 passed

- [ ] **Step 9: 跑既有测试确认不回归**

Run: `cd backend && python -m pytest tests/test_node_type_field_sync.py tests/test_smoke.py -v`
Expected: 全部 pass

- [ ] **Step 10: Commit（含 Task 2 的 Schema 改动）**

```bash
git add backend/app/admin/schemas/node_type.py backend/app/admin/node_type.py backend/tests/test_node_type_domain_binding.py backend/tests/test_field_max_length_default.py
git commit -m "$(cat <<'EOF'
feat(node-type): 剥离 5 死字段 + Modal 侧 domainIds 一次事务保存

- Schema: NodeTypeCreate/Update/Item/Detail 删 icon/color/shape/renderMode/dnTemplate
- Schema: NodeTypeCreate/Update 加可选 domain_ids
- Route: create/update 事务内一并 replace domain_node_types 关联
- 语义: domain_ids=None 不动关联，[]=清空，[...]=覆盖

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Excel 导出更新（表头去死字段 + 加所属网管列）

**Files:**
- Modify: `backend/app/admin/node_type.py:497-529, 532-569`
- Create: `backend/tests/test_node_type_excel_domains.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_node_type_excel_domains.py`：

```python
"""节点类型 Excel 导入导出的所属网管列。"""
import io

import openpyxl


def _seed_domain(client, name: str) -> str:
    r = client.post("/admin/api/domains", json={"name": name})
    assert r.status_code == 200, r.text
    return r.json()["data"]["id"]


def test_export_has_domain_column_no_legacy_columns(client):
    """导出 xlsx 类型汇总表头含"所属网管/设备"，不含死字段列。"""
    dom_a = _seed_domain(client, "网管A")
    r = client.post("/admin/api/node-types", json={
        "code": "sw_e1", "name": "交换机", "category": "physical",
        "domainIds": [dom_a],
    })
    type_id = r.json()["data"]["id"]

    r = client.post("/admin/api/node-types/export", json={"ids": [type_id]})
    assert r.status_code == 200, r.text
    wb = openpyxl.load_workbook(io.BytesIO(r.content))
    ws = wb["类型汇总"]
    headers = [c.value for c in ws[1] if c.value]

    assert "所属网管/设备" in headers
    for legacy in ("图标", "颜色", "形状", "渲染模式", "DN模板"):
        assert legacy not in headers, f"导出不应保留死字段列 {legacy}"


def test_export_domain_column_uses_pipe_separated_names(client):
    """导出的网管列值格式 '网管A|网管B'。"""
    dom_a = _seed_domain(client, "网管A")
    dom_b = _seed_domain(client, "网管B")
    r = client.post("/admin/api/node-types", json={
        "code": "sw_e2", "name": "交换机", "category": "physical",
        "domainIds": [dom_a, dom_b],
    })
    type_id = r.json()["data"]["id"]

    r = client.post("/admin/api/node-types/export", json={"ids": [type_id]})
    wb = openpyxl.load_workbook(io.BytesIO(r.content))
    ws = wb["类型汇总"]
    headers = {c.value: idx for idx, c in enumerate(ws[1]) if c.value}
    dom_idx = headers["所属网管/设备"]
    val = ws.cell(row=2, column=dom_idx + 1).value

    assert set(val.split("|")) == {"网管A", "网管B"}
```

- [ ] **Step 2: 跑测试确认 FAIL**

Run: `cd backend && python -m pytest tests/test_node_type_excel_domains.py::test_export_has_domain_column_no_legacy_columns -v`
Expected: FAIL — 表头仍含"图标"等死字段列

- [ ] **Step 3: 修改 `_build_node_types_excel`（第 497-529 行）**

替换整个函数：

```python
def _build_node_types_excel(items: list[dict]) -> BytesIO:
    wb = Workbook()

    ws1 = wb.active
    ws1.title = "类型汇总"
    ws1.append(["编码", "名称", "分类", "所属网管/设备",
                "描述", "创建时间", "更新时间"])
    for item in items:
        dom_names = item.get("domainNames") or []
        ws1.append([
            item.get("code"), item.get("name"), item.get("category"),
            "|".join(dom_names) if dom_names else None,
            item.get("description"), item.get("createdAt"), item.get("updatedAt"),
        ])

    for item in items:
        fields = item.get("fields") or []
        sheet_name = _safe_sheet_name(item.get("code", item.get("id", "unknown")))
        ws = wb.create_sheet(title=sheet_name)
        ws.append(["字段标识", "显示名称", "字段类型", "最大长度",
                    "默认值", "选项", "必填", "排序"])
        for f in fields:
            ws.append([
                f.get("fieldKey"), f.get("fieldLabel"),
                f.get("fieldType"), f.get("maxLength"), f.get("defaultValue"),
                f.get("options"), "是" if f.get("required") else "否",
                f.get("sortOrder"),
            ])

    output = BytesIO()
    wb.save(output)
    output.seek(0)
    return output
```

- [ ] **Step 4: 修改 `export_node_types`（第 532-569 行）**

替换 NodeTypeDetail 构造 + 关联查询：

```python
@router.post("/node-types/export")
def export_node_types(data: TypeExportRequest):
    with connect() as conn:
        if data.ids:
            placeholders = ",".join("?" for _ in data.ids)
            rows = conn.execute(
                f"SELECT * FROM node_types WHERE id IN ({placeholders}) ORDER BY category, name",
                tuple(data.ids),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM node_types ORDER BY category, name"
            ).fetchall()
        items = []
        for r in rows:
            dom_rows = conn.execute("""
                SELECT d.id, d.name FROM domains d
                INNER JOIN domain_node_types dnt ON dnt.domain_id = d.id
                WHERE dnt.node_type_id = ?
            """, (r["id"],)).fetchall()
            item = NodeTypeDetail(
                id=r["id"],
                code=r["code"],
                name=r["name"],
                category=r["category"],
                description=r["description"],
                domain_ids=[dr["id"] for dr in dom_rows],
                domain_names=[dr["name"] for dr in dom_rows],
                created_at=r["created_at"],
                updated_at=r["updated_at"],
                fields=_get_node_type_fields(conn, r["id"]),
            )
            items.append(item.model_dump(mode="json", by_alias=True))

    excel = _build_node_types_excel(items)
    return StreamingResponse(
        excel,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=node-types-export.xlsx"},
    )
```

- [ ] **Step 5: 跑测试确认 PASS**

Run: `cd backend && python -m pytest tests/test_node_type_excel_domains.py -v -k "export"`
Expected: 2 passed

- [ ] **Step 6: Commit**

```bash
git add backend/app/admin/node_type.py backend/tests/test_node_type_excel_domains.py
git commit -m "$(cat <<'EOF'
feat(node-type): Excel 导出剥离死字段列 + 加所属网管/设备列

- 类型汇总表头改成 编码 / 名称 / 分类 / 所属网管/设备 / 描述 / 时间
- 网管列值格式 '网管A|网管B'，按 domains.name (UNIQUE) 拼接

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Excel 导入更新（读所属网管列 + text max_length 兜底）

**Files:**
- Modify: `backend/app/admin/node_type.py:641-767`
- Modify: `backend/tests/test_node_type_excel_domains.py` (追加测试)

- [ ] **Step 1: 写失败测试**

在 `test_node_type_excel_domains.py` 末尾追加：

```python
def _build_workbook_with_domains(code: str, domain_cell: str, field_maxlen=None):
    """构造一份包含"所属网管/设备"列的最小导入 xlsx。"""
    import openpyxl as _op

    wb = _op.Workbook()
    ws = wb.active
    ws.title = "类型汇总"
    ws.append(["编码", "名称", "分类", "所属网管/设备", "描述"])
    ws.append([code, "测试", "physical", domain_cell, None])

    fs = wb.create_sheet(title=code)
    fs.append(["字段标识", "显示名称", "字段类型", "最大长度",
                "默认值", "选项", "必填", "排序"])
    fs.append(["ip", "IP", "text", field_maxlen, None, None, "否", 0])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def test_import_reads_domain_column_and_links(client):
    """导入 xlsx 含"所属网管/设备"列 → 类型创建时自动关联对应网管。"""
    dom_a = _seed_domain(client, "网管A")
    buf = _build_workbook_with_domains("sw_imp_link", "网管A", field_maxlen=50)

    r = client.post("/admin/api/node-types/import",
                    files={"file": ("test.xlsx", buf, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["created"] == 1

    items = client.get("/admin/api/node-types").json()["data"]["items"]
    match = next(it for it in items if it["code"] == "sw_imp_link")
    assert match["domainIds"] == [dom_a]


def test_import_unknown_domain_records_error_and_skips_link(client):
    """导入 xlsx 里网管名不存在 → 类型创建成功，errors 记录，关联跳过。"""
    _seed_domain(client, "网管A")
    buf = _build_workbook_with_domains("sw_imp_bad", "网管A|幽灵网管", field_maxlen=50)

    r = client.post("/admin/api/node-types/import",
                    files={"file": ("test.xlsx", buf, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    assert r.status_code == 200, r.text
    result = r.json()["data"]
    assert result["created"] == 1
    assert any("幽灵网管" in e for e in result["errors"])

    items = client.get("/admin/api/node-types").json()["data"]["items"]
    match = next(it for it in items if it["code"] == "sw_imp_bad")
    # 只关联到"网管A"，跳过不存在的
    assert len(match["domainIds"]) == 1


def test_import_text_field_missing_maxlen_defaults_to_255(client):
    """导入 xlsx text 字段"最大长度"列为空 → 落库 max_length=255。"""
    buf = _build_workbook_with_domains("sw_imp_mx", "", field_maxlen=None)

    r = client.post("/admin/api/node-types/import",
                    files={"file": ("test.xlsx", buf, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["created"] == 1

    items = client.get("/admin/api/node-types").json()["data"]["items"]
    match = next(it for it in items if it["code"] == "sw_imp_mx")
    ip_field = next(f for f in match["fields"] if f["fieldKey"] == "ip")
    assert ip_field["maxLength"] == 255


def test_import_legacy_workbook_without_domain_column_still_works(client):
    """老 xlsx（含"图标/颜色"列，无"所属网管/设备"列）仍能正常导入。"""
    import openpyxl as _op

    wb = _op.Workbook()
    ws = wb.active
    ws.title = "类型汇总"
    ws.append(["编码", "名称", "分类", "图标", "颜色", "形状", "渲染模式", "DN模板", "描述"])
    ws.append(["sw_legacy", "老交换机", "physical",
                "🔀", "#123456", "rect", "flat", "sw={ip}", "老格式"])
    fs = wb.create_sheet(title="sw_legacy")
    fs.append(["字段标识", "显示名称", "字段类型", "最大长度", "默认值", "选项", "必填", "排序"])
    fs.append(["ip", "IP", "text", 50, None, None, "否", 0])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    r = client.post("/admin/api/node-types/import",
                    files={"file": ("test.xlsx", buf, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["created"] == 1

    items = client.get("/admin/api/node-types").json()["data"]["items"]
    match = next(it for it in items if it["code"] == "sw_legacy")
    # 死字段列被忽略，导入仍成功
    assert match["name"] == "老交换机"
    assert match["domainIds"] == []
```

- [ ] **Step 2: 跑测试确认 FAIL**

Run: `cd backend && python -m pytest tests/test_node_type_excel_domains.py -v -k "import"`
Expected: 4 个测试全部 FAIL（domain 列未读取，max_length 未兜底，legacy 格式可能因为老字段读取但 Schema 剥离字段后 UPDATE 语句已改）

- [ ] **Step 3: 修改 `import_node_types`（第 641-767 行）**

替换整个函数：

```python
@router.post("/node-types/import")
async def import_node_types(file: UploadFile = File(...)):
    if not file.filename or not file.filename.endswith('.xlsx'):
        raise HTTPException(
            status_code=400,
            detail={"code": 40210, "message": "仅支持 .xlsx 文件"},
        )

    contents = await file.read()
    wb = _load_import_workbook(contents)
    ws = wb["类型汇总"]
    result = TypeImportResult()

    with transaction() as conn:
        headers = _build_header_map(ws)
        # code -> [domain_id, ...]，None 表示行未提供"所属网管/设备"列
        pending_links: dict[str, Optional[list[str]]] = {}

        for row in ws.iter_rows(min_row=2, values_only=True):
            if all(v is None or v == '' for v in row):
                break
            code = _col(headers, "编码", row)
            name = _col(headers, "名称", row)
            category = _col(headers, "分类", row)

            if not code or not name or not category:
                result.errors.append(f"编码={code or '(空)'} 缺少必填字段（编码/名称/分类），跳过")
                continue

            description = _col(headers, "描述", row)

            existing = conn.execute(
                "SELECT id FROM node_types WHERE code = ?", (code,)
            ).fetchone()

            if existing:
                type_id = existing["id"]
                conn.execute(
                    """UPDATE node_types SET name=?, category=?, description=?,
                       updated_at=datetime('now')
                       WHERE id=?""",
                    (name, category, description, type_id),
                )
                result.updated += 1
            else:
                type_id = _new_id()
                conn.execute(
                    """INSERT INTO node_types
                       (id, code, name, category, description)
                       VALUES (?,?,?,?,?)""",
                    (type_id, code, name, category, description),
                )
                result.created += 1

            # 解析"所属网管/设备"列 → 收集待关联 domain_id
            if "所属网管/设备" in headers:
                cell = _col(headers, "所属网管/设备", row)
                if cell:
                    names = [n.strip() for n in cell.split("|") if n.strip()]
                    dom_ids: list[str] = []
                    for dname in names:
                        drow = conn.execute(
                            "SELECT id FROM domains WHERE name = ?", (dname,)
                        ).fetchone()
                        if drow:
                            dom_ids.append(drow["id"])
                        else:
                            result.errors.append(
                                f"[{code}] 网管/设备 '{dname}' 不存在，关联跳过"
                            )
                    pending_links[type_id] = dom_ids
                else:
                    pending_links[type_id] = []

            sheet_name = _safe_sheet_name(code)
            if sheet_name in wb.sheetnames:
                conn.execute(
                    "DELETE FROM node_type_fields WHERE node_type_id = ?",
                    (type_id,),
                )
                fheaders = _build_header_map(wb[sheet_name])
                seen_fields: set[str] = set()
                for frow in wb[sheet_name].iter_rows(min_row=2, values_only=True):
                    if all(v is None or v == '' for v in frow):
                        break
                    fkey = _col(fheaders, "字段标识", frow)
                    flabel = _col(fheaders, "显示名称", frow)
                    ftype_raw = _col(fheaders, "字段类型", frow)
                    if not fkey or not flabel or not ftype_raw:
                        continue
                    if fkey in seen_fields:
                        result.errors.append(
                            f"[{code}] 字段标识 {fkey} 重复，跳过"
                        )
                        continue
                    seen_fields.add(fkey)
                    ftype = ftype_raw.strip().lower()
                    if ftype not in ('text', 'number', 'select', 'boolean', 'array'):
                        result.errors.append(
                            f"[{code}] 字段 {fkey} 类型 '{ftype_raw}' 无效，仅支持 text/number/select/boolean/array，跳过"
                        )
                        continue
                    maxlen_raw = _col(fheaders, "最大长度", frow)
                    if ftype == 'text':
                        # text 类型 max_length 兜底 255
                        try:
                            maxlen = int(maxlen_raw) if maxlen_raw else 255
                            if maxlen < 1:
                                maxlen = 255
                        except (ValueError, TypeError):
                            maxlen = 255
                    else:
                        try:
                            maxlen = int(maxlen_raw) if maxlen_raw else None
                        except (ValueError, TypeError):
                            maxlen = None
                    defval = _col(fheaders, "默认值", frow)
                    opts = _col(fheaders, "选项", frow)
                    req_raw = _col(fheaders, "必填", frow) or ""
                    req = 1 if req_raw == "是" else 0
                    sort_raw = _col(fheaders, "排序", frow)
                    sort = int(sort_raw) if sort_raw and sort_raw.isdigit() else 0

                    # array 类型：default_value 必须是合法 JSON array
                    if ftype == 'array' and defval:
                        import json as _json
                        try:
                            _parsed = _json.loads(defval)
                            if not isinstance(_parsed, list):
                                result.errors.append(
                                    f"[{code}] 字段 {fkey} 的默认值必须是 JSON array，跳过"
                                )
                                continue
                        except _json.JSONDecodeError:
                            result.errors.append(
                                f"[{code}] 字段 {fkey} 的默认值不是合法 JSON，跳过"
                            )
                            continue

                    conn.execute(
                        """INSERT INTO node_type_fields
                           (node_type_id, field_key, field_label, field_type,
                            max_length, default_value, options, required, sort_order)
                           VALUES (?,?,?,?,?,?,?,?,?)""",
                        (type_id, fkey, flabel, ftype,
                         maxlen, defval, opts, req, sort),
                    )
                    result.total_fields += 1

        # 一次性写入 domain_node_types
        for type_id, dom_ids in pending_links.items():
            conn.execute("DELETE FROM domain_node_types WHERE node_type_id = ?", (type_id,))
            for did in dom_ids:
                conn.execute(
                    "INSERT OR IGNORE INTO domain_node_types (domain_id, node_type_id) VALUES (?, ?)",
                    (did, type_id),
                )

    return {
        "code": 0,
        "data": result.model_dump(mode="json", by_alias=True),
        "message": "ok",
    }
```

- [ ] **Step 4: 跑测试确认 PASS**

Run: `cd backend && python -m pytest tests/test_node_type_excel_domains.py -v`
Expected: 6 passed

- [ ] **Step 5: 跑既有测试确认不回归**

Run: `cd backend && python -m pytest tests/ -v --tb=short`
Expected: 全部 pass（若 test_node_type_field_sync 里有依赖旧 renderMode 字段的测试断言，需同步修 —— 若无则跳过）

- [ ] **Step 6: Commit**

```bash
git add backend/app/admin/node_type.py backend/tests/test_node_type_excel_domains.py
git commit -m "$(cat <<'EOF'
feat(node-type): Excel 导入读所属网管列 + text max_length 兜底 255

- 类型汇总 Sheet 读"所属网管/设备"列，按 domains.name 反查，找不到记 error 跳过关联
- 字段 Sheet text 类型"最大长度"空/非法/非文本 → 兜底 255
- 老 xlsx（含图标/颜色/渲染模式等死字段列）不再读取这些列，仅忽略

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: 前端 api/types.ts 同步类型定义

**Files:**
- Modify: `frontend/src/api/types.ts:52-95`

- [ ] **Step 1: 编辑 `frontend/src/api/types.ts` 第 52-95 行**

替换 `NodeTypeItem` / `NodeTypeDetail` / `NodeTypeCreate` / `NodeTypeUpdate`：

```typescript
export interface NodeTypeItem {
  id: string
  code: string
  name: string
  category: string
  description: string | null
  domainIds: string[]
  domainNames: string[]
  createdAt: string
  updatedAt: string
}

export interface NodeTypeDetail extends NodeTypeItem {
  fields: NodeTypeFieldItem[]
}

export interface NodeTypeCreate {
  code: string
  name: string
  category: string
  description?: string | null
  domainIds?: string[] | null
  fields?: NodeTypeFieldInput[] | null
}

export interface NodeTypeUpdate {
  name?: string | null
  description?: string | null
  domainIds?: string[] | null
  fields?: NodeTypeFieldInput[] | null
}
```

- [ ] **Step 2: TypeScript 编译检查**

Run: `cd frontend && npx vue-tsc --noEmit`
Expected: 报错，指向 `NodeTypeModal.vue` 和 `NodeTypeTable.vue` 里引用了已删的 icon/color/shape/renderMode/dnTemplate 字段（这些将在 Task 7、8 修复）

- [ ] **Step 3: 暂不 commit**

跳过 commit，等 Task 7、8 修完前端引用后一起 commit。

---

## Task 7: NodeTypeModal.vue 表单区瘦身 + 加网管选择器

**Files:**
- Modify: `frontend/src/components/types/NodeTypeModal.vue` (整个文件)

- [ ] **Step 1: 替换 `frontend/src/components/types/NodeTypeModal.vue` 整个文件**

```vue
<script setup lang="ts">
import { ref, computed, watch, h, onMounted } from 'vue'
import { Modal } from 'ant-design-vue'
import NodeTypeFieldEditor from './NodeTypeFieldEditor.vue'
import { nodeTypeApi } from '@/api/types'
import { domainApi, type DomainItem } from '@/api/domain'
import type {
  NodeTypeCreate, NodeTypeUpdate, NodeTypeDetail, NodeTypeFieldInput,
} from '@/api/types'

const CATEGORIES = ['physical', 'virtual', 'cloud', 'application']

interface NodeTypeForm {
  code: string
  name: string
  category: string
  description: string
  domainIds: string[]
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
  description: '',
  domainIds: [],
  fields: [],
})

const form = ref<NodeTypeForm>(defaultForm())
const originalFieldKeys = ref<Set<string>>(new Set())
const domains = ref<DomainItem[]>([])

onMounted(async () => {
  try {
    const res = await domainApi.list()
    domains.value = res.items
  } catch {
    domains.value = []
  }
})

watch(() => props.open, (open) => {
  if (!open) return
  if (props.editing) {
    form.value = {
      code: props.editing.code,
      name: props.editing.name,
      category: props.editing.category,
      description: props.editing.description ?? '',
      domainIds: [...(props.editing.domainIds ?? [])],
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
      description: form.value.description || null,
      domainIds: form.value.domainIds,
      fields: form.value.fields,
    })
  } else {
    emit('create', {
      code: form.value.code,
      name: form.value.name,
      category: form.value.category,
      description: form.value.description || null,
      domainIds: form.value.domainIds,
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
          <a-form-item label="所属网管/设备">
            <a-select
              v-model:value="form.domainIds"
              mode="multiple"
              placeholder="可选，支持搜索"
              :options="domains.map(d => ({ value: d.id, label: d.name }))"
              :filter-option="(input: string, option: any) => option.label.toLowerCase().includes(input.toLowerCase())"
              allow-clear
            />
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

- [ ] **Step 2: TypeScript 编译检查**

Run: `cd frontend && npx vue-tsc --noEmit`
Expected: 报错减少到只剩 `NodeTypeTable.vue` 里引用 icon/color/renderMode 的部分

- [ ] **Step 3: 暂不 commit**

等 Task 8 完成后一起 commit。

---

## Task 8: NodeTypeTable.vue 删死字段展示列

**Files:**
- Modify: `frontend/src/components/types/NodeTypeTable.vue:345-357`

- [ ] **Step 1: 编辑 `frontend/src/components/types/NodeTypeTable.vue` 第 345-357 行**

删除以下三块 `<a-table-column>`：
- 第 345-350 行：`title="图标"`
- 第 351-356 行：`title="颜色"`
- 第 357 行：`title="渲染模式"`

改动后第 344 行紧接着就是 358 行的"所属网管/设备"列。

删除完成后核对上下文（用 grep 确认没有其它遗留引用）：

Run: `cd frontend && grep -n "icon\|color\|renderMode" src/components/types/NodeTypeTable.vue`
Expected: 只剩样式相关（如 `.color-swatch`），无 `record.icon` / `record.color` / `record.renderMode` 引用

- [ ] **Step 2: TypeScript 编译检查**

Run: `cd frontend && npx vue-tsc --noEmit`
Expected: 无报错（0 errors）

- [ ] **Step 3: 前端 dev 启动确认无运行时报错**

Run: `cd frontend && npm run dev`（后台运行）
浏览器打开 http://localhost:5173，进入"类型管理"→ 打开列表 + 新建 Modal + 编辑 Modal，控制台无红色报错。

关闭 dev server（Ctrl+C）。

- [ ] **Step 4: Commit（合并 Task 6、7、8）**

```bash
git add frontend/src/api/types.ts frontend/src/components/types/NodeTypeModal.vue frontend/src/components/types/NodeTypeTable.vue
git commit -m "$(cat <<'EOF'
feat(node-type-ui): NodeTypeModal 集成"所属网管/设备"多选 + 剥离死字段

- api/types.ts: NodeType 接口删 icon/color/shape/renderMode/dnTemplate，加 domainIds
- NodeTypeModal: 表单只留 code/name/category/description/所属网管，移除 Modal body 高度限制
- NodeTypeTable: 删掉"图标/颜色/渲染模式"三列
- 保存时 domainIds 随 create/update payload 一次事务完成

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: NodeTypeFieldEditor.vue 独立滚动 + 删底部按钮

**Files:**
- Modify: `frontend/src/components/types/NodeTypeFieldEditor.vue` (整个文件)

- [ ] **Step 1: 替换整个文件**

```vue
<script setup lang="ts">
import { ref, computed } from 'vue'
import {
  Table, Input, InputNumber, Select, Switch, Button, Tooltip, message,
} from 'ant-design-vue'
import {
  PlusOutlined, DeleteOutlined, ArrowUpOutlined, ArrowDownOutlined, ImportOutlined,
} from '@ant-design/icons-vue'
import type { NodeTypeFieldInput } from '@/api/types'
import JsonGenerateFieldsModal from '@/components/shared/JsonGenerateFieldsModal.vue'
import type { FieldLike } from '@/utils/jsonFieldMatch'

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
    maxLength: 255,
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

function isFieldKeyLocked(field: NodeTypeFieldInput): boolean {
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

const jsonModalOpen = ref(false)

function handleJsonGenerate(newFields: FieldLike[]) {
  emit('update:fields', [...localFields.value, ...newFields])
}
</script>

<template>
  <div class="node-type-field-editor">
    <div class="toolbar toolbar-top">
      <Button type="primary" size="small" @click="addField">
        <PlusOutlined /> 新增字段
      </Button>
      <Button size="small" @click="jsonModalOpen = true">
        <ImportOutlined /> 从 JSON 生成字段
      </Button>
      <span class="hint">{{ localFields.length }} 个字段</span>
    </div>

    <Table
      :columns="columns"
      :data-source="localFields"
      :pagination="false"
      :row-key="(_record: NodeTypeFieldInput, index?: number) => `row-${index}`"
      size="small"
      :scroll="{ x: 900, y: 300 }"
    >
      <template #bodyCell="{ column, index, record }">
        <template v-if="column.key === 'fieldKey'">
          <Input
            :value="record.fieldKey"
            size="small"
            placeholder="key"
            :disabled="isFieldKeyLocked(record)"
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
            <Select.Option value="array">array</Select.Option>
          </Select>
        </template>
        <template v-else-if="column.key === 'maxLength'">
          <InputNumber
            :value="record.maxLength"
            size="small"
            :min="1"
            :disabled="record.fieldType !== 'text'"
            :placeholder="record.fieldType === 'text' ? '默认 255' : ''"
            style="width: 100%"
            @change="(v: any) => updateField(index, 'maxLength', v)"
          />
        </template>
        <template v-else-if="column.key === 'defaultValue'">
          <Input
            :value="record.defaultValue || ''"
            size="small"
            :placeholder="record.fieldType === 'array' ? 'JSON: [&quot;a&quot;,&quot;b&quot;]' : '默认值'"
            @update:value="(v: string) => updateField(index, 'defaultValue', v || null)"
            @blur="() => validateArrayDefault(record)"
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

    <JsonGenerateFieldsModal
      v-model:open="jsonModalOpen"
      :existing-fields="localFields"
      :sort-order-start="localFields.length"
      @apply="handleJsonGenerate"
    />
  </div>
</template>

<style scoped>
.node-type-field-editor {
  display: flex;
  flex-direction: column;
  height: 360px;
  overflow: hidden;
}
.toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 0;
  background: #fff;
  flex-shrink: 0;
}
.toolbar-top { border-bottom: 1px solid #f0f0f0; }
.hint { color: #999; font-size: 12px; }
.action-buttons { display: flex; gap: 2px; }
</style>
```

- [ ] **Step 2: TypeScript 编译检查**

Run: `cd frontend && npx vue-tsc --noEmit`
Expected: 0 errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/types/NodeTypeFieldEditor.vue
git commit -m "$(cat <<'EOF'
feat(node-type-ui): 字段编辑区独立滚动 + 表头 sticky + 删底部冗余按钮

- 容器 height: 360px overflow: hidden, toolbar flex 固定顶部
- Table :scroll="{ x: 900, y: 300 }" 触发表头 sticky
- 移除 Affix 包裹和底部 toolbar-bottom 冗余"新增字段"按钮
- MaxLen text 类型 placeholder 提示"默认 255"，新增字段默认 maxLength=255

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: EdgeTypeFieldEditor.vue 独立滚动 + 删底部按钮

**Files:**
- Modify: `frontend/src/components/types/EdgeTypeFieldEditor.vue`

- [ ] **Step 1: 替换整个文件**

（结构与 Task 9 一致，替换 `NodeTypeFieldInput` 为 `EdgeTypeFieldInput`、注释里换成边字段）

```vue
<script setup lang="ts">
import { ref, computed } from 'vue'
import {
  Table, Input, InputNumber, Select, Switch, Button, Tooltip, message,
} from 'ant-design-vue'
import {
  PlusOutlined, DeleteOutlined, ArrowUpOutlined, ArrowDownOutlined, ImportOutlined,
} from '@ant-design/icons-vue'
import type { EdgeTypeFieldInput } from '@/api/types'
import JsonGenerateFieldsModal from '@/components/shared/JsonGenerateFieldsModal.vue'
import type { FieldLike } from '@/utils/jsonFieldMatch'

const props = defineProps<{
  fields: EdgeTypeFieldInput[]
}>()

const emit = defineEmits<{
  (e: 'update:fields', v: EdgeTypeFieldInput[]): void
}>()

const localFields = computed({
  get: () => props.fields,
  set: (v) => emit('update:fields', v),
})

function addField() {
  const newField: EdgeTypeFieldInput = {
    fieldKey: '',
    fieldLabel: '',
    fieldType: 'text',
    maxLength: 255,
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

function updateField(index: number, key: keyof EdgeTypeFieldInput, value: any) {
  const next = [...localFields.value]
  next[index] = { ...next[index], [key]: value }
  emit('update:fields', next)
}

function validateArrayDefault(field: EdgeTypeFieldInput) {
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

function isFieldKeyLocked(field: EdgeTypeFieldInput): boolean {
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

const jsonModalOpen = ref(false)

function handleJsonGenerate(newFields: FieldLike[]) {
  emit('update:fields', [...localFields.value, ...newFields])
}
</script>

<template>
  <div class="edge-type-field-editor">
    <div class="toolbar toolbar-top">
      <Button type="primary" size="small" @click="addField">
        <PlusOutlined /> 新增字段
      </Button>
      <Button size="small" @click="jsonModalOpen = true">
        <ImportOutlined /> 从 JSON 生成字段
      </Button>
      <span class="hint">{{ localFields.length }} 个字段</span>
    </div>

    <Table
      :columns="columns"
      :data-source="localFields"
      :pagination="false"
      :row-key="(_record: EdgeTypeFieldInput, index?: number) => `row-${index}`"
      size="small"
      :scroll="{ x: 900, y: 300 }"
    >
      <template #bodyCell="{ column, index, record }">
        <template v-if="column.key === 'fieldKey'">
          <Input
            :value="record.fieldKey"
            size="small"
            placeholder="key"
            :disabled="isFieldKeyLocked(record)"
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
            <Select.Option value="array">array</Select.Option>
          </Select>
        </template>
        <template v-else-if="column.key === 'maxLength'">
          <InputNumber
            :value="record.maxLength"
            size="small"
            :min="1"
            :disabled="record.fieldType !== 'text'"
            :placeholder="record.fieldType === 'text' ? '默认 255' : ''"
            style="width: 100%"
            @change="(v: any) => updateField(index, 'maxLength', v)"
          />
        </template>
        <template v-else-if="column.key === 'defaultValue'">
          <Input
            :value="record.defaultValue || ''"
            size="small"
            :placeholder="record.fieldType === 'array' ? 'JSON: [&quot;a&quot;,&quot;b&quot;]' : '默认值'"
            @update:value="(v: string) => updateField(index, 'defaultValue', v || null)"
            @blur="() => validateArrayDefault(record)"
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

    <JsonGenerateFieldsModal
      v-model:open="jsonModalOpen"
      :existing-fields="localFields"
      :sort-order-start="localFields.length"
      @apply="handleJsonGenerate"
    />
  </div>
</template>

<style scoped>
.edge-type-field-editor {
  display: flex;
  flex-direction: column;
  height: 360px;
  overflow: hidden;
}
.toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 0;
  background: #fff;
  flex-shrink: 0;
}
.toolbar-top { border-bottom: 1px solid #f0f0f0; }
.hint { color: #999; font-size: 12px; }
.action-buttons { display: flex; gap: 2px; }
</style>
```

- [ ] **Step 2: TypeScript 编译检查**

Run: `cd frontend && npx vue-tsc --noEmit`
Expected: 0 errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/types/EdgeTypeFieldEditor.vue
git commit -m "$(cat <<'EOF'
feat(edge-type-ui): 字段编辑区独立滚动 + 删底部按钮 + MaxLen 默认 255

同 NodeTypeFieldEditor：容器固定 360px 独立滚动，Table scroll.y=300
表头 sticky，Affix 移除，底部冗余"新增字段"按钮删除。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: AlarmSchemaFieldEditor.vue 独立滚动 + 删底部按钮

**Files:**
- Modify: `frontend/src/components/alarmSchemas/AlarmSchemaFieldEditor.vue`

- [ ] **Step 1: 替换整个文件**

（与 Task 9 结构一致，保留 `AlarmSchemaFieldInput` 类型和 `mappingTarget` 列，Table `x: 1000`）

```vue
<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import {
  Table, Input, InputNumber, Select, Switch, Button, Tooltip, message,
} from 'ant-design-vue'
import {
  PlusOutlined, DeleteOutlined, ArrowUpOutlined, ArrowDownOutlined, ImportOutlined,
} from '@ant-design/icons-vue'
import type { AlarmSchemaFieldInput } from '@/api/alarmSchema'
import { nodeFieldsApi, type AvailableNodeFields } from '@/api/nodeFields'
import JsonGenerateFieldsModal from '@/components/shared/JsonGenerateFieldsModal.vue'
import type { FieldLike } from '@/utils/jsonFieldMatch'

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
    maxLength: 255,
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

function validateArrayDefault(field: AlarmSchemaFieldInput) {
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
  { title: '操作', key: 'actions', width: 90, fixed: 'right' as const },
]

const jsonModalOpen = ref(false)

function handleJsonGenerate(newFields: FieldLike[]) {
  emit('update:fields', [...localFields.value, ...newFields])
}
</script>

<template>
  <div class="alarm-field-editor">
    <div class="toolbar toolbar-top">
      <Button type="primary" size="small" @click="addField">
        <PlusOutlined /> 新增字段
      </Button>
      <Button size="small" @click="jsonModalOpen = true">
        <ImportOutlined /> 从 JSON 生成字段
      </Button>
      <span class="hint">{{ localFields.length }} 个字段</span>
    </div>

    <Table
      :columns="columns"
      :data-source="localFields"
      :pagination="false"
      row-key="fieldKey"
      size="small"
      :scroll="{ x: 1000, y: 300 }"
    >
      <template #bodyCell="{ column, index, record }">
        <template v-if="column.key === 'fieldKey'">
          <Input
            :value="record.fieldKey"
            size="small"
            placeholder="key"
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
            <Select.Option value="array">array</Select.Option>
          </Select>
        </template>
        <template v-else-if="column.key === 'maxLength'">
          <InputNumber
            :value="record.maxLength"
            size="small"
            :min="1"
            :disabled="record.fieldType !== 'text'"
            :placeholder="record.fieldType === 'text' ? '默认 255' : ''"
            style="width: 100%"
            @change="(v: any) => updateField(index, 'maxLength', v)"
          />
        </template>
        <template v-else-if="column.key === 'defaultValue'">
          <Input
            :value="record.defaultValue || ''"
            size="small"
            :placeholder="record.fieldType === 'array' ? 'JSON: [&quot;a&quot;,&quot;b&quot;]' : '默认值'"
            @update:value="(v: string) => updateField(index, 'defaultValue', v || null)"
            @blur="() => validateArrayDefault(record)"
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
        <template v-else-if="column.key === 'mappingTarget'">
          <Select
            :value="record.mappingTarget || undefined"
            size="small"
            style="width: 100%"
            allow-clear
            show-search
            placeholder="不映射"
            @change="(v: any) => updateField(index, 'mappingTarget', v || null)"
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
            @change="(v: any) => updateField(index, 'sortOrder', v ?? 0)"
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

    <JsonGenerateFieldsModal
      v-model:open="jsonModalOpen"
      :existing-fields="localFields"
      :sort-order-start="localFields.length"
      @apply="handleJsonGenerate"
    />
  </div>
</template>

<style scoped>
.alarm-field-editor {
  display: flex;
  flex-direction: column;
  height: 360px;
  overflow: hidden;
}
.toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 0;
  background: #fff;
  flex-shrink: 0;
}
.toolbar-top { border-bottom: 1px solid #f0f0f0; }
.hint { color: #999; font-size: 12px; }
.action-buttons { display: flex; gap: 2px; }
</style>
```

- [ ] **Step 2: TypeScript 编译检查**

Run: `cd frontend && npx vue-tsc --noEmit`
Expected: 0 errors

- [ ] **Step 3: 前端 dev 手动回归 3 个编辑器**

Run: `cd frontend && npm run dev`（后台）
浏览器进入：
- 类型管理 → 新建节点类型 → 字段配置 → 加 15 个字段 → 表头在滚动时保持可见 → 底部无第二个"新增字段"按钮 ✅
- 类型管理 → 新建边类型 → 字段配置 → 同上 ✅
- 告警模板管理 → 新建告警模板 → 字段配置 → 同上 ✅

关闭 dev server。

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/alarmSchemas/AlarmSchemaFieldEditor.vue
git commit -m "$(cat <<'EOF'
feat(alarm-schema-ui): 字段编辑区独立滚动 + 删底部按钮 + MaxLen 默认 255

同 NodeType/EdgeType 字段编辑器：容器 360px 独立滚动，
Table scroll={x:1000, y:300} 表头 sticky，Affix 移除，
底部冗余"新增字段"按钮删除，MaxLen text 类型 placeholder 默认 255。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## 收尾自检

- [ ] 后端全量测试通过

Run: `cd backend && python -m pytest tests/ --tb=short`
Expected: 全部 pass（包括新增测试）

- [ ] 前端 TypeScript 无错

Run: `cd frontend && npx vue-tsc --noEmit`
Expected: 0 errors

- [ ] 前后端联调手动回归

启动后端：`cd backend && python -m app.main`（后台）
启动前端：`cd frontend && npm run dev`（后台）

验证清单：
- 类型管理页面正常加载 —— 无"图标/颜色/渲染模式"列
- 新建节点类型 Modal —— 表单只有 code/name/category/描述/所属网管，无 icon/color/shape/renderMode/dnTemplate
- 网管多选可搜索、多选、编辑回填正确
- 字段编辑区固定高度 360px 独立滚动，表头 sticky
- 新增 text 字段 MaxLen 留空 → 保存成功 → 编辑回显 MaxLen=255
- Excel 导出的 xlsx 类型汇总表头含"所属网管/设备"，不含死字段列
- Excel 导入新格式 xlsx（含所属网管列）→ 关联正确建立
- Excel 导入老格式 xlsx（含死字段列，无所属网管列）→ 类型创建成功，死字段列被忽略
- 边类型 Modal、告警模板 Modal 的字段编辑器行为一致

停止后端和前端进程。

- [ ] Commit + Push（可选）

若所有验证通过：`git push origin main`

---

## 记录

**关联 spec**：`docs/superpowers/specs/2026-07-05-node-type-management-refinements-design.md`

**估算工时**：11 个任务，每任务 15-30 分钟，总计约 3-5 小时（含手动回归）
