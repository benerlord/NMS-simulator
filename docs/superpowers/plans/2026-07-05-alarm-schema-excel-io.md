# 告警模板 Excel 导入导出 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为告警模板（alarm_schemas）加 Excel 多 Sheet 导出/导入端点及前端 UI，格式与节点类型对齐（模板汇总 Sheet + 每 code 独立字段 Sheet），支持 preview 弹窗确认覆盖。

**Architecture:**
- 后端在 `backend/app/admin/alarm_schema.py` 内联 openpyxl 工具（`_safe_sheet_name` / `_build_header_map` / `_col` / `_load_import_workbook` / `_build_alarm_schemas_excel`）+ 3 个新端点（`POST /export` / `POST /import/preview` / `POST /import`）
- 前端 `api/alarmSchema.ts` 加 3 个方法；`AlarmSchemaTable.vue` 顶部工具栏加"批量导出 Dropdown + 导入按钮"，导入用 `Modal.confirm` 内联渲染 VNode 预览
- 导入策略：text max_length 空/非法兜底 255；code 存在则覆盖（DELETE + INSERT 字段）；display_field_key/mapping_target 不校验引用完整性；行级隔离（一行失败不影响其他行）

**Tech Stack:** FastAPI + SQLite + openpyxl + Pydantic v2 CamelModel + Vue 3.5 `<script setup>` + Ant Design Vue 4 + pytest

---

## File Structure

**新建：**
- `backend/tests/test_alarm_schema_excel.py` — 后端 e2e 测试（导出 + preview + 导入）

**修改后端：**
- `backend/app/admin/schemas/alarm.py` — 新增 4 个 Pydantic 类
- `backend/app/admin/schemas/__init__.py` — 导出新类
- `backend/app/admin/alarm_schema.py` — 新增 5 个内联工具 + 3 个端点

**修改前端：**
- `frontend/src/api/alarmSchema.ts` — 新增 3 个 interface + 3 个 API 方法
- `frontend/src/components/alarmSchemas/AlarmSchemaTable.vue` — 顶部工具栏 + rowSelection + 导入/导出处理函数

**依赖顺序：**
- Task 1（Schema 类）→ Task 2/3/4（Route 端点）
- Task 2/3/4 全后端完成 → Task 5（前端 API）→ Task 6（前端组件）

---

## Task 1: 后端 Schema — 4 个 Pydantic 类

**Files:**
- Modify: `backend/app/admin/schemas/alarm.py`
- Modify: `backend/app/admin/schemas/__init__.py`

- [ ] **Step 1: 在 `schemas/alarm.py` 末尾追加 4 个 Schema 类**

```python
# --- alarm_schema Excel I/O ---

class AlarmSchemaExportRequest(CamelModel):
    ids: Optional[list[str]] = Field(default=None)


class AlarmSchemaImportPreviewItem(CamelModel):
    code: str
    name: str
    old_name: Optional[str] = None


class AlarmSchemaImportPreview(CamelModel):
    to_create: list[AlarmSchemaImportPreviewItem] = Field(default_factory=list)
    to_update: list[AlarmSchemaImportPreviewItem] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class AlarmSchemaImportResult(CamelModel):
    created: int = 0
    updated: int = 0
    total_fields: int = 0
    errors: list[str] = Field(default_factory=list)
```

- [ ] **Step 2: 在 `schemas/__init__.py` 的 `from .alarm import (...)` 导入块里追加 4 个类名**

打开 `backend/app/admin/schemas/__init__.py`，找到 `from .alarm import (` 块（当前包含 `AlarmSchemaCreate` 等），在该块内部末尾追加：

```python
    AlarmSchemaExportRequest,
    AlarmSchemaImportPreviewItem,
    AlarmSchemaImportPreview,
    AlarmSchemaImportResult,
```

并在文件末尾 `__all__` 列表里追加：

```python
    "AlarmSchemaExportRequest",
    "AlarmSchemaImportPreviewItem",
    "AlarmSchemaImportPreview",
    "AlarmSchemaImportResult",
```

- [ ] **Step 3: 快速 import 验证**

Run: `cd backend && python -c "from app.admin.schemas import AlarmSchemaExportRequest, AlarmSchemaImportPreviewItem, AlarmSchemaImportPreview, AlarmSchemaImportResult; print('ok')"`
Expected: `ok`

- [ ] **Step 4: 确认既有测试无回归**

Run: `cd backend && python -m pytest tests/ -q --tb=short`
Expected: 全部 pass（Schema 层新增字段不影响已有逻辑）

- [ ] **Step 5: Commit**

```bash
git add backend/app/admin/schemas/alarm.py backend/app/admin/schemas/__init__.py
git commit -m "$(cat <<'EOF'
feat(alarm-schema): 新增 Excel 导入导出 Pydantic Schema 类

- AlarmSchemaExportRequest: 导出请求
- AlarmSchemaImportPreviewItem / AlarmSchemaImportPreview: preview 响应
- AlarmSchemaImportResult: 正式导入响应

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: 后端导出端点

**Files:**
- Modify: `backend/app/admin/alarm_schema.py`
- Create: `backend/tests/test_alarm_schema_excel.py`

- [ ] **Step 1: 创建测试文件 `backend/tests/test_alarm_schema_excel.py`**

```python
"""告警模板 Excel 导入导出 e2e 测试。"""
import io

import openpyxl


def _create_schema(client, code: str, name: str, description: str = "",
                    display_field_key: str = None, fields: list = None) -> str:
    payload = {
        "code": code,
        "name": name,
        "description": description,
        "displayFieldKey": display_field_key,
        "fields": fields or [
            {"fieldKey": "level", "fieldLabel": "级别", "fieldType": "text",
             "maxLength": 20, "required": True, "sortOrder": 0}
        ],
    }
    r = client.post("/admin/api/alarm-schemas", json=payload)
    assert r.status_code == 200, r.text
    return r.json()["data"]["id"]


# ============== 导出测试 ==============

def test_export_all_returns_xlsx_with_summary_sheet(client):
    """导出全部 → xlsx 含'模板汇总' Sheet + 每 code 独立字段 Sheet。"""
    _create_schema(client, "as_a", "模板A")
    _create_schema(client, "as_b", "模板B")

    r = client.post("/admin/api/alarm-schemas/export", json={})
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    wb = openpyxl.load_workbook(io.BytesIO(r.content))
    assert "模板汇总" in wb.sheetnames
    assert "as_a" in wb.sheetnames
    assert "as_b" in wb.sheetnames


def test_export_ids_only_returns_selected(client):
    """按 ids 导出 → xlsx 只含指定模板。"""
    sid_a = _create_schema(client, "as_only_a", "只A")
    _create_schema(client, "as_only_b", "只B")

    r = client.post("/admin/api/alarm-schemas/export", json={"ids": [sid_a]})
    assert r.status_code == 200
    wb = openpyxl.load_workbook(io.BytesIO(r.content))
    assert "as_only_a" in wb.sheetnames
    assert "as_only_b" not in wb.sheetnames


def test_export_summary_contains_display_field_key_column(client):
    """汇总 Sheet 表头含'展示字段Key'列，值正确。"""
    _create_schema(
        client, "as_disp", "模板显示", display_field_key="level",
        fields=[
            {"fieldKey": "level", "fieldLabel": "级别", "fieldType": "text",
             "maxLength": 20, "required": True, "sortOrder": 0}
        ],
    )

    r = client.post("/admin/api/alarm-schemas/export", json={})
    wb = openpyxl.load_workbook(io.BytesIO(r.content))
    ws = wb["模板汇总"]
    headers = [c.value for c in ws[1] if c.value]
    assert "展示字段Key" in headers

    # 找到 as_disp 行
    idx = {h: i for i, h in enumerate(headers)}
    code_col = idx["Code"] + 1
    disp_col = idx["展示字段Key"] + 1
    found = None
    for row in ws.iter_rows(min_row=2, values_only=False):
        if row[code_col - 1].value == "as_disp":
            found = row[disp_col - 1].value
            break
    assert found == "level"


def test_export_field_sheet_contains_mapping_target_column(client):
    """每模板字段 Sheet 表头含'映射节点属性'列，值正确。"""
    _create_schema(
        client, "as_map", "映射模板",
        fields=[
            {"fieldKey": "severity", "fieldLabel": "严重度",
             "fieldType": "text", "maxLength": 20,
             "mappingTarget": "node_severity", "sortOrder": 0}
        ],
    )

    r = client.post("/admin/api/alarm-schemas/export", json={})
    wb = openpyxl.load_workbook(io.BytesIO(r.content))
    ws = wb["as_map"]
    headers = [c.value for c in ws[1] if c.value]
    assert "映射节点属性" in headers

    idx = {h: i for i, h in enumerate(headers)}
    map_col_1based = idx["映射节点属性"] + 1
    assert ws.cell(row=2, column=map_col_1based).value == "node_severity"
```

- [ ] **Step 2: 跑测试确认 FAIL**

Run: `cd backend && python -m pytest tests/test_alarm_schema_excel.py -v -k "export"`
Expected: 4 个测试全部 FAIL（`/admin/api/alarm-schemas/export` 端点尚未存在，404 或 405）

- [ ] **Step 3: 修改 `backend/app/admin/alarm_schema.py`**

在文件顶部 import 区补充：

```python
import re
from io import BytesIO

from fastapi import UploadFile, File
from fastapi.responses import StreamingResponse
from openpyxl import Workbook, load_workbook
```

同时在原有 `from app.admin.schemas import (...)` 里追加：

```python
    AlarmSchemaExportRequest,
    AlarmSchemaImportPreviewItem,
    AlarmSchemaImportPreview,
    AlarmSchemaImportResult,
```

在文件底部（现有 `delete_alarm_schema` 之后）追加内联工具 + 导出端点：

```python
# ============== Excel 导入导出 ==============

_SHEET_INVALID_CHARS = re.compile(r'[\\\*/\[\]\?:]')


def _safe_sheet_name(code: str) -> str:
    name = _SHEET_INVALID_CHARS.sub('_', code)
    if len(name) > 31:
        name = name[:28] + "..."
    return name


def _build_alarm_schemas_excel(items: list[dict]) -> BytesIO:
    wb = Workbook()

    ws1 = wb.active
    ws1.title = "模板汇总"
    ws1.append(["Code", "名称", "描述", "展示字段Key",
                "字段数", "创建时间", "更新时间"])
    for item in items:
        ws1.append([
            item.get("code"),
            item.get("name"),
            item.get("description"),
            item.get("displayFieldKey"),
            len(item.get("fields") or []),
            item.get("createdAt"),
            item.get("updatedAt"),
        ])

    for item in items:
        fields = item.get("fields") or []
        sheet_name = _safe_sheet_name(item.get("code", item.get("id", "unknown")))
        ws = wb.create_sheet(title=sheet_name)
        ws.append(["字段标识", "显示名称", "字段类型", "最大长度",
                    "默认值", "选项", "必填", "排序", "映射节点属性"])
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
                f.get("mappingTarget"),
            ])

    output = BytesIO()
    wb.save(output)
    output.seek(0)
    return output


@router.post("/alarm-schemas/export")
def export_alarm_schemas(data: AlarmSchemaExportRequest):
    with connect() as conn:
        if data.ids:
            placeholders = ",".join("?" for _ in data.ids)
            rows = conn.execute(
                f"SELECT * FROM alarm_schemas WHERE id IN ({placeholders}) ORDER BY created_at DESC",
                tuple(data.ids),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM alarm_schemas ORDER BY created_at DESC"
            ).fetchall()
        items = []
        for r in rows:
            detail = _row_to_detail(conn, r)
            items.append(detail.model_dump(mode="json", by_alias=True))

    excel = _build_alarm_schemas_excel(items)
    return StreamingResponse(
        excel,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=alarm-schemas-export.xlsx"},
    )
```

- [ ] **Step 4: 跑测试确认 PASS**

Run: `cd backend && python -m pytest tests/test_alarm_schema_excel.py -v -k "export"`
Expected: 4 passed

- [ ] **Step 5: 跑全套确认不回归**

Run: `cd backend && python -m pytest tests/ -q --tb=short`
Expected: 全部 pass

- [ ] **Step 6: Commit**

```bash
git add backend/app/admin/alarm_schema.py backend/tests/test_alarm_schema_excel.py
git commit -m "$(cat <<'EOF'
feat(alarm-schema): Excel 导出端点 + 多 Sheet 结构

- 汇总 Sheet: Code / 名称 / 描述 / 展示字段Key / 字段数 / 时间
- 每模板字段 Sheet: field_key / label / type / maxLen / default / options / required / sort / 映射节点属性
- 支持全部导出或按 ids 过滤

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: 后端导入 preview 端点

**Files:**
- Modify: `backend/app/admin/alarm_schema.py`
- Modify: `backend/tests/test_alarm_schema_excel.py` (追加测试)

- [ ] **Step 1: 在 `test_alarm_schema_excel.py` 末尾追加测试**

```python
# ============== 导入 preview 测试 ==============

def _build_import_xlsx(rows: list[dict]) -> io.BytesIO:
    """构造一份最小导入 xlsx。rows: [{code, name, description, displayFieldKey, fields: [...]}]"""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "模板汇总"
    ws.append(["Code", "名称", "描述", "展示字段Key"])
    for r in rows:
        ws.append([r.get("code"), r.get("name"), r.get("description"), r.get("displayFieldKey")])

    for r in rows:
        code = r.get("code")
        fields = r.get("fields") or [
            {"fieldKey": "level", "fieldLabel": "级别", "fieldType": "text",
             "maxLength": 20, "required": True, "sortOrder": 0}
        ]
        fs = wb.create_sheet(title=code)
        fs.append(["字段标识", "显示名称", "字段类型", "最大长度",
                    "默认值", "选项", "必填", "排序", "映射节点属性"])
        for f in fields:
            fs.append([
                f.get("fieldKey"), f.get("fieldLabel"), f.get("fieldType"),
                f.get("maxLength"), f.get("defaultValue"), f.get("options"),
                "是" if f.get("required") else "否",
                f.get("sortOrder", 0), f.get("mappingTarget"),
            ])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def test_import_preview_categorizes_create_and_update(client):
    """已存在 code → toUpdate；不存在 → toCreate。"""
    _create_schema(client, "as_exists", "已存在")
    buf = _build_import_xlsx([
        {"code": "as_exists", "name": "已存在改名"},
        {"code": "as_new_1", "name": "新1"},
        {"code": "as_new_2", "name": "新2"},
    ])

    r = client.post(
        "/admin/api/alarm-schemas/import/preview",
        files={"file": ("test.xlsx", buf,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]

    to_create_codes = [item["code"] for item in data["toCreate"]]
    to_update_codes = [item["code"] for item in data["toUpdate"]]
    assert sorted(to_create_codes) == ["as_new_1", "as_new_2"]
    assert to_update_codes == ["as_exists"]


def test_import_preview_records_old_name_on_update(client):
    """覆盖项 oldName 与新 name 不同时正确记录。"""
    _create_schema(client, "as_rename", "旧名字")
    buf = _build_import_xlsx([
        {"code": "as_rename", "name": "新名字"},
    ])

    r = client.post(
        "/admin/api/alarm-schemas/import/preview",
        files={"file": ("test.xlsx", buf,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert r.status_code == 200
    item = r.json()["data"]["toUpdate"][0]
    assert item["code"] == "as_rename"
    assert item["name"] == "新名字"
    assert item["oldName"] == "旧名字"


def test_import_preview_missing_summary_sheet_returns_400(client):
    """缺'模板汇总' Sheet → 400。"""
    wb = openpyxl.Workbook()
    wb.active.title = "OtherSheet"
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    r = client.post(
        "/admin/api/alarm-schemas/import/preview",
        files={"file": ("bad.xlsx", buf,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert r.status_code == 400
    assert "模板汇总" in r.json()["detail"]["message"]


def test_import_preview_missing_required_records_error(client):
    """Code 或名称缺失的行 → errors 记录。"""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "模板汇总"
    ws.append(["Code", "名称", "描述"])
    ws.append([None, "缺 code 的行", "desc"])
    ws.append(["as_ok", None, "缺 name 的行"])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    r = client.post(
        "/admin/api/alarm-schemas/import/preview",
        files={"file": ("bad.xlsx", buf,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert len(data["errors"]) == 2
    assert data["toCreate"] == []
    assert data["toUpdate"] == []
```

- [ ] **Step 2: 跑测试确认 FAIL**

Run: `cd backend && python -m pytest tests/test_alarm_schema_excel.py -v -k "preview"`
Expected: 4 个测试 FAIL（端点未实现）

- [ ] **Step 3: 在 `alarm_schema.py` 追加内联工具 + preview 端点**

在 `_build_alarm_schemas_excel` 之后追加：

```python
def _build_header_map(ws) -> dict[str, int]:
    """读取第 1 行构建 {表头名: 列索引}，空返回 {}."""
    row = next(ws.iter_rows(min_row=1, max_row=1, values_only=True), None)
    if not row:
        return {}
    return {str(v).strip(): i for i, v in enumerate(row) if v is not None and str(v).strip()}


def _col(headers: dict[str, int], name: str, row: tuple):
    """按表头名取值，找不到列或空值返回 None。"""
    idx = headers.get(name)
    if idx is None or idx >= len(row):
        return None
    val = row[idx]
    if val is None:
        return None
    return str(val).strip() or None


def _load_import_workbook(contents: bytes):
    try:
        wb = load_workbook(filename=BytesIO(contents))
    except Exception:
        raise HTTPException(
            status_code=400,
            detail={"code": 40410, "message": "文件无法解析，请确认是有效的 xlsx 文件"},
        )
    if "模板汇总" not in wb.sheetnames:
        raise HTTPException(
            status_code=400,
            detail={"code": 40411, "message": "缺少「模板汇总」Sheet"},
        )
    return wb


@router.post("/alarm-schemas/import/preview")
async def preview_alarm_schemas_import(file: UploadFile = File(...)):
    if not file.filename or not file.filename.endswith('.xlsx'):
        raise HTTPException(
            status_code=400,
            detail={"code": 40412, "message": "仅支持 .xlsx 文件"},
        )

    contents = await file.read()
    wb = _load_import_workbook(contents)
    ws = wb["模板汇总"]

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
                "SELECT id, name FROM alarm_schemas WHERE code = ?", (code,)
            ).fetchone()

            if existing:
                to_update.append({
                    "code": code,
                    "name": name,
                    "old_name": existing["name"],
                })
            else:
                to_create.append({"code": code, "name": name})

    preview = AlarmSchemaImportPreview(
        to_create=[AlarmSchemaImportPreviewItem(**c) for c in to_create],
        to_update=[AlarmSchemaImportPreviewItem(**u) for u in to_update],
        errors=errors,
    )
    return {"code": 0, "data": preview.model_dump(mode="json", by_alias=True), "message": "ok"}
```

- [ ] **Step 4: 跑测试确认 PASS**

Run: `cd backend && python -m pytest tests/test_alarm_schema_excel.py -v -k "preview"`
Expected: 4 passed

- [ ] **Step 5: 跑全套确认不回归**

Run: `cd backend && python -m pytest tests/ -q --tb=short`
Expected: 全部 pass

- [ ] **Step 6: Commit**

```bash
git add backend/app/admin/alarm_schema.py backend/tests/test_alarm_schema_excel.py
git commit -m "$(cat <<'EOF'
feat(alarm-schema): Excel 导入 preview 端点

- POST /alarm-schemas/import/preview: multipart 上传 xlsx
- 返回 toCreate / toUpdate（含 oldName） / errors 三分类
- 缺'模板汇总' Sheet → 400
- Code/名称缺失记 errors 跳过

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: 后端正式导入端点

**Files:**
- Modify: `backend/app/admin/alarm_schema.py`
- Modify: `backend/tests/test_alarm_schema_excel.py` (追加测试)

- [ ] **Step 1: 在 `test_alarm_schema_excel.py` 末尾追加测试**

```python
# ============== 正式导入测试 ==============

def test_import_creates_new_schema_with_fields(client):
    """新模板 + 字段一起导入。"""
    buf = _build_import_xlsx([
        {"code": "as_imp_new", "name": "导入新",
         "fields": [
             {"fieldKey": "severity", "fieldLabel": "严重度",
              "fieldType": "text", "maxLength": 30, "sortOrder": 0},
             {"fieldKey": "count", "fieldLabel": "计数",
              "fieldType": "number", "sortOrder": 1},
         ]},
    ])

    r = client.post(
        "/admin/api/alarm-schemas/import",
        files={"file": ("test.xlsx", buf,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["created"] == 1
    assert data["updated"] == 0
    assert data["totalFields"] == 2

    r = client.get("/admin/api/alarm-schemas").json()["data"]
    match = next(it for it in r if it["code"] == "as_imp_new")
    detail = client.get(f"/admin/api/alarm-schemas/{match['id']}").json()["data"]
    assert [f["fieldKey"] for f in detail["fields"]] == ["severity", "count"]


def test_import_overwrites_existing_schema(client):
    """已存在 code → name 覆盖，字段全部替换。"""
    _create_schema(
        client, "as_imp_ov", "旧名字",
        fields=[
            {"fieldKey": "old_field", "fieldLabel": "旧字段",
             "fieldType": "text", "maxLength": 10, "sortOrder": 0}
        ],
    )
    buf = _build_import_xlsx([
        {"code": "as_imp_ov", "name": "新名字",
         "fields": [
             {"fieldKey": "new_field", "fieldLabel": "新字段",
              "fieldType": "text", "maxLength": 30, "sortOrder": 0}
         ]},
    ])

    r = client.post(
        "/admin/api/alarm-schemas/import",
        files={"file": ("test.xlsx", buf,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["updated"] == 1
    assert data["created"] == 0

    lst = client.get("/admin/api/alarm-schemas").json()["data"]
    match = next(it for it in lst if it["code"] == "as_imp_ov")
    assert match["name"] == "新名字"
    detail = client.get(f"/admin/api/alarm-schemas/{match['id']}").json()["data"]
    field_keys = [f["fieldKey"] for f in detail["fields"]]
    assert field_keys == ["new_field"]
    assert "old_field" not in field_keys


def test_import_text_field_missing_maxlen_defaults_to_255(client):
    """text 字段最大长度为空 → 落库 255。"""
    buf = _build_import_xlsx([
        {"code": "as_imp_mx", "name": "空长度",
         "fields": [
             {"fieldKey": "note", "fieldLabel": "备注",
              "fieldType": "text", "maxLength": None, "sortOrder": 0}
         ]},
    ])

    r = client.post(
        "/admin/api/alarm-schemas/import",
        files={"file": ("test.xlsx", buf,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert r.status_code == 200
    lst = client.get("/admin/api/alarm-schemas").json()["data"]
    match = next(it for it in lst if it["code"] == "as_imp_mx")
    detail = client.get(f"/admin/api/alarm-schemas/{match['id']}").json()["data"]
    note = next(f for f in detail["fields"] if f["fieldKey"] == "note")
    assert note["maxLength"] == 255


def test_import_invalid_field_type_records_error(client):
    """field_type 非白名单 → errors 记录跳过。"""
    buf = _build_import_xlsx([
        {"code": "as_imp_bad", "name": "有非法类型",
         "fields": [
             {"fieldKey": "good_field", "fieldLabel": "合法",
              "fieldType": "text", "maxLength": 20, "sortOrder": 0},
             {"fieldKey": "bad_field", "fieldLabel": "非法",
              "fieldType": "invalid_type", "sortOrder": 1},
         ]},
    ])

    r = client.post(
        "/admin/api/alarm-schemas/import",
        files={"file": ("test.xlsx", buf,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["created"] == 1
    assert data["totalFields"] == 1  # 只有 good_field 入库
    assert any("invalid_type" in e for e in data["errors"])


def test_import_field_key_conflict_with_fixed_col_records_error(client):
    """field_key 与固定列（id/node_id/alarm_index/created_at/updated_at）冲突 → errors 记录。"""
    buf = _build_import_xlsx([
        {"code": "as_imp_fx", "name": "固定列冲突",
         "fields": [
             {"fieldKey": "id", "fieldLabel": "冲突 id",
              "fieldType": "text", "maxLength": 20, "sortOrder": 0},
             {"fieldKey": "safe_key", "fieldLabel": "安全",
              "fieldType": "text", "maxLength": 20, "sortOrder": 1},
         ]},
    ])

    r = client.post(
        "/admin/api/alarm-schemas/import",
        files={"file": ("test.xlsx", buf,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["totalFields"] == 1
    assert any("id" in e and "固定列" in e for e in data["errors"])


def test_import_invalid_mapping_target_records_error(client):
    """mapping_target 非合法标识符 → errors 记录跳过。"""
    buf = _build_import_xlsx([
        {"code": "as_imp_mp", "name": "非法映射",
         "fields": [
             {"fieldKey": "level", "fieldLabel": "级别",
              "fieldType": "text", "maxLength": 20,
              "mappingTarget": "123abc", "sortOrder": 0},
         ]},
    ])

    r = client.post(
        "/admin/api/alarm-schemas/import",
        files={"file": ("test.xlsx", buf,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["totalFields"] == 0
    assert any("123abc" in e for e in data["errors"])


def test_import_partial_failure_isolated_per_row(client):
    """某模板字段解析失败不影响其他模板。"""
    buf = _build_import_xlsx([
        {"code": "as_imp_ok", "name": "正常",
         "fields": [
             {"fieldKey": "level", "fieldLabel": "级别",
              "fieldType": "text", "maxLength": 20, "sortOrder": 0},
         ]},
        {"code": "as_imp_bad2", "name": "含错误字段",
         "fields": [
             {"fieldKey": "bad", "fieldLabel": "坏",
              "fieldType": "not_a_type", "sortOrder": 0},
         ]},
        {"code": "as_imp_ok2", "name": "又正常",
         "fields": [
             {"fieldKey": "count", "fieldLabel": "计数",
              "fieldType": "number", "sortOrder": 0},
         ]},
    ])

    r = client.post(
        "/admin/api/alarm-schemas/import",
        files={"file": ("test.xlsx", buf,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["created"] == 3  # 3 个模板都创建
    assert data["totalFields"] == 2  # 只有 2 个字段成功
    assert len(data["errors"]) >= 1
```

- [ ] **Step 2: 跑测试确认 FAIL**

Run: `cd backend && python -m pytest tests/test_alarm_schema_excel.py -v -k "import and not preview"`
Expected: 7 个测试 FAIL（正式导入端点未实现）

- [ ] **Step 3: 在 `alarm_schema.py` 追加正式导入端点**

在 preview 端点后追加：

```python
@router.post("/alarm-schemas/import")
async def import_alarm_schemas(file: UploadFile = File(...)):
    if not file.filename or not file.filename.endswith('.xlsx'):
        raise HTTPException(
            status_code=400,
            detail={"code": 40412, "message": "仅支持 .xlsx 文件"},
        )

    contents = await file.read()
    wb = _load_import_workbook(contents)
    ws = wb["模板汇总"]
    result = AlarmSchemaImportResult()

    with transaction() as conn:
        headers = _build_header_map(ws)
        for row in ws.iter_rows(min_row=2, values_only=True):
            if all(v is None or v == '' for v in row):
                break
            code = _col(headers, "Code", row)
            name = _col(headers, "名称", row)
            if not code or not name:
                result.errors.append(f"Code={code or '(空)'} 缺少必填字段（Code/名称），跳过")
                continue

            description = _col(headers, "描述", row)
            display_field_key = _col(headers, "展示字段Key", row)

            existing = conn.execute(
                "SELECT id FROM alarm_schemas WHERE code = ?", (code,)
            ).fetchone()

            if existing:
                schema_id = existing["id"]
                conn.execute(
                    """UPDATE alarm_schemas SET name=?, description=?,
                       display_field_key=?, updated_at=datetime('now')
                       WHERE id=?""",
                    (name, description, display_field_key, schema_id),
                )
                result.updated += 1
            else:
                schema_id = _new_id()
                conn.execute(
                    """INSERT INTO alarm_schemas
                       (id, code, name, description, display_field_key)
                       VALUES (?,?,?,?,?)""",
                    (schema_id, code, name, description, display_field_key),
                )
                result.created += 1

            sheet_name = _safe_sheet_name(code)
            if sheet_name in wb.sheetnames:
                conn.execute(
                    "DELETE FROM alarm_schema_fields WHERE alarm_schema_id = ?",
                    (schema_id,),
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
                    if not _IDENT_RE.match(fkey):
                        result.errors.append(
                            f"[{code}] 字段标识 {fkey} 非法（仅支持字母/数字/下划线），跳过"
                        )
                        continue
                    if fkey in _FIXED_COLS:
                        result.errors.append(
                            f"[{code}] 字段标识 {fkey} 与固定列冲突，跳过"
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
                            f"[{code}] 字段 {fkey} 类型 '{ftype_raw}' 无效（invalid_type 类），跳过"
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
                    mapping = _col(fheaders, "映射节点属性", frow)

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

                    if mapping and not _IDENT_RE.match(mapping):
                        result.errors.append(
                            f"[{code}] 字段 {fkey} 的映射节点属性 '{mapping}' 非法（仅支持字母/数字/下划线），跳过"
                        )
                        continue

                    conn.execute(
                        """INSERT INTO alarm_schema_fields
                           (alarm_schema_id, field_key, field_label, field_type,
                            max_length, default_value, options, required,
                            sort_order, mapping_target)
                           VALUES (?,?,?,?,?,?,?,?,?,?)""",
                        (schema_id, fkey, flabel, ftype, maxlen, defval, opts,
                         req, sort, mapping),
                    )
                    result.total_fields += 1

    return {
        "code": 0,
        "data": result.model_dump(mode="json", by_alias=True),
        "message": "ok",
    }
```

- [ ] **Step 4: 跑测试确认 PASS**

Run: `cd backend && python -m pytest tests/test_alarm_schema_excel.py -v`
Expected: 全部 pass（4 export + 4 preview + 7 import = 15 tests）

- [ ] **Step 5: 跑全套确认不回归**

Run: `cd backend && python -m pytest tests/ -q --tb=short`
Expected: 全部 pass

- [ ] **Step 6: Commit**

```bash
git add backend/app/admin/alarm_schema.py backend/tests/test_alarm_schema_excel.py
git commit -m "$(cat <<'EOF'
feat(alarm-schema): Excel 正式导入端点

- POST /alarm-schemas/import: multipart 上传 xlsx
- code 存在 → UPDATE name/description/display_field_key + DELETE&INSERT 字段
- code 不存在 → INSERT 新模板
- text max_length 空/非法/<1 → 兜底 255
- 非法字段类型 / field_key 与固定列冲突 / 非法 mapping_target → errors 记录跳过
- 行级隔离：一行错误不影响其他行

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: 前端 API 层

**Files:**
- Modify: `frontend/src/api/alarmSchema.ts`

- [ ] **Step 1: 编辑 `frontend/src/api/alarmSchema.ts`**

在文件顶部 import 区替换（原来只 `import { apiGet, apiPost, apiPut, apiDelete } from './http'`）为：

```typescript
import http, { apiGet, apiPost, apiPut, apiDelete } from './http'
```

在 `AlarmSchemaUpdate` interface 之后（即 `export const alarmSchemaApi` 之前），追加 3 个 interface：

```typescript
export interface AlarmSchemaImportPreviewItem {
  code: string
  name: string
  oldName?: string | null
}

export interface AlarmSchemaImportPreview {
  toCreate: AlarmSchemaImportPreviewItem[]
  toUpdate: AlarmSchemaImportPreviewItem[]
  errors: string[]
}

export interface AlarmSchemaImportResult {
  created: number
  updated: number
  totalFields: number
  errors: string[]
}
```

然后在 `alarmSchemaApi` 对象里追加 3 个方法（放在 `delete` 之后）：

```typescript
  export: (ids?: string[]): Promise<Blob> =>
    http.post('/alarm-schemas/export', { ids }, { responseType: 'blob' }).then(r => r.data),

  importPreview: (file: File): Promise<AlarmSchemaImportPreview> => {
    const form = new FormData()
    form.append('file', file)
    return http.post('/alarm-schemas/import/preview', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then(r => r.data.data)
  },

  import: (file: File): Promise<AlarmSchemaImportResult> => {
    const form = new FormData()
    form.append('file', file)
    return http.post('/alarm-schemas/import', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then(r => r.data.data)
  },
```

- [ ] **Step 2: TypeScript 编译检查**

Run: `cd frontend && npx vue-tsc --noEmit`
Expected: 0 errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/alarmSchema.ts
git commit -m "$(cat <<'EOF'
feat(alarm-schema-ui): 前端 API 层加导出/预览/导入方法

- AlarmSchemaImportPreviewItem / Preview / Result 三 interface
- alarmSchemaApi.export(ids?) 返回 Blob
- alarmSchemaApi.importPreview(file) 返回 Preview
- alarmSchemaApi.import(file) 返回 Result

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: 前端 AlarmSchemaTable UI

**Files:**
- Modify: `frontend/src/components/alarmSchemas/AlarmSchemaTable.vue` (整个文件)

- [ ] **Step 1: 替换整个 `frontend/src/components/alarmSchemas/AlarmSchemaTable.vue`**

```vue
<script setup lang="ts">
import { onMounted, ref, h } from 'vue'
import { Modal, Menu, MenuItem, message } from 'ant-design-vue'
import {
  PlusOutlined, ExportOutlined, ImportOutlined, DownOutlined,
} from '@ant-design/icons-vue'
import { useAlarmSchemas } from '@/composables/useAlarmSchemas'
import AlarmSchemaModal from './AlarmSchemaModal.vue'
import {
  alarmSchemaApi,
  type AlarmSchemaImportPreview,
} from '@/api/alarmSchema'
import { downloadBlob, timestampExcelFilename } from '@/utils/download'

const { schemas, loading, fetchSchemas, deleteSchema } = useAlarmSchemas()
const modalVisible = ref(false)
const editingId = ref<string | null>(null)
const fieldsCount = ref<Record<string, number>>({})
const selectedRowKeys = ref<string[]>([])
const fileInputRef = ref<HTMLInputElement | null>(null)

async function refresh() {
  await fetchSchemas()
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
    okText: '删除',
    okType: 'danger',
    cancelText: '取消',
    onOk: () => deleteSchema(id).then(refresh),
  })
}

async function handleExport(ids?: string[]) {
  try {
    const blob = await alarmSchemaApi.export(ids)
    downloadBlob(blob, timestampExcelFilename('alarm-schemas-export'))
    message.success('导出成功')
  } catch {}
}

function handleExportMenuClick({ key }: { key: string }) {
  if (key === 'all') {
    handleExport()
  } else if (key === 'selected') {
    if (selectedRowKeys.value.length === 0) {
      message.warning('请先勾选要导出的模板')
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

  let preview: AlarmSchemaImportPreview
  try {
    preview = await alarmSchemaApi.importPreview(file)
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
    const result = await alarmSchemaApi.import(file)
    const parts: string[] = []
    if (result.created) parts.push(`新建 ${result.created} 个`)
    if (result.updated) parts.push(`更新 ${result.updated} 个`)
    parts.push(`导入 ${result.totalFields} 个字段`)
    message.success(parts.join('，'))
    if (result.errors.length) {
      message.warning(result.errors.slice(0, 3).join('；') + (result.errors.length > 3 ? '…' : ''))
    }
    refresh()
  } catch {}
}

const columns = [
  { title: 'Code', dataIndex: 'code', key: 'code', width: 180 },
  { title: '名称', dataIndex: 'name', key: 'name' },
  { title: '字段数', key: 'fieldsCount', width: 100 },
  { title: '描述', dataIndex: 'description', key: 'description' },
  { title: '操作', key: 'actions', width: 140 },
]

onMounted(refresh)
</script>

<template>
  <div>
    <input
      ref="fileInputRef"
      type="file"
      accept=".xlsx"
      style="display: none"
      @change="handleFileChosen"
    />

    <div style="margin-bottom: 16px; display: flex; gap: 8px;">
      <a-button type="primary" @click="handleCreate">
        <template #icon><PlusOutlined /></template>
        新建告警模板
      </a-button>

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
    </div>

    <a-table
      :columns="columns"
      :data-source="schemas"
      :loading="loading"
      :pagination="{
        defaultPageSize: 10,
        pageSizeOptions: ['10', '20', '50'],
        showSizeChanger: true,
        showTotal: (total: number) => `共 ${total} 条`,
      }"
      :row-selection="{
        selectedRowKeys,
        onChange: (keys: string[]) => (selectedRowKeys = keys),
      }"
      row-key="id"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'fieldsCount'">
          {{ fieldsCount[record.id] ?? '-' }}
        </template>
        <template v-if="column.key === 'description'">
          <span style="color: rgba(0,0,0,0.45)">{{ record.description || '-' }}</span>
        </template>
        <template v-if="column.key === 'actions'">
          <a-space>
            <a-button type="link" size="small" @click="handleEdit(record.id)">编辑</a-button>
            <a-button type="link" size="small" danger @click="handleDelete(record.id, record.name)">删除</a-button>
          </a-space>
        </template>
      </template>
    </a-table>

    <AlarmSchemaModal
      v-model:visible="modalVisible"
      :schema-id="editingId"
      @saved="refresh"
    />
  </div>
</template>
```

- [ ] **Step 2: TypeScript 编译检查**

Run: `cd frontend && npx vue-tsc --noEmit`
Expected: 0 errors

- [ ] **Step 3: 前端 dev 启动验证（可选）**

Run: `cd frontend && npm run dev`（后台）
浏览器访问告警模板管理页面：
- 新建 2 个模板 → 点"批量导出 → 全部导出" → 下载 xlsx，打开验证含"模板汇总" Sheet + 2 个 code Sheet
- 勾选 1 个 → "批量导出 → 导出选中（1 项）" → xlsx 只含 1 个
- 手动修改 xlsx 后点"导入" → 选文件 → preview 弹窗 → 确认 → 结果 toast
- 停止 dev server

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/alarmSchemas/AlarmSchemaTable.vue
git commit -m "$(cat <<'EOF'
feat(alarm-schema-ui): AlarmSchemaTable 加导入/导出 UI

- 顶部工具栏加"批量导出 Dropdown（全部/选中）"和"导入"按钮
- 表格加 rowSelection 支持勾选
- 导入用 Modal.confirm 内联渲染 VNode 预览（toCreate/toUpdate/errors）
- 与节点类型导入交互一致

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## 收尾自检

- [ ] 后端全量测试通过

Run: `cd backend && python -m pytest tests/ --tb=short`
Expected: 全部 pass（包括新增 15 个 alarm_schema Excel 测试）

- [ ] 前端 TypeScript 无错

Run: `cd frontend && npx vue-tsc --noEmit`
Expected: 0 errors

- [ ] 前后端联调手动回归

启动后端：`cd backend && python -m app.main`（后台）
启动前端：`cd frontend && npm run dev`（后台）

验证清单：
- 空库建 3 个告警模板 → 全部导出 → xlsx 内容正确（1 汇总 Sheet + 3 code Sheet）
- 改一个模板名字 → 导入原 xlsx → preview 显示"将覆盖 3 个"其中 1 个 oldName 不同 → 确认后模板复原
- 建 5 个模板勾选 2 个 → 导出选中 → xlsx 只含 2 个模板
- 手动编辑 xlsx 加新 code 一行 → 导入 → preview 显示"将新建 1 个 / 将覆盖 N 个"
- 导入含 field_type='invalid' 的 xlsx → 结果显示 warnings 提示

停止后端和前端进程。

- [ ] Commit + Push（可选）

若所有验证通过：`git push origin main`

---

## 记录

**关联 spec**：`docs/superpowers/specs/2026-07-05-alarm-schema-excel-io-design.md`

**估算工时**：6 个任务，每任务 15-40 分钟，总计约 2-4 小时（含手动回归）
