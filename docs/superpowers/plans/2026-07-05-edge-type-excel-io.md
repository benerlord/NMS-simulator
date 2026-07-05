# 边类型 Excel 导入导出 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 边类型（edge_types）从 JSON 导出改造为 Excel 多 Sheet 导出，并新增 preview + import 端点及前端 UI，交互模式与节点类型/告警模板一致。

**Architecture:**
- 后端参数化 `_load_import_workbook` 支持 `expected_sheet` 参数；改造 `export_edge_types` 返回 xlsx blob；新增 `POST /edge-types/import/preview` 和 `POST /edge-types/import` 端点；工具函数 `_safe_sheet_name`/`_build_header_map`/`_col` 直接复用节点类型侧现有实现
- 前端 `edgeTypeApi.export` 签名改为 `Promise<Blob>`；新增 `importPreview/import` 方法；`EdgeTypeTable.vue` 顶部"批量导出"改成 Dropdown + 加"导入"按钮；导入用 `Modal.confirm` 内联 VNode 预览
- 导入策略：text max_length 空/非法兜底 255；code 存在覆盖式；语义非法（非 connect/contain）跳过整行；有向/唯一目标"是"→true 其他→false；allow_codes 引用不存在 node_type code → warning 但字符串仍保存

**Tech Stack:** FastAPI + SQLite + openpyxl + Pydantic v2 CamelModel + Vue 3.5 `<script setup>` + Ant Design Vue 4 + pytest

---

## File Structure

**新建：**
- `backend/tests/test_edge_type_excel.py` — 后端 e2e 测试（导出 + preview + 导入）

**修改后端：**
- `backend/app/admin/schemas/node_type.py` — 新增 3 个 Pydantic 类（`EdgeTypeImportPreviewItem`/`Preview`/`Result`）
- `backend/app/admin/schemas/__init__.py` — 导出新类
- `backend/app/admin/node_type.py` — `_load_import_workbook` 加 `expected_sheet` 参数；新增 `_build_edge_types_excel`；改造 `export_edge_types`；新增 preview/import 端点

**修改前端：**
- `frontend/src/api/types.ts` — `edgeTypeApi.export` 改签名；新增 3 interface + `importPreview/import` 方法
- `frontend/src/components/types/EdgeTypeTable.vue` — 顶部工具栏 Dropdown + 导入按钮 + `handleFileChosen`/`doImport`

**依赖顺序：**
- Task 1 → Task 2/3/4（后端）
- Task 4 → Task 5 → Task 6（前端）

---

## Task 1: `_load_import_workbook` 参数化 + Schema 3 类

**Files:**
- Modify: `backend/app/admin/node_type.py:582-595`
- Modify: `backend/app/admin/schemas/node_type.py`
- Modify: `backend/app/admin/schemas/__init__.py`

- [ ] **Step 1: 修改 `backend/app/admin/node_type.py:582-595`**

原代码：
```python
def _load_import_workbook(contents: bytes) -> Workbook:
    try:
        wb = load_workbook(filename=BytesIO(contents))
    except Exception:
        raise HTTPException(
            status_code=400,
            detail={"code": 40211, "message": "文件无法解析，请确认是有效的 xlsx 文件"},
        )
    if "类型汇总" not in wb.sheetnames:
        raise HTTPException(
            status_code=400,
            detail={"code": 40212, "message": "缺少「类型汇总」Sheet"},
        )
    return wb
```

替换为：
```python
def _load_import_workbook(contents: bytes, expected_sheet: str = "类型汇总") -> Workbook:
    try:
        wb = load_workbook(filename=BytesIO(contents))
    except Exception:
        raise HTTPException(
            status_code=400,
            detail={"code": 40211, "message": "文件无法解析，请确认是有效的 xlsx 文件"},
        )
    if expected_sheet not in wb.sheetnames:
        raise HTTPException(
            status_code=400,
            detail={"code": 40212, "message": f"缺少「{expected_sheet}」Sheet"},
        )
    return wb
```

- [ ] **Step 2: 在 `backend/app/admin/schemas/node_type.py` 末尾追加 3 个 Schema 类**

在文件末尾追加（`FieldDeleteImpactResponse` 之后）：

```python
# --- edge_type Excel I/O ---

class EdgeTypeImportPreviewItem(CamelModel):
    code: str
    name: str
    old_name: Optional[str] = None


class EdgeTypeImportPreview(CamelModel):
    to_create: list[EdgeTypeImportPreviewItem] = Field(default_factory=list)
    to_update: list[EdgeTypeImportPreviewItem] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class EdgeTypeImportResult(CamelModel):
    created: int = 0
    updated: int = 0
    total_fields: int = 0
    errors: list[str] = Field(default_factory=list)
```

- [ ] **Step 3: 在 `backend/app/admin/schemas/__init__.py` 里追加 3 个类的导入和 `__all__`**

打开 `backend/app/admin/schemas/__init__.py`，找到 `from .node_type import (` 块（当前包含 `EdgeTypeCreate` 等），在该块内部末尾追加：

```python
    EdgeTypeImportPreviewItem,
    EdgeTypeImportPreview,
    EdgeTypeImportResult,
```

在文件末尾 `__all__` 列表里追加：

```python
    "EdgeTypeImportPreviewItem",
    "EdgeTypeImportPreview",
    "EdgeTypeImportResult",
```

- [ ] **Step 4: 快速 import 验证**

Run: `cd backend && python -c "from app.admin.schemas import EdgeTypeImportPreviewItem, EdgeTypeImportPreview, EdgeTypeImportResult; print('ok')"`
Expected: `ok`

- [ ] **Step 5: 跑全套测试确认节点类型侧 `_load_import_workbook` 参数化无回归**

Run: `cd backend && python -m pytest tests/ -q --tb=short`
Expected: 全部 pass（节点类型侧原调用 `_load_import_workbook(contents)` 使用默认参数 `"类型汇总"`，行为不变）

- [ ] **Step 6: Commit**

```bash
git add backend/app/admin/node_type.py backend/app/admin/schemas/node_type.py backend/app/admin/schemas/__init__.py
git commit -m "$(cat <<'EOF'
feat(edge-type): 新增 Excel 导入 Pydantic Schema 类 + workbook 加载参数化

- _load_import_workbook 加 expected_sheet 参数（默认"类型汇总"，节点类型侧行为不变）
- EdgeTypeImportPreviewItem / Preview / Result 三个新 Schema 类

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: 改造 export_edge_types 为 xlsx blob + `_build_edge_types_excel`

**Files:**
- Modify: `backend/app/admin/node_type.py:999-1032`
- Create: `backend/tests/test_edge_type_excel.py`

- [ ] **Step 1: 创建测试文件 `backend/tests/test_edge_type_excel.py`**

```python
"""边类型 Excel 导入导出 e2e 测试。"""
import io

import openpyxl


def _create_edge_type(
    client, code: str, name: str, semantic: str = "connect",
    directed: bool = True, exclusive_target: bool = False,
    allow_source: str = None, allow_target: str = None,
    line_style: str = None, color: str = None, description: str = None,
    fields: list = None,
) -> str:
    payload = {
        "code": code, "name": name, "semantic": semantic,
        "directed": directed, "exclusiveTarget": exclusive_target,
        "allowSourceTypeCodes": allow_source,
        "allowTargetTypeCodes": allow_target,
        "lineStyle": line_style, "color": color,
        "description": description,
        "fields": fields or [],
    }
    r = client.post("/admin/api/edge-types", json=payload)
    assert r.status_code == 200, r.text
    return r.json()["data"]["id"]


# ============== 导出测试 ==============

def test_export_all_returns_xlsx_with_summary_sheet(client):
    """导出全部 → xlsx 含'边类型汇总' Sheet + 每 code 独立字段 Sheet。"""
    _create_edge_type(client, "et_a", "边A")
    _create_edge_type(client, "et_b", "边B")

    r = client.post("/admin/api/edge-types/export", json={})
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    wb = openpyxl.load_workbook(io.BytesIO(r.content))
    assert "边类型汇总" in wb.sheetnames
    assert "et_a" in wb.sheetnames
    assert "et_b" in wb.sheetnames


def test_export_summary_contains_semantic_and_directed_columns(client):
    """汇总 Sheet 表头正确（13 列）。"""
    _create_edge_type(client, "et_hdr", "边表头")

    r = client.post("/admin/api/edge-types/export", json={})
    wb = openpyxl.load_workbook(io.BytesIO(r.content))
    ws = wb["边类型汇总"]
    headers = [c.value for c in ws[1] if c.value]

    for h in ["Code", "名称", "语义", "有向", "唯一目标",
              "允许源类型", "允许目标类型", "线条样式", "颜色",
              "描述", "字段数", "创建时间", "更新时间"]:
        assert h in headers, f"缺少表头 {h}"


def test_export_directed_and_exclusive_serialized_as_yes_no(client):
    """有向 / 唯一目标 布尔 → '是' / '否'。"""
    _create_edge_type(client, "et_yes", "有向的", directed=True, exclusive_target=True)
    _create_edge_type(client, "et_no", "无向的", directed=False, exclusive_target=False)

    r = client.post("/admin/api/edge-types/export", json={})
    wb = openpyxl.load_workbook(io.BytesIO(r.content))
    ws = wb["边类型汇总"]
    headers = {c.value: idx for idx, c in enumerate(ws[1]) if c.value}
    dir_col = headers["有向"] + 1
    exc_col = headers["唯一目标"] + 1
    code_col = headers["Code"] + 1

    values = {}
    for row in ws.iter_rows(min_row=2, values_only=False):
        code = row[code_col - 1].value
        if code in ("et_yes", "et_no"):
            values[code] = (row[dir_col - 1].value, row[exc_col - 1].value)

    assert values["et_yes"] == ("是", "是")
    assert values["et_no"] == ("否", "否")


def test_export_allow_codes_kept_as_comma_separated_string(client):
    """允许源/目标类型 逗号分隔字符串原样输出。"""
    _create_edge_type(
        client, "et_al", "有白名单",
        allow_source="switch,router", allow_target="server",
    )

    r = client.post("/admin/api/edge-types/export", json={})
    wb = openpyxl.load_workbook(io.BytesIO(r.content))
    ws = wb["边类型汇总"]
    headers = {c.value: idx for idx, c in enumerate(ws[1]) if c.value}
    src_col = headers["允许源类型"] + 1
    tgt_col = headers["允许目标类型"] + 1
    code_col = headers["Code"] + 1

    for row in ws.iter_rows(min_row=2, values_only=False):
        if row[code_col - 1].value == "et_al":
            assert row[src_col - 1].value == "switch,router"
            assert row[tgt_col - 1].value == "server"
            return
    raise AssertionError("et_al 行未找到")


def test_export_ids_only_returns_selected(client):
    """按 ids 过滤导出。"""
    tid_a = _create_edge_type(client, "et_only_a", "只A")
    _create_edge_type(client, "et_only_b", "只B")

    r = client.post("/admin/api/edge-types/export", json={"ids": [tid_a]})
    assert r.status_code == 200
    wb = openpyxl.load_workbook(io.BytesIO(r.content))
    assert "et_only_a" in wb.sheetnames
    assert "et_only_b" not in wb.sheetnames
```

- [ ] **Step 2: 跑测试确认 FAIL**

Run: `cd backend && python -m pytest tests/test_edge_type_excel.py -v -k "export"`
Expected: 5 个测试 FAIL（现在 export 返回 JSON `{items: []}` 不是 xlsx）

- [ ] **Step 3: 替换 `backend/app/admin/node_type.py:999-1032` 的 `export_edge_types` 函数并新增 `_build_edge_types_excel`**

先在文件里找 `_build_node_types_excel` 函数（约第 497 行）之后追加：

```python
def _build_edge_types_excel(items: list[dict]) -> BytesIO:
    wb = Workbook()

    ws1 = wb.active
    ws1.title = "边类型汇总"
    ws1.append(["Code", "名称", "语义", "有向", "唯一目标",
                "允许源类型", "允许目标类型", "线条样式", "颜色",
                "描述", "字段数", "创建时间", "更新时间"])
    for item in items:
        ws1.append([
            item.get("code"),
            item.get("name"),
            item.get("semantic"),
            "是" if item.get("directed") else "否",
            "是" if item.get("exclusiveTarget") else "否",
            item.get("allowSourceTypeCodes"),
            item.get("allowTargetTypeCodes"),
            item.get("lineStyle"),
            item.get("color"),
            item.get("description"),
            len(item.get("fields") or []),
            item.get("createdAt"),
            item.get("updatedAt"),
        ])

    for item in items:
        fields = item.get("fields") or []
        sheet_name = _safe_sheet_name(item.get("code", item.get("id", "unknown")))
        ws = wb.create_sheet(title=sheet_name)
        ws.append(["字段标识", "显示名称", "字段类型", "最大长度",
                    "默认值", "选项", "必填", "排序"])
        for f in fields:
            ws.append([
                f.get("fieldKey"),
                f.get("fieldLabel"),
                f.get("fieldType"),
                f.get("maxLength"),
                f.get("defaultValue"),
                f.get("options"),
                "是" if f.get("required") else "否",
                f.get("sortOrder"),
            ])

    output = BytesIO()
    wb.save(output)
    output.seek(0)
    return output
```

然后替换第 999-1032 行的 `export_edge_types` 函数：

```python
@router.post("/edge-types/export")
def export_edge_types(data: TypeExportRequest):
    with connect() as conn:
        if data.ids:
            placeholders = ",".join("?" for _ in data.ids)
            rows = conn.execute(
                f"SELECT * FROM edge_types WHERE id IN ({placeholders}) ORDER BY name",
                tuple(data.ids),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM edge_types ORDER BY name"
            ).fetchall()
        items = []
        for r in rows:
            item = EdgeTypeDetail(
                id=r["id"],
                code=r["code"],
                name=r["name"],
                semantic=r["semantic"],
                directed=bool(r["directed"]),
                exclusive_target=bool(r["exclusive_target"]),
                allow_source_type_codes=r["allow_source_type_codes"],
                allow_target_type_codes=r["allow_target_type_codes"],
                line_style=r["line_style"],
                color=r["color"],
                description=r["description"],
                created_at=r["created_at"],
                updated_at=r["updated_at"],
                fields=_get_edge_type_fields(conn, r["id"]),
            )
            items.append(item.model_dump(mode="json", by_alias=True))

    excel = _build_edge_types_excel(items)
    return StreamingResponse(
        excel,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=edge-types-export.xlsx"},
    )
```

- [ ] **Step 4: 跑测试确认 PASS**

Run: `cd backend && python -m pytest tests/test_edge_type_excel.py -v -k "export"`
Expected: 5 passed

- [ ] **Step 5: 跑全套确认不回归**

Run: `cd backend && python -m pytest tests/ -q --tb=short`
Expected: 全部 pass

- [ ] **Step 6: Commit**

```bash
git add backend/app/admin/node_type.py backend/tests/test_edge_type_excel.py
git commit -m "$(cat <<'EOF'
feat(edge-type): 导出改造为 Excel 多 Sheet（原 JSON 格式移除）

- 新增 _build_edge_types_excel: 边类型汇总 Sheet (13 列) + 每 code 独立字段 Sheet
- export_edge_types 返回 StreamingResponse xlsx blob（原返回 JSON {items:[]}）
- 有向/唯一目标/必填 → "是"/"否"；allow_codes 保持逗号分隔字符串

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: 导入 preview 端点

**Files:**
- Modify: `backend/app/admin/node_type.py`
- Modify: `backend/tests/test_edge_type_excel.py` (追加测试)

- [ ] **Step 1: 在 `test_edge_type_excel.py` 末尾追加测试**

```python
# ============== 导入 preview 测试 ==============

def _build_edge_import_xlsx(rows: list[dict]) -> io.BytesIO:
    """构造一份最小导入 xlsx。rows: [{code, name, semantic, directed, exclusive_target,
    allow_source, allow_target, line_style, color, description, fields: [...]}]"""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "边类型汇总"
    ws.append(["Code", "名称", "语义", "有向", "唯一目标",
               "允许源类型", "允许目标类型", "线条样式", "颜色", "描述"])
    for r in rows:
        ws.append([
            r.get("code"), r.get("name"),
            r.get("semantic", "connect"),
            "是" if r.get("directed", True) else "否",
            "是" if r.get("exclusive_target", False) else "否",
            r.get("allow_source"), r.get("allow_target"),
            r.get("line_style"), r.get("color"),
            r.get("description"),
        ])

    for r in rows:
        code = r.get("code")
        fields = r.get("fields")
        if fields is None:
            continue
        fs = wb.create_sheet(title=code)
        fs.append(["字段标识", "显示名称", "字段类型", "最大长度",
                    "默认值", "选项", "必填", "排序"])
        for f in fields:
            fs.append([
                f.get("fieldKey"), f.get("fieldLabel"), f.get("fieldType"),
                f.get("maxLength"), f.get("defaultValue"), f.get("options"),
                "是" if f.get("required") else "否",
                f.get("sortOrder", 0),
            ])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def test_import_preview_categorizes_create_and_update(client):
    """已存在 code → toUpdate；不存在 → toCreate。"""
    _create_edge_type(client, "et_exists", "已存在")
    buf = _build_edge_import_xlsx([
        {"code": "et_exists", "name": "已存在改名"},
        {"code": "et_new_1", "name": "新1"},
        {"code": "et_new_2", "name": "新2"},
    ])

    r = client.post(
        "/admin/api/edge-types/import/preview",
        files={"file": ("test.xlsx", buf,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]

    to_create_codes = [item["code"] for item in data["toCreate"]]
    to_update_codes = [item["code"] for item in data["toUpdate"]]
    assert sorted(to_create_codes) == ["et_new_1", "et_new_2"]
    assert to_update_codes == ["et_exists"]


def test_import_preview_records_old_name_on_update(client):
    """覆盖项 oldName 与新 name 不同时正确记录。"""
    _create_edge_type(client, "et_rename", "旧名字")
    buf = _build_edge_import_xlsx([
        {"code": "et_rename", "name": "新名字"},
    ])

    r = client.post(
        "/admin/api/edge-types/import/preview",
        files={"file": ("test.xlsx", buf,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert r.status_code == 200
    item = r.json()["data"]["toUpdate"][0]
    assert item["code"] == "et_rename"
    assert item["name"] == "新名字"
    assert item["oldName"] == "旧名字"


def test_import_preview_missing_summary_sheet_returns_400(client):
    """缺'边类型汇总' Sheet → 400。"""
    wb = openpyxl.Workbook()
    wb.active.title = "OtherSheet"
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    r = client.post(
        "/admin/api/edge-types/import/preview",
        files={"file": ("bad.xlsx", buf,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert r.status_code == 400
    assert "边类型汇总" in r.json()["detail"]["message"]
```

- [ ] **Step 2: 跑测试确认 FAIL**

Run: `cd backend && python -m pytest tests/test_edge_type_excel.py -v -k "preview"`
Expected: 3 个测试 FAIL（端点未实现）

- [ ] **Step 3: 在 `backend/app/admin/node_type.py` 末尾（`export_edge_types` 之后、`delete_edge_type` 之前）追加 preview 端点**

需要先在文件顶部的 `from app.admin.schemas.node_type import (` 中确保导入了新类。找到该 import 块，追加：

```python
    EdgeTypeImportPreviewItem,
    EdgeTypeImportPreview,
    EdgeTypeImportResult,
```

然后在 `export_edge_types` 函数（约行 999-1042 位置）之后追加：

```python
@router.post("/edge-types/import/preview")
async def preview_edge_types_import(file: UploadFile = File(...)):
    if not file.filename or not file.filename.endswith('.xlsx'):
        raise HTTPException(
            status_code=400,
            detail={"code": 40310, "message": "仅支持 .xlsx 文件"},
        )

    contents = await file.read()
    wb = _load_import_workbook(contents, "边类型汇总")
    ws = wb["边类型汇总"]

    to_create: list[dict] = []
    to_update: list[dict] = []
    errors: list[str] = []

    with connect() as conn:
        headers = _build_header_map(ws)
        for row in ws.iter_rows(min_row=2, values_only=True):
            if all(v is None or v == '' for v in row):
                break
            code = _col(headers, "Code", row)
            name = _col(headers, "名称", row)

            if not code or not name:
                errors.append(f"Code={code or '(空)'} 缺少必填字段（Code/名称），跳过")
                continue

            existing = conn.execute(
                "SELECT id, name FROM edge_types WHERE code = ?", (code,)
            ).fetchone()

            if existing:
                to_update.append({
                    "code": code,
                    "name": name,
                    "old_name": existing["name"],
                })
            else:
                to_create.append({"code": code, "name": name})

    preview = EdgeTypeImportPreview(
        to_create=[EdgeTypeImportPreviewItem(**c) for c in to_create],
        to_update=[EdgeTypeImportPreviewItem(**u) for u in to_update],
        errors=errors,
    )
    return {"code": 0, "data": preview.model_dump(mode="json", by_alias=True), "message": "ok"}
```

- [ ] **Step 4: 跑测试确认 PASS**

Run: `cd backend && python -m pytest tests/test_edge_type_excel.py -v -k "preview"`
Expected: 3 passed

- [ ] **Step 5: 跑全套确认不回归**

Run: `cd backend && python -m pytest tests/ -q --tb=short`
Expected: 全部 pass

- [ ] **Step 6: Commit**

```bash
git add backend/app/admin/node_type.py backend/tests/test_edge_type_excel.py
git commit -m "$(cat <<'EOF'
feat(edge-type): Excel 导入 preview 端点

- POST /edge-types/import/preview: multipart 上传 xlsx
- 返回 toCreate / toUpdate（含 oldName） / errors 三分类
- 缺'边类型汇总' Sheet → 400（复用参数化 _load_import_workbook）

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: 正式导入端点

**Files:**
- Modify: `backend/app/admin/node_type.py`
- Modify: `backend/tests/test_edge_type_excel.py` (追加测试)

- [ ] **Step 1: 在 `test_edge_type_excel.py` 末尾追加测试**

```python
# ============== 正式导入测试 ==============

def test_import_creates_new_edge_type_with_fields(client):
    """新边类型 + 字段一起导入。"""
    buf = _build_edge_import_xlsx([
        {"code": "et_imp_new", "name": "导入新", "semantic": "connect",
         "directed": True, "line_style": "solid", "color": "#1890ff",
         "fields": [
             {"fieldKey": "bandwidth", "fieldLabel": "带宽",
              "fieldType": "text", "maxLength": 30, "sortOrder": 0},
             {"fieldKey": "priority", "fieldLabel": "优先级",
              "fieldType": "number", "sortOrder": 1},
         ]},
    ])

    r = client.post(
        "/admin/api/edge-types/import",
        files={"file": ("test.xlsx", buf,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["created"] == 1
    assert data["updated"] == 0
    assert data["totalFields"] == 2

    lst = client.get("/admin/api/edge-types").json()["data"]["items"]
    match = next(it for it in lst if it["code"] == "et_imp_new")
    detail = client.get(f"/admin/api/edge-types/{match['id']}").json()["data"]
    assert [f["fieldKey"] for f in detail["fields"]] == ["bandwidth", "priority"]
    assert detail["lineStyle"] == "solid"
    assert detail["color"] == "#1890ff"


def test_import_overwrites_existing_edge_type(client):
    """已存在 code → 主表覆盖，字段全部替换。"""
    _create_edge_type(
        client, "et_imp_ov", "旧名字",
        fields=[
            {"fieldKey": "old_field", "fieldLabel": "旧字段",
             "fieldType": "text", "maxLength": 10, "sortOrder": 0}
        ],
    )
    buf = _build_edge_import_xlsx([
        {"code": "et_imp_ov", "name": "新名字",
         "fields": [
             {"fieldKey": "new_field", "fieldLabel": "新字段",
              "fieldType": "text", "maxLength": 30, "sortOrder": 0}
         ]},
    ])

    r = client.post(
        "/admin/api/edge-types/import",
        files={"file": ("test.xlsx", buf,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["updated"] == 1
    assert data["created"] == 0

    lst = client.get("/admin/api/edge-types").json()["data"]["items"]
    match = next(it for it in lst if it["code"] == "et_imp_ov")
    assert match["name"] == "新名字"
    detail = client.get(f"/admin/api/edge-types/{match['id']}").json()["data"]
    field_keys = [f["fieldKey"] for f in detail["fields"]]
    assert field_keys == ["new_field"]
    assert "old_field" not in field_keys


def test_import_directed_column_yes_maps_to_true(client):
    """'有向'='是' → True；'否' 或其他 → False。"""
    buf = _build_edge_import_xlsx([
        {"code": "et_dir_yes", "name": "有向是", "directed": True},
        {"code": "et_dir_no", "name": "有向否", "directed": False},
    ])

    r = client.post(
        "/admin/api/edge-types/import",
        files={"file": ("test.xlsx", buf,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert r.status_code == 200
    lst = client.get("/admin/api/edge-types").json()["data"]["items"]
    yes = next(it for it in lst if it["code"] == "et_dir_yes")
    no = next(it for it in lst if it["code"] == "et_dir_no")
    assert yes["directed"] is True
    assert no["directed"] is False


def test_import_invalid_semantic_records_error_and_skips_row(client):
    """'语义' 非 connect/contain → errors 记录，跳过整行。"""
    buf = _build_edge_import_xlsx([
        {"code": "et_bad_sem", "name": "非法语义", "semantic": "invalid_sem"},
        {"code": "et_ok_sem", "name": "合法", "semantic": "connect"},
    ])

    r = client.post(
        "/admin/api/edge-types/import",
        files={"file": ("test.xlsx", buf,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["created"] == 1  # 只有 et_ok_sem 被创建
    assert any("invalid_sem" in e for e in data["errors"])

    lst = client.get("/admin/api/edge-types").json()["data"]["items"]
    codes = [it["code"] for it in lst]
    assert "et_ok_sem" in codes
    assert "et_bad_sem" not in codes


def test_import_text_field_missing_maxlen_defaults_to_255(client):
    """text 字段最大长度为空 → 落库 255。"""
    buf = _build_edge_import_xlsx([
        {"code": "et_imp_mx", "name": "空长度",
         "fields": [
             {"fieldKey": "note", "fieldLabel": "备注",
              "fieldType": "text", "maxLength": None, "sortOrder": 0}
         ]},
    ])

    r = client.post(
        "/admin/api/edge-types/import",
        files={"file": ("test.xlsx", buf,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert r.status_code == 200
    lst = client.get("/admin/api/edge-types").json()["data"]["items"]
    match = next(it for it in lst if it["code"] == "et_imp_mx")
    detail = client.get(f"/admin/api/edge-types/{match['id']}").json()["data"]
    note = next(f for f in detail["fields"] if f["fieldKey"] == "note")
    assert note["maxLength"] == 255


def test_import_allow_codes_unknown_node_code_records_warning(client):
    """allow_source/target 引用不存在的 node_type code → warning，字符串仍保存。"""
    # 种一个已知的 node_type
    r = client.post("/admin/api/node-types", json={
        "code": "known_node", "name": "已知节点", "category": "physical",
    })
    assert r.status_code == 200, r.text

    buf = _build_edge_import_xlsx([
        {"code": "et_allow", "name": "白名单",
         "allow_source": "known_node,ghost_node",
         "allow_target": "another_ghost"},
    ])

    r = client.post(
        "/admin/api/edge-types/import",
        files={"file": ("test.xlsx", buf,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["created"] == 1
    assert any("ghost_node" in e for e in data["errors"])
    assert any("another_ghost" in e for e in data["errors"])

    lst = client.get("/admin/api/edge-types").json()["data"]["items"]
    match = next(it for it in lst if it["code"] == "et_allow")
    # 字符串仍保存
    assert match["allowSourceTypeCodes"] == "known_node,ghost_node"
    assert match["allowTargetTypeCodes"] == "another_ghost"


def test_import_partial_failure_isolated_per_row(client):
    """某边类型字段解析失败不影响其他边类型。"""
    buf = _build_edge_import_xlsx([
        {"code": "et_imp_ok", "name": "正常",
         "fields": [
             {"fieldKey": "level", "fieldLabel": "级别",
              "fieldType": "text", "maxLength": 20, "sortOrder": 0},
         ]},
        {"code": "et_imp_bad", "name": "含错误字段",
         "fields": [
             {"fieldKey": "bad", "fieldLabel": "坏",
              "fieldType": "not_a_type", "sortOrder": 0},
         ]},
        {"code": "et_imp_ok2", "name": "又正常",
         "fields": [
             {"fieldKey": "count", "fieldLabel": "计数",
              "fieldType": "number", "sortOrder": 0},
         ]},
    ])

    r = client.post(
        "/admin/api/edge-types/import",
        files={"file": ("test.xlsx", buf,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["created"] == 3  # 3 个边类型都创建
    assert data["totalFields"] == 2  # 只有 2 个字段成功
    assert len(data["errors"]) >= 1
```

- [ ] **Step 2: 跑测试确认 FAIL**

Run: `cd backend && python -m pytest tests/test_edge_type_excel.py -v -k "import and not preview"`
Expected: 7 个测试 FAIL

- [ ] **Step 3: 在 `backend/app/admin/node_type.py` 中，preview 端点之后追加正式导入端点**

在 `preview_edge_types_import` 端点之后追加：

```python
@router.post("/edge-types/import")
async def import_edge_types(file: UploadFile = File(...)):
    if not file.filename or not file.filename.endswith('.xlsx'):
        raise HTTPException(
            status_code=400,
            detail={"code": 40310, "message": "仅支持 .xlsx 文件"},
        )

    contents = await file.read()
    wb = _load_import_workbook(contents, "边类型汇总")
    ws = wb["边类型汇总"]
    result = EdgeTypeImportResult()

    _IDENT_RE_EDGE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

    with transaction() as conn:
        headers = _build_header_map(ws)
        # 预取所有 node_type.code 集合用于 allow_codes 引用校验
        known_node_codes = {
            r["code"] for r in conn.execute("SELECT code FROM node_types").fetchall()
        }

        for row in ws.iter_rows(min_row=2, values_only=True):
            if all(v is None or v == '' for v in row):
                break
            code = _col(headers, "Code", row)
            name = _col(headers, "名称", row)
            if not code or not name:
                result.errors.append(f"Code={code or '(空)'} 缺少必填字段（Code/名称），跳过")
                continue

            semantic_raw = _col(headers, "语义", row) or "connect"
            semantic = semantic_raw.strip().lower()
            if semantic not in ("connect", "contain"):
                result.errors.append(
                    f"[{code}] 语义 '{semantic_raw}' 非法（仅支持 connect/contain），跳过整行"
                )
                continue

            directed = 1 if _col(headers, "有向", row) == "是" else 0
            exclusive_target = 1 if _col(headers, "唯一目标", row) == "是" else 0
            allow_source_raw = _col(headers, "允许源类型", row)
            allow_target_raw = _col(headers, "允许目标类型", row)
            line_style = _col(headers, "线条样式", row)
            color = _col(headers, "颜色", row)
            description = _col(headers, "描述", row)

            # allow_codes 引用校验（warning-only，仍保存字符串）
            for kind, raw in [("源", allow_source_raw), ("目标", allow_target_raw)]:
                if raw:
                    for c in [x.strip() for x in raw.split(",") if x.strip()]:
                        if c not in known_node_codes:
                            result.errors.append(
                                f"[{code}] 允许{kind}类型 '{c}' 不存在的节点类型 code，字符串仍保存"
                            )

            existing = conn.execute(
                "SELECT id FROM edge_types WHERE code = ?", (code,)
            ).fetchone()

            if existing:
                type_id = existing["id"]
                conn.execute(
                    """UPDATE edge_types SET name=?, semantic=?, directed=?, exclusive_target=?,
                       allow_source_type_codes=?, allow_target_type_codes=?, line_style=?,
                       color=?, description=?, updated_at=datetime('now')
                       WHERE id=?""",
                    (name, semantic, directed, exclusive_target,
                     allow_source_raw, allow_target_raw, line_style, color,
                     description, type_id),
                )
                result.updated += 1
            else:
                type_id = _new_edge_id()
                conn.execute(
                    """INSERT INTO edge_types
                       (id, code, name, semantic, directed, exclusive_target,
                        allow_source_type_codes, allow_target_type_codes,
                        line_style, color, description)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (type_id, code, name, semantic, directed, exclusive_target,
                     allow_source_raw, allow_target_raw, line_style, color, description),
                )
                result.created += 1

            sheet_name = _safe_sheet_name(code)
            if sheet_name in wb.sheetnames:
                conn.execute(
                    "DELETE FROM edge_type_fields WHERE edge_type_id = ?",
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
                    if not _IDENT_RE_EDGE.match(fkey):
                        result.errors.append(
                            f"[{code}] 字段标识 {fkey} 非法（仅支持字母/数字/下划线），跳过"
                        )
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
                            f"[{code}] 字段 {fkey} 类型 '{ftype_raw}' 无效，跳过"
                        )
                        continue

                    maxlen_raw = _col(fheaders, "最大长度", frow)
                    if ftype == 'text':
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
                        """INSERT INTO edge_type_fields
                           (edge_type_id, field_key, field_label, field_type,
                            max_length, default_value, options, required, sort_order)
                           VALUES (?,?,?,?,?,?,?,?,?)""",
                        (type_id, fkey, flabel, ftype, maxlen, defval, opts, req, sort),
                    )
                    result.total_fields += 1

    return {
        "code": 0,
        "data": result.model_dump(mode="json", by_alias=True),
        "message": "ok",
    }
```

- [ ] **Step 4: 跑测试确认 PASS**

Run: `cd backend && python -m pytest tests/test_edge_type_excel.py -v`
Expected: 全部 pass（5 export + 3 preview + 7 import = 15 tests）

- [ ] **Step 5: 跑全套确认不回归**

Run: `cd backend && python -m pytest tests/ -q --tb=short`
Expected: 全部 pass

- [ ] **Step 6: Commit**

```bash
git add backend/app/admin/node_type.py backend/tests/test_edge_type_excel.py
git commit -m "$(cat <<'EOF'
feat(edge-type): Excel 正式导入端点

- POST /edge-types/import: multipart 上传 xlsx
- code 存在 → UPDATE 主表 + DELETE&INSERT 字段
- code 不存在 → INSERT 新边类型
- 语义非 connect/contain → errors 记录跳过整行
- 有向/唯一目标 '是'→True 其他→False
- allow_codes 引用不存在 node_type code → warning 但字符串仍保存
- text max_length 空/非法 → 兜底 255
- 行级隔离：一行错误不影响其他行

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: 前端 API 层

**Files:**
- Modify: `frontend/src/api/types.ts:242-243`

- [ ] **Step 1: 编辑 `frontend/src/api/types.ts`**

首先确保文件顶部 import 有 `http`。查找现有的：
```typescript
import http from './http'
import { apiGet, apiPost, apiPut, apiDelete } from './http'
```
（如果已经这样合并了，无需改动；否则统一成上面格式。）

在 `EdgeTypeUpdate` interface 之后（`export const edgeTypeApi` 之前），追加 3 个 interface：

```typescript
export interface EdgeTypeImportPreviewItem {
  code: string
  name: string
  oldName?: string | null
}

export interface EdgeTypeImportPreview {
  toCreate: EdgeTypeImportPreviewItem[]
  toUpdate: EdgeTypeImportPreviewItem[]
  errors: string[]
}

export interface EdgeTypeImportResult {
  created: number
  updated: number
  totalFields: number
  errors: string[]
}
```

然后替换 `edgeTypeApi.export` 方法（原第 242-243 行）:

```typescript
  export: (ids?: string[]): Promise<Blob> =>
    http.post('/edge-types/export', { ids }, { responseType: 'blob' }).then(r => r.data),
```

并在 `edgeTypeApi.export` 之后追加两个新方法：

```typescript
  importPreview: (file: File): Promise<EdgeTypeImportPreview> => {
    const form = new FormData()
    form.append('file', file)
    return http.post('/edge-types/import/preview', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then(r => r.data.data)
  },

  import: (file: File): Promise<EdgeTypeImportResult> => {
    const form = new FormData()
    form.append('file', file)
    return http.post('/edge-types/import', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then(r => r.data.data)
  },
```

- [ ] **Step 2: TypeScript 编译检查**

Run: `cd frontend && npx vue-tsc --noEmit`
Expected: 会出现错误 —— 因为 `EdgeTypeTable.vue` 里还在按旧签名调用 `edgeTypeApi.export(ids)`（期望返回 `{items: []}`）；这些错误将在 Task 6 修复。仅忽略 EdgeTypeTable.vue 相关的错误。

如果有其他文件里也调用 `edgeTypeApi.export`，需要一并 grep 检查，本次改动只涉及 EdgeTypeTable.vue：

Run: `cd frontend && grep -rn "edgeTypeApi\.export" src/ 2>&1`
Expected: 只出现在 `src/components/types/EdgeTypeTable.vue`

- [ ] **Step 3: 暂不 commit**

跳过 commit，Task 6 一起 commit。

---

## Task 6: 前端 EdgeTypeTable UI

**Files:**
- Modify: `frontend/src/components/types/EdgeTypeTable.vue` (整个文件)

- [ ] **Step 1: 替换整个 `frontend/src/components/types/EdgeTypeTable.vue`**

```vue
<script setup lang="ts">
import { ref, computed, h } from 'vue'
import {
  PlusOutlined, EditOutlined, DeleteOutlined,
  ExportOutlined, ImportOutlined, DownOutlined,
} from '@ant-design/icons-vue'
import { message, Modal, Menu, MenuItem } from 'ant-design-vue'
import EdgeTypeModal from './EdgeTypeModal.vue'
import { useEdgeTypes, useNodeTypes } from '@/composables/useTypes'
import { edgeTypeApi } from '@/api/types'
import { downloadBlob, timestampExcelFilename } from '@/utils/download'
import type {
  EdgeTypeDetail, EdgeTypeCreate, EdgeTypeUpdate,
  EdgeTypeImportPreview,
} from '@/api/types'

const {
  edgeTypes,
  edgeTypesLoading,
  fetchEdgeTypes,
  createEdgeType,
  updateEdgeType,
  deleteEdgeType,
  deleteEdgeTypes,
} = useEdgeTypes()

const { nodeTypes, fetchNodeTypes } = useNodeTypes()

defineExpose({ refresh: fetchEdgeTypes })

const modalOpen = ref(false)
const modalEditing = ref<EdgeTypeDetail | null>(null)
const modalLoading = ref(false)
const fileInputRef = ref<HTMLInputElement | null>(null)

function openCreate() {
  modalEditing.value = null
  modalOpen.value = true
}

function openEdit(item: EdgeTypeDetail) {
  modalEditing.value = item
  modalOpen.value = true
}

async function handleCreate(data: EdgeTypeCreate) {
  modalLoading.value = true
  try {
    await createEdgeType(data)
    message.success('创建成功')
    modalOpen.value = false
  } finally {
    modalLoading.value = false
  }
}

async function handleUpdate(id: string, data: EdgeTypeUpdate) {
  modalLoading.value = true
  try {
    await updateEdgeType(id, data)
    message.success('更新成功')
    modalOpen.value = false
  } finally {
    modalLoading.value = false
  }
}

async function handleDelete(item: EdgeTypeDetail) {
  try {
    await deleteEdgeType(item.id)
    message.success('删除成功')
  } catch {}
}

const selectedRowKeys = ref<string[]>([])
const searchText = ref('')

const filteredEdgeTypes = computed(() => {
  const kw = searchText.value.trim().toLowerCase()
  if (!kw) return edgeTypes.value
  return edgeTypes.value.filter(et =>
    et.code.toLowerCase().includes(kw) ||
    et.name.toLowerCase().includes(kw) ||
    (et.description ?? '').toLowerCase().includes(kw)
  )
})

async function handleExport(ids?: string[]) {
  try {
    const blob = await edgeTypeApi.export(ids)
    downloadBlob(blob, timestampExcelFilename('edge-types-export'))
    message.success('导出成功')
  } catch {}
}

function handleExportMenuClick({ key }: { key: string }) {
  if (key === 'all') {
    handleExport()
  } else if (key === 'selected') {
    if (selectedRowKeys.value.length === 0) {
      message.warning('请先勾选要导出的边类型')
      return
    }
    handleExport(selectedRowKeys.value)
  }
}

function handleImportClick() {
  fileInputRef.value?.click()
}

async function handleFileChosen(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return

  let preview: EdgeTypeImportPreview
  try {
    preview = await edgeTypeApi.importPreview(file)
  } catch {
    return
  }

  const children: ReturnType<typeof h>[] = []

  if (preview.toCreate.length) {
    children.push(
      h('div', { style: { fontWeight: 'bold', marginBottom: '4px' } },
        `将新建（${preview.toCreate.length} 个）：`),
      ...preview.toCreate.map(item =>
        h('div', { style: { paddingLeft: '8px' } },
          `• ${item.code}（${item.name || item.code}）`),
      ),
    )
  }

  if (preview.toUpdate.length) {
    if (children.length) children.push(h('br'))
    children.push(
      h('div', { style: { fontWeight: 'bold', marginBottom: '4px' } },
        `将覆盖（字段将被替换）（${preview.toUpdate.length} 个）：`),
      ...preview.toUpdate.map(item => {
        const nameChanged = item.oldName && item.oldName !== item.name
        const text = nameChanged
          ? `• ${item.code}（${item.oldName} → ${item.name}）`
          : `• ${item.code}（${item.name || item.code}）`
        return h('div', { style: { paddingLeft: '8px' } }, text)
      }),
    )
  }

  if (preview.errors.length) {
    if (children.length) children.push(h('br'))
    children.push(
      h('div', { style: { color: '#faad14' } },
        `⚠ 有 ${preview.errors.length} 行因缺少必填字段将被跳过。`),
    )
  }

  if (preview.toUpdate.length > 0) {
    Modal.confirm({
      title: '确认导入',
      content: h('div', { style: { lineHeight: '1.8' } }, children),
      okText: '确认导入',
      cancelText: '取消',
      width: 480,
      onOk: () => doImport(file),
    })
  } else {
    await doImport(file)
  }
}

async function doImport(file: File) {
  try {
    const result = await edgeTypeApi.import(file)
    const parts: string[] = []
    if (result.created) parts.push(`新建 ${result.created} 个`)
    if (result.updated) parts.push(`更新 ${result.updated} 个`)
    parts.push(`导入 ${result.totalFields} 个字段`)
    message.success(parts.join('，'))
    if (result.errors.length) {
      message.warning(result.errors.slice(0, 3).join('；') + (result.errors.length > 3 ? '…' : ''))
    }
    fetchEdgeTypes()
  } catch {}
}

async function handleBatchDelete() {
  if (selectedRowKeys.value.length === 0) return
  try {
    const result = await deleteEdgeTypes(selectedRowKeys.value)
    if (result.skipped.length > 0) {
      const skippedInfo = result.skipped.map(s => `${s.id}: ${s.reason}`).join('; ')
      message.warning(`部分类型未能删除: ${skippedInfo}`)
    } else {
      message.success(`成功删除 ${result.deletedCount} 个边类型`)
    }
    selectedRowKeys.value = []
  } catch {}
}

fetchEdgeTypes()
fetchNodeTypes()
</script>

<template>
  <div class="edge-type-table">
    <input
      ref="fileInputRef"
      type="file"
      accept=".xlsx"
      style="display: none"
      @change="handleFileChosen"
    />

    <div class="table-toolbar">
      <span class="toolbar-title">边类型</span>
      <a-space>
        <a-input-search
          v-model:value="searchText"
          placeholder="搜索代码/名称/描述"
          allow-clear
          style="width: 220px"
        />
        <a-popconfirm
          :title="`确定删除选中的 ${selectedRowKeys.length} 个边类型？`"
          :disabled="selectedRowKeys.length === 0"
          ok-text="确定"
          cancel-text="取消"
          @confirm="handleBatchDelete"
        >
          <a-button :disabled="selectedRowKeys.length === 0" danger>
            <template #icon><DeleteOutlined /></template>
            批量删除
          </a-button>
        </a-popconfirm>
        <a-dropdown>
          <a-button>
            <template #icon><ExportOutlined /></template>
            批量导出
            <DownOutlined />
          </a-button>
          <template #overlay>
            <Menu @click="handleExportMenuClick">
              <MenuItem key="all">全部导出</MenuItem>
              <MenuItem key="selected" :disabled="selectedRowKeys.length === 0">
                导出选中（{{ selectedRowKeys.length }} 项）
              </MenuItem>
            </Menu>
          </template>
        </a-dropdown>
        <a-button @click="handleImportClick">
          <template #icon><ImportOutlined /></template>
          导入
        </a-button>
        <a-button type="primary" @click="openCreate">
          <template #icon><PlusOutlined /></template>
          新建边类型
        </a-button>
      </a-space>
    </div>

    <a-table
      :dataSource="filteredEdgeTypes"
      :loading="edgeTypesLoading"
      :pagination="{
        defaultPageSize: 10,
        pageSizeOptions: ['10', '20', '50'],
        showSizeChanger: true,
        showTotal: (total: number) => `共 ${total} 条`,
      }"
      rowKey="id"
      :rowSelection="{ selectedRowKeys, onChange: (keys: string[]) => { selectedRowKeys = keys } }"
    >
      <a-table-column title="代码" dataIndex="code" width="140" />
      <a-table-column title="名称" dataIndex="name" width="120" />
      <a-table-column title="语义" dataIndex="semantic" width="100">
        <template #default="{ text }">
          <a-tag>{{ text }}</a-tag>
        </template>
      </a-table-column>
      <a-table-column title="颜色" dataIndex="color" width="80">
        <template #default="{ text }">
          <span v-if="text" class="color-swatch" :style="{ backgroundColor: text }"></span>
          <span v-else class="placeholder">-</span>
        </template>
      </a-table-column>
      <a-table-column title="线条样式" dataIndex="lineStyle" width="90">
        <template #default="{ text }">
          {{ text ?? '-' }}
        </template>
      </a-table-column>
      <a-table-column title="有向" dataIndex="directed" width="60">
        <template #default="{ text }">
          <a-tag :color="text ? 'blue' : 'default'">{{ text ? '是' : '否' }}</a-tag>
        </template>
      </a-table-column>
      <a-table-column title="唯一目标" dataIndex="exclusiveTarget" width="90">
        <template #default="{ text }">
          <a-tag :color="text ? 'orange' : 'default'">{{ text ? '是' : '否' }}</a-tag>
        </template>
      </a-table-column>
      <a-table-column title="字段数" dataIndex="fields" width="80">
        <template #default="{ text }">
          {{ text?.length ?? 0 }}
        </template>
      </a-table-column>
      <a-table-column title="操作" width="160" fixed="right">
        <template #default="{ record }">
          <a-space>
            <a-button type="link" size="small" @click="openEdit(record)">
              <template #icon><EditOutlined /></template>
            </a-button>
            <a-popconfirm
              title="确定删除该边类型？"
              ok-text="确定"
              cancel-text="取消"
              @confirm="handleDelete(record)"
            >
              <a-button type="link" size="small" danger>
                <template #icon><DeleteOutlined /></template>
              </a-button>
            </a-popconfirm>
          </a-space>
        </template>
      </a-table-column>

    </a-table>

    <EdgeTypeModal
      v-model:open="modalOpen"
      :editing="modalEditing"
      :loading="modalLoading"
      :node-types="nodeTypes"
      @create="handleCreate"
      @update="handleUpdate"
    />
  </div>
</template>

<style scoped>
.edge-type-table {
  margin-bottom: 32px;
}

.table-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.toolbar-title {
  font-size: 16px;
  font-weight: 500;
  color: rgba(0, 0, 0, 0.85);
}

.color-swatch {
  display: inline-block;
  width: 20px;
  height: 20px;
  border-radius: 4px;
  border: 1px solid rgba(0, 0, 0, 0.1);
}

.placeholder {
  color: rgba(0, 0, 0, 0.25);
}
</style>
```

- [ ] **Step 2: TypeScript 编译检查**

Run: `cd frontend && npx vue-tsc --noEmit`
Expected: 0 errors

- [ ] **Step 3: 前端 dev 启动验证（可选）**

Run: `cd frontend && npm run dev`（后台）
浏览器访问类型管理 → 边类型：
- 建 2 边类型 → "批量导出 → 全部导出" → 下载 xlsx，打开验证含"边类型汇总" + 2 个 code Sheet
- 勾选 1 个 → "批量导出 → 导出选中（1 项）" → xlsx 只含 1 个
- 手动修改 xlsx 后点"导入" → 选文件 → preview 弹窗 → 确认 → 结果 toast
- 停止 dev server

- [ ] **Step 4: Commit（合并 Task 5、6）**

```bash
git add frontend/src/api/types.ts frontend/src/components/types/EdgeTypeTable.vue
git commit -m "$(cat <<'EOF'
feat(edge-type-ui): EdgeTypeTable 集成 Excel 导入导出

- api/types: edgeTypeApi.export 改签名返回 Blob；新增 importPreview/import 方法
  和 EdgeTypeImportPreviewItem/Preview/Result 3 interface
- EdgeTypeTable: 顶部工具栏"批量导出"改成 Dropdown（全部/选中）+ 加"导入"按钮
- 隐藏 <input type="file" accept=".xlsx"> + handleFileChosen 走 preview 弹窗
- 导入用 Modal.confirm 内联渲染 VNode 预览（toCreate/toUpdate/errors）
- 与节点类型/告警模板导入交互模式一致
- 删除 downloadJson 依赖（原 JSON 导出彻底移除）

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## 收尾自检

- [ ] 后端全量测试通过

Run: `cd backend && python -m pytest tests/ --tb=short`
Expected: 全部 pass（含新增 15 个 edge_type_excel 测试）

- [ ] 前端 TypeScript 无错

Run: `cd frontend && npx vue-tsc --noEmit`
Expected: 0 errors

- [ ] 前后端联调手动回归

启动后端：`cd backend && python -m app.main`（后台）
启动前端：`cd frontend && npm run dev`（后台）

验证清单：
- 类型管理 → 边类型：建 3 边类型 → 全部导出 → xlsx 结构正确
- 编辑一个改名字 → 导入原 xlsx → preview 显示"将覆盖 3 个"含 oldName → 确认后模板复原
- 建 5 边类型勾选 2 个 → 导出选中 → xlsx 只含 2 个
- 手动改 xlsx 加新 code → 导入 → preview 显示"将新建 1 个 / 将覆盖 N 个"
- 手动改 xlsx "语义" 列为 `invalid` → 导入 → 结果 warning 提示

停止后端和前端进程。

- [ ] Commit + Push（可选）

若所有验证通过：`git push origin main`

---

## 记录

**关联 spec**：`docs/superpowers/specs/2026-07-05-edge-type-excel-io-design.md`

**估算工时**：6 个任务，每任务 15-30 分钟，总计约 2-4 小时（含手动回归）
