# 画布批量 JSON 导入节点 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在画布左侧 TypePalette 上加"批量导入"按钮，用户粘贴 JSON 数组一次性创建多个同类型实体节点，采用行级隔离预览 + 单事务后端提交。

**Architecture:** 前端纯函数库 `jsonBulkNodes.ts` 复用现有 `jsonFieldMatch.ts` 的 `keyMatch/coerceValue`，完成"文本 → 分组预览"。新增两个 Vue 组件（Modal 容器 + 预览子组件）。后端新增单一端点 `POST /topologies/{id}/nodes/bulk`，一个事务、行级 `continue` 收集 skipped。位置写入独立的 `canvas_nodes` 表（`nodes` 表无 x/y 列）。

**Tech Stack:** FastAPI + Pydantic v2 CamelModel + SQLite (WAL) / Vue 3.5 `<script setup>` + Ant Design Vue 4 + `@antv/x6` / pytest + FastAPI TestClient

**参考文档：**
- 设计方案：`docs/superpowers/specs/2026-07-06-canvas-bulk-json-import-design.md`
- 相关代码模式：`frontend/src/components/shared/JsonFillValuesModal.vue`（两步式 Modal 模板）
- 相关代码模式：`frontend/src/utils/jsonFieldMatch.ts`（keyMatch + coerceValue 复用）
- 相关代码模式：`backend/tests/test_array_field_type.py`（TestClient 用例结构）

---

## 文件结构

**前端新增：**
- `frontend/src/utils/jsonBulkNodes.ts` — 纯函数：`parseBulkJson`, `buildBulkPreview`, 类型定义
- `frontend/src/components/canvas/BulkImportPreview.vue` — 预览子组件（四分组 Collapse）
- `frontend/src/components/canvas/BulkImportNodesModal.vue` — 两步式 Modal 容器

**前端修改：**
- `frontend/src/api/node.ts` — 追加 `bulkCreate` 方法及类型
- `frontend/src/components/canvas/TypePalette.vue` — 类型卡片 hover 增"批量导入"图标按钮
- `frontend/src/views/CanvasView.vue` — 挂载 Modal + 事件处理

**后端新增：** 无新文件

**后端修改：**
- `backend/app/admin/schemas/node.py` — 追加 5 个 Pydantic 类（BulkNodeItem/BulkNodesCreateRequest/BulkCreatedItem/BulkSkippedItem/BulkNodesCreateResponse）
- `backend/app/admin/node.py` — 追加 `_validate_attrs_for_bulk` helper + `POST /topologies/{topology_id}/nodes/bulk` 端点

**测试新增：**
- `backend/tests/test_node_bulk.py` — 12 个 pytest 用例

---

## Task 1: 后端 Schema — 批量请求/响应

**Files:**
- Modify: `backend/app/admin/schemas/node.py`

- [ ] **Step 1: 追加 5 个 Pydantic 类到文件末尾**

打开 `backend/app/admin/schemas/node.py`，在文件末尾（`NodeListResponse` 之后）追加：

```python
class BulkNodeItem(CamelModel):
    name: str = Field(..., min_length=1, max_length=100)
    x: float
    y: float
    attrs: dict[str, Optional[str]] = Field(default_factory=dict)


class BulkNodesCreateRequest(CamelModel):
    node_type_id: str
    items: list[BulkNodeItem]


class BulkCreatedItem(CamelModel):
    index: int
    id: str
    name: str


class BulkSkippedItem(CamelModel):
    index: int
    name: Optional[str] = None
    reason: str


class BulkNodesCreateResponse(CamelModel):
    created: list[BulkCreatedItem]
    skipped: list[BulkSkippedItem]
```

- [ ] **Step 2: 校验语法**

Run: `cd backend && python -c "from app.admin.schemas.node import BulkNodesCreateRequest, BulkNodesCreateResponse; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/admin/schemas/node.py
git commit -m "feat(node): 批量导入节点 Pydantic Schema"
```

---

## Task 2: 后端 `_validate_attrs_for_bulk` helper

**Files:**
- Modify: `backend/app/admin/node.py`

- [ ] **Step 1: 追加 helper 函数到 `node.py`（现有 helper 之后、路由之前）**

在 `backend/app/admin/node.py` 中，找到 `_build_node_detail` 函数（结束于第 104 行左右），在其后、`@router.get("/topologies/{topology_id}/nodes")` 之前追加：

```python
def _validate_attrs_for_bulk(field_map: dict, attrs: dict) -> Optional[str]:
    """批量导入时对单行 attrs 做校验。
    - 必填字段（required=1）若在 attrs 中缺失或为空 → 返回错误理由
    - text 类型字段若超过 max_length → 返回错误理由
    - 返回 None 表示通过
    field_map: {field_key: sqlite3.Row}（含 field_label, field_type, max_length, required 列）
    """
    for field_key, field in field_map.items():
        if field["required"] and not attrs.get(field_key):
            return f"必填字段「{field['field_label']}」缺失"
    for field_key, value in attrs.items():
        field = field_map.get(field_key)
        if field is None or value is None:
            continue
        if field["field_type"] == "text":
            max_length = field["max_length"] or 255
            if len(value) > max_length:
                return f"字段「{field['field_label']}」内容长度不能超过 {max_length}"
    return None
```

- [ ] **Step 2: 校验导入清单**

在 `node.py` 顶部导入区确认 `Optional` 已导入（已存在于第 2 行 `from typing import Optional`）。

Run: `cd backend && python -c "from app.admin.node import _validate_attrs_for_bulk; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/admin/node.py
git commit -m "feat(node): 批量导入行级 attrs 校验 helper"
```

---

## Task 3: 后端 `POST /topologies/{id}/nodes/bulk` 端点（失败测试先行）

**Files:**
- Modify: `backend/app/admin/node.py`
- Test: `backend/tests/test_node_bulk.py`

- [ ] **Step 1: 创建测试文件，先写第一个失败用例**

Create `backend/tests/test_node_bulk.py`:

```python
"""画布批量 JSON 导入节点 — 端点集成测试。

对应 spec: docs/superpowers/specs/2026-07-06-canvas-bulk-json-import-design.md
"""
import pytest


def _make_topology(client) -> str:
    r = client.post("/admin/api/topologies", json={"name": "TestTopo"})
    return r.json()["data"]["id"]


def _make_node_type(client, code: str = "sw", fields: list | None = None) -> str:
    body = {"code": code, "name": code.upper(), "category": "physical"}
    if fields is not None:
        body["fields"] = fields
    r = client.post("/admin/api/node-types", json=body)
    return r.json()["data"]["id"]


def _fetch_nodes(client, topo_id: str) -> list:
    r = client.get(f"/admin/api/topologies/{topo_id}/nodes")
    return r.json()["data"]["items"]


def test_bulk_create_single_success(client):
    """单条正常创建 → created=1, skipped=0, DB 有节点。"""
    topo = _make_topology(client)
    ntype = _make_node_type(client, "sw", [
        {"fieldKey": "ip", "fieldLabel": "IP", "fieldType": "text"},
    ])
    r = client.post(f"/admin/api/topologies/{topo}/nodes/bulk", json={
        "nodeTypeId": ntype,
        "items": [{"name": "sw-01", "x": 100.0, "y": 200.0, "attrs": {"ip": "10.0.0.1"}}],
    })
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert len(data["created"]) == 1
    assert data["created"][0]["name"] == "sw-01"
    assert data["skipped"] == []
    nodes = _fetch_nodes(client, topo)
    assert any(n["name"] == "sw-01" and n["x"] == 100.0 and n["y"] == 200.0 for n in nodes)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_node_bulk.py::test_bulk_create_single_success -v`
Expected: FAIL with 404 (端点不存在)

- [ ] **Step 3: 实现端点**

在 `backend/app/admin/node.py` 顶部导入区追加 schema：

```python
from app.admin.schemas.node import (
    NodeCreate,
    NodeUpdate,
    NodeDetail,
    NodeItem,
    NodeListItem,
    NodePositionUpdate,
    NodeAttrSet,
    BulkNodesCreateRequest,   # 新增
)
```

在 `set_node_attrs` 路由之后（文件末尾）追加端点：

```python
# POST /admin/api/topologies/{topology_id}/nodes/bulk
@router.post("/topologies/{topology_id}/nodes/bulk")
def bulk_create_nodes(topology_id: str, req: BulkNodesCreateRequest) -> dict:
    with transaction() as conn:
        # 1. 前置检查：拓扑存在
        topo = conn.execute(
            "SELECT id FROM topologies WHERE id = ?", (topology_id,)
        ).fetchone()
        if not topo:
            raise HTTPException(
                status_code=404,
                detail={"code": 40402, "message": "拓扑不存在"},
            )
        # 2. 前置检查：节点类型存在
        ntype = conn.execute(
            "SELECT id FROM node_types WHERE id = ?", (req.node_type_id,)
        ).fetchone()
        if not ntype:
            raise HTTPException(
                status_code=404,
                detail={"code": 40403, "message": "节点类型不存在"},
            )

        # 3. 加载字段元数据
        field_rows = conn.execute(
            "SELECT field_key, field_label, field_type, max_length, required "
            "FROM node_type_fields WHERE node_type_id = ?",
            (req.node_type_id,),
        ).fetchall()
        field_map = {r["field_key"]: r for r in field_rows}

        # 4. 预取同拓扑内已存在的 name
        existing_names = {
            r["name"] for r in conn.execute(
                "SELECT name FROM nodes WHERE topology_id = ?", (topology_id,)
            ).fetchall()
        }

        created: list[dict] = []
        skipped: list[dict] = []
        seen_in_batch: set[str] = set()

        for idx, item in enumerate(req.items):
            name = (item.name or "").strip()
            if not name:
                skipped.append({"index": idx, "name": item.name, "reason": "name 为空"})
                continue
            if name in existing_names:
                skipped.append({"index": idx, "name": name, "reason": "画布已有同名节点"})
                continue
            if name in seen_in_batch:
                skipped.append({"index": idx, "name": name, "reason": "批次内名称重复"})
                continue

            err = _validate_attrs_for_bulk(field_map, item.attrs)
            if err:
                skipped.append({"index": idx, "name": name, "reason": err})
                continue

            node_id = _new_id()
            conn.execute(
                "INSERT INTO nodes (id, topology_id, node_type_id, name, status) "
                "VALUES (?, ?, ?, ?, 'online')",
                (node_id, topology_id, req.node_type_id, name),
            )
            conn.execute(
                "INSERT OR REPLACE INTO canvas_nodes (node_id, topology_id, x, y) "
                "VALUES (?, ?, ?, ?)",
                (node_id, topology_id, item.x, item.y),
            )
            for field_key, value in item.attrs.items():
                if value is None or field_key not in field_map:
                    continue
                conn.execute(
                    "INSERT INTO node_attrs (node_id, field_key, value) VALUES (?, ?, ?)",
                    (node_id, field_key, value),
                )
            created.append({"index": idx, "id": node_id, "name": name})
            seen_in_batch.add(name)

    return {"code": 0, "data": {"created": created, "skipped": skipped}, "message": "ok"}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_node_bulk.py::test_bulk_create_single_success -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/admin/node.py backend/tests/test_node_bulk.py
git commit -m "feat(node): 批量创建端点 + 首个成功用例"
```

---

## Task 4: 后端端点 — 补齐 11 个隔离用例

**Files:**
- Modify: `backend/tests/test_node_bulk.py`

- [ ] **Step 1: 追加多条正常创建用例**

在 `test_node_bulk.py` 中追加：

```python
def test_bulk_create_multiple_success(client):
    """多条正常创建 → 事务一次提交，x/y 正确写入。"""
    topo = _make_topology(client)
    ntype = _make_node_type(client, "sw")
    r = client.post(f"/admin/api/topologies/{topo}/nodes/bulk", json={
        "nodeTypeId": ntype,
        "items": [
            {"name": "sw-01", "x": 100.0, "y": 200.0, "attrs": {}},
            {"name": "sw-02", "x": 320.0, "y": 200.0, "attrs": {}},
            {"name": "sw-03", "x": 540.0, "y": 200.0, "attrs": {}},
        ],
    })
    assert r.status_code == 200
    data = r.json()["data"]
    assert len(data["created"]) == 3
    assert data["skipped"] == []
    nodes = _fetch_nodes(client, topo)
    assert len(nodes) == 3
    positions = {n["name"]: (n["x"], n["y"]) for n in nodes}
    assert positions["sw-01"] == (100.0, 200.0)
    assert positions["sw-03"] == (540.0, 200.0)
```

- [ ] **Step 2: 追加前置错误用例（拓扑 / 类型不存在）**

```python
def test_bulk_create_topology_not_found(client):
    """拓扑不存在 → 404，不走行级处理。"""
    ntype = _make_node_type(client, "sw")
    r = client.post("/admin/api/topologies/topo_does_not_exist/nodes/bulk", json={
        "nodeTypeId": ntype,
        "items": [{"name": "x", "x": 0, "y": 0, "attrs": {}}],
    })
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == 40402


def test_bulk_create_node_type_not_found(client):
    """节点类型不存在 → 404。"""
    topo = _make_topology(client)
    r = client.post(f"/admin/api/topologies/{topo}/nodes/bulk", json={
        "nodeTypeId": "ntype_does_not_exist",
        "items": [{"name": "x", "x": 0, "y": 0, "attrs": {}}],
    })
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == 40403
```

- [ ] **Step 3: 追加行级 skip 用例（必填 / 长度 / 名称）**

```python
def test_bulk_create_required_field_missing(client):
    """必填字段缺失 → 该行 skipped，其他行成功。"""
    topo = _make_topology(client)
    ntype = _make_node_type(client, "sw", [
        {"fieldKey": "ip", "fieldLabel": "IP", "fieldType": "text", "required": True},
    ])
    r = client.post(f"/admin/api/topologies/{topo}/nodes/bulk", json={
        "nodeTypeId": ntype,
        "items": [
            {"name": "sw-01", "x": 0, "y": 0, "attrs": {"ip": "10.0.0.1"}},
            {"name": "sw-02", "x": 0, "y": 0, "attrs": {}},  # 缺 ip
        ],
    })
    data = r.json()["data"]
    assert len(data["created"]) == 1 and data["created"][0]["name"] == "sw-01"
    assert len(data["skipped"]) == 1
    assert data["skipped"][0]["name"] == "sw-02"
    assert "IP" in data["skipped"][0]["reason"]


def test_bulk_create_text_max_length_exceeded(client):
    """text 字段超 max_length → 该行 skipped，理由含 fieldLabel + 长度。"""
    topo = _make_topology(client)
    ntype = _make_node_type(client, "sw", [
        {"fieldKey": "ip", "fieldLabel": "IP", "fieldType": "text", "maxLength": 10},
    ])
    r = client.post(f"/admin/api/topologies/{topo}/nodes/bulk", json={
        "nodeTypeId": ntype,
        "items": [
            {"name": "sw-01", "x": 0, "y": 0, "attrs": {"ip": "10.0.0.1"}},
            {"name": "sw-02", "x": 0, "y": 0, "attrs": {"ip": "this-ip-is-way-too-long-1234567890"}},
        ],
    })
    data = r.json()["data"]
    assert len(data["created"]) == 1
    assert len(data["skipped"]) == 1
    assert "IP" in data["skipped"][0]["reason"]
    assert "10" in data["skipped"][0]["reason"]


def test_bulk_create_text_no_max_length_fallback_255(client):
    """text 字段 max_length 未设 → 默认 255（不 skip 250 长度值）。"""
    topo = _make_topology(client)
    ntype = _make_node_type(client, "sw", [
        {"fieldKey": "note", "fieldLabel": "备注", "fieldType": "text"},
    ])
    r = client.post(f"/admin/api/topologies/{topo}/nodes/bulk", json={
        "nodeTypeId": ntype,
        "items": [
            {"name": "sw-01", "x": 0, "y": 0, "attrs": {"note": "x" * 250}},
        ],
    })
    data = r.json()["data"]
    assert len(data["created"]) == 1
    assert data["skipped"] == []


def test_bulk_create_existing_name_skipped(client):
    """画布已有同名 → 该行 skipped。"""
    topo = _make_topology(client)
    ntype = _make_node_type(client, "sw")
    client.post(f"/admin/api/topologies/{topo}/nodes", json={
        "nodeTypeId": ntype, "name": "sw-01", "status": "online",
    })
    r = client.post(f"/admin/api/topologies/{topo}/nodes/bulk", json={
        "nodeTypeId": ntype,
        "items": [
            {"name": "sw-01", "x": 0, "y": 0, "attrs": {}},
            {"name": "sw-02", "x": 0, "y": 0, "attrs": {}},
        ],
    })
    data = r.json()["data"]
    assert len(data["created"]) == 1
    assert data["created"][0]["name"] == "sw-02"
    assert len(data["skipped"]) == 1
    assert "画布已有同名" in data["skipped"][0]["reason"]


def test_bulk_create_batch_duplicate_name_skipped(client):
    """批次内重名 → 第一个 created，后续 skipped。"""
    topo = _make_topology(client)
    ntype = _make_node_type(client, "sw")
    r = client.post(f"/admin/api/topologies/{topo}/nodes/bulk", json={
        "nodeTypeId": ntype,
        "items": [
            {"name": "sw-01", "x": 0, "y": 0, "attrs": {}},
            {"name": "sw-01", "x": 0, "y": 0, "attrs": {}},
            {"name": "sw-02", "x": 0, "y": 0, "attrs": {}},
        ],
    })
    data = r.json()["data"]
    assert len(data["created"]) == 2
    assert {c["name"] for c in data["created"]} == {"sw-01", "sw-02"}
    assert len(data["skipped"]) == 1
    assert "批次内" in data["skipped"][0]["reason"]
```

- [ ] **Step 4: 追加边界用例**

```python
def test_bulk_create_empty_items(client):
    """空 items → created=0, skipped=0, HTTP 200。"""
    topo = _make_topology(client)
    ntype = _make_node_type(client, "sw")
    r = client.post(f"/admin/api/topologies/{topo}/nodes/bulk", json={
        "nodeTypeId": ntype, "items": [],
    })
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["created"] == []
    assert data["skipped"] == []


def test_bulk_create_unknown_field_key_silently_ignored(client):
    """items 中包含未定义的 field_key → 静默忽略、不进 node_attrs、不算错。"""
    topo = _make_topology(client)
    ntype = _make_node_type(client, "sw", [
        {"fieldKey": "ip", "fieldLabel": "IP", "fieldType": "text"},
    ])
    r = client.post(f"/admin/api/topologies/{topo}/nodes/bulk", json={
        "nodeTypeId": ntype,
        "items": [{
            "name": "sw-01", "x": 0, "y": 0,
            "attrs": {"ip": "10.0.0.1", "unknown_field": "xxx"},
        }],
    })
    assert r.status_code == 200
    data = r.json()["data"]
    assert len(data["created"]) == 1
    node_id = data["created"][0]["id"]
    r = client.get(f"/admin/api/nodes/{node_id}")
    attrs = r.json()["data"]["attrs"]
    assert attrs.get("ip") == "10.0.0.1"
    assert "unknown_field" not in attrs


def test_bulk_create_name_whitespace_stripped(client):
    """name 前后空格 → 后端 strip。"""
    topo = _make_topology(client)
    ntype = _make_node_type(client, "sw")
    r = client.post(f"/admin/api/topologies/{topo}/nodes/bulk", json={
        "nodeTypeId": ntype,
        "items": [{"name": "  sw-01  ", "x": 0, "y": 0, "attrs": {}}],
    })
    data = r.json()["data"]
    assert data["created"][0]["name"] == "sw-01"
```

- [ ] **Step 5: 运行完整套件**

Run: `cd backend && python -m pytest tests/test_node_bulk.py -v`
Expected: 12 passed

- [ ] **Step 6: Commit**

```bash
git add backend/tests/test_node_bulk.py
git commit -m "test(node-bulk): 覆盖行级隔离 + 边界用例（12 测）"
```

---

## Task 5: 前端 `jsonBulkNodes.ts` 纯函数库

**Files:**
- Create: `frontend/src/utils/jsonBulkNodes.ts`

- [ ] **Step 1: 创建纯函数库**

Create `frontend/src/utils/jsonBulkNodes.ts`:

```ts
import { keyMatch } from './jsonFieldMatch'
import type { FieldLike } from './jsonFieldMatch'

export interface BulkPreviewValid {
  index: number
  name: string
  attrs: Record<string, string>
  x: number
  y: number
  warnings: string[]  // 值不兼容的字段 label 列表（该字段不填但行仍导入）
}

export interface BulkPreviewSkipped {
  index: number
  name: string | null
  reason: string
  raw: Record<string, unknown>
}

export interface BulkPreview {
  valid: BulkPreviewValid[]
  skipped: BulkPreviewSkipped[]
  duplicatesInBatch: Array<{ index: number; name: string }>
  unmatchedKeys: string[]
}

export interface LayoutOptions {
  startX: number
  startY: number
  cols: number
  dx?: number
  dy?: number
}

export type ParseResult =
  | { ok: true; items: Record<string, unknown>[] }
  | { ok: false; error: string }

const DEFAULT_DX = 220
const DEFAULT_DY = 140

export function parseBulkJson(text: string): ParseResult {
  const trimmed = text.trim()
  if (!trimmed) return { ok: false, error: '请粘贴 JSON 数组' }
  let parsed: unknown
  try {
    parsed = JSON.parse(trimmed)
  } catch (e: any) {
    return { ok: false, error: `JSON 解析失败：${e?.message || '语法错误'}` }
  }
  if (!Array.isArray(parsed)) {
    return { ok: false, error: `JSON 顶层必须是数组，收到 ${typeof parsed}` }
  }
  const badIdx: number[] = []
  for (let i = 0; i < parsed.length; i++) {
    const v = parsed[i]
    if (v === null || typeof v !== 'object' || Array.isArray(v)) {
      badIdx.push(i)
    }
  }
  if (badIdx.length > 0) {
    return { ok: false, error: `第 ${badIdx.join(', ')} 项不是 object` }
  }
  return { ok: true, items: parsed as Record<string, unknown>[] }
}

function coerceForBulk(
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
      return { ok: true, value: String(n) }
    }
    return { ok: false, reason: 'number 字段值必须是数字或数字字符串' }
  }
  if (fieldType === 'select') {
    if (typeof jsonValue !== 'string') return { ok: false, reason: 'select 字段值必须是字符串' }
    const opts = (options || '').split(',').map((s) => s.trim()).filter(Boolean)
    if (!opts.includes(jsonValue)) return { ok: false, reason: `值不在选项 [${opts.join(', ')}] 中` }
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

function extractName(
  item: Record<string, unknown>,
  nameKey: string,
  typeName: string,
  autoIdx: number,
): string {
  if (nameKey === '__auto__') {
    return `${typeName}_${autoIdx}`
  }
  for (const [k, v] of Object.entries(item)) {
    if (keyMatch(k, nameKey)) {
      if (v === null || v === undefined) return ''
      return String(v).trim()
    }
  }
  return ''
}

export function buildBulkPreview(
  items: Record<string, unknown>[],
  fields: FieldLike[],
  nameKey: string,
  typeName: string,
  existingNames: Set<string>,
  layout: LayoutOptions,
): BulkPreview {
  const result: BulkPreview = {
    valid: [],
    skipped: [],
    duplicatesInBatch: [],
    unmatchedKeys: [],
  }
  const dx = layout.dx ?? DEFAULT_DX
  const dy = layout.dy ?? DEFAULT_DY
  const cols = Math.max(1, Math.floor(layout.cols))
  const seenInBatch = new Set<string>()
  const unmatchedSet = new Set<string>()

  let autoIdx = 1
  for (let idx = 0; idx < items.length; idx++) {
    const item = items[idx]
    const name = extractName(item, nameKey, typeName, autoIdx)
    if (nameKey === '__auto__') autoIdx += 1

    if (!name) {
      result.skipped.push({ index: idx, name: null, reason: 'name 为空', raw: item })
      continue
    }
    if (existingNames.has(name)) {
      result.skipped.push({ index: idx, name, reason: '画布已有同名节点', raw: item })
      continue
    }
    if (seenInBatch.has(name)) {
      result.duplicatesInBatch.push({ index: idx, name })
      continue
    }

    const attrs: Record<string, string> = {}
    const warnings: string[] = []

    for (const [jsonKey, jsonValue] of Object.entries(item)) {
      const matched = fields.find((f) => keyMatch(jsonKey, f.fieldKey))
      if (!matched) {
        unmatchedSet.add(jsonKey)
        continue
      }
      const coerced = coerceForBulk(jsonValue, matched.fieldType, matched.options)
      if (!coerced.ok) {
        warnings.push(matched.fieldLabel)
        continue
      }
      attrs[matched.fieldKey] = coerced.value
    }

    for (const f of fields) {
      if (!attrs[f.fieldKey] && f.defaultValue) {
        attrs[f.fieldKey] = f.defaultValue
      }
    }

    let missingRequired: string | null = null
    for (const f of fields) {
      if (f.required && !attrs[f.fieldKey]) {
        missingRequired = f.fieldLabel
        break
      }
    }
    if (missingRequired) {
      result.skipped.push({
        index: idx,
        name,
        reason: `必填字段「${missingRequired}」缺失`,
        raw: item,
      })
      continue
    }

    const validIdx = result.valid.length
    const x = Math.round(layout.startX + (validIdx % cols) * dx)
    const y = Math.round(layout.startY + Math.floor(validIdx / cols) * dy)

    result.valid.push({ index: idx, name, attrs, x, y, warnings })
    seenInBatch.add(name)
  }

  result.unmatchedKeys = Array.from(unmatchedSet)
  return result
}
```

- [ ] **Step 2: 校验 tsc 编译**

Run: `cd frontend && npx vue-tsc --noEmit -p tsconfig.app.json 2>&1 | head -30`
Expected: 无 `jsonBulkNodes.ts` 相关错误（其他既有错误可忽略）

- [ ] **Step 3: Commit**

```bash
git add frontend/src/utils/jsonBulkNodes.ts
git commit -m "feat(canvas): jsonBulkNodes 纯函数库（parse + preview）"
```

---

## Task 6: 前端 `nodeApi.bulkCreate` API 方法

**Files:**
- Modify: `frontend/src/api/node.ts`

- [ ] **Step 1: 追加类型与方法**

打开 `frontend/src/api/node.ts`，在文件末尾（`nodeApi` 对象闭合 `}` 之前）追加：

在 `nodeApi` 对象之前追加类型：

```ts
export interface BulkNodeItem {
  name: string
  x: number
  y: number
  attrs: Record<string, string | null>
}

export interface BulkNodesCreateRequest {
  nodeTypeId: string
  items: BulkNodeItem[]
}

export interface BulkCreatedItem {
  index: number
  id: string
  name: string
}

export interface BulkSkippedItem {
  index: number
  name: string | null
  reason: string
}

export interface BulkNodesCreateResponse {
  created: BulkCreatedItem[]
  skipped: BulkSkippedItem[]
}
```

在 `nodeApi` 对象末尾（最后一个方法之后）追加：

```ts
  bulkCreate: (
    topologyId: string,
    data: BulkNodesCreateRequest,
  ): Promise<BulkNodesCreateResponse> =>
    apiPost(`/topologies/${topologyId}/nodes/bulk`, data),
```

- [ ] **Step 2: 校验编译**

Run: `cd frontend && npx vue-tsc --noEmit -p tsconfig.app.json 2>&1 | grep -E "node.ts|bulkCreate"` 
Expected: 无输出（无相关错误）

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/node.ts
git commit -m "feat(canvas): nodeApi.bulkCreate 方法"
```

---

## Task 7: 前端 `BulkImportPreview.vue` 预览子组件

**Files:**
- Create: `frontend/src/components/canvas/BulkImportPreview.vue`

- [ ] **Step 1: 创建预览子组件**

Create `frontend/src/components/canvas/BulkImportPreview.vue`:

```vue
<script setup lang="ts">
import { computed } from 'vue'
import { Alert, Collapse, Table, Tag, Tooltip } from 'ant-design-vue'
import type { BulkPreview } from '@/utils/jsonBulkNodes'

interface Props {
  preview: BulkPreview
}
const props = defineProps<Props>()

const validColumns = [
  { title: '#', dataIndex: 'index', width: 60 },
  { title: 'Name', dataIndex: 'name', width: 160 },
  { title: 'X', dataIndex: 'x', width: 70 },
  { title: 'Y', dataIndex: 'y', width: 70 },
  { title: 'attrs 摘要', key: 'attrsSummary' },
  { title: '警告', key: 'warnings', width: 100 },
]

const skippedColumns = [
  { title: '#', dataIndex: 'index', width: 60 },
  { title: 'Name', dataIndex: 'name', width: 160 },
  { title: '理由', dataIndex: 'reason' },
]

const dupColumns = [
  { title: '#', dataIndex: 'index', width: 60 },
  { title: 'Name', dataIndex: 'name' },
]

const activeKey = computed(() => {
  const keys: string[] = []
  if (props.preview.valid.length > 0) keys.push('valid')
  if (props.preview.skipped.length > 0) keys.push('skipped')
  if (props.preview.duplicatesInBatch.length > 0) keys.push('dup')
  return keys
})

function attrsSummary(attrs: Record<string, string>): string {
  const entries = Object.entries(attrs)
  if (entries.length === 0) return '-'
  const short = entries.slice(0, 3).map(([k, v]) => `${k}=${v}`).join(', ')
  return entries.length > 3 ? `${short}, ...(${entries.length - 3})` : short
}
</script>

<template>
  <div class="bulk-preview">
    <Alert
      v-if="preview.unmatchedKeys.length > 0"
      type="info"
      show-icon
      style="margin-bottom: 12px"
    >
      <template #message>
        JSON 中以下 key 未在字段定义里，将被忽略：
        <Tag v-for="k in preview.unmatchedKeys" :key="k">{{ k }}</Tag>
      </template>
    </Alert>

    <Collapse :active-key="activeKey" :bordered="false">
      <Collapse.Panel key="valid" :header="`✅ 将导入 (${preview.valid.length})`">
        <Table
          :columns="validColumns"
          :data-source="preview.valid"
          :pagination="false"
          size="small"
          :row-key="(r: any) => `v-${r.index}`"
          :scroll="{ y: 240 }"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'attrsSummary'">
              <span class="attrs-summary">{{ attrsSummary(record.attrs) }}</span>
            </template>
            <template v-else-if="column.key === 'warnings'">
              <Tooltip v-if="record.warnings.length > 0" :title="record.warnings.join(', ')">
                <Tag color="orange">{{ record.warnings.length }} 字段跳过</Tag>
              </Tooltip>
              <span v-else>-</span>
            </template>
          </template>
        </Table>
      </Collapse.Panel>

      <Collapse.Panel
        v-if="preview.skipped.length > 0"
        key="skipped"
        :header="`⏭️ 将跳过 (${preview.skipped.length})`"
      >
        <Table
          :columns="skippedColumns"
          :data-source="preview.skipped"
          :pagination="false"
          size="small"
          :row-key="(r: any) => `s-${r.index}`"
          :scroll="{ y: 240 }"
        />
      </Collapse.Panel>

      <Collapse.Panel
        v-if="preview.duplicatesInBatch.length > 0"
        key="dup"
        :header="`⚠️ 批次内重名 (${preview.duplicatesInBatch.length})`"
      >
        <Table
          :columns="dupColumns"
          :data-source="preview.duplicatesInBatch"
          :pagination="false"
          size="small"
          :row-key="(r: any) => `d-${r.index}`"
          :scroll="{ y: 240 }"
        />
      </Collapse.Panel>
    </Collapse>
  </div>
</template>

<style scoped>
.bulk-preview { padding: 4px 0; }
.attrs-summary {
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 11px;
  color: #666;
}
</style>
```

- [ ] **Step 2: 校验编译**

Run: `cd frontend && npx vue-tsc --noEmit -p tsconfig.app.json 2>&1 | grep BulkImportPreview`
Expected: 无输出

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/canvas/BulkImportPreview.vue
git commit -m "feat(canvas): BulkImportPreview 预览子组件"
```

---

## Task 8: 前端 `BulkImportNodesModal.vue` 两步式容器

**Files:**
- Create: `frontend/src/components/canvas/BulkImportNodesModal.vue`

- [ ] **Step 1: 创建 Modal 容器**

Create `frontend/src/components/canvas/BulkImportNodesModal.vue`:

```vue
<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { Modal, Input, Select, InputNumber, Button, Alert, Form, message } from 'ant-design-vue'
import BulkImportPreview from './BulkImportPreview.vue'
import { parseBulkJson, buildBulkPreview } from '@/utils/jsonBulkNodes'
import type { BulkPreview } from '@/utils/jsonBulkNodes'
import { nodeApi } from '@/api/node'
import type { NodeTypeDetail, NodeTypeFieldItem } from '@/api/types'
import type { FieldLike } from '@/utils/jsonFieldMatch'

interface Props {
  open: boolean
  topologyId: string
  nodeType: NodeTypeDetail | null
  defaultStartX: number
  defaultStartY: number
  existingNames: string[]
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'update:open', v: boolean): void
  (e: 'imported', createdIds: string[]): void
}>()

const step = ref<1 | 2>(1)
const jsonText = ref('')
const nameKey = ref<string>('__auto__')
const startX = ref(0)
const startY = ref(0)
const cols = ref(6)
const parseError = ref('')
const preview = ref<BulkPreview | null>(null)
const submitting = ref(false)

const fields = computed<FieldLike[]>(() => {
  const src = (props.nodeType?.fields ?? []) as NodeTypeFieldItem[]
  return src.map((f) => ({
    fieldKey: f.fieldKey,
    fieldLabel: f.fieldLabel,
    fieldType: f.fieldType as FieldLike['fieldType'],
    maxLength: f.maxLength ?? null,
    defaultValue: f.defaultValue ?? null,
    options: f.options ?? null,
    required: !!f.required,
    sortOrder: f.sortOrder ?? 0,
  }))
})

const parsedItems = ref<Record<string, unknown>[]>([])

const nameKeyOptions = computed(() => {
  const opts = [{ value: '__auto__', label: `自动生成 ${props.nodeType?.name ?? ''}_<idx>` }]
  if (parsedItems.value.length > 0) {
    const first = parsedItems.value[0]
    for (const k of Object.keys(first)) {
      opts.push({ value: k, label: k })
    }
  }
  return opts
})

const largeArrayWarning = computed(() =>
  parsedItems.value.length > 500 ? '数组超过 500 项，性能考虑建议分批' : ''
)

const emptyArrayWarning = computed(() =>
  parsedItems.value.length === 0 && jsonText.value.trim().startsWith('[]')
    ? '数组为空，没有可导入项'
    : ''
)

const canParse = computed(() => jsonText.value.trim().length > 0)
const canImport = computed(() => preview.value && preview.value.valid.length > 0)

let parseDebounceTimer: ReturnType<typeof setTimeout> | null = null
watch(jsonText, (v) => {
  if (parseDebounceTimer) clearTimeout(parseDebounceTimer)
  parseDebounceTimer = setTimeout(() => {
    const r = parseBulkJson(v)
    if (r.ok) {
      parsedItems.value = r.items
      // 若当前选中的 nameKey 不在新 keys 中，重置
      if (nameKey.value !== '__auto__' && r.items.length > 0) {
        const firstKeys = Object.keys(r.items[0])
        if (!firstKeys.includes(nameKey.value)) {
          nameKey.value = '__auto__'
        }
      }
    } else {
      parsedItems.value = []
    }
  }, 400)
})

watch(
  () => props.open,
  (v) => {
    if (v) {
      step.value = 1
      jsonText.value = ''
      nameKey.value = '__auto__'
      startX.value = Math.round(props.defaultStartX)
      startY.value = Math.round(props.defaultStartY)
      cols.value = 6
      parseError.value = ''
      preview.value = null
      parsedItems.value = []
    }
  },
)

function goPreview() {
  parseError.value = ''
  preview.value = null
  const r = parseBulkJson(jsonText.value)
  if (!r.ok) {
    parseError.value = r.error
    return
  }
  parsedItems.value = r.items
  const existingSet = new Set(props.existingNames)
  preview.value = buildBulkPreview(
    r.items,
    fields.value,
    nameKey.value,
    props.nodeType?.name ?? 'node',
    existingSet,
    { startX: startX.value, startY: startY.value, cols: cols.value },
  )
  step.value = 2
}

function backToEdit() {
  step.value = 1
}

async function confirmImport() {
  if (!preview.value || !props.nodeType) return
  submitting.value = true
  try {
    const items = preview.value.valid.map((v) => ({
      name: v.name,
      x: v.x,
      y: v.y,
      attrs: v.attrs as Record<string, string | null>,
    }))
    const resp = await nodeApi.bulkCreate(props.topologyId, {
      nodeTypeId: props.nodeType.id,
      items,
    })
    const totalCreated = resp.created.length
    const backendSkipped = resp.skipped.length
    if (backendSkipped > 0) {
      message.warning(`成功导入 ${totalCreated} 个，服务端跳过 ${backendSkipped} 个（详情见弹窗）`)
      Modal.info({
        title: '服务端跳过详情',
        content: resp.skipped.map((s) => `${s.name || '(空)'}：${s.reason}`).join('\n'),
      })
    } else {
      message.success(`成功导入 ${totalCreated} 个节点`)
    }
    emit('imported', resp.created.map((c) => c.id))
    emit('update:open', false)
  } catch (err: any) {
    message.error(`批量导入失败：${err?.message ?? '未知错误'}`)
  } finally {
    submitting.value = false
  }
}

function doCancel() {
  emit('update:open', false)
}
</script>

<template>
  <Modal
    :open="open"
    :title="`批量导入 ${nodeType?.name ?? ''}`"
    :width="820"
    :footer="null"
    :styles="{ body: { maxHeight: 'calc(100vh - 180px)', overflowY: 'auto' } }"
    @cancel="doCancel"
  >
    <!-- Step 1: 输入 -->
    <div v-if="step === 1">
      <Form layout="vertical">
        <a-row :gutter="16">
          <a-col :span="12">
            <Form.Item label="名称来源">
              <Select v-model:value="nameKey" :options="nameKeyOptions" />
            </Form.Item>
          </a-col>
          <a-col :span="4">
            <Form.Item label="起始 X">
              <InputNumber v-model:value="startX" style="width: 100%" />
            </Form.Item>
          </a-col>
          <a-col :span="4">
            <Form.Item label="起始 Y">
              <InputNumber v-model:value="startY" style="width: 100%" />
            </Form.Item>
          </a-col>
          <a-col :span="4">
            <Form.Item label="每行列数">
              <InputNumber v-model:value="cols" :min="1" :max="20" style="width: 100%" />
            </Form.Item>
          </a-col>
        </a-row>

        <Form.Item label="JSON 数组">
          <Input.TextArea
            v-model:value="jsonText"
            :rows="12"
            placeholder='[{"name":"sw-01","ip":"10.0.0.1"}, {"name":"sw-02","ip":"10.0.0.2"}]'
            style="font-family: Consolas, Monaco, monospace; font-size: 12px;"
          />
        </Form.Item>
      </Form>

      <Alert
        v-if="largeArrayWarning"
        :message="largeArrayWarning"
        type="warning"
        show-icon
        style="margin-bottom: 12px;"
      />
      <Alert
        v-if="emptyArrayWarning"
        :message="emptyArrayWarning"
        type="warning"
        show-icon
        style="margin-bottom: 12px;"
      />
      <Alert
        v-if="parseError"
        :message="parseError"
        type="error"
        show-icon
        style="margin-bottom: 12px;"
      />

      <div class="modal-footer">
        <Button @click="doCancel">取消</Button>
        <Button type="primary" :disabled="!canParse" @click="goPreview">解析预览</Button>
      </div>
    </div>

    <!-- Step 2: 预览 -->
    <div v-else-if="step === 2 && preview">
      <BulkImportPreview :preview="preview" />
      <div class="modal-footer">
        <Button @click="backToEdit">返回编辑</Button>
        <Button
          type="primary"
          :disabled="!canImport"
          :loading="submitting"
          @click="confirmImport"
        >
          确认导入 {{ preview.valid.length }} 条
        </Button>
      </div>
    </div>
  </Modal>
</template>

<style scoped>
.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding-top: 12px;
  border-top: 1px solid #f0f0f0;
  margin-top: 12px;
}
</style>
```

- [ ] **Step 2: 校验编译**

Run: `cd frontend && npx vue-tsc --noEmit -p tsconfig.app.json 2>&1 | grep BulkImportNodesModal`
Expected: 无输出

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/canvas/BulkImportNodesModal.vue
git commit -m "feat(canvas): BulkImportNodesModal 两步式导入 Modal"
```

---

## Task 9: 前端 TypePalette hover 加"批量导入"按钮

**Files:**
- Modify: `frontend/src/components/canvas/TypePalette.vue`

- [ ] **Step 1: 顶部导入 ImportOutlined 图标**

打开 `frontend/src/components/canvas/TypePalette.vue`，在 `<script setup>` 顶部现有导入之后追加：

```ts
import { ImportOutlined } from '@ant-design/icons-vue'
```

- [ ] **Step 2: 声明 emit**

在 `defineProps<Props>()` 之后追加：

```ts
const emit = defineEmits<{
  (e: 'bulk-import', nodeType: NodeTypeDetail): void
}>()

function onBulkImportClick(event: MouseEvent, nodeType: NodeTypeDetail) {
  event.stopPropagation()
  emit('bulk-import', nodeType)
}
```

- [ ] **Step 3: 模板里加 hover 显示的按钮**

在模板中找到（约第 150-160 行）：

```html
<div
  v-for="nt in types"
  :key="nt.id"
  :id="`type-item-${nt.id}`"
  class="node-type-item"
  draggable="true"
  @dragstart="onDragStart($event, nt)"
>
  <span class="node-type-name">{{ nt.name }}</span>
  <span class="node-type-code">{{ nt.code }}</span>
</div>
```

替换为：

```html
<div
  v-for="nt in types"
  :key="nt.id"
  :id="`type-item-${nt.id}`"
  class="node-type-item"
  draggable="true"
  @dragstart="onDragStart($event, nt)"
>
  <span class="node-type-name">{{ nt.name }}</span>
  <span class="node-type-code">{{ nt.code }}</span>
  <span
    class="bulk-import-btn"
    title="批量 JSON 导入"
    @click="onBulkImportClick($event, nt)"
    @mousedown.stop
    @dragstart.prevent.stop
  >
    <ImportOutlined />
  </span>
</div>
```

- [ ] **Step 4: 加 CSS**

在 `<style scoped>` 里找到 `.node-type-code { ... }` 后追加：

```css
.bulk-import-btn {
  margin-left: 4px;
  color: #bfbfbf;
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.15s, color 0.15s;
  padding: 2px 4px;
}
.node-type-item:hover .bulk-import-btn { opacity: 1; }
.bulk-import-btn:hover { color: #1890ff; }
```

- [ ] **Step 5: 校验编译**

Run: `cd frontend && npx vue-tsc --noEmit -p tsconfig.app.json 2>&1 | grep TypePalette`
Expected: 无输出

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/canvas/TypePalette.vue
git commit -m "feat(canvas): TypePalette hover 显示批量导入按钮"
```

---

## Task 10: 前端 CanvasView 挂载 Modal + 事件联动

**Files:**
- Modify: `frontend/src/views/CanvasView.vue`

- [ ] **Step 1: 顶部导入 BulkImportNodesModal**

打开 `frontend/src/views/CanvasView.vue`，在现有 `import` 中（约第 13 行 `NodeAttrsModal` 之后）追加：

```ts
import BulkImportNodesModal from '@/components/canvas/BulkImportNodesModal.vue'
```

- [ ] **Step 2: 追加状态**

在 `<script setup>` 末尾（约 `onBeforeUnmount(() => {...})` 之前）追加：

```ts
// Bulk import modal state
const bulkImportModalOpen = ref(false)
const bulkImportNodeType = ref<NodeTypeDetail | null>(null)
const bulkImportDefaultStartX = ref(0)
const bulkImportDefaultStartY = ref(0)

const existingNames = computed(() => {
  if (!graphData.value) return []
  return graphData.value.nodes.map((n) => n.name).filter((n): n is string => !!n)
})

function handleBulkImportOpen(nodeType: NodeTypeDetail) {
  const g = graph.value as Graph | null
  const cols = 6
  const dx = 220
  const dy = 140
  if (g) {
    const rect = g.container.getBoundingClientRect()
    const center = g.pageToLocal(rect.left + rect.width / 2, rect.top + rect.height / 2)
    bulkImportDefaultStartX.value = Math.round(center.x - (cols * dx) / 2)
    bulkImportDefaultStartY.value = Math.round(center.y - dy)
  } else {
    bulkImportDefaultStartX.value = 0
    bulkImportDefaultStartY.value = 0
  }
  bulkImportNodeType.value = nodeType
  bulkImportModalOpen.value = true
}

async function handleBulkImported(createdIds: string[]) {
  await fetchGraph()
  await fetchGroupGraph()
  const g = graph.value as Graph | null
  if (g && createdIds.length > 0) {
    const firstCell = g.getCellById(createdIds[0])
    if (firstCell && firstCell.isNode()) {
      const pos = firstCell.getPosition()
      g.centerPoint(pos.x, pos.y)
    }
  }
}
```

- [ ] **Step 3: 模板里挂 Modal + TypePalette 事件绑定**

找到模板中的 `<TypePalette :topology-id="topologyId" />`（约第 1037 行），替换为：

```html
<TypePalette :topology-id="topologyId" @bulk-import="handleBulkImportOpen" />
```

在 `<NodeAttrsModal ... />` 结束标签之后（约第 1104 行）追加：

```html
<BulkImportNodesModal
  v-model:open="bulkImportModalOpen"
  :topology-id="topologyId"
  :node-type="bulkImportNodeType"
  :default-start-x="bulkImportDefaultStartX"
  :default-start-y="bulkImportDefaultStartY"
  :existing-names="existingNames"
  @imported="handleBulkImported"
/>
```

- [ ] **Step 4: 校验编译**

Run: `cd frontend && npx vue-tsc --noEmit -p tsconfig.app.json 2>&1 | grep -E "CanvasView|BulkImport"`
Expected: 无输出

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/CanvasView.vue
git commit -m "feat(canvas): CanvasView 挂载批量导入 Modal + 事件联动"
```

---

## Task 11: 手动 E2E 验证 + 回归清单

**Files:** 无（人工验证）

- [ ] **Step 1: 启动后端**

Run: `cd backend && python -m app.main`
Expected: `Uvicorn running on http://0.0.0.0:8080`

- [ ] **Step 2: 启动前端**

Run: `cd frontend && npm run dev`
Expected: `Local:   http://localhost:5173/`

- [ ] **Step 3: 手动 E2E 场景 1 —— 基本导入**

浏览器打开 `http://localhost:5173`，进入一个拓扑的画布：
- 左侧 TypePalette hover 任一节点类型 → 出现批量导入图标（右侧）
- 点击图标 → BulkImportNodesModal 打开，标题含类型名
- 在 textarea 粘贴（假设该类型有 `ip` 字段）：
```json
[
  {"name": "sw-01", "ip": "10.0.0.1"},
  {"name": "sw-02", "ip": "10.0.0.2"},
  {"name": "sw-03", "ip": "10.0.0.3"}
]
```
- 停打后约 400ms，"名称来源"下拉 options 应包含 `name`, `ip`
- 保持 `__auto__` 或选 `name`
- 点[解析预览] → Step 2 显示"✅ 将导入 (3)"
- 展开面板，X/Y 应按 6 列网格从设定起点向右分布，`attrs 摘要` 显示 `ip=10.0.0.1`
- 点[确认导入 3 条] → 提示"成功导入 3 个节点"
- Modal 关闭 → 画布出现 3 个新节点，按网格排布，视口居中于第一个

- [ ] **Step 4: 手动 E2E 场景 2 —— 错误分组**

再次打开批量导入 Modal，粘贴：
```json
[
  {"name": "sw-04", "ip": "10.0.0.4"},
  {"name": "sw-01", "ip": "10.0.0.5"},
  {"name": "sw-05"},
  {"name": "sw-04", "ip": "10.0.0.6"},
  {"ip": "10.0.0.7"}
]
```
- 解析预览 → 预期分组：
  - ✅ 将导入：sw-04（如类型无 required 字段）
  - ⏭️ 将跳过：sw-01（画布已有同名，来自 Step 3）；缺 name 的一行（reason='name 为空'）；若 ip 是 required，sw-05 也会 skipped
  - ⚠️ 批次内重名：第二个 sw-04

- [ ] **Step 5: 手动 E2E 场景 3 —— JSON 语法错误 / 空数组 / 非数组**

- 粘贴 `{"foo":1}` → 点[解析预览] → 顶部红色 Alert："JSON 顶层必须是数组，收到 object"
- 粘贴 `[1, 2, 3]` → 顶部红色 Alert："第 0, 1, 2 项不是 object"
- 粘贴 `[]` → 输入区显示黄色 Alert "数组为空"

- [ ] **Step 6: 回归验证清单**

对照以下逐项验证零回归：

- 拖拽单个类型到画布 → NodeAttrsModal 正常弹出（未破坏）
- NodeAttrsModal 里"从 JSON 填充"按钮 → JsonFillValuesModal 正常工作
- 节点组的宏节点创建（GroupCreateModal） → 正常工作
- 类型管理页 Excel 导入导出 → 正常工作
- 画布保存 / 撤销 / 重做 → 正常工作

- [ ] **Step 7: 关闭进程释放端口**

`Ctrl+C` 停止后端与前端进程。

Run: `netstat -ano | grep -E "8080|5173" | head -5`
Expected: 无输出（端口已释放）

- [ ] **Step 8: 若发现回归或缺陷，回到对应 Task 修复；否则记录 E2E 通过**

无需 commit；此任务只做人工验证。

---

## 自查（写完 Plan 后）

**Spec 覆盖：**
- §1 目标：Task 3+8+9+10 覆盖端点、组件、入口、集线
- §2 用户流程：Task 8/10 组件与集线完整对齐流程图
- §3 7 个决策：全部落到具体 Task 中
- §4 组件与文件结构：Task 5-10 一一对应
- §5 后端契约：Task 1-4 覆盖
- §6 前端数据流：Task 5 纯函数库对齐
- §7 错误分类：Task 5/7/8 全部实现（Modal Alert / 分组 / warning）
- §8 UI 呈现：Task 7/8 完整实现两步式 + 分组
- §9 布局默认值：Task 10 `handleBulkImportOpen` 实现 startX/Y 计算
- §10 测试策略：Task 3-4 后端集成 12 用例；Task 11 手动 E2E；前端单元测试因项目无 vitest 由手动 E2E 兜底

**类型一致性检查：**
- `BulkNodeItem` 后端 Pydantic（Task 1）字段 = `BulkNodeItem` 前端 TS interface（Task 6）字段 ✓（name/x/y/attrs）
- `BulkNodesCreateRequest` 后端（Task 1）= 前端（Task 6）✓（nodeTypeId + items）
- `BulkNodesCreateResponse` 后端 = 前端 ✓
- `BulkPreview` 前端类型（Task 5）与 `BulkImportPreview` 组件 props（Task 7）一致 ✓
- `LayoutOptions` 前端类型（Task 5）字段与 `BulkImportNodesModal` 传入（Task 8）一致 ✓
- `handleBulkImportOpen` 拿的类型是 `NodeTypeDetail`（Task 9 emit），Modal 接收也是 `NodeTypeDetail | null`（Task 8）✓
