# 接口 Excel 导入导出 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将现有的接口 JSON 导入/导出彻底替换为 Excel（.xlsx）——每个网管/设备一个 Sheet、一行一个接口，变长嵌套字段用"多行文本 + 固定列 + `|` 分隔"表达。

**Architecture:** 后端新增内部模块 `backend/app/admin/_api_excel.py` 承担 workbook 编解码（纯函数 + openpyxl 调用），路由层 `POST /apis/export`（返回 xlsx 二进制）和 `POST /apis/import`（读 xlsx → upsert）只做 DB 事务和 mock 路由注册。前端把导出/导入按钮的文件类型从 `.json` 改成 `.xlsx`。

**Tech Stack:** Python 3.9 / FastAPI / SQLite / openpyxl（已在项目里）/ Vue 3.5 / Ant Design Vue 4 / axios

**Spec:** `docs/superpowers/specs/2026-07-04-apis-excel-io-design.md`

---

## 文件清单

**新增：**
- `backend/app/admin/_api_excel.py` — Workbook 编解码 + 校验（纯函数 + openpyxl）
- `backend/tests/test_apis_excel.py` — pytest 测试文件

**修改：**
- `backend/app/admin/api_config.py:774-941` — `export_apis` / `import_apis` 两个函数整段替换
- `frontend/src/api/api_config.ts:152-164` — `export` 返回 `Blob`、`import` 仅接受 `.xlsx`
- `frontend/src/components/apis/ApiConfigTable.vue:210-233, 386-428, 567-573` — 导出用 blob 下载 + 导入去掉客户端 JSON 预览 + `accept` 改 `.xlsx`

**不动：**
- 数据库 schema / 迁移
- mock 路由注册（`app.mock.registry`）
- 请求流水线（`app.core.request_pipeline`）

---

## 常量约定（全 plan 引用）

在 `_api_excel.py` 顶部定义，所有任务共用：

```python
HEADER_COLUMNS = ["name", "required", "expectValue", "example", "description"]
QUERY_COLUMNS = ["name", "type", "required", "example", "description"]
BODY_COLUMNS = ["contentType", "required", "example", "description"]
PARAM_MAPPING_COLUMNS = ["name", "in", "type", "required", "bindTo"]

MAIN_HEADERS = [
    "方法", "路径", "接口名", "启用", "分类", "分组", "数据源", "拓扑",
    "鉴权类型", "鉴权头名",
    "请求头", "Query 参数", "请求体",
    "SQL 语句", "响应模板", "参数映射",
    "静态响应体",
    "故障-延迟毫秒", "故障-错误率", "故障-错误状态码",
]

INSTRUCTION_SHEET_NAME = "_使用说明"
UNCATEGORIZED_SHEET_NAME = "未归类"
SHEET_NAME_MAX_LEN = 31
INVALID_SHEET_CHARS = r':\/?*[]'
```

---

## Task 1: `_api_excel.py` — 变长单元格编解码

**Files:**
- Create: `backend/app/admin/_api_excel.py`
- Create: `backend/tests/test_apis_excel.py`

- [ ] **Step 1: 建立测试骨架 + 写第一个失败测试**

创建 `backend/tests/test_apis_excel.py`：

```python
import pytest

from app.admin._api_excel import (
    ExcelValidationError,
    format_cell_list,
    parse_cell_list,
    HEADER_COLUMNS,
)


def test_format_cell_list_empty_returns_empty_string():
    assert format_cell_list([], HEADER_COLUMNS) == ""


def test_format_cell_list_single_record():
    records = [{"name": "Authorization", "required": True, "expectValue": "Bearer x", "example": "", "description": ""}]
    assert format_cell_list(records, HEADER_COLUMNS) == "Authorization|是|Bearer x||"


def test_format_cell_list_multiple_records_uses_newline():
    records = [
        {"name": "A", "required": True, "expectValue": "", "example": "", "description": ""},
        {"name": "B", "required": False, "expectValue": "", "example": "", "description": ""},
    ]
    assert format_cell_list(records, HEADER_COLUMNS) == "A|是|||\nB|否|||"


def test_format_cell_list_missing_key_treated_as_empty():
    records = [{"name": "A"}]
    assert format_cell_list(records, HEADER_COLUMNS) == "A||||"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_apis_excel.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.admin._api_excel'`

- [ ] **Step 3: 建立模块 + 实现 `format_cell_list`**

创建 `backend/app/admin/_api_excel.py`：

```python
"""接口 Excel 导入/导出的内部工具（编解码 + 校验，不直接触碰 DB）。"""
from typing import Any


HEADER_COLUMNS = ["name", "required", "expectValue", "example", "description"]
QUERY_COLUMNS = ["name", "type", "required", "example", "description"]
BODY_COLUMNS = ["contentType", "required", "example", "description"]
PARAM_MAPPING_COLUMNS = ["name", "in", "type", "required", "bindTo"]

MAIN_HEADERS = [
    "方法", "路径", "接口名", "启用", "分类", "分组", "数据源", "拓扑",
    "鉴权类型", "鉴权头名",
    "请求头", "Query 参数", "请求体",
    "SQL 语句", "响应模板", "参数映射",
    "静态响应体",
    "故障-延迟毫秒", "故障-错误率", "故障-错误状态码",
]

INSTRUCTION_SHEET_NAME = "_使用说明"
UNCATEGORIZED_SHEET_NAME = "未归类"
SHEET_NAME_MAX_LEN = 31
INVALID_SHEET_CHARS = ":\\/?*[]"

FIELD_SEP = "|"
RECORD_SEP = "\n"


class ExcelValidationError(Exception):
    """行级校验错误——被上层 parse_workbook 捕获并塞进 errors 列表。"""


def _format_field(value: Any) -> str:
    """把 Python 值渲染成单元格里的一段字段字符串。"""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "是" if value else "否"
    return str(value)


def format_cell_list(records: list[dict], columns: list[str]) -> str:
    """把结构化记录列表序列化成"多行 + 竖线分隔"的单元格文本。

    空列表 -> 空字符串（不是 "|||"）。
    """
    if not records:
        return ""
    lines: list[str] = []
    for rec in records:
        fields = [_format_field(rec.get(col)) for col in columns]
        lines.append(FIELD_SEP.join(fields))
    return RECORD_SEP.join(lines)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_apis_excel.py -v`
Expected: 4 tests PASS

- [ ] **Step 5: 追加 `parse_cell_list` 的失败测试**

追加到 `backend/tests/test_apis_excel.py`：

```python
def test_parse_cell_list_empty_returns_empty_list():
    assert parse_cell_list("", HEADER_COLUMNS, row_hint="第 1 行") == []


def test_parse_cell_list_single_record():
    result = parse_cell_list("Authorization|是|Bearer x||", HEADER_COLUMNS, row_hint="第 1 行")
    assert result == [{"name": "Authorization", "required": True, "expectValue": "Bearer x", "example": "", "description": ""}]


def test_parse_cell_list_multiple_records():
    text = "A|是|||\nB|否|||"
    result = parse_cell_list(text, HEADER_COLUMNS, row_hint="第 1 行")
    assert len(result) == 2
    assert result[0]["name"] == "A" and result[0]["required"] is True
    assert result[1]["name"] == "B" and result[1]["required"] is False


def test_parse_cell_list_skips_blank_lines():
    text = "A|是|||\n\nB|否|||"
    result = parse_cell_list(text, HEADER_COLUMNS, row_hint="第 1 行")
    assert len(result) == 2


def test_parse_cell_list_fewer_fields_treated_as_empty():
    result = parse_cell_list("A|是", HEADER_COLUMNS, row_hint="第 1 行")
    assert result == [{"name": "A", "required": True, "expectValue": "", "example": "", "description": ""}]


def test_parse_cell_list_more_fields_raises():
    with pytest.raises(ExcelValidationError) as exc:
        parse_cell_list("A|是|X|Y|Z|EXTRA", HEADER_COLUMNS, row_hint="第 3 行 请求头")
    assert "第 3 行 请求头" in str(exc.value)
    assert "字段数" in str(exc.value)


def test_parse_cell_list_accepts_true_false_synonyms():
    result = parse_cell_list("A|true|||", HEADER_COLUMNS, row_hint="")
    assert result[0]["required"] is True
    result = parse_cell_list("A|false|||", HEADER_COLUMNS, row_hint="")
    assert result[0]["required"] is False


def test_parse_cell_list_round_trip():
    records = [
        {"name": "X", "required": True, "expectValue": "v1", "example": "e1", "description": "d1"},
        {"name": "Y", "required": False, "expectValue": "", "example": "", "description": ""},
    ]
    text = format_cell_list(records, HEADER_COLUMNS)
    parsed = parse_cell_list(text, HEADER_COLUMNS, row_hint="")
    assert parsed == records
```

- [ ] **Step 6: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_apis_excel.py -v`
Expected: 8 new tests FAIL with `NameError: name 'parse_cell_list' is not defined` （或 `ImportError`）

- [ ] **Step 7: 实现 `parse_cell_list`**

追加到 `backend/app/admin/_api_excel.py`：

```python
_TRUE_TOKENS = {"是", "true", "1", "yes", "y"}
_FALSE_TOKENS = {"否", "false", "0", "no", "n", ""}


def _is_boolean_column(column: str) -> bool:
    """哪些列在解析时按 bool 处理。"""
    return column == "required"


def _parse_field(value: str, column: str) -> Any:
    """把单元格里的字段字符串解回 Python 值。"""
    stripped = value.strip()
    if _is_boolean_column(column):
        lower = stripped.lower()
        if lower in _TRUE_TOKENS:
            return True
        if lower in _FALSE_TOKENS:
            return False
        raise ExcelValidationError(f"必填列的值 '{value}' 无法识别（应为 是/否）")
    return stripped


def parse_cell_list(cell_text: str, columns: list[str], row_hint: str) -> list[dict]:
    """把"多行 + 竖线分隔"的单元格文本解析回记录列表。

    row_hint 用来在报错时给出 sheet/行/列的位置提示，如 "Sheet '网管A' 第 3 行 请求头"。
    """
    if cell_text is None or cell_text == "":
        return []
    records: list[dict] = []
    for line in cell_text.split(RECORD_SEP):
        line = line.strip()
        if not line:
            continue
        if FIELD_SEP not in line and len(columns) > 1:
            # 只有一个"字段"但列不止一个：也允许，只填第一列
            fields = [line]
        else:
            fields = line.split(FIELD_SEP)
        if len(fields) > len(columns):
            raise ExcelValidationError(
                f"{row_hint}：字段数 {len(fields)} 超过预期 {len(columns)}（列顺序：{columns}）"
            )
        # 缺的字段补空
        while len(fields) < len(columns):
            fields.append("")
        record = {}
        for col, raw in zip(columns, fields):
            try:
                record[col] = _parse_field(raw, col)
            except ExcelValidationError as e:
                raise ExcelValidationError(f"{row_hint}：{e}") from e
        records.append(record)
    return records
```

- [ ] **Step 8: 运行测试确认全通过**

Run: `cd backend && python -m pytest tests/test_apis_excel.py -v`
Expected: 12 tests PASS

- [ ] **Step 9: 追加"值含 `|`"测试**

追加：

```python
def test_parse_cell_list_value_with_pipe_raises():
    # 第 3 个字段（expectValue）含 |，会被 split 成多余字段 → 字段数超限报错
    with pytest.raises(ExcelValidationError) as exc:
        parse_cell_list("A|是|foo|bar||", HEADER_COLUMNS, row_hint="第 5 行 请求头")
    assert "第 5 行" in str(exc.value)
```

- [ ] **Step 10: 运行测试确认通过（`|` 用例走既有"字段数超限"分支）**

Run: `cd backend && python -m pytest tests/test_apis_excel.py -v`
Expected: 13 tests PASS

- [ ] **Step 11: 提交**

```bash
git add backend/app/admin/_api_excel.py backend/tests/test_apis_excel.py
git commit -m "$(cat <<'EOF'
feat(apis): _api_excel 变长单元格编解码

format_cell_list / parse_cell_list 纯函数 + 13 个单测：
- 空数组 <-> 空字符串
- required 列 True/False 与 "是"/"否" 双向转换
- 字段数不足自动补空，超限抛 ExcelValidationError
- 值含 | 走"字段数超限"分支报错（不做转义）

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: `_api_excel.py` — Sheet 名清洗

**Files:**
- Modify: `backend/app/admin/_api_excel.py`（追加）
- Modify: `backend/tests/test_apis_excel.py`（追加）

- [ ] **Step 1: 写失败测试**

追加到 `backend/tests/test_apis_excel.py`：

```python
from app.admin._api_excel import sanitize_sheet_name


def test_sanitize_sheet_name_passthrough_valid():
    used: set[str] = set()
    assert sanitize_sheet_name("网管A", used) == "网管A"
    assert "网管A" in used


def test_sanitize_sheet_name_replaces_invalid_chars():
    used: set[str] = set()
    assert sanitize_sheet_name("A/B", used) == "A_B"
    assert sanitize_sheet_name(r"C\D", used) == "C_D"
    assert sanitize_sheet_name("E?F*G", used) == "E_F_G"
    assert sanitize_sheet_name("H[I]J", used) == "H_I_J"
    assert sanitize_sheet_name("K:L", used) == "K_L"


def test_sanitize_sheet_name_truncates_to_31_chars():
    used: set[str] = set()
    long_name = "网" * 40
    result = sanitize_sheet_name(long_name, used)
    assert len(result) == 31


def test_sanitize_sheet_name_appends_dedupe_suffix():
    used: set[str] = set()
    a = sanitize_sheet_name("A/B", used)
    b = sanitize_sheet_name("A_B", used)
    c = sanitize_sheet_name("A_B", used)
    assert a == "A_B"
    assert b == "A_B~2"
    assert c == "A_B~3"


def test_sanitize_sheet_name_dedupe_after_truncation():
    used: set[str] = set()
    long_a = "X" * 40
    long_b = "X" * 40
    assert sanitize_sheet_name(long_a, used) == "X" * 31
    # 第二次被截断成同名 → 追加后缀，且总长仍 ≤ 31
    result = sanitize_sheet_name(long_b, used)
    assert result.endswith("~2")
    assert len(result) <= 31
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_apis_excel.py -v`
Expected: 5 new tests FAIL with `ImportError` 或 `AttributeError`

- [ ] **Step 3: 实现 `sanitize_sheet_name`**

追加到 `backend/app/admin/_api_excel.py`：

```python
def sanitize_sheet_name(name: str, used: set[str]) -> str:
    """把 domain 名清洗成 Excel 合法 sheet 名并防重名。

    - 非法字符（`: \\ / ? * [ ]`）替换为下划线
    - 超过 31 字符从右截断
    - 与 used 中已存在的名字冲突时追加 `~2`、`~3`... 后缀，最终长度仍 ≤ 31
    - 每次调用会把返回的名字加入 used

    副作用：修改传入的 used 集合。
    """
    sanitized = name
    for ch in INVALID_SHEET_CHARS:
        sanitized = sanitized.replace(ch, "_")
    if len(sanitized) > SHEET_NAME_MAX_LEN:
        sanitized = sanitized[:SHEET_NAME_MAX_LEN]

    if sanitized not in used:
        used.add(sanitized)
        return sanitized

    suffix = 2
    while True:
        tag = f"~{suffix}"
        base_max = SHEET_NAME_MAX_LEN - len(tag)
        candidate = sanitized[:base_max] + tag
        if candidate not in used:
            used.add(candidate)
            return candidate
        suffix += 1
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_apis_excel.py -v`
Expected: 18 tests PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/admin/_api_excel.py backend/tests/test_apis_excel.py
git commit -m "$(cat <<'EOF'
feat(apis): sanitize_sheet_name Excel Sheet 名清洗

- 非法字符 (: \ / ? * [ ]) 替换为下划线
- 超 31 字符从右截断
- 重名追加 ~2/~3 后缀且总长 ≤ 31
- 5 个单测覆盖 pass-through / 清洗 / 截断 / 去重 / 截断后去重

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: `_api_excel.py` — `build_workbook` 导出

**Files:**
- Modify: `backend/app/admin/_api_excel.py`
- Modify: `backend/tests/test_apis_excel.py`

- [ ] **Step 1: 写失败测试（最小可行 workbook）**

追加到 `backend/tests/test_apis_excel.py`：

```python
import io
from openpyxl import load_workbook

from app.admin._api_excel import (
    build_workbook,
    INSTRUCTION_SHEET_NAME,
    UNCATEGORIZED_SHEET_NAME,
    MAIN_HEADERS,
)


def _make_api_row(**overrides):
    """构造一行 api_configs 数据（用 dict 模拟 sqlite3.Row）。"""
    base = {
        "id": "api_test1",
        "name": "测试接口",
        "method": "GET",
        "path": "/api/test",
        "enabled": 1,
        "group_name": None,
        "domain_id": None,
        "category": None,
        "data_source": "static",
        "topology_id": None,
        "sql_text": None,
        "config": "{}",
    }
    base.update(overrides)
    return base


def _load_bytes(wb):
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return load_workbook(buf)


def test_build_workbook_empty_produces_instruction_sheet_only():
    wb = build_workbook(api_rows=[], domains=[], topologies=[])
    reloaded = _load_bytes(wb)
    assert INSTRUCTION_SHEET_NAME in reloaded.sheetnames
    # 首个 Sheet 必须是使用说明
    assert reloaded.sheetnames[0] == INSTRUCTION_SHEET_NAME


def test_build_workbook_uncategorized_apis_go_to_special_sheet():
    apis = [_make_api_row(domain_id=None)]
    wb = build_workbook(api_rows=apis, domains=[], topologies=[])
    reloaded = _load_bytes(wb)
    assert UNCATEGORIZED_SHEET_NAME in reloaded.sheetnames
    ws = reloaded[UNCATEGORIZED_SHEET_NAME]
    # 第 1 行是表头
    assert [c.value for c in ws[1]] == MAIN_HEADERS
    # 第 2 行是数据
    assert ws.cell(row=2, column=1).value == "GET"
    assert ws.cell(row=2, column=2).value == "/api/test"


def test_build_workbook_per_domain_sheet_with_original_name_in_comment():
    apis = [_make_api_row(domain_id="dom_1")]
    domains = [{"id": "dom_1", "name": "网管/A"}]
    wb = build_workbook(api_rows=apis, domains=domains, topologies=[])
    reloaded = _load_bytes(wb)
    # 域名 "网管/A" 被清洗成 "网管_A"
    assert "网管_A" in reloaded.sheetnames
    ws = reloaded["网管_A"]
    # A1 comment 里存原始域名
    assert ws["A1"].comment is not None
    assert "网管/A" in ws["A1"].comment.text


def test_build_workbook_uses_topology_name_not_id():
    apis = [_make_api_row(topology_id="topo_x", data_source="sql", sql_text="SELECT 1")]
    topos = [{"id": "topo_x", "name": "MyTopo"}]
    wb = build_workbook(api_rows=apis, domains=[], topologies=topos)
    reloaded = _load_bytes(wb)
    ws = reloaded[UNCATEGORIZED_SHEET_NAME]
    # 第 8 列 = "拓扑"
    topo_col = MAIN_HEADERS.index("拓扑") + 1
    assert ws.cell(row=2, column=topo_col).value == "MyTopo"


def test_build_workbook_serializes_headers_query_params():
    config = {
        "request": {
            "headers": [{"name": "Auth", "required": True, "expectValue": "Bearer"}],
            "query": [{"name": "pageNo", "type": "int", "required": True}],
        },
        "params": [{"name": "id", "in": "query", "type": "string", "required": True, "bindTo": "id_"}],
    }
    apis = [_make_api_row(config=__import__("json").dumps(config))]
    wb = build_workbook(api_rows=apis, domains=[], topologies=[])
    reloaded = _load_bytes(wb)
    ws = reloaded[UNCATEGORIZED_SHEET_NAME]
    headers_col = MAIN_HEADERS.index("请求头") + 1
    query_col = MAIN_HEADERS.index("Query 参数") + 1
    param_col = MAIN_HEADERS.index("参数映射") + 1
    assert ws.cell(row=2, column=headers_col).value == "Auth|是|Bearer||"
    assert ws.cell(row=2, column=query_col).value == "pageNo|int|是||"
    assert ws.cell(row=2, column=param_col).value == "id|query|string|是|id_"


def test_build_workbook_fault_columns():
    config = {"fault": {"delayMs": 100, "errorRate": 0.5, "errorStatus": 503}}
    apis = [_make_api_row(config=__import__("json").dumps(config))]
    wb = build_workbook(api_rows=apis, domains=[], topologies=[])
    reloaded = _load_bytes(wb)
    ws = reloaded[UNCATEGORIZED_SHEET_NAME]
    delay_col = MAIN_HEADERS.index("故障-延迟毫秒") + 1
    rate_col = MAIN_HEADERS.index("故障-错误率") + 1
    status_col = MAIN_HEADERS.index("故障-错误状态码") + 1
    assert ws.cell(row=2, column=delay_col).value == 100
    assert ws.cell(row=2, column=rate_col).value == 0.5
    assert ws.cell(row=2, column=status_col).value == 503
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_apis_excel.py -v`
Expected: 6 new tests FAIL

- [ ] **Step 3: 实现 `build_workbook`**

追加到 `backend/app/admin/_api_excel.py`：

```python
import json as _json
from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Font, PatternFill

# 表头样式
_HEADER_FONT = Font(bold=True)
_HEADER_FILL = PatternFill(start_color="F0F0F0", end_color="F0F0F0", fill_type="solid")
_WRAP_ALIGNMENT = Alignment(wrap_text=True, vertical="top")

# 每列的期望宽度（字符数）
_COLUMN_WIDTHS = {
    "方法": 10, "路径": 40, "接口名": 18, "启用": 8, "分类": 12, "分组": 12,
    "数据源": 10, "拓扑": 15, "鉴权类型": 12, "鉴权头名": 15,
    "请求头": 40, "Query 参数": 40, "请求体": 30,
    "SQL 语句": 80, "响应模板": 80, "参数映射": 40,
    "静态响应体": 60,
    "故障-延迟毫秒": 14, "故障-错误率": 12, "故障-错误状态码": 16,
}

# 每列表头的 comment 说明（导入方在此对齐语义）
_HEADER_COMMENTS = {
    "方法": "GET/POST/PUT/PATCH/DELETE，空 → 跳过该行",
    "路径": "必填。全局唯一（method+path），跨 Sheet 移动 = 换域",
    "启用": "是/否；空视为「是」",
    "拓扑": "拓扑名（不是 ID）；找不到时留空 + warning",
    "请求头": "每行「名称|必填|期望值|样例|说明」；用换行分隔多条；\n值中禁止出现 |",
    "Query 参数": "每行「名称|类型|必填|样例|说明」；类型 string/int/bool",
    "请求体": "「Content-Type|必填|样例|说明」；不多值",
    "参数映射": "每行「参数名|位置|类型|必填|SQL绑定名」；位置 query/path/body",
    "故障-延迟毫秒": "空 = 不注入延迟",
    "故障-错误率": "0~1 之间，空 = 不注入错误",
    "故障-错误状态码": "空 = 默认 500",
}


def _decode_config(config_json: str) -> dict:
    if not config_json:
        return {}
    try:
        return _json.loads(config_json)
    except _json.JSONDecodeError:
        return {}


def _api_row_to_excel_values(api: dict, topology_name_by_id: dict[str, str]) -> list:
    """把一行 api_configs 记录转成 Excel 一行的 20 个单元格值（按 MAIN_HEADERS 顺序）。"""
    config = _decode_config(api.get("config") or "")
    request = config.get("request") or {}
    auth = config.get("auth") or {}
    fault = config.get("fault") or {}

    headers = request.get("headers") or []
    query = request.get("query") or []
    body = request.get("body") or None
    param_mappings = config.get("params") or []

    topology_name = topology_name_by_id.get(api.get("topology_id") or "", "") if api.get("topology_id") else ""

    body_cell = ""
    if isinstance(body, dict):
        body_cell = format_cell_list([body], BODY_COLUMNS)

    return [
        api.get("method") or "",
        api.get("path") or "",
        api.get("name") or "",
        "是" if api.get("enabled") else "否",
        api.get("category") or "",
        api.get("group_name") or "",
        api.get("data_source") or "",
        topology_name,
        auth.get("type") or "none",
        auth.get("headerName") or "",
        format_cell_list(headers, HEADER_COLUMNS),
        format_cell_list(query, QUERY_COLUMNS),
        body_cell,
        api.get("sql_text") or "",
        config.get("responseTemplate") or "",
        format_cell_list(param_mappings, PARAM_MAPPING_COLUMNS),
        config.get("staticBody") or "",
        fault.get("delayMs"),
        fault.get("errorRate"),
        fault.get("errorStatus"),
    ]


def _write_instruction_sheet(wb: Workbook) -> None:
    ws = wb.active
    ws.title = INSTRUCTION_SHEET_NAME
    lines = [
        "接口 Excel 导入/导出使用说明",
        "",
        "1. 每个网管/设备一个 Sheet；一行一个接口。",
        "2. 变长字段（请求头 / Query 参数 / 参数映射）用「换行 + 竖线 |」表达：",
        "   例：请求头单元格 = 'Authorization|是|Bearer x||\\nX-Trace-Id|否|||'",
        "3. 值中禁止出现 |，否则该行导入时报错。",
        "4. 必填字段用「是 / 否」，也接受 true / false。",
        "5. 拓扑列填拓扑名（不是 ID），未找到时导入后为空并给出 warning。",
        "6. 匹配规则：按 (方法, 路径) 全局匹配；命中 → 更新（含换域），未命中 → 新建。",
        "7. 删除接口请到 UI 操作，从 Excel 里删除行不会删接口。",
        "8. Sheet 名 _ 开头（如本 Sheet）导入时被忽略。",
        "9. 域名含非法字符或超 31 字符时 Sheet 名会被自动清洗，A1 单元格的 comment 里记录原始域名。",
    ]
    for i, line in enumerate(lines, start=1):
        ws.cell(row=i, column=1, value=line)
    ws.column_dimensions["A"].width = 100


def _write_data_sheet(ws, api_rows: list[dict], topology_name_by_id: dict[str, str], original_domain_name: str) -> None:
    """写入表头 + 数据行，并在 A1 comment 里记录原始域名。"""
    # 表头
    for col_idx, header in enumerate(MAIN_HEADERS, start=1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.font = _HEADER_FONT
        cell.fill = _HEADER_FILL
        if header in _HEADER_COMMENTS:
            cell.comment = Comment(_HEADER_COMMENTS[header], "system")
        # 列宽
        col_letter = ws.cell(row=1, column=col_idx).column_letter
        ws.column_dimensions[col_letter].width = _COLUMN_WIDTHS.get(header, 15)

    # A1 记录原始域名（用于导入回填，防止 Sheet 名清洗后找不到域）
    if original_domain_name:
        existing_comment_text = ws["A1"].comment.text if ws["A1"].comment else ""
        marker = f"__ORIGINAL_DOMAIN__={original_domain_name}"
        combined = f"{existing_comment_text}\n{marker}" if existing_comment_text else marker
        ws["A1"].comment = Comment(combined, "system")

    # 数据行
    for row_idx, api in enumerate(api_rows, start=2):
        values = _api_row_to_excel_values(api, topology_name_by_id)
        for col_idx, val in enumerate(values, start=1):
            cell = ws.cell(row=row_idx, column=col_idx, value=val)
            cell.alignment = _WRAP_ALIGNMENT

    # 冻结表头行
    ws.freeze_panes = "A2"


def build_workbook(
    api_rows: list[dict],
    domains: list[dict],
    topologies: list[dict],
) -> Workbook:
    """构建 xlsx。

    api_rows: [{id, name, method, path, enabled, group_name, domain_id, category,
                data_source, topology_id, sql_text, config}]
    domains:  [{id, name}]
    topologies: [{id, name}]
    """
    wb = Workbook()
    _write_instruction_sheet(wb)

    topology_name_by_id = {t["id"]: t["name"] for t in topologies}
    domain_by_id = {d["id"]: d for d in domains}

    # 按 domain_id 分组
    apis_by_domain: dict[Optional[str], list[dict]] = {}
    for api in api_rows:
        dom_id = api.get("domain_id")
        apis_by_domain.setdefault(dom_id, []).append(api)

    used_sheet_names: set[str] = {INSTRUCTION_SHEET_NAME}

    # 每个域一个 Sheet
    for dom_id, apis in apis_by_domain.items():
        if dom_id is None:
            sheet_name = UNCATEGORIZED_SHEET_NAME
            original_name = ""
            used_sheet_names.add(sheet_name)
        else:
            dom = domain_by_id.get(dom_id)
            if dom is None:
                sheet_name = sanitize_sheet_name(f"未知域_{dom_id[:8]}", used_sheet_names)
                original_name = ""
            else:
                original_name = dom["name"]
                sheet_name = sanitize_sheet_name(original_name, used_sheet_names)
        ws = wb.create_sheet(title=sheet_name)
        _write_data_sheet(ws, apis, topology_name_by_id, original_name)

    return wb
```

在 `_api_excel.py` 文件顶部把 `Optional` 加进 import：

```python
from typing import Any, Optional
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_apis_excel.py -v`
Expected: 24 tests PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/admin/_api_excel.py backend/tests/test_apis_excel.py
git commit -m "$(cat <<'EOF'
feat(apis): build_workbook 导出

- _使用说明 Sheet 打头，无 API 时仍返回
- 一域一 Sheet + 未归类 Sheet 兜底
- A1 comment 记录原始域名（防 Sheet 名清洗后失联）
- 拓扑列展示拓扑名而非 ID
- headers/query/params 走 format_cell_list 序列化
- 故障三列（延迟/错误率/状态码）单独展开
- 6 个单测覆盖空 workbook / 未归类 / Sheet 名清洗 + comment / 拓扑名 / 变长字段 / 故障

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: `_api_excel.py` — `parse_workbook` 导入

**Files:**
- Modify: `backend/app/admin/_api_excel.py`
- Modify: `backend/tests/test_apis_excel.py`

- [ ] **Step 1: 写失败测试（ParseResult 数据类 + 基本回环）**

追加到 `backend/tests/test_apis_excel.py`：

```python
from app.admin._api_excel import parse_workbook, ParseResult


def _build_test_workbook_bytes(builder):
    """helper: 传一个 (wb) -> None 的回调，写入完毕后返回 bytes。"""
    from openpyxl import Workbook as _Wb
    wb = _Wb()
    # 删掉默认 Sheet
    default = wb.active
    wb.remove(default)
    builder(wb)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_parse_workbook_ignores_underscore_sheets():
    def build(wb):
        ws = wb.create_sheet("_使用说明")
        ws["A1"] = "instructions"
        ws2 = wb.create_sheet("网管A")
        for col_idx, h in enumerate(MAIN_HEADERS, start=1):
            ws2.cell(row=1, column=col_idx, value=h)
        ws2.cell(row=2, column=1, value="GET")
        ws2.cell(row=2, column=2, value="/api/x")
        ws2.cell(row=2, column=3, value="X")
        ws2.cell(row=2, column=7, value="static")
    data = _build_test_workbook_bytes(build)

    result = parse_workbook(io.BytesIO(data), existing_domains=[], existing_topologies=[])
    assert isinstance(result, ParseResult)
    assert len(result.rows) == 1
    assert result.rows[0]["method"] == "GET"
    assert result.rows[0]["path"] == "/api/x"


def test_parse_workbook_empty_raises_fatal():
    def build(wb):
        wb.create_sheet("_使用说明")  # 只有说明 Sheet
    data = _build_test_workbook_bytes(build)

    with pytest.raises(ExcelValidationError) as exc:
        parse_workbook(io.BytesIO(data), existing_domains=[], existing_topologies=[])
    assert "未找到" in str(exc.value)


def test_parse_workbook_skip_row_without_method_or_path():
    def build(wb):
        ws = wb.create_sheet("网管A")
        for col_idx, h in enumerate(MAIN_HEADERS, start=1):
            ws.cell(row=1, column=col_idx, value=h)
        # 第 2 行只有 path 没 method
        ws.cell(row=2, column=2, value="/api/y")
        # 第 3 行完整
        ws.cell(row=3, column=1, value="POST")
        ws.cell(row=3, column=2, value="/api/z")
        ws.cell(row=3, column=3, value="Z")
        ws.cell(row=3, column=7, value="static")
    data = _build_test_workbook_bytes(build)

    result = parse_workbook(io.BytesIO(data), existing_domains=[], existing_topologies=[])
    assert len(result.rows) == 1
    assert result.rows[0]["path"] == "/api/z"


def test_parse_workbook_uses_a1_comment_for_original_domain():
    def build(wb):
        ws = wb.create_sheet("网管_A")
        for col_idx, h in enumerate(MAIN_HEADERS, start=1):
            ws.cell(row=1, column=col_idx, value=h)
        from openpyxl.comments import Comment
        ws["A1"].comment = Comment("__ORIGINAL_DOMAIN__=网管/A", "system")
        ws.cell(row=2, column=1, value="GET")
        ws.cell(row=2, column=2, value="/api/x")
        ws.cell(row=2, column=3, value="X")
        ws.cell(row=2, column=7, value="static")
    data = _build_test_workbook_bytes(build)

    result = parse_workbook(
        io.BytesIO(data),
        existing_domains=[{"id": "dom_orig", "name": "网管/A"}],
        existing_topologies=[],
    )
    # 应能识别原始域名并回填 domain_id
    assert result.rows[0]["domain_id"] == "dom_orig"


def test_parse_workbook_topology_name_resolution():
    def build(wb):
        ws = wb.create_sheet("网管A")
        for col_idx, h in enumerate(MAIN_HEADERS, start=1):
            ws.cell(row=1, column=col_idx, value=h)
        ws.cell(row=2, column=1, value="GET")
        ws.cell(row=2, column=2, value="/a")
        ws.cell(row=2, column=3, value="A")
        ws.cell(row=2, column=7, value="sql")
        # 拓扑列 = 第 8 列
        ws.cell(row=2, column=8, value="TopoX")

        ws.cell(row=3, column=1, value="GET")
        ws.cell(row=3, column=2, value="/b")
        ws.cell(row=3, column=3, value="B")
        ws.cell(row=3, column=7, value="sql")
        ws.cell(row=3, column=8, value="不存在的拓扑")
    data = _build_test_workbook_bytes(build)

    result = parse_workbook(
        io.BytesIO(data),
        existing_domains=[],
        existing_topologies=[{"id": "topo_x", "name": "TopoX", "created_at": "2020-01-01"}],
    )
    assert result.rows[0]["topology_id"] == "topo_x"
    assert result.rows[1]["topology_id"] is None
    assert any("不存在的拓扑" in w for w in result.warnings)


def test_parse_workbook_invalid_method_row_error():
    def build(wb):
        ws = wb.create_sheet("网管A")
        for col_idx, h in enumerate(MAIN_HEADERS, start=1):
            ws.cell(row=1, column=col_idx, value=h)
        ws.cell(row=2, column=1, value="FOO")
        ws.cell(row=2, column=2, value="/api/x")
        ws.cell(row=2, column=3, value="X")
        ws.cell(row=2, column=7, value="static")
    data = _build_test_workbook_bytes(build)

    result = parse_workbook(io.BytesIO(data), existing_domains=[], existing_topologies=[])
    assert result.rows == []
    assert any("FOO" in e for e in result.errors)


def test_parse_workbook_deserializes_headers_and_params():
    def build(wb):
        ws = wb.create_sheet("网管A")
        for col_idx, h in enumerate(MAIN_HEADERS, start=1):
            ws.cell(row=1, column=col_idx, value=h)
        ws.cell(row=2, column=1, value="GET")
        ws.cell(row=2, column=2, value="/api/x")
        ws.cell(row=2, column=3, value="X")
        ws.cell(row=2, column=7, value="sql")
        # 请求头列 = 11
        ws.cell(row=2, column=11, value="Auth|是|Bearer||")
        # Query 参数列 = 12
        ws.cell(row=2, column=12, value="pageNo|int|是||")
        # 参数映射列 = 16
        ws.cell(row=2, column=16, value="id|query|string|是|id_")
        # SQL 列 = 14
        ws.cell(row=2, column=14, value="SELECT 1")
        # 响应模板列 = 15
        ws.cell(row=2, column=15, value="{}")
    data = _build_test_workbook_bytes(build)

    result = parse_workbook(io.BytesIO(data), existing_domains=[], existing_topologies=[])
    row = result.rows[0]
    assert row["config"]["request"]["headers"] == [
        {"name": "Auth", "required": True, "expectValue": "Bearer", "example": "", "description": ""}
    ]
    assert row["config"]["request"]["query"] == [
        {"name": "pageNo", "type": "int", "required": True, "example": "", "description": ""}
    ]
    assert row["config"]["params"] == [
        {"name": "id", "in": "query", "type": "string", "required": True, "bindTo": "id_"}
    ]
    assert row["sql_text"] == "SELECT 1"


def test_parse_workbook_fault_columns_optional():
    def build(wb):
        ws = wb.create_sheet("网管A")
        for col_idx, h in enumerate(MAIN_HEADERS, start=1):
            ws.cell(row=1, column=col_idx, value=h)
        ws.cell(row=2, column=1, value="GET")
        ws.cell(row=2, column=2, value="/a")
        ws.cell(row=2, column=3, value="A")
        ws.cell(row=2, column=7, value="static")
        # 故障列 18/19/20
        ws.cell(row=2, column=18, value=100)
        ws.cell(row=2, column=19, value=0.5)
        ws.cell(row=2, column=20, value=503)

        # 第二行不写故障 → config.fault 不应存在
        ws.cell(row=3, column=1, value="GET")
        ws.cell(row=3, column=2, value="/b")
        ws.cell(row=3, column=3, value="B")
        ws.cell(row=3, column=7, value="static")
    data = _build_test_workbook_bytes(build)

    result = parse_workbook(io.BytesIO(data), existing_domains=[], existing_topologies=[])
    assert result.rows[0]["config"]["fault"] == {"delayMs": 100, "errorRate": 0.5, "errorStatus": 503}
    assert "fault" not in result.rows[1]["config"]


def test_parse_workbook_auto_creates_domain_from_new_sheet():
    def build(wb):
        ws = wb.create_sheet("新网管")
        for col_idx, h in enumerate(MAIN_HEADERS, start=1):
            ws.cell(row=1, column=col_idx, value=h)
        ws.cell(row=2, column=1, value="GET")
        ws.cell(row=2, column=2, value="/a")
        ws.cell(row=2, column=3, value="A")
        ws.cell(row=2, column=7, value="static")
    data = _build_test_workbook_bytes(build)

    result = parse_workbook(io.BytesIO(data), existing_domains=[], existing_topologies=[])
    assert result.rows[0]["domain_id"] is None  # 待创建
    assert result.rows[0]["_new_domain_name"] == "新网管"
    assert "新网管" in result.auto_created_domains


def test_parse_workbook_uncategorized_sheet_has_no_domain():
    def build(wb):
        ws = wb.create_sheet(UNCATEGORIZED_SHEET_NAME)
        for col_idx, h in enumerate(MAIN_HEADERS, start=1):
            ws.cell(row=1, column=col_idx, value=h)
        ws.cell(row=2, column=1, value="GET")
        ws.cell(row=2, column=2, value="/a")
        ws.cell(row=2, column=3, value="A")
        ws.cell(row=2, column=7, value="static")
    data = _build_test_workbook_bytes(build)

    result = parse_workbook(io.BytesIO(data), existing_domains=[], existing_topologies=[])
    assert result.rows[0]["domain_id"] is None
    assert result.rows[0].get("_new_domain_name") is None
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_apis_excel.py -v`
Expected: 10 new tests FAIL

- [ ] **Step 3: 实现 `ParseResult` + `parse_workbook`**

追加到 `backend/app/admin/_api_excel.py`：

```python
from dataclasses import dataclass, field
from openpyxl import load_workbook as _load_workbook


ALLOWED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}
ALLOWED_DATA_SOURCES = {"sql", "static"}


@dataclass
class ParseResult:
    rows: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    auto_created_domains: list[str] = field(default_factory=list)


def _extract_original_domain(a1_cell) -> Optional[str]:
    """从 A1 comment 里提取 __ORIGINAL_DOMAIN__= 后面的文本，找不到返回 None。"""
    if a1_cell.comment is None:
        return None
    text = a1_cell.comment.text or ""
    marker = "__ORIGINAL_DOMAIN__="
    for line in text.split("\n"):
        if line.startswith(marker):
            return line[len(marker):].strip()
    return None


def _resolve_topology(
    topo_name: str,
    existing_topologies: list[dict],
    row_hint: str,
    warnings: list[str],
) -> Optional[str]:
    """按名称查 topology_id；多命中取最早创建；未命中记 warning 返回 None。"""
    if not topo_name:
        return None
    matches = [t for t in existing_topologies if t.get("name") == topo_name]
    if not matches:
        warnings.append(f"{row_hint}：拓扑名 '{topo_name}' 未找到，已留空")
        return None
    if len(matches) > 1:
        matches_sorted = sorted(matches, key=lambda t: t.get("created_at") or "")
        chosen = matches_sorted[0]
        warnings.append(f"{row_hint}：拓扑名 '{topo_name}' 有 {len(matches)} 个匹配，使用 {chosen['id']}")
        return chosen["id"]
    return matches[0]["id"]


def _parse_bool_cell(value: Any, default: bool = True) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    s = str(value).strip().lower()
    if s in _TRUE_TOKENS:
        return True
    if s in _FALSE_TOKENS:
        return False
    return default


def _parse_number_cell(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return value
    try:
        s = str(value).strip()
        if not s:
            return None
        return float(s) if "." in s else int(s)
    except (ValueError, TypeError):
        raise ExcelValidationError(f"数字列填了非数字 '{value}'")


def _resolve_domain_for_sheet(
    sheet_title: str,
    original_domain_name: Optional[str],
    existing_domains: list[dict],
    auto_created: list[str],
) -> tuple[Optional[str], Optional[str]]:
    """返回 (domain_id, new_domain_name_to_create)。

    - 未归类 Sheet → (None, None)
    - A1 comment 有原始域名，且在 existing_domains 里 → (id, None)
    - A1 comment 有原始域名，但域已被删/改名 → (None, 原始名字)：新建
    - A1 无 comment，用 sheet_title 查 existing_domains
    - 都找不到 → 待创建
    """
    if sheet_title == UNCATEGORIZED_SHEET_NAME:
        return (None, None)

    lookup_name = original_domain_name or sheet_title
    matches = [d for d in existing_domains if d.get("name") == lookup_name]
    if matches:
        matches_sorted = sorted(matches, key=lambda d: d.get("created_at") or "")
        return (matches_sorted[0]["id"], None)

    # 待创建
    if lookup_name not in auto_created:
        auto_created.append(lookup_name)
    return (None, lookup_name)


def _row_to_config(cells: dict, row_hint: str) -> dict:
    """把一行的所有单元格值组装成 api_configs.config 字典 + sql_text + static_body。

    cells 是 {表头名: 单元格值} 的字典。抛 ExcelValidationError 表示行级错误。
    """
    config: dict = {}

    headers_text = cells.get("请求头") or ""
    query_text = cells.get("Query 参数") or ""
    body_text = cells.get("请求体") or ""
    params_text = cells.get("参数映射") or ""

    headers = parse_cell_list(headers_text, HEADER_COLUMNS, f"{row_hint} 请求头") if headers_text else []
    query = parse_cell_list(query_text, QUERY_COLUMNS, f"{row_hint} Query 参数") if query_text else []
    body_records = parse_cell_list(body_text, BODY_COLUMNS, f"{row_hint} 请求体") if body_text else []
    params = parse_cell_list(params_text, PARAM_MAPPING_COLUMNS, f"{row_hint} 参数映射") if params_text else []

    request: dict = {}
    if headers:
        request["headers"] = headers
    if query:
        request["query"] = query
    if body_records:
        request["body"] = body_records[0]
    if request:
        config["request"] = request

    auth_type = (cells.get("鉴权类型") or "none").strip() or "none"
    auth_header_name = (cells.get("鉴权头名") or "").strip()
    if auth_type != "none" or auth_header_name:
        auth = {"type": auth_type}
        if auth_header_name:
            auth["headerName"] = auth_header_name
        config["auth"] = auth

    if params:
        config["params"] = params

    resp_tpl = cells.get("响应模板")
    if resp_tpl:
        config["responseTemplate"] = str(resp_tpl)

    static_body = cells.get("静态响应体")
    if static_body:
        config["staticBody"] = str(static_body)

    delay_ms = _parse_number_cell(cells.get("故障-延迟毫秒"))
    error_rate = _parse_number_cell(cells.get("故障-错误率"))
    error_status = _parse_number_cell(cells.get("故障-错误状态码"))
    fault: dict = {}
    if delay_ms is not None:
        fault["delayMs"] = int(delay_ms)
    if error_rate is not None:
        fault["errorRate"] = float(error_rate)
    if error_status is not None:
        fault["errorStatus"] = int(error_status)
    if fault:
        config["fault"] = fault

    return config


def parse_workbook(
    file_like,
    existing_domains: list[dict],
    existing_topologies: list[dict],
) -> ParseResult:
    """解析上传的 xlsx 文件对象。

    file_like: 支持 read() 的对象（如 UploadFile.file 或 io.BytesIO）
    existing_domains: [{id, name, created_at}]
    existing_topologies: [{id, name, created_at}]

    抛 ExcelValidationError → 致命错误（文件损坏 / 无数据 Sheet）。
    行级错误 → 收进 result.errors，那行被跳过。
    """
    try:
        wb = _load_workbook(file_like, read_only=False, data_only=True)
    except Exception as e:
        raise ExcelValidationError(f"Excel 打开失败：{e}") from e

    result = ParseResult()
    data_sheet_count = 0

    for ws in wb.worksheets:
        title = ws.title
        if title.startswith("_"):
            continue
        data_sheet_count += 1

        # 表头映射
        headers_in_sheet = [ws.cell(row=1, column=c).value for c in range(1, len(MAIN_HEADERS) + 1)]
        # 允许列缺失（用 None 填空），按 MAIN_HEADERS 的顺序建索引
        col_index = {h: i + 1 for i, h in enumerate(MAIN_HEADERS)}

        original_domain = _extract_original_domain(ws["A1"])
        domain_id, new_domain_name = _resolve_domain_for_sheet(
            title, original_domain, existing_domains, result.auto_created_domains,
        )

        for row_num in range(2, ws.max_row + 1):
            row_hint = f"Sheet '{title}' 第 {row_num} 行"
            cells = {}
            for header in MAIN_HEADERS:
                cells[header] = ws.cell(row=row_num, column=col_index[header]).value

            method_raw = cells.get("方法")
            path = cells.get("路径")
            if not method_raw or not path:
                # 整行空 → 静默跳过；单缺 method 或 path 也跳过（不算错，用户可能在整理表）
                continue
            method = str(method_raw).strip().upper()
            if method not in ALLOWED_METHODS:
                result.errors.append(f"{row_hint}：method '{method}' 不合法（允许 {sorted(ALLOWED_METHODS)}）")
                continue

            data_source = (str(cells.get("数据源") or "").strip() or "static").lower()
            if data_source not in ALLOWED_DATA_SOURCES:
                result.errors.append(f"{row_hint}：数据源 '{data_source}' 不合法")
                continue

            try:
                config = _row_to_config(cells, row_hint)
            except ExcelValidationError as e:
                result.errors.append(str(e))
                continue

            topology_id = _resolve_topology(
                str(cells.get("拓扑") or "").strip(),
                existing_topologies,
                row_hint,
                result.warnings,
            )

            row = {
                "method": method,
                "path": str(path).strip(),
                "name": str(cells.get("接口名") or "").strip(),
                "enabled": _parse_bool_cell(cells.get("启用"), default=True),
                "category": (str(cells.get("分类") or "").strip() or None),
                "group_name": (str(cells.get("分组") or "").strip() or None),
                "data_source": data_source,
                "topology_id": topology_id,
                "sql_text": (str(cells.get("SQL 语句") or "").strip() or None) if data_source == "sql" else None,
                "config": config,
                "domain_id": domain_id,
                "_new_domain_name": new_domain_name,
                "_sheet": title,
                "_row_num": row_num,
            }
            result.rows.append(row)

    if data_sheet_count == 0:
        raise ExcelValidationError("Excel 中未找到任何数据 Sheet")

    return result
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_apis_excel.py -v`
Expected: 34 tests PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/admin/_api_excel.py backend/tests/test_apis_excel.py
git commit -m "$(cat <<'EOF'
feat(apis): parse_workbook 导入解析

- ParseResult 数据类：rows / errors / warnings / auto_created_domains
- Sheet 名 _ 开头忽略；未找到数据 Sheet 抛致命错
- A1 comment 里的 __ORIGINAL_DOMAIN__ 优先于 Sheet 名回填域
- 拓扑名解析：唯一/多命中(最早)/未命中(warning) 三分支
- method / 数据源枚举校验
- 变长字段解回 headers/query/body/params
- 故障三列 → config.fault 部分/全部/无
- 10 个单测覆盖上述路径

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: 重写 `POST /apis/export` 端点

**Files:**
- Modify: `backend/app/admin/api_config.py:774-813`
- Modify: `backend/tests/test_apis_excel.py`（追加端到端测试）

- [ ] **Step 1: 写端到端失败测试**

追加到 `backend/tests/test_apis_excel.py`：

```python
def test_export_endpoint_returns_xlsx_binary(client):
    # 造 1 个域 + 1 个静态接口
    r = client.post("/admin/api/domains", json={"name": "网管X"})
    assert r.status_code == 200, r.text
    dom_id = r.json()["data"]["id"]

    r = client.post("/admin/api/apis", json={
        "method": "GET",
        "path": "/api/e2e-export",
        "name": "E2E导出",
        "enabled": True,
        "domainId": dom_id,
        "dataSource": "static",
        "config": {"staticBody": '{"ok":true}'},
    })
    assert r.status_code == 200, r.text

    r = client.post("/admin/api/apis/export", json={})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    wb = load_workbook(io.BytesIO(r.content))
    assert "网管X" in wb.sheetnames
    ws = wb["网管X"]
    assert ws.cell(row=2, column=1).value == "GET"
    assert ws.cell(row=2, column=2).value == "/api/e2e-export"


def test_export_endpoint_filter_by_ids(client):
    r = client.post("/admin/api/apis", json={
        "method": "GET", "path": "/api/one", "name": "one",
        "dataSource": "static", "config": {},
    })
    api1_id = r.json()["data"]["id"]
    r = client.post("/admin/api/apis", json={
        "method": "GET", "path": "/api/two", "name": "two",
        "dataSource": "static", "config": {},
    })

    r = client.post("/admin/api/apis/export", json={"ids": [api1_id]})
    assert r.status_code == 200
    wb = load_workbook(io.BytesIO(r.content))
    # 未归类 Sheet 应只有 1 行数据
    ws = wb[UNCATEGORIZED_SHEET_NAME]
    assert ws.cell(row=2, column=2).value == "/api/one"
    assert ws.cell(row=3, column=2).value is None  # 只有一行
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_apis_excel.py::test_export_endpoint_returns_xlsx_binary -v`
Expected: FAIL（旧 export 返回 JSON，`content-type` 是 `application/json`）

- [ ] **Step 3: 重写 `export_apis` 端点**

编辑 `backend/app/admin/api_config.py:774-813`，把 `# ============== Export / Import ==============` 到 `return { "code": 0, "data": { "schemaVersion": ..., ... } }` 那一整段替换为：

```python
# ============== Export / Import ==============

@router.post("/apis/export")
def export_apis(data: dict):
    """导出接口为 Excel (.xlsx)"""
    import io as _io
    from fastapi.responses import Response
    from app.admin._api_excel import build_workbook

    ids = data.get("ids")
    domain_id = data.get("domainId")
    with connect() as conn:
        if ids:
            placeholders = ",".join("?" for _ in ids)
            rows = conn.execute(
                f"SELECT * FROM api_configs WHERE id IN ({placeholders}) ORDER BY method, path",
                tuple(ids),
            ).fetchall()
        elif domain_id:
            rows = conn.execute(
                "SELECT * FROM api_configs WHERE domain_id = ? ORDER BY method, path",
                (domain_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM api_configs ORDER BY method, path"
            ).fetchall()
        api_rows = [dict(r) for r in rows]

        domains = [dict(r) for r in conn.execute("SELECT id, name FROM domains").fetchall()]
        topologies = [dict(r) for r in conn.execute("SELECT id, name FROM topologies").fetchall()]

    wb = build_workbook(api_rows=api_rows, domains=domains, topologies=topologies)
    buf = _io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=apis-export.xlsx"},
    )
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_apis_excel.py::test_export_endpoint_returns_xlsx_binary tests/test_apis_excel.py::test_export_endpoint_filter_by_ids -v`
Expected: 2 PASS

- [ ] **Step 5: 跑全套测试确认无回归**

Run: `cd backend && python -m pytest -v`
Expected: 全部 PASS

- [ ] **Step 6: 提交**

```bash
git add backend/app/admin/api_config.py backend/tests/test_apis_excel.py
git commit -m "$(cat <<'EOF'
feat(apis): 导出端点改返回 Excel

- POST /apis/export 现在返回 xlsx 二进制流（不走 {code,data} 包装）
- 保留 ids / domainId 过滤参数不变
- 补 2 个端到端测试

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: 重写 `POST /apis/import` 端点

**Files:**
- Modify: `backend/app/admin/api_config.py:816-941`
- Modify: `backend/tests/test_apis_excel.py`（追加端到端测试）

- [ ] **Step 1: 写端到端失败测试**

追加到 `backend/tests/test_apis_excel.py`：

```python
def _upload_xlsx_bytes(client, xlsx_bytes: bytes):
    return client.post(
        "/admin/api/apis/import",
        files={"file": ("test.xlsx", xlsx_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )


def test_import_endpoint_rejects_non_xlsx(client):
    r = client.post(
        "/admin/api/apis/import",
        files={"file": ("test.json", b'{"apis":[]}', "application/json")},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == 40410


def test_import_endpoint_creates_new_api(client):
    def build(wb):
        ws = wb.create_sheet("新网管")
        for col_idx, h in enumerate(MAIN_HEADERS, start=1):
            ws.cell(row=1, column=col_idx, value=h)
        ws.cell(row=2, column=1, value="GET")
        ws.cell(row=2, column=2, value="/api/imported")
        ws.cell(row=2, column=3, value="导入接口")
        ws.cell(row=2, column=7, value="static")
    data = _build_test_workbook_bytes(build)

    r = _upload_xlsx_bytes(client, data)
    assert r.status_code == 200, r.text
    result = r.json()["data"]
    assert result["created"] == 1
    assert result["updated"] == 0
    assert "新网管" in result["autoCreatedDomains"]

    # 校验 DB 里出现了
    r2 = client.get("/admin/api/apis")
    apis = r2.json()["data"]["items"]
    assert any(a["path"] == "/api/imported" for a in apis)


def test_import_endpoint_updates_existing_api(client):
    r = client.post("/admin/api/apis", json={
        "method": "GET", "path": "/api/exists", "name": "原名字",
        "dataSource": "static", "config": {},
    })
    original_id = r.json()["data"]["id"]

    def build(wb):
        ws = wb.create_sheet(UNCATEGORIZED_SHEET_NAME)
        for col_idx, h in enumerate(MAIN_HEADERS, start=1):
            ws.cell(row=1, column=col_idx, value=h)
        ws.cell(row=2, column=1, value="GET")
        ws.cell(row=2, column=2, value="/api/exists")
        ws.cell(row=2, column=3, value="新名字")
        ws.cell(row=2, column=7, value="static")
    data = _build_test_workbook_bytes(build)

    r = _upload_xlsx_bytes(client, data)
    assert r.status_code == 200
    assert r.json()["data"]["updated"] == 1
    assert r.json()["data"]["created"] == 0

    r2 = client.get(f"/admin/api/apis/{original_id}")
    assert r2.json()["data"]["name"] == "新名字"


def test_import_endpoint_preserves_unknown_config_keys(client):
    # 预先造一个带未来字段的接口
    r = client.post("/admin/api/apis", json={
        "method": "POST", "path": "/api/keep-me", "name": "keep",
        "dataSource": "static",
        "config": {"customFuture": "x", "auth": {"type": "none"}},
    })

    # 用 Excel 更新它（只碰鉴权）
    def build(wb):
        ws = wb.create_sheet(UNCATEGORIZED_SHEET_NAME)
        for col_idx, h in enumerate(MAIN_HEADERS, start=1):
            ws.cell(row=1, column=col_idx, value=h)
        ws.cell(row=2, column=1, value="POST")
        ws.cell(row=2, column=2, value="/api/keep-me")
        ws.cell(row=2, column=3, value="keep")
        ws.cell(row=2, column=7, value="static")
        # 鉴权类型 = 第 9 列
        ws.cell(row=2, column=9, value="xtoken")
        # 鉴权头名 = 第 10 列
        ws.cell(row=2, column=10, value="X-New-Token")
    data = _build_test_workbook_bytes(build)

    r = _upload_xlsx_bytes(client, data)
    assert r.status_code == 200

    r2 = client.get(f"/admin/api/apis?path=/api/keep-me")
    items = r2.json()["data"]["items"]
    assert len(items) == 1
    detail = client.get(f"/admin/api/apis/{items[0]['id']}").json()["data"]
    assert detail["config"]["customFuture"] == "x"
    assert detail["config"]["auth"] == {"type": "xtoken", "headerName": "X-New-Token"}


def test_import_endpoint_cross_sheet_move_changes_domain(client):
    # 先造两个域
    dom1 = client.post("/admin/api/domains", json={"name": "网管1"}).json()["data"]["id"]
    dom2 = client.post("/admin/api/domains", json={"name": "网管2"}).json()["data"]["id"]

    # 造一个绑到网管1 的接口
    client.post("/admin/api/apis", json={
        "method": "GET", "path": "/api/mover", "name": "mover",
        "domainId": dom1, "dataSource": "static", "config": {},
    })

    # 用 Excel 把它挪到网管2
    def build(wb):
        ws = wb.create_sheet("网管2")
        for col_idx, h in enumerate(MAIN_HEADERS, start=1):
            ws.cell(row=1, column=col_idx, value=h)
        ws.cell(row=2, column=1, value="GET")
        ws.cell(row=2, column=2, value="/api/mover")
        ws.cell(row=2, column=3, value="mover")
        ws.cell(row=2, column=7, value="static")
    data = _build_test_workbook_bytes(build)

    r = _upload_xlsx_bytes(client, data)
    assert r.status_code == 200
    assert r.json()["data"]["updated"] == 1

    # 接口应该在 dom2 里，不在 dom1 里
    r_dom1 = client.get(f"/admin/api/apis?domainId={dom1}").json()["data"]["items"]
    r_dom2 = client.get(f"/admin/api/apis?domainId={dom2}").json()["data"]["items"]
    assert not any(a["path"] == "/api/mover" for a in r_dom1)
    assert any(a["path"] == "/api/mover" for a in r_dom2)


def test_import_endpoint_reports_row_errors_but_continues(client):
    def build(wb):
        ws = wb.create_sheet(UNCATEGORIZED_SHEET_NAME)
        for col_idx, h in enumerate(MAIN_HEADERS, start=1):
            ws.cell(row=1, column=col_idx, value=h)
        # 坏行：非法 method
        ws.cell(row=2, column=1, value="FOO")
        ws.cell(row=2, column=2, value="/api/bad")
        ws.cell(row=2, column=3, value="bad")
        ws.cell(row=2, column=7, value="static")
        # 好行
        ws.cell(row=3, column=1, value="GET")
        ws.cell(row=3, column=2, value="/api/good")
        ws.cell(row=3, column=3, value="good")
        ws.cell(row=3, column=7, value="static")
    data = _build_test_workbook_bytes(build)

    r = _upload_xlsx_bytes(client, data)
    assert r.status_code == 200
    result = r.json()["data"]
    assert result["created"] == 1
    assert len(result["errors"]) == 1
    assert "FOO" in result["errors"][0]


def test_import_endpoint_fatal_error_on_empty_workbook(client):
    def build(wb):
        wb.create_sheet(INSTRUCTION_SHEET_NAME)
    data = _build_test_workbook_bytes(build)

    r = _upload_xlsx_bytes(client, data)
    assert r.status_code == 400
    assert "未找到" in r.json()["detail"]["message"]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_apis_excel.py::test_import_endpoint_rejects_non_xlsx tests/test_apis_excel.py::test_import_endpoint_creates_new_api -v`
Expected: FAIL（旧 import 只认 JSON，或行为不匹配）

- [ ] **Step 3: 重写 `import_apis` 端点**

编辑 `backend/app/admin/api_config.py:816-941`，把整个 `import_apis` 函数替换为：

```python
@router.post("/apis/import")
async def import_apis(file: UploadFile = File(...)) -> dict:
    """从 Excel (.xlsx) 导入接口，以 (method, path) 全局匹配 upsert。"""
    if not file.filename or not file.filename.lower().endswith('.xlsx'):
        raise HTTPException(
            status_code=400,
            detail={"code": 40410, "message": "仅支持 .xlsx 文件"},
        )

    from app.admin._api_excel import parse_workbook, ExcelValidationError

    contents = await file.read()
    try:
        with connect() as conn:
            existing_domains = [dict(r) for r in conn.execute(
                "SELECT id, name, created_at FROM domains"
            ).fetchall()]
            existing_topologies = [dict(r) for r in conn.execute(
                "SELECT id, name, created_at FROM topologies"
            ).fetchall()]
    except Exception as e:
        raise HTTPException(status_code=500, detail={"code": 50001, "message": f"读取参考数据失败: {e}"})

    try:
        import io as _io
        result = parse_workbook(_io.BytesIO(contents), existing_domains, existing_topologies)
    except ExcelValidationError as e:
        raise HTTPException(status_code=400, detail={"code": 40411, "message": str(e)})

    created = 0
    updated = 0
    new_routes: list[tuple[str, str, str]] = []
    auto_created_domain_ids: dict[str, str] = {}  # name -> id

    with transaction() as conn:
        # 先按需自动建域（幂等）
        for dom_name in result.auto_created_domains:
            existing = conn.execute("SELECT id FROM domains WHERE name = ?", (dom_name,)).fetchone()
            if existing:
                auto_created_domain_ids[dom_name] = existing["id"]
            else:
                new_id = f"dom_{uuid.uuid4().hex[:12]}"
                conn.execute(
                    "INSERT INTO domains (id, name, description) VALUES (?, ?, ?)",
                    (new_id, dom_name, "导入时自动创建"),
                )
                auto_created_domain_ids[dom_name] = new_id

        for row in result.rows:
            domain_id = row.get("domain_id")
            if not domain_id and row.get("_new_domain_name"):
                domain_id = auto_created_domain_ids.get(row["_new_domain_name"])

            method = row["method"]
            path = row["path"]
            existing = conn.execute(
                "SELECT id, config FROM api_configs WHERE method = ? AND path = ?",
                (method, path),
            ).fetchone()

            new_config = row["config"]
            if existing:
                # 保留未被表格覆盖的 config 键
                try:
                    old_config = json.loads(existing["config"]) if existing["config"] else {}
                except json.JSONDecodeError:
                    old_config = {}
                merged_config = {**old_config, **new_config}
                conn.execute(
                    """UPDATE api_configs SET name=?, data_source=?, topology_id=?,
                       sql_text=?, config=?, enabled=?, group_name=?, domain_id=?,
                       category=?, updated_at=datetime('now')
                       WHERE id=?""",
                    (
                        row["name"], row["data_source"], row["topology_id"],
                        row["sql_text"], json.dumps(merged_config, ensure_ascii=False),
                        1 if row["enabled"] else 0,
                        row["group_name"], domain_id, row["category"],
                        existing["id"],
                    ),
                )
                updated += 1
            else:
                api_id = _new_id()
                conn.execute(
                    """INSERT INTO api_configs
                       (id, name, method, path, enabled, group_name, domain_id,
                        category, data_source, topology_id, sql_text, config)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        api_id, row["name"], method, path,
                        1 if row["enabled"] else 0,
                        row["group_name"], domain_id, row["category"],
                        row["data_source"], row["topology_id"], row["sql_text"],
                        json.dumps(new_config, ensure_ascii=False),
                    ),
                )
                created += 1
                new_routes.append((api_id, method, path))

    # 事务成功后再挂载路由，避免回滚时留下幽灵路由
    if new_routes:
        from app.mock.registry import registry as mock_registry
        for rid, rmethod, rpath in new_routes:
            mock_registry.register(rid, rmethod, rpath)

    return {
        "code": 0,
        "data": {
            "created": created,
            "updated": updated,
            "errors": result.errors,
            "warnings": result.warnings,
            "autoCreatedDomains": result.auto_created_domains,
        },
        "message": "ok",
    }
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_apis_excel.py -v`
Expected: 全部 34 + 8 = 42 PASS

- [ ] **Step 5: 跑全套测试确认无回归**

Run: `cd backend && python -m pytest -v`
Expected: 全部 PASS

- [ ] **Step 6: 提交**

```bash
git add backend/app/admin/api_config.py backend/tests/test_apis_excel.py
git commit -m "$(cat <<'EOF'
feat(apis): 导入端点改吃 Excel + 未建模 config 键保留

- POST /apis/import 收窄到 .xlsx，非法扩展名 → 400 + 40410
- (method, path) 全局匹配：命中更新（含 domain_id）、未命中新建
- 未建模 config 键（如未来新增字段）在 UPDATE 时保留
- 响应新增 warnings 字段（拓扑名解析告警等）
- 8 个端到端测试

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: 前端 `api_config.ts` — export 返回 Blob、import 收窄到 .xlsx

**Files:**
- Modify: `frontend/src/api/api_config.ts:152-164`

- [ ] **Step 1: 修改 `export` 和 `import` 方法**

替换 `frontend/src/api/api_config.ts:152-164` 那段（原 `export` 和 `import` 两个方法）为：

```typescript
  export: (params?: { domainId?: string; ids?: string[] }): Promise<Blob> =>
    http.post('/apis/export', params || {}, { responseType: 'blob' }).then(r => r.data),

  deleteDirectory: (domainId: string): Promise<{ deletedApis: number; deletedDirectory: number }> =>
    apiDelete(`/apis/directory/${domainId}`),

  import: (file: File): Promise<{ created: number; updated: number; errors: string[]; warnings: string[]; autoCreatedDomains: string[] }> => {
    if (!file.name.toLowerCase().endsWith('.xlsx')) {
      return Promise.reject(new Error('仅支持 .xlsx 文件'))
    }
    const form = new FormData()
    form.append('file', file)
    return http.post('/apis/import', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then(r => r.data.data)
  },
```

（改动点：`export` 返回 Blob；`import` 前端拦截非 .xlsx，且返回类型加 `warnings` 字段）

- [ ] **Step 2: 类型检查**

Run: `cd frontend && npx vue-tsc --noEmit`
Expected: 无 TS 报错（会有 ApiConfigTable 里的 `.replace` 报错，下一 Task 解决）

- [ ] **Step 3: 提交（先不做前端 UI，Task 8 一并跑通再联调）**

```bash
git add frontend/src/api/api_config.ts
git commit -m "$(cat <<'EOF'
feat(apis): api_config.ts export 返回 Blob、import 收窄到 .xlsx

- export 走 responseType: 'blob'，返回 Promise<Blob>
- import 前端拦截非 .xlsx；返回类型新增 warnings 字段

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: 前端 `ApiConfigTable.vue` — 导出/导入 UI 改造

**Files:**
- Modify: `frontend/src/components/apis/ApiConfigTable.vue:210-233, 300-428, 567-573`

- [ ] **Step 1: 改 `handleExport` 和 `handleExportByCategory` 直接 blob 下载**

替换 `frontend/src/components/apis/ApiConfigTable.vue:210-233` 那两段：

```typescript
async function handleExport() {
  try {
    const ids = selectedApiIds.value.size > 0 ? [...selectedApiIds.value] : undefined
    const blob = await apiConfigApi.export(ids ? { ids } : {})
    downloadBlob(blob, timestampExcelFilename('apis-export'))
    message.success(ids ? `已导出 ${ids.length} 个接口` : '导出成功')
    selectedApiIds.value.clear()
  } catch {}
}

async function handleExportByCategory(apiIds: string[]) {
  // 空目录直接提示并返回，避免传 {} 给后端被解释成"导出全部"
  if (apiIds.length === 0) {
    message.info('该目录下暂无接口可导出')
    return
  }
  try {
    const blob = await apiConfigApi.export({ ids: apiIds })
    downloadBlob(blob, timestampExcelFilename('apis-export'))
    message.success(`已导出 ${apiIds.length} 个接口`)
  } catch {}
}
```

- [ ] **Step 2: 替换 `handleFileChosen` — 去掉客户端 JSON 预览**

先在 `ApiConfigTable.vue` 找到 `handleFileChosen`（大约在 300-428 行，取决于当前修改后的实际位置），把整个函数替换为：

```typescript
async function handleFileChosen(e: Event) {
  const target = e.target as HTMLInputElement
  const file = target.files?.[0]
  if (!file) return
  target.value = '' // 允许连选同一文件

  if (!file.name.toLowerCase().endsWith('.xlsx')) {
    message.error('仅支持 .xlsx 文件')
    return
  }

  Modal.confirm({
    title: '确认导入',
    content: `将导入文件 "${file.name}"。已存在的接口按 (方法, 路径) 匹配更新，不存在的新建。确认继续？`,
    okText: '确认导入',
    cancelText: '取消',
    width: 480,
    onOk: async () => {
      try {
        const result = await apiConfigApi.import(file)
        const parts: string[] = []
        if (result.created) parts.push(`新建 ${result.created} 个`)
        if (result.updated) parts.push(`更新 ${result.updated} 个`)
        message.success(parts.join('，') || '导入完成')
        if (result.autoCreatedDomains.length) {
          message.info(`自动创建了 ${result.autoCreatedDomains.length} 个目录：${result.autoCreatedDomains.join('、')}`)
        }
        if (result.warnings.length) {
          message.warning(result.warnings.join('；'))
        }
        if (result.errors.length) {
          message.error(`${result.errors.length} 行被跳过：${result.errors.slice(0, 3).join('；')}${result.errors.length > 3 ? '…' : ''}`)
        }
        emit('refresh')
      } catch (err: any) {
        message.error(err?.message || '导入失败')
      }
    },
  })
}
```

- [ ] **Step 3: 改 input 的 accept**

在 `ApiConfigTable.vue` 找到 file input（约 567-573 行）：

```html
<input
  ref="fileInputRef"
  type="file"
  accept=".xlsx"
  style="display: none"
  @change="handleFileChosen"
/>
```

- [ ] **Step 4: 清理无用 import**

在 `<script setup>` 头部检查是否还用到 `h`（如果只有 handleFileChosen 用到，且新版本没用 h → 移除 `h` from `import { ref, computed, watch, h } from 'vue'`）。同时可能还引用了 `ApiConfigDetail`（用于旧 JSON 预览的类型），如果不再用到也移除。

Run: `cd frontend && npx vue-tsc --noEmit`
Expected: 无 TS 报错

- [ ] **Step 5: 手动最小验证（可选，跳到 Task 9 也行）**

开发环境启动：`cd backend && python -m app.main` + `cd frontend && npm run dev`。

浏览器打开 → 接口配置页 → 点"导出" → 应下载一个 `apis-export-YYYYMMDDTHHMMSS.xlsx` 文件；Excel 打开看到 `_使用说明` + 每域一个 Sheet。

- [ ] **Step 6: 提交**

```bash
git add frontend/src/components/apis/ApiConfigTable.vue
git commit -m "$(cat <<'EOF'
feat(apis): 表格页导出/导入改用 Excel

- 导出：直接 blob 下载 apis-export-TS.xlsx，不再手动改后缀
- 导入：accept=.xlsx，改用简化确认对话（不再客户端预览 JSON）
- 后端返回 warnings 时前端 message.warning 展示
- errors 数量多时截断展示前 3 条

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: 手动集成验证

**Files:** 无代码修改

- [ ] **Step 1: 启动前后端**

```bash
# 终端 1
cd backend && python -m app.main
# 终端 2
cd frontend && npm run dev
```

- [ ] **Step 2: 端到端"导出→改→导入"闭环**

浏览器 http://localhost:5173：
1. 接口配置页 → "导出" → 得到 `apis-export-YYYYMMDD...xlsx`
2. Excel 打开：
   - [ ] `_使用说明` 是第一个 Sheet，内容完整
   - [ ] 每个域一个 Sheet（域名有 `/` 的 Sheet 名应变成 `_`）
   - [ ] `未归类` Sheet 存在（如果有未归类接口）
   - [ ] 表头行冻结、加粗、有 comment
   - [ ] 变长字段单元格内容形如 `Auth|是|Bearer||`
3. 改一个接口的"接口名"列，保存
4. UI → "导入" → 选刚刚改过的 xlsx → 应弹出确认框 → 确认 → toast 显示 `更新 1 个`
5. 刷新表格 → 该接口名字已更新

- [ ] **Step 3: 拒收非 .xlsx**

导入按钮 → 尝试选一个 `.json` 文件（如果 file input 会过滤，只能通过在 devtools 里改 accept）→ 或直接对空表格 fetch 上传：

```bash
curl -F "file=@some.txt;filename=some.json;type=application/json" http://localhost:8080/admin/api/apis/import
```

Expected: `{"detail":{"code":40410,"message":"仅支持 .xlsx 文件"}}`

- [ ] **Step 4: 空文件报错**

新建一个空 Excel（只留默认 Sheet1 空表），改名为 `empty.xlsx` → 导入 → toast 应显示错误 "Excel 中未找到任何数据 Sheet"

- [ ] **Step 5: 跨 Sheet 移动 = 换域**

1. 前端造两个域 A、B，各绑 1 个接口
2. 导出 xlsx
3. Excel 里把 A 的接口那行剪切粘贴到 B 的 Sheet 里，保存
4. 导入 → 该接口 domain 应变为 B

- [ ] **Step 6: 关闭进程**

按 `Ctrl+C` 关闭前后端；确认没有残留端口占用（`netstat -ano | findstr :8080` 或 `lsof -i:8080` 应无输出）。

- [ ] **Step 7: 无代码变更，不提交**

（本 Task 只做验证，若发现 bug 请回到对应 Task 修复并新建 commit）

---

## Self-Review Checklist（写完 plan 后自查记录）

- [x] **Spec 覆盖**：
  - Sheet 划分（一域一 Sheet + 未归类 + `_使用说明`）→ Task 3
  - 主表 20 列 → Task 3 常量 + Task 4 反解
  - 变长单元格「多行 + `|`」+ 值含 `|` 报错 → Task 1
  - Sheet 名清洗 + A1 comment → Task 2 + Task 3
  - `(method, path)` 全局匹配 → Task 6
  - 拓扑名解析 3 分支 → Task 4
  - 未在 Excel 里的接口"保留不删" → Task 6（隐式：只做 upsert，不做 DELETE）
  - 未建模 config 键保留 → Task 6
  - warnings 结构 → Task 4 + Task 6
  - 事务边界 + 两阶段路由挂载 → Task 6
  - 完全替换 JSON → Task 5 + Task 6
  - 前端 accept 收窄 → Task 8
  - 空文件致命错 → Task 4

- [x] **占位扫描**：无 TBD / TODO；每步含实际代码/命令
- [x] **类型一致性**：
  - `ParseResult` 字段一致：Task 4 定义 → Task 6 使用
  - `MAIN_HEADERS` 常量：Task 1 定义 → Task 3 / Task 4 / Task 6 一致引用
  - `format_cell_list(records, columns)` 参数顺序在所有测试和实现里一致
  - `parse_cell_list(cell_text, columns, row_hint)` 三参签名前后一致
  - `sanitize_sheet_name(name, used)` 副作用（改 used）在测试和实现中一致
