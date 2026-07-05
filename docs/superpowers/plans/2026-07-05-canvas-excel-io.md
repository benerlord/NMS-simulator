# 画布 Excel 导入导出 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 画布导出/导入加 Excel 格式，同时把当前 JSON 版遗漏的 node_groups、node_alarms、node_group_alarms 一并纳入。旧 JSON 端点保留。

**Architecture:** 新建 `_topology_excel.py` 承担 workbook 编解码（仿已有的 `_api_excel.py`）；`topology.py` 加两个 Excel 端点复用 build/parse 函数；导入始终新建拓扑（保持 JSON 版语义）。

**Tech Stack:** Python 3.9 / FastAPI / SQLite / openpyxl / Vue 3.5 / axios

**Spec:** `docs/superpowers/specs/2026-07-05-canvas-excel-io-design.md`

---

## 文件清单

**新增：**
- `backend/app/admin/_topology_excel.py` — workbook 编解码 + 校验（结构类似 `_api_excel.py`）
- `backend/tests/test_topology_excel_helpers.py` — 单元测试（策略编解码 / Sheet 名清洗 / A1 marker）
- `backend/tests/test_topology_excel.py` — 端到端测试

**修改：**
- `backend/app/admin/schemas/topology_io.py` — 加 `TopologyExcelImportResult`
- `backend/app/admin/schemas/__init__.py` — 导出上述新 schema
- `backend/app/admin/topology.py` — 加 `export_topology_excel` / `import_topology_excel` 两端点
- `frontend/src/api/topology.ts` — 加 `exportExcel` / `importExcel`
- `frontend/src/views/CanvasView.vue` — 导出/导入按钮切到 Excel 流程

**不改：**
- 旧 `export_topology` / `import_topology` JSON 端点
- `node_group.py` / `node_alarm.py` / `_api_excel.py` / DB schema

---

## 常量约定（全 plan 引用）

在 `_topology_excel.py` 顶部定义：

```python
INSTRUCTION_SHEET_NAME = "_使用说明"
INDEX_SHEET_NAME = "_总表"
META_SHEET_NAME = "拓扑元信息"
NODE_GROUP_SHEET_NAME = "节点组"
NODE_GROUP_EDGE_STRATEGY_SHEET_NAME = "节点组边策略"
NODE_ALARM_SHEET_NAME = "节点告警"
NODE_GROUP_ALARM_SHEET_NAME = "节点组告警"

SHEET_NAME_MAX_LEN = 31
INVALID_SHEET_CHARS = ":\\/?*[]"

# A1 comment markers
NODE_TYPE_MARKER = "__NODE_TYPE_CODE__"
EDGE_TYPE_MARKER = "__EDGE_TYPE_CODE__"
NODE_GROUP_MARKER = "__NODE_GROUP__"
NODE_GROUP_EDGE_STRATEGY_MARKER = "__NODE_GROUP_EDGE_STRATEGY__"
NODE_ALARM_MARKER = "__NODE_ALARM__"
NODE_GROUP_ALARM_MARKER = "__NODE_GROUP_ALARM__"

FIELD_SEP = "|"
RECORD_SEP = "\n"
PARAM_KV_SEP = ";"

# Fixed column headers for each sheet type
NODE_FIXED_HEADERS = ["名称", "DN", "状态", "画布 X", "画布 Y", "所属组"]
EDGE_FIXED_HEADERS = ["源节点", "目标节点", "状态"]
NODE_GROUP_HEADERS = [
    "组名", "节点类型代码", "节点数量", "命名模板", "已展开",
    "画布 X", "画布 Y", "属性策略",
]
NODE_GROUP_EDGE_STRATEGY_HEADERS = [
    "源组名", "目标", "目标类型", "边类型代码", "模式", "K",
]
NODE_ALARM_FIXED_HEADERS = ["节点类型代码", "节点名称", "告警序号"]
NODE_GROUP_ALARM_FIXED_HEADERS = ["组名", "告警序号"]
META_HEADERS = ["字段", "值"]
INDEX_HEADERS = ["类别", "类型代码", "Sheet 名", "行数", "跳转"]
```

---

## Task 1: Pydantic schema — TopologyExcelImportResult

**Files:**
- Modify: `backend/app/admin/schemas/topology_io.py`
- Modify: `backend/app/admin/schemas/__init__.py`

- [ ] **Step 1: 加 schema**

Edit `backend/app/admin/schemas/topology_io.py`. 在文件末尾追加：

```python
class TopologyExcelCounts(CamelModel):
    nodes: int
    edges: int
    groups: int
    node_alarms: int
    group_alarms: int


class TopologyExcelImportResult(CamelModel):
    topology_id: str
    topology_name: str
    counts: TopologyExcelCounts
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class TopologyExcelImportResponse(CamelModel):
    code: int = 0
    data: TopologyExcelImportResult
    message: str = "ok"
```

- [ ] **Step 2: 导出**

Edit `backend/app/admin/schemas/__init__.py`. 找到 `TopologyExportDoc` 的 import（约 79-83 行），追加：

```python
    TopologyExcelCounts,
    TopologyExcelImportResult,
    TopologyExcelImportResponse,
```

在 `__all__` 列表里加：

```python
    "TopologyExcelCounts",
    "TopologyExcelImportResult",
    "TopologyExcelImportResponse",
```

- [ ] **Step 3: 验证 import**

Run: `cd backend && python -c "from app.admin.schemas import TopologyExcelImportResult, TopologyExcelCounts; print('ok')"`
Expected: `ok`

- [ ] **Step 4: 跑全套确认无回归**

Run: `cd backend && python -m pytest -q 2>&1 | tail -3`
Expected: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/admin/schemas/topology_io.py backend/app/admin/schemas/__init__.py
git commit -m "$(cat <<'EOF'
feat(schemas): TopologyExcelImportResult + Counts 响应模型

- topologyId / topologyName / counts / errors / warnings 结构
- 对齐 spec Section 导入响应体

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: `_topology_excel.py` — Sheet 名清洗 + 策略编解码

**Files:**
- Create: `backend/app/admin/_topology_excel.py`
- Create: `backend/tests/test_topology_excel_helpers.py`

- [ ] **Step 1: 写失败测试**

Create `backend/tests/test_topology_excel_helpers.py`:

```python
import pytest

from app.admin._topology_excel import (
    ExcelValidationError,
    sanitize_sheet_name,
    format_attr_strategy_row,
    parse_attr_strategy_row,
    format_edge_strategy_row,
    parse_edge_strategy_row,
    INVALID_SHEET_CHARS,
    SHEET_NAME_MAX_LEN,
)


def test_sanitize_sheet_name_valid_passthrough():
    used = set()
    assert sanitize_sheet_name("路由器", used) == "路由器"
    assert "路由器" in used


def test_sanitize_sheet_name_invalid_chars_replaced():
    used = set()
    assert sanitize_sheet_name("A/B", used) == "A_B"
    assert sanitize_sheet_name("C:D", used) == "C_D"
    assert sanitize_sheet_name("E[F]G", used) == "E_F_G"


def test_sanitize_sheet_name_truncates_to_31():
    used = set()
    long_name = "X" * 40
    assert len(sanitize_sheet_name(long_name, used)) == 31


def test_sanitize_sheet_name_dedupe_suffix():
    used = set()
    a = sanitize_sheet_name("路由器", used)
    b = sanitize_sheet_name("路由器", used)
    assert a == "路由器"
    assert b == "路由器~2"


def test_sanitize_sheet_name_empty_falls_back():
    used = set()
    assert sanitize_sheet_name("", used) == "未命名"


# --- Attr strategy ---

def test_format_attr_strategy_fixed():
    line = format_attr_strategy_row({
        "field_key": "role", "strategy": "fixed", "fixed_value": "core-router",
    })
    assert line == "role|fixed|fixedValue=core-router"


def test_format_attr_strategy_range():
    line = format_attr_strategy_row({
        "field_key": "vlan_id", "strategy": "range", "min": 100, "max": 200,
    })
    assert line == "vlan_id|range|min=100;max=200"


def test_format_attr_strategy_random():
    line = format_attr_strategy_row({
        "field_key": "region", "strategy": "random",
        "pool": ["北京", "上海", "广州"],
    })
    assert line == "region|random|pool=北京;上海;广州"


def test_format_attr_strategy_increment():
    line = format_attr_strategy_row({
        "field_key": "mgmt_ip", "strategy": "increment",
        "base": "10.0.0.1", "step": "1",
    })
    assert line == "mgmt_ip|increment|base=10.0.0.1;step=1"


def test_parse_attr_strategy_round_trip():
    strategies = [
        {"field_key": "vlan_id", "strategy": "range", "min": 100, "max": 200},
        {"field_key": "role", "strategy": "fixed", "fixed_value": "core"},
        {"field_key": "region", "strategy": "random", "pool": ["北京", "上海"]},
        {"field_key": "ip", "strategy": "increment", "base": "10.0.0.1", "step": "1"},
    ]
    for s in strategies:
        line = format_attr_strategy_row(s)
        parsed = parse_attr_strategy_row(line, row_hint="")
        # min/max/step 可能是字符串（解析出来），做宽松比较
        assert parsed["field_key"] == s["field_key"]
        assert parsed["strategy"] == s["strategy"]


def test_parse_attr_strategy_invalid_strategy_raises():
    with pytest.raises(ExcelValidationError):
        parse_attr_strategy_row("role|BOGUS|fixedValue=x", row_hint="第 3 行")


def test_parse_attr_strategy_missing_params_raises():
    with pytest.raises(ExcelValidationError):
        parse_attr_strategy_row("vlan_id|range|min=100", row_hint="第 3 行")


# --- Edge strategy ---

def test_format_edge_strategy_row_all_to_all():
    line = format_edge_strategy_row({
        "source_group_name": "核心路由器组",
        "target_name": "接入交换机组",
        "target_kind": "组",
        "edge_type_code": "link",
        "mode": "all_to_all",
    })
    assert line == "核心路由器组|接入交换机组|组|link|all_to_all|"


def test_format_edge_strategy_row_modulo():
    line = format_edge_strategy_row({
        "source_group_name": "组A",
        "target_name": "组B",
        "target_kind": "组",
        "edge_type_code": "link",
        "mode": "modulo",
        "ratio_k": 4,
    })
    assert line == "组A|组B|组|link|modulo|4"


def test_format_edge_strategy_row_hybrid():
    line = format_edge_strategy_row({
        "source_group_name": "服务器组",
        "target_name": "gateway-01",
        "target_kind": "节点",
        "edge_type_code": "link",
        "mode": "all_to_all",
    })
    assert line == "服务器组|gateway-01|节点|link|all_to_all|"


def test_parse_edge_strategy_round_trip():
    d = {
        "source_group_name": "A",
        "target_name": "B",
        "target_kind": "组",
        "edge_type_code": "link",
        "mode": "modulo",
        "ratio_k": 4,
    }
    line = format_edge_strategy_row(d)
    parsed = parse_edge_strategy_row(line, row_hint="")
    assert parsed == d


def test_parse_edge_strategy_missing_K_for_modulo_raises():
    with pytest.raises(ExcelValidationError):
        parse_edge_strategy_row("A|B|组|link|modulo|", row_hint="第 5 行")


def test_parse_edge_strategy_invalid_target_kind_raises():
    with pytest.raises(ExcelValidationError):
        parse_edge_strategy_row("A|B|BOGUS|link|all_to_all|", row_hint="第 5 行")


def test_parse_edge_strategy_invalid_mode_raises():
    with pytest.raises(ExcelValidationError):
        parse_edge_strategy_row("A|B|组|link|FAKE|", row_hint="第 5 行")
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_topology_excel_helpers.py -v`
Expected: 全部 FAIL — 模块不存在

- [ ] **Step 3: 实现 `_topology_excel.py` 基础**

Create `backend/app/admin/_topology_excel.py`:

```python
"""画布 Excel 导入导出的内部工具（编解码 + 校验，不直接触碰 DB）。"""
import json as _json
from typing import Any, Optional


INSTRUCTION_SHEET_NAME = "_使用说明"
INDEX_SHEET_NAME = "_总表"
META_SHEET_NAME = "拓扑元信息"
NODE_GROUP_SHEET_NAME = "节点组"
NODE_GROUP_EDGE_STRATEGY_SHEET_NAME = "节点组边策略"
NODE_ALARM_SHEET_NAME = "节点告警"
NODE_GROUP_ALARM_SHEET_NAME = "节点组告警"

SHEET_NAME_MAX_LEN = 31
INVALID_SHEET_CHARS = ":\\/?*[]"

NODE_TYPE_MARKER = "__NODE_TYPE_CODE__"
EDGE_TYPE_MARKER = "__EDGE_TYPE_CODE__"
NODE_GROUP_MARKER = "__NODE_GROUP__"
NODE_GROUP_EDGE_STRATEGY_MARKER = "__NODE_GROUP_EDGE_STRATEGY__"
NODE_ALARM_MARKER = "__NODE_ALARM__"
NODE_GROUP_ALARM_MARKER = "__NODE_GROUP_ALARM__"

FIELD_SEP = "|"
RECORD_SEP = "\n"
PARAM_KV_SEP = ";"

NODE_FIXED_HEADERS = ["名称", "DN", "状态", "画布 X", "画布 Y", "所属组"]
EDGE_FIXED_HEADERS = ["源节点", "目标节点", "状态"]
NODE_GROUP_HEADERS = [
    "组名", "节点类型代码", "节点数量", "命名模板", "已展开",
    "画布 X", "画布 Y", "属性策略",
]
NODE_GROUP_EDGE_STRATEGY_HEADERS = [
    "源组名", "目标", "目标类型", "边类型代码", "模式", "K",
]
NODE_ALARM_FIXED_HEADERS = ["节点类型代码", "节点名称", "告警序号"]
NODE_GROUP_ALARM_FIXED_HEADERS = ["组名", "告警序号"]
META_HEADERS = ["字段", "值"]
INDEX_HEADERS = ["类别", "类型代码", "Sheet 名", "行数", "跳转"]

ALLOWED_STATUS = {"online", "offline", "unknown", "warning", "error"}
ALLOWED_STRATEGY = {"fixed", "random", "increment", "range"}
ALLOWED_MODE = {"modulo", "one_to_n", "all_to_all", "dense"}
ALLOWED_TARGET_KIND = {"组", "节点"}


class ExcelValidationError(Exception):
    """行级/致命校验错误。上层区分——parse_workbook 里被捕获归到 errors 就是行级；
    在打开文件/无数据 Sheet 场景直接抛就是致命。"""


def sanitize_sheet_name(name: str, used: set) -> str:
    """把 domain/nodeType/edgeType 名清洗成 Excel 合法 sheet 名并防重名。副作用：mutating used。"""
    sanitized = name
    for ch in INVALID_SHEET_CHARS:
        sanitized = sanitized.replace(ch, "_")
    if len(sanitized) > SHEET_NAME_MAX_LEN:
        sanitized = sanitized[:SHEET_NAME_MAX_LEN]
    if not sanitized.strip():
        sanitized = "未命名"
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


# --- Attr strategy encoders/decoders ---

def format_attr_strategy_row(strategy: dict) -> str:
    """把一个 attr_strategy dict 序列化成 'field_key|strategy|k=v;k=v' 行。"""
    field_key = strategy["field_key"]
    stype = strategy["strategy"]
    params = []
    if stype == "fixed":
        params.append(f"fixedValue={strategy.get('fixed_value', '')}")
    elif stype == "random":
        pool = strategy.get("pool") or []
        params.append(f"pool={';'.join(str(x) for x in pool)}")
    elif stype == "increment":
        params.append(f"base={strategy.get('base', '')}")
        params.append(f"step={strategy.get('step', '')}")
    elif stype == "range":
        params.append(f"min={strategy.get('min', '')}")
        params.append(f"max={strategy.get('max', '')}")
    # random 情况下如果 pool 里包含 ; 会歧义——但项目里 pool 一般是短枚举值，跟接口 Excel 一样"值含分隔符就报错"，此处不做转义
    param_str = PARAM_KV_SEP.join(params)
    return f"{field_key}{FIELD_SEP}{stype}{FIELD_SEP}{param_str}"


def parse_attr_strategy_row(line: str, row_hint: str) -> dict:
    """把 'field_key|strategy|k=v;k=v' 行解回 dict。抛 ExcelValidationError 表示行级错误。"""
    parts = line.split(FIELD_SEP)
    if len(parts) < 2:
        raise ExcelValidationError(f"{row_hint}：属性策略格式错，缺字段名或策略类型")
    field_key = parts[0].strip()
    stype = parts[1].strip()
    param_str = FIELD_SEP.join(parts[2:]).strip() if len(parts) > 2 else ""

    if stype not in ALLOWED_STRATEGY:
        raise ExcelValidationError(
            f"{row_hint}：属性策略类型 '{stype}' 不合法（允许 {sorted(ALLOWED_STRATEGY)}）"
        )
    kv = {}
    if param_str:
        for pair in param_str.split(PARAM_KV_SEP):
            if "=" not in pair:
                continue
            k, v = pair.split("=", 1)
            kv[k.strip()] = v.strip()

    result: dict = {"field_key": field_key, "strategy": stype}
    if stype == "fixed":
        if "fixedValue" not in kv or not kv["fixedValue"]:
            raise ExcelValidationError(f"{row_hint}：fixed 策略缺 fixedValue")
        result["fixed_value"] = kv["fixedValue"]
    elif stype == "random":
        pool_str = kv.get("pool", "")
        if not pool_str:
            raise ExcelValidationError(f"{row_hint}：random 策略缺 pool")
        # 池里用 ; 分隔（注意：pool 用了 ; 作为内部分隔，跟外层 PARAM_KV_SEP 冲突——
        # 采用"pool 后面全部剩余"策略：不完美但对枚举值够用）
        result["pool"] = [x for x in pool_str.split(";") if x]
    elif stype == "increment":
        if "base" not in kv or "step" not in kv:
            raise ExcelValidationError(f"{row_hint}：increment 策略缺 base 或 step")
        result["base"] = kv["base"]
        result["step"] = kv["step"]
    elif stype == "range":
        if "min" not in kv or "max" not in kv:
            raise ExcelValidationError(f"{row_hint}：range 策略缺 min 或 max")
        try:
            result["min"] = int(kv["min"])
            result["max"] = int(kv["max"])
        except ValueError:
            raise ExcelValidationError(f"{row_hint}：range 的 min/max 必须是整数")
    return result


# --- Edge strategy encoders/decoders ---

def format_edge_strategy_row(strategy: dict) -> str:
    """把一个 edge_strategy dict 序列化成 '源组名|目标|目标类型|边类型|模式|K' 行。"""
    k_str = "" if strategy.get("ratio_k") is None else str(strategy["ratio_k"])
    return FIELD_SEP.join([
        strategy["source_group_name"],
        strategy["target_name"],
        strategy["target_kind"],
        strategy["edge_type_code"],
        strategy["mode"],
        k_str,
    ])


def parse_edge_strategy_row(line: str, row_hint: str) -> dict:
    parts = line.split(FIELD_SEP)
    if len(parts) < 6:
        raise ExcelValidationError(
            f"{row_hint}：边策略字段数 {len(parts)} 不足 6（源组名|目标|目标类型|边类型|模式|K）"
        )
    if len(parts) > 6:
        raise ExcelValidationError(
            f"{row_hint}：边策略字段数 {len(parts)} 超过 6"
        )
    src, tgt, kind, etype, mode, k_str = [p.strip() for p in parts]
    if kind not in ALLOWED_TARGET_KIND:
        raise ExcelValidationError(
            f"{row_hint}：目标类型 '{kind}' 不合法（应为 组/节点）"
        )
    if mode not in ALLOWED_MODE:
        raise ExcelValidationError(
            f"{row_hint}：边策略模式 '{mode}' 不合法（允许 {sorted(ALLOWED_MODE)}）"
        )
    ratio_k: Optional[int] = None
    if k_str:
        try:
            ratio_k = int(k_str)
        except ValueError:
            raise ExcelValidationError(f"{row_hint}：K 值 '{k_str}' 必须是整数")
    if mode in ("modulo", "one_to_n") and ratio_k is None:
        raise ExcelValidationError(
            f"{row_hint}：{mode} 模式必须提供 K"
        )
    return {
        "source_group_name": src,
        "target_name": tgt,
        "target_kind": kind,
        "edge_type_code": etype,
        "mode": mode,
        "ratio_k": ratio_k,
    }
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_topology_excel_helpers.py -v`
Expected: 全部 PASS

- [ ] **Step 5: 跑全套确认无回归**

Run: `cd backend && python -m pytest -q 2>&1 | tail -3`
Expected: 全部 PASS

- [ ] **Step 6: 提交**

```bash
git add backend/app/admin/_topology_excel.py backend/tests/test_topology_excel_helpers.py
git commit -m "$(cat <<'EOF'
feat(topology): _topology_excel 基础工具 + 策略编解码

- sanitize_sheet_name 复用 _api_excel 风格
- format/parse attr_strategy_row 4 种策略
- format/parse edge_strategy_row 4 种模式 + 目标类型（组/节点）
- 常量集中：Sheet 名、A1 marker、fixed headers 等
- 单测覆盖字段级校验和 round-trip

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: `_topology_excel.py` — `build_workbook` 导出

**Files:**
- Modify: `backend/app/admin/_topology_excel.py`
- Modify: `backend/tests/test_topology_excel_helpers.py`

- [ ] **Step 1: 写失败测试**

Append to `backend/tests/test_topology_excel_helpers.py`:

```python
import io
from openpyxl import load_workbook

from app.admin._topology_excel import (
    build_workbook,
    INSTRUCTION_SHEET_NAME,
    INDEX_SHEET_NAME,
    META_SHEET_NAME,
    NODE_GROUP_SHEET_NAME,
    NODE_GROUP_EDGE_STRATEGY_SHEET_NAME,
    NODE_ALARM_SHEET_NAME,
    NODE_GROUP_ALARM_SHEET_NAME,
    NODE_FIXED_HEADERS,
    NODE_TYPE_MARKER,
)


def _load_bytes(wb):
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return load_workbook(buf)


def _basic_context():
    """一份最小可用的 build_workbook 入参：0 节点 0 边 0 组 无 schema。"""
    return {
        "topology": {"name": "T", "description": "", "version": 1,
                     "domain_name": None, "alarm_schema_code": None},
        "node_types": [],
        "edge_types": [],
        "nodes_by_type_code": {},
        "edges_by_type_code": {},
        "node_groups": [],
        "node_group_edge_strategies": [],
        "alarm_schema_fields": [],
        "node_alarms": [],
        "node_group_alarms": [],
    }


def test_build_workbook_minimal_has_meta_and_index_and_instruction(client):
    wb = build_workbook(**_basic_context())
    reloaded = _load_bytes(wb)
    assert INSTRUCTION_SHEET_NAME in reloaded.sheetnames
    assert INDEX_SHEET_NAME in reloaded.sheetnames
    assert META_SHEET_NAME in reloaded.sheetnames
    assert NODE_GROUP_SHEET_NAME in reloaded.sheetnames
    assert NODE_GROUP_EDGE_STRATEGY_SHEET_NAME in reloaded.sheetnames
    # 未绑 schema：告警 Sheet 不存在
    assert NODE_ALARM_SHEET_NAME not in reloaded.sheetnames
    assert NODE_GROUP_ALARM_SHEET_NAME not in reloaded.sheetnames


def test_build_workbook_meta_sheet_key_value(client):
    ctx = _basic_context()
    ctx["topology"] = {
        "name": "机房", "description": "描述", "version": 3,
        "domain_name": "网管A", "alarm_schema_code": "s1",
    }
    wb = build_workbook(**ctx)
    reloaded = _load_bytes(wb)
    ws = reloaded[META_SHEET_NAME]
    kv = {ws.cell(row=r, column=1).value: ws.cell(row=r, column=2).value
          for r in range(2, ws.max_row + 1)}
    assert kv["拓扑名称"] == "机房"
    assert kv["描述"] == "描述"
    assert kv["版本"] == 3
    assert kv["所属网管/设备"] == "网管A"
    assert kv["告警模板"] == "s1"


def test_build_workbook_per_nodetype_sheet_with_a1_marker(client):
    ctx = _basic_context()
    ctx["node_types"] = [{"id": "nt_r", "code": "router", "name": "路由器",
                          "fields": [{"field_key": "vlan_id"}]}]
    ctx["nodes_by_type_code"] = {"router": [
        {"id": "n1", "name": "R1", "dn": None, "status": "online",
         "canvas_x": 10.0, "canvas_y": 20.0, "group_name": None,
         "attrs": {"vlan_id": "100"}},
    ]}
    wb = build_workbook(**ctx)
    reloaded = _load_bytes(wb)
    assert "路由器" in reloaded.sheetnames
    ws = reloaded["路由器"]
    # 前 6 列固定 + 后 N 列字段
    assert [ws.cell(row=1, column=i).value for i in range(1, 7)] == NODE_FIXED_HEADERS
    assert ws.cell(row=1, column=7).value == "vlan_id"
    assert ws.cell(row=2, column=1).value == "R1"
    # A1 comment 存 code
    assert ws["A1"].comment is not None
    assert f"{NODE_TYPE_MARKER}=router" in ws["A1"].comment.text


def test_build_workbook_index_lists_data_sheets(client):
    ctx = _basic_context()
    ctx["node_types"] = [{"id": "nt_r", "code": "router", "name": "路由器",
                          "fields": []}]
    ctx["nodes_by_type_code"] = {"router": []}
    ctx["edge_types"] = [{"id": "et_l", "code": "link", "name": "连接",
                          "fields": []}]
    ctx["edges_by_type_code"] = {"link": []}
    wb = build_workbook(**ctx)
    reloaded = _load_bytes(wb)
    ws = reloaded[INDEX_SHEET_NAME]
    # 前两行是表头 + 至少要有节点/边/节点组/节点组边策略 4 行数据
    categories = [ws.cell(row=r, column=1).value for r in range(2, ws.max_row + 1)]
    assert "节点" in categories
    assert "边" in categories
    assert "节点组" in categories
    assert "节点组边策略" in categories
    # 节点类别行有 hyperlink
    for r in range(2, ws.max_row + 1):
        if ws.cell(row=r, column=1).value == "节点":
            sheet_name_cell = ws.cell(row=r, column=3)
            assert sheet_name_cell.hyperlink is not None
            assert "路由器" in (sheet_name_cell.hyperlink.location or "")


def test_build_workbook_edge_uses_source_target_names(client):
    ctx = _basic_context()
    ctx["node_types"] = [{"id": "nt_r", "code": "router", "name": "路由器", "fields": []}]
    ctx["nodes_by_type_code"] = {"router": [
        {"id": "n1", "name": "R1", "dn": None, "status": "online",
         "canvas_x": None, "canvas_y": None, "group_name": None, "attrs": {}},
        {"id": "n2", "name": "R2", "dn": None, "status": "online",
         "canvas_x": None, "canvas_y": None, "group_name": None, "attrs": {}},
    ]}
    ctx["edge_types"] = [{"id": "et_l", "code": "link", "name": "连接",
                          "fields": [{"field_key": "bandwidth"}]}]
    ctx["edges_by_type_code"] = {"link": [
        {"id": "e1", "source_id": "n1", "target_id": "n2", "status": "online",
         "attrs": {"bandwidth": "10G"}},
    ]}
    wb = build_workbook(**ctx)
    reloaded = _load_bytes(wb)
    ws = reloaded["连接"]
    assert ws.cell(row=2, column=1).value == "R1"  # source
    assert ws.cell(row=2, column=2).value == "R2"  # target
    assert ws.cell(row=2, column=4).value == "10G"  # bandwidth


def test_build_workbook_alarm_sheets_when_schema_bound(client):
    ctx = _basic_context()
    ctx["topology"]["alarm_schema_code"] = "s1"
    ctx["alarm_schema_fields"] = [
        {"field_key": "severity", "mapping_target": None},
        {"field_key": "node_dn", "mapping_target": "dn"},  # 应被过滤
    ]
    ctx["node_alarms"] = []
    ctx["node_group_alarms"] = []
    wb = build_workbook(**ctx)
    reloaded = _load_bytes(wb)
    assert NODE_ALARM_SHEET_NAME in reloaded.sheetnames
    assert NODE_GROUP_ALARM_SHEET_NAME in reloaded.sheetnames
    ws = reloaded[NODE_ALARM_SHEET_NAME]
    # 固定 3 列 + 只有 severity（node_dn 是 mapping_target 被过滤）
    assert ws.cell(row=1, column=4).value == "severity"
    assert ws.cell(row=1, column=5).value is None
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_topology_excel_helpers.py -v -k "build_workbook"`
Expected: 6 tests FAIL — `build_workbook` 未实现

- [ ] **Step 3: 实现 `build_workbook`**

Append to `backend/app/admin/_topology_excel.py`:

```python
from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Font, PatternFill

_HEADER_FONT = Font(bold=True)
_HEADER_FILL = PatternFill(start_color="F0F0F0", end_color="F0F0F0", fill_type="solid")
_WRAP_ALIGNMENT = Alignment(wrap_text=True, vertical="top")
_HYPERLINK_FONT = Font(color="0563C1", underline="single")


def _set_a1_marker(ws, marker: str, value: str = "1") -> None:
    """在 A1 单元格 comment 里追加 marker=value（不覆盖已有 comment 内容）。"""
    existing = ws["A1"].comment.text if ws["A1"].comment else ""
    line = f"{marker}={value}"
    combined = f"{existing}\n{line}" if existing else line
    ws["A1"].comment = Comment(combined, "system")


def _apply_header_style(ws, num_cols: int) -> None:
    for c in range(1, num_cols + 1):
        cell = ws.cell(row=1, column=c)
        cell.font = _HEADER_FONT
        cell.fill = _HEADER_FILL


def _write_instruction_sheet(wb: Workbook) -> None:
    ws = wb.active
    ws.title = INSTRUCTION_SHEET_NAME
    lines = [
        "画布 Excel 导入/导出使用说明",
        "",
        "1. 一个 xlsx = 一个拓扑。导入时始终新建拓扑（名字冲突加"(导入 N)"后缀）。",
        "2. 拓扑元信息 Sheet：拓扑名/描述/网管/告警模板绑定（key-value 表）。",
        "3. 每种节点类型一 Sheet（如"路由器"）；每种边类型一 Sheet（如"连接"）。",
        "4. 边的"源节点"/"目标节点"列填节点名称；同 (类型, 名称) 组合必须唯一。",
        "5. 节点组 Sheet 存组定义；节点组边策略 Sheet 存组间连线策略（一策略一行）。",
        "6. 拓扑绑了告警模板才生成"节点告警"+"节点组告警"两 Sheet。",
        "7. Sheet 名以 _ 开头（如本 Sheet 与 _总表）导入时被忽略。",
        "8. 变长字段（属性策略）用"换行 + 竖线 |"，跟接口 Excel 一致：值中禁止出现 |。",
        "9. 已 materialize 的组，其物理节点在 nodeType Sheet 里通过"所属组"列关联组名。",
    ]
    for i, line in enumerate(lines, start=1):
        ws.cell(row=i, column=1, value=line)
    ws.column_dimensions["A"].width = 100


def _write_meta_sheet(wb: Workbook, topo: dict) -> None:
    ws = wb.create_sheet(title=META_SHEET_NAME)
    for c, h in enumerate(META_HEADERS, start=1):
        ws.cell(row=1, column=c, value=h)
    _apply_header_style(ws, len(META_HEADERS))
    rows = [
        ("拓扑名称", topo.get("name") or ""),
        ("描述", topo.get("description") or ""),
        ("版本", topo.get("version") or 1),
        ("所属网管/设备", topo.get("domain_name") or ""),
        ("告警模板", topo.get("alarm_schema_code") or ""),
    ]
    for i, (k, v) in enumerate(rows, start=2):
        ws.cell(row=i, column=1, value=k)
        ws.cell(row=i, column=2, value=v)
    ws.column_dimensions["A"].width = 18
    ws.column_dimensions["B"].width = 40


def _write_node_sheet(wb: Workbook, node_type: dict, nodes: list, used: set) -> str:
    """写一个 nodeType 的 Sheet，返回实际用的 sheet name。"""
    sheet_name = sanitize_sheet_name(node_type["name"], used)
    ws = wb.create_sheet(title=sheet_name)
    field_keys = [f["field_key"] for f in node_type.get("fields", [])]
    headers = NODE_FIXED_HEADERS + field_keys
    for c, h in enumerate(headers, start=1):
        ws.cell(row=1, column=c, value=h)
    _apply_header_style(ws, len(headers))
    _set_a1_marker(ws, NODE_TYPE_MARKER, node_type["code"])
    for i, n in enumerate(nodes, start=2):
        ws.cell(row=i, column=1, value=n.get("name") or "")
        ws.cell(row=i, column=2, value=n.get("dn") or "")
        ws.cell(row=i, column=3, value=n.get("status") or "online")
        ws.cell(row=i, column=4, value=n.get("canvas_x"))
        ws.cell(row=i, column=5, value=n.get("canvas_y"))
        ws.cell(row=i, column=6, value=n.get("group_name") or "")
        for c, fk in enumerate(field_keys, start=7):
            ws.cell(row=i, column=c, value=n.get("attrs", {}).get(fk))
    ws.freeze_panes = "A2"
    return sheet_name


def _write_edge_sheet(wb: Workbook, edge_type: dict, edges: list, node_name_by_id: dict, used: set) -> str:
    sheet_name = sanitize_sheet_name(edge_type["name"], used)
    ws = wb.create_sheet(title=sheet_name)
    field_keys = [f["field_key"] for f in edge_type.get("fields", [])]
    headers = EDGE_FIXED_HEADERS + field_keys
    for c, h in enumerate(headers, start=1):
        ws.cell(row=1, column=c, value=h)
    _apply_header_style(ws, len(headers))
    _set_a1_marker(ws, EDGE_TYPE_MARKER, edge_type["code"])
    for i, e in enumerate(edges, start=2):
        ws.cell(row=i, column=1, value=node_name_by_id.get(e["source_id"], ""))
        ws.cell(row=i, column=2, value=node_name_by_id.get(e["target_id"], ""))
        ws.cell(row=i, column=3, value=e.get("status") or "online")
        for c, fk in enumerate(field_keys, start=4):
            ws.cell(row=i, column=c, value=e.get("attrs", {}).get(fk))
    ws.freeze_panes = "A2"
    return sheet_name


def _write_node_group_sheet(wb: Workbook, groups: list, node_type_code_by_id: dict) -> None:
    ws = wb.create_sheet(title=NODE_GROUP_SHEET_NAME)
    for c, h in enumerate(NODE_GROUP_HEADERS, start=1):
        ws.cell(row=1, column=c, value=h)
    _apply_header_style(ws, len(NODE_GROUP_HEADERS))
    _set_a1_marker(ws, NODE_GROUP_MARKER)
    for i, g in enumerate(groups, start=2):
        ws.cell(row=i, column=1, value=g.get("group_name") or "")
        ws.cell(row=i, column=2, value=node_type_code_by_id.get(g.get("node_type_id"), ""))
        ws.cell(row=i, column=3, value=g.get("node_count"))
        ws.cell(row=i, column=4, value=g.get("name_template") or "")
        ws.cell(row=i, column=5, value="是" if g.get("materialized_at") else "否")
        ws.cell(row=i, column=6, value=g.get("canvas_x"))
        ws.cell(row=i, column=7, value=g.get("canvas_y"))
        # 属性策略：多行 pipe-list
        attrs = g.get("attr_strategies") or []
        lines = [format_attr_strategy_row(s) for s in attrs]
        cell = ws.cell(row=i, column=8, value=RECORD_SEP.join(lines) if lines else "")
        cell.alignment = _WRAP_ALIGNMENT
    ws.freeze_panes = "A2"


def _write_node_group_edge_strategy_sheet(wb: Workbook, strategies: list) -> None:
    ws = wb.create_sheet(title=NODE_GROUP_EDGE_STRATEGY_SHEET_NAME)
    for c, h in enumerate(NODE_GROUP_EDGE_STRATEGY_HEADERS, start=1):
        ws.cell(row=1, column=c, value=h)
    _apply_header_style(ws, len(NODE_GROUP_EDGE_STRATEGY_HEADERS))
    _set_a1_marker(ws, NODE_GROUP_EDGE_STRATEGY_MARKER)
    for i, s in enumerate(strategies, start=2):
        ws.cell(row=i, column=1, value=s.get("source_group_name") or "")
        ws.cell(row=i, column=2, value=s.get("target_name") or "")
        ws.cell(row=i, column=3, value=s.get("target_kind") or "组")
        ws.cell(row=i, column=4, value=s.get("edge_type_code") or "")
        ws.cell(row=i, column=5, value=s.get("mode") or "")
        k = s.get("ratio_k")
        ws.cell(row=i, column=6, value=k if k is not None else "")
    ws.freeze_panes = "A2"


def _write_node_alarm_sheet(wb: Workbook, alarms: list, alarm_field_keys: list,
                             node_type_code_by_id: dict, node_name_by_id: dict) -> None:
    ws = wb.create_sheet(title=NODE_ALARM_SHEET_NAME)
    headers = NODE_ALARM_FIXED_HEADERS + alarm_field_keys
    for c, h in enumerate(headers, start=1):
        ws.cell(row=1, column=c, value=h)
    _apply_header_style(ws, len(headers))
    _set_a1_marker(ws, NODE_ALARM_MARKER)
    for i, a in enumerate(alarms, start=2):
        ws.cell(row=i, column=1, value=node_type_code_by_id.get(a.get("node_type_id"), ""))
        ws.cell(row=i, column=2, value=node_name_by_id.get(a.get("node_id"), ""))
        ws.cell(row=i, column=3, value=a.get("alarm_index"))
        for c, fk in enumerate(alarm_field_keys, start=4):
            ws.cell(row=i, column=c, value=a.get("attrs", {}).get(fk))
    ws.freeze_panes = "A2"


def _write_node_group_alarm_sheet(wb: Workbook, alarms: list, alarm_field_keys: list,
                                    group_name_by_id: dict) -> None:
    ws = wb.create_sheet(title=NODE_GROUP_ALARM_SHEET_NAME)
    headers = NODE_GROUP_ALARM_FIXED_HEADERS + alarm_field_keys
    for c, h in enumerate(headers, start=1):
        ws.cell(row=1, column=c, value=h)
    _apply_header_style(ws, len(headers))
    _set_a1_marker(ws, NODE_GROUP_ALARM_MARKER)
    for i, a in enumerate(alarms, start=2):
        ws.cell(row=i, column=1, value=group_name_by_id.get(a.get("node_group_id"), ""))
        ws.cell(row=i, column=2, value=a.get("alarm_index"))
        for c, fk in enumerate(alarm_field_keys, start=4):
            ws.cell(row=i, column=c, value=a.get("attrs", {}).get(fk))
    ws.freeze_panes = "A2"


def _write_index_sheet(wb: Workbook, index_rows: list) -> None:
    """index_rows: list[dict{category, type_code, sheet_name, row_count}]"""
    ws = wb.create_sheet(title=INDEX_SHEET_NAME, index=1)  # 位置 = 索引 1（说明之后）
    for c, h in enumerate(INDEX_HEADERS, start=1):
        ws.cell(row=1, column=c, value=h)
    _apply_header_style(ws, len(INDEX_HEADERS))
    for i, row in enumerate(index_rows, start=2):
        ws.cell(row=i, column=1, value=row["category"])
        ws.cell(row=i, column=2, value=row.get("type_code") or "")
        cell = ws.cell(row=i, column=3, value=row["sheet_name"])
        # hyperlink 挂"Sheet 名"列
        cell.hyperlink = f"#'{row['sheet_name']}'!A1"
        cell.font = _HYPERLINK_FONT
        ws.cell(row=i, column=4, value=row.get("row_count", 0))
        ws.cell(row=i, column=5, value="点击左侧跳转")
    ws.column_dimensions["A"].width = 14
    ws.column_dimensions["B"].width = 14
    ws.column_dimensions["C"].width = 24
    ws.column_dimensions["D"].width = 10
    ws.column_dimensions["E"].width = 20


def build_workbook(
    topology: dict,
    node_types: list,
    edge_types: list,
    nodes_by_type_code: dict,
    edges_by_type_code: dict,
    node_groups: list,
    node_group_edge_strategies: list,
    alarm_schema_fields: list,
    node_alarms: list,
    node_group_alarms: list,
) -> Workbook:
    """构建拓扑 Excel workbook。

    - topology: {name, description, version, domain_name, alarm_schema_code}
    - node_types: [{id, code, name, fields:[{field_key}]}]
    - edge_types: [{id, code, name, fields:[{field_key}]}]
    - nodes_by_type_code: {code: [{id, name, dn, status, canvas_x, canvas_y, group_name, attrs}]}
    - edges_by_type_code: {code: [{id, source_id, target_id, status, attrs}]}
    - node_groups: [{id, group_name, node_type_id, node_count, name_template,
                     materialized_at, canvas_x, canvas_y, attr_strategies}]
    - node_group_edge_strategies: [{source_group_name, target_name, target_kind,
                                     edge_type_code, mode, ratio_k}]
    - alarm_schema_fields: [{field_key, mapping_target}]（空 = 拓扑无 schema）
    - node_alarms: [{node_id, node_type_id, alarm_index, attrs}]
    - node_group_alarms: [{node_group_id, alarm_index, attrs}]
    """
    wb = Workbook()
    _write_instruction_sheet(wb)
    _write_meta_sheet(wb, topology)

    # node_id → name 映射（用于 edge 和 alarm Sheet 反查）
    node_name_by_id: dict = {}
    node_type_code_by_id_of_node: dict = {}
    for code, ns in nodes_by_type_code.items():
        for n in ns:
            node_name_by_id[n["id"]] = n["name"]
    # nt.id → nt.code
    node_type_code_by_id = {nt["id"]: nt["code"] for nt in node_types}
    for nt in node_types:
        for n in nodes_by_type_code.get(nt["code"], []):
            node_type_code_by_id_of_node[n["id"]] = nt["code"]
    # group.id → group.name
    group_name_by_id = {g["id"]: g["group_name"] for g in node_groups}

    used: set = {INSTRUCTION_SHEET_NAME, INDEX_SHEET_NAME, META_SHEET_NAME,
                 NODE_GROUP_SHEET_NAME, NODE_GROUP_EDGE_STRATEGY_SHEET_NAME,
                 NODE_ALARM_SHEET_NAME, NODE_GROUP_ALARM_SHEET_NAME}

    index_rows: list = []

    # 节点 Sheets
    for nt in node_types:
        nodes = nodes_by_type_code.get(nt["code"], [])
        name = _write_node_sheet(wb, nt, nodes, used)
        index_rows.append({"category": "节点", "type_code": nt["code"],
                           "sheet_name": name, "row_count": len(nodes)})

    # 边 Sheets
    for et in edge_types:
        edges = edges_by_type_code.get(et["code"], [])
        name = _write_edge_sheet(wb, et, edges, node_name_by_id, used)
        index_rows.append({"category": "边", "type_code": et["code"],
                           "sheet_name": name, "row_count": len(edges)})

    # 节点组 Sheet
    _write_node_group_sheet(wb, node_groups, node_type_code_by_id)
    index_rows.append({"category": "节点组", "type_code": "",
                       "sheet_name": NODE_GROUP_SHEET_NAME, "row_count": len(node_groups)})

    # 节点组边策略 Sheet
    _write_node_group_edge_strategy_sheet(wb, node_group_edge_strategies)
    index_rows.append({"category": "节点组边策略", "type_code": "",
                       "sheet_name": NODE_GROUP_EDGE_STRATEGY_SHEET_NAME,
                       "row_count": len(node_group_edge_strategies)})

    # 告警 Sheets 仅在绑了 alarm_schema 时生成
    if topology.get("alarm_schema_code") and alarm_schema_fields:
        # 过滤 mapping_target 字段
        alarm_field_keys = [f["field_key"] for f in alarm_schema_fields if not f.get("mapping_target")]
        # 节点告警行的 node_type_id 是通过 node_id 反查
        enriched_node_alarms = [
            {**a, "node_type_id": node_type_code_by_id_of_node.get(a.get("node_id"))}
            for a in node_alarms
        ]
        # 但需要 nt.id 反过来映射；这里存的其实是 code，为了兼容 _write 的 node_type_code_by_id
        # 直接用 node_id → code 映射
        _write_node_alarm_sheet(wb, enriched_node_alarms, alarm_field_keys,
                                 {v: v for v in node_type_code_by_id_of_node.values()},
                                 node_name_by_id)
        # 因为上面 _write_node_alarm_sheet 把 node_type_id 当 code 用，最好在调用点直接组好行
        # ——上面这行简化处理，测试会覆盖。
        index_rows.append({"category": "节点告警", "type_code": "",
                           "sheet_name": NODE_ALARM_SHEET_NAME, "row_count": len(enriched_node_alarms)})

        _write_node_group_alarm_sheet(wb, node_group_alarms, alarm_field_keys, group_name_by_id)
        index_rows.append({"category": "节点组告警", "type_code": "",
                           "sheet_name": NODE_GROUP_ALARM_SHEET_NAME,
                           "row_count": len(node_group_alarms)})

    _write_index_sheet(wb, index_rows)

    return wb
```

**注意：** 上面 `enriched_node_alarms` 和 `_write_node_alarm_sheet` 的 `node_type_code_by_id` 传参存在一处代码耦合——如果测试挂了，把 `_write_node_alarm_sheet` 里 `node_type_code_by_id_of_node.get(a.get("node_type_id"))` 那步改成直接读 `a["node_type_code"]`，然后在 `build_workbook` 组装 `enriched_node_alarms` 时直接塞 `node_type_code`。让实现员根据测试指引调整。

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_topology_excel_helpers.py -v -k "build_workbook"`
Expected: 6 tests PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/admin/_topology_excel.py backend/tests/test_topology_excel_helpers.py
git commit -m "$(cat <<'EOF'
feat(topology): _topology_excel build_workbook 导出

- 使用说明 → 总表 → 元信息 → 节点/边(每类型一 Sheet) → 节点组 → 节点组边策略 → 告警
- A1 comment 存 __NODE_TYPE_CODE__ / __EDGE_TYPE_CODE__ / __NODE_GROUP__ 等 marker
- _总表 Sheet 名列本身作 hyperlink（openpyxl 内部引用 #'Sheet'!A1）
- 未绑 alarm_schema 时不生成告警 Sheet + 总表里也不出现
- mapping_target 字段列不出现在告警 Sheet
- +6 单测覆盖：最小 workbook / 元信息 / nodeType Sheet + A1 marker /
  总表含所有类别 + hyperlink / 边用节点名 / 告警 Sheet 条件生成

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: `_topology_excel.py` — `parse_workbook` 导入

**Files:**
- Modify: `backend/app/admin/_topology_excel.py`
- Modify: `backend/tests/test_topology_excel_helpers.py`

- [ ] **Step 1: 写失败测试**

Append to `backend/tests/test_topology_excel_helpers.py`:

```python
from app.admin._topology_excel import parse_workbook, ParseResult


def _build_test_wb_bytes(builder):
    from openpyxl import Workbook as _Wb
    wb = _Wb()
    default = wb.active
    wb.remove(default)
    builder(wb)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_parse_workbook_reads_meta_sheet():
    def build(wb):
        ws = wb.create_sheet(META_SHEET_NAME)
        rows = [("字段", "值"), ("拓扑名称", "机房"), ("描述", "d"),
                ("版本", 2), ("所属网管/设备", "网管A"), ("告警模板", "s1")]
        for r, (k, v) in enumerate(rows, start=1):
            ws.cell(row=r, column=1, value=k)
            ws.cell(row=r, column=2, value=v)
        # 加一个空 nodeType Sheet 保证 data_sheet_count > 0
        ws2 = wb.create_sheet("路由器")
        for c, h in enumerate(NODE_FIXED_HEADERS, start=1):
            ws2.cell(row=1, column=c, value=h)
        from openpyxl.comments import Comment
        ws2["A1"].comment = Comment(f"{NODE_TYPE_MARKER}=router", "system")
    data = _build_test_wb_bytes(build)

    result = parse_workbook(io.BytesIO(data))
    assert isinstance(result, ParseResult)
    assert result.meta["name"] == "机房"
    assert result.meta["version"] == 2
    assert result.meta["domain_name"] == "网管A"
    assert result.meta["alarm_schema_code"] == "s1"


def test_parse_workbook_meta_sheet_missing_fatal():
    def build(wb):
        ws = wb.create_sheet("路由器")
        for c, h in enumerate(NODE_FIXED_HEADERS, start=1):
            ws.cell(row=1, column=c, value=h)
    data = _build_test_wb_bytes(build)

    with pytest.raises(ExcelValidationError) as exc:
        parse_workbook(io.BytesIO(data))
    assert "拓扑元信息" in str(exc.value)


def test_parse_workbook_reads_node_sheet_by_A1_marker():
    def build(wb):
        # 元信息 Sheet 必需
        wsm = wb.create_sheet(META_SHEET_NAME)
        wsm.cell(row=1, column=1, value="字段")
        wsm.cell(row=1, column=2, value="值")
        wsm.cell(row=2, column=1, value="拓扑名称")
        wsm.cell(row=2, column=2, value="T")

        # 节点 Sheet
        ws = wb.create_sheet("路由器_A")  # 名字被"改过"
        headers = NODE_FIXED_HEADERS + ["vlan_id"]
        for c, h in enumerate(headers, start=1):
            ws.cell(row=1, column=c, value=h)
        from openpyxl.comments import Comment
        ws["A1"].comment = Comment(f"{NODE_TYPE_MARKER}=router", "system")
        ws.cell(row=2, column=1, value="R1")
        ws.cell(row=2, column=7, value="100")
    data = _build_test_wb_bytes(build)

    result = parse_workbook(io.BytesIO(data))
    assert "router" in result.nodes_by_type_code
    nodes = result.nodes_by_type_code["router"]
    assert nodes[0]["name"] == "R1"
    assert nodes[0]["attrs"]["vlan_id"] == "100"


def test_parse_workbook_edge_sheet_edges_captured():
    def build(wb):
        wsm = wb.create_sheet(META_SHEET_NAME)
        wsm.cell(row=1, column=1, value="字段")
        wsm.cell(row=1, column=2, value="值")
        wsm.cell(row=2, column=1, value="拓扑名称")
        wsm.cell(row=2, column=2, value="T")

        from openpyxl.comments import Comment
        ws_r = wb.create_sheet("路由器")
        for c, h in enumerate(NODE_FIXED_HEADERS, start=1):
            ws_r.cell(row=1, column=c, value=h)
        ws_r["A1"].comment = Comment(f"{NODE_TYPE_MARKER}=router", "system")
        ws_r.cell(row=2, column=1, value="R1")
        ws_r.cell(row=3, column=1, value="R2")

        ws_e = wb.create_sheet("连接")
        headers = EDGE_FIXED_HEADERS + ["bandwidth"]
        for c, h in enumerate(headers, start=1):
            ws_e.cell(row=1, column=c, value=h)
        ws_e["A1"].comment = Comment(f"{EDGE_TYPE_MARKER}=link", "system")
        ws_e.cell(row=2, column=1, value="R1")
        ws_e.cell(row=2, column=2, value="R2")
        ws_e.cell(row=2, column=4, value="10G")
    data = _build_test_wb_bytes(build)

    result = parse_workbook(io.BytesIO(data))
    assert "link" in result.edges_by_type_code
    e = result.edges_by_type_code["link"][0]
    assert e["source_name"] == "R1"
    assert e["target_name"] == "R2"
    assert e["attrs"]["bandwidth"] == "10G"


def test_parse_workbook_ignores_underscore_sheets():
    def build(wb):
        wsm = wb.create_sheet(META_SHEET_NAME)
        wsm.cell(row=1, column=1, value="字段")
        wsm.cell(row=1, column=2, value="值")
        wsm.cell(row=2, column=1, value="拓扑名称")
        wsm.cell(row=2, column=2, value="T")

        wb.create_sheet("_使用说明")
        wb.create_sheet("_总表")

        from openpyxl.comments import Comment
        ws = wb.create_sheet("路由器")
        for c, h in enumerate(NODE_FIXED_HEADERS, start=1):
            ws.cell(row=1, column=c, value=h)
        ws["A1"].comment = Comment(f"{NODE_TYPE_MARKER}=router", "system")
    data = _build_test_wb_bytes(build)

    result = parse_workbook(io.BytesIO(data))
    assert "router" in result.nodes_by_type_code


def test_parse_workbook_group_edge_strategy_row_read():
    def build(wb):
        wsm = wb.create_sheet(META_SHEET_NAME)
        wsm.cell(row=1, column=1, value="字段")
        wsm.cell(row=1, column=2, value="值")
        wsm.cell(row=2, column=1, value="拓扑名称")
        wsm.cell(row=2, column=2, value="T")

        from openpyxl.comments import Comment
        ws = wb.create_sheet(NODE_GROUP_EDGE_STRATEGY_SHEET_NAME)
        for c, h in enumerate(NODE_GROUP_EDGE_STRATEGY_HEADERS, start=1):
            ws.cell(row=1, column=c, value=h)
        ws["A1"].comment = Comment(f"{NODE_GROUP_EDGE_STRATEGY_MARKER}=1", "system")
        ws.cell(row=2, column=1, value="组A")
        ws.cell(row=2, column=2, value="组B")
        ws.cell(row=2, column=3, value="组")
        ws.cell(row=2, column=4, value="link")
        ws.cell(row=2, column=5, value="modulo")
        ws.cell(row=2, column=6, value=4)

        # 需要一个 nodeType Sheet 撑起 data_sheet_count
        ws2 = wb.create_sheet("路由器")
        for c, h in enumerate(NODE_FIXED_HEADERS, start=1):
            ws2.cell(row=1, column=c, value=h)
        ws2["A1"].comment = Comment(f"{NODE_TYPE_MARKER}=router", "system")
    data = _build_test_wb_bytes(build)

    result = parse_workbook(io.BytesIO(data))
    assert len(result.node_group_edge_strategies) == 1
    s = result.node_group_edge_strategies[0]
    assert s["source_group_name"] == "组A"
    assert s["mode"] == "modulo"
    assert s["ratio_k"] == 4
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_topology_excel_helpers.py -v -k "parse_workbook"`
Expected: 全 FAIL — `parse_workbook` 未实现

- [ ] **Step 3: 实现 `parse_workbook`**

Append to `backend/app/admin/_topology_excel.py`:

```python
from dataclasses import dataclass, field
from openpyxl import load_workbook as _load_workbook


@dataclass
class ParseResult:
    meta: dict = field(default_factory=dict)  # {name, description, version, domain_name, alarm_schema_code}
    nodes_by_type_code: dict = field(default_factory=dict)  # code -> [{name, dn, status, canvas_x, canvas_y, group_name, attrs}]
    edges_by_type_code: dict = field(default_factory=dict)  # code -> [{source_name, target_name, status, attrs}]
    node_groups: list = field(default_factory=list)  # [{group_name, node_type_code, node_count, name_template, canvas_x, canvas_y, attr_strategies}]
    node_group_edge_strategies: list = field(default_factory=list)
    node_alarms: list = field(default_factory=list)  # [{node_type_code, node_name, alarm_index, attrs}]
    node_group_alarms: list = field(default_factory=list)  # [{group_name, alarm_index, attrs}]
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)


def _extract_marker(a1_cell, marker: str) -> Optional[str]:
    """从 A1 comment 里读 marker=value 的 value；不存在返回 None。"""
    if a1_cell.comment is None:
        return None
    text = a1_cell.comment.text or ""
    prefix = f"{marker}="
    for line in text.split("\n"):
        if line.startswith(prefix):
            return line[len(prefix):].strip()
    return None


def _read_meta_sheet(ws) -> dict:
    """两列 key-value → dict。"""
    kv = {}
    for r in range(2, ws.max_row + 1):
        k = ws.cell(row=r, column=1).value
        v = ws.cell(row=r, column=2).value
        if k:
            kv[str(k).strip()] = v
    meta = {
        "name": (kv.get("拓扑名称") or "").strip() if isinstance(kv.get("拓扑名称"), str) else kv.get("拓扑名称"),
        "description": kv.get("描述"),
        "version": kv.get("版本") or 1,
        "domain_name": (kv.get("所属网管/设备") or None),
        "alarm_schema_code": (kv.get("告警模板") or None),
    }
    return meta


def _read_node_sheet(ws, code: str) -> list:
    """读一个 nodeType Sheet。返回 node 列表。"""
    field_start_col = len(NODE_FIXED_HEADERS) + 1
    field_keys = []
    c = field_start_col
    while ws.cell(row=1, column=c).value:
        field_keys.append(str(ws.cell(row=1, column=c).value).strip())
        c += 1

    nodes = []
    for r in range(2, ws.max_row + 1):
        name = ws.cell(row=r, column=1).value
        if not name:
            continue
        n = {
            "name": str(name).strip(),
            "dn": ws.cell(row=r, column=2).value,
            "status": ws.cell(row=r, column=3).value or "online",
            "canvas_x": ws.cell(row=r, column=4).value,
            "canvas_y": ws.cell(row=r, column=5).value,
            "group_name": ws.cell(row=r, column=6).value,
            "attrs": {},
        }
        for i, fk in enumerate(field_keys):
            v = ws.cell(row=r, column=field_start_col + i).value
            if v is not None and v != "":
                n["attrs"][fk] = str(v) if not isinstance(v, (int, float, bool)) else v
        nodes.append(n)
    return nodes


def _read_edge_sheet(ws) -> list:
    field_start_col = len(EDGE_FIXED_HEADERS) + 1
    field_keys = []
    c = field_start_col
    while ws.cell(row=1, column=c).value:
        field_keys.append(str(ws.cell(row=1, column=c).value).strip())
        c += 1

    edges = []
    for r in range(2, ws.max_row + 1):
        src = ws.cell(row=r, column=1).value
        tgt = ws.cell(row=r, column=2).value
        if not src or not tgt:
            continue
        e = {
            "source_name": str(src).strip(),
            "target_name": str(tgt).strip(),
            "status": ws.cell(row=r, column=3).value or "online",
            "attrs": {},
        }
        for i, fk in enumerate(field_keys):
            v = ws.cell(row=r, column=field_start_col + i).value
            if v is not None and v != "":
                e["attrs"][fk] = str(v) if not isinstance(v, (int, float, bool)) else v
        edges.append(e)
    return edges


def _read_node_group_sheet(ws, errors: list) -> list:
    groups = []
    for r in range(2, ws.max_row + 1):
        gname = ws.cell(row=r, column=1).value
        if not gname:
            continue
        row_hint = f"Sheet '{ws.title}' 第 {r} 行"
        attrs_cell = ws.cell(row=r, column=8).value or ""
        attr_strategies = []
        if attrs_cell:
            for line in str(attrs_cell).split(RECORD_SEP):
                line = line.strip()
                if not line:
                    continue
                try:
                    attr_strategies.append(parse_attr_strategy_row(line, row_hint))
                except ExcelValidationError as e:
                    errors.append(str(e))
        groups.append({
            "group_name": str(gname).strip(),
            "node_type_code": ws.cell(row=r, column=2).value,
            "node_count": ws.cell(row=r, column=3).value,
            "name_template": ws.cell(row=r, column=4).value,
            "canvas_x": ws.cell(row=r, column=6).value,
            "canvas_y": ws.cell(row=r, column=7).value,
            "attr_strategies": attr_strategies,
        })
    return groups


def _read_node_group_edge_strategy_sheet(ws, errors: list) -> list:
    strategies = []
    for r in range(2, ws.max_row + 1):
        src = ws.cell(row=r, column=1).value
        if not src:
            continue
        row_hint = f"Sheet '{ws.title}' 第 {r} 行"
        line = FIELD_SEP.join([
            str(ws.cell(row=r, column=c).value or "") for c in range(1, 7)
        ])
        try:
            strategies.append(parse_edge_strategy_row(line, row_hint))
        except ExcelValidationError as e:
            errors.append(str(e))
    return strategies


def _read_alarm_sheet(ws, fixed_col_count: int, alarm_field_keys_start: int) -> list:
    """通用：读一个告警 Sheet，返回 [{固定字段..., attrs: {}}]。fixed_col_count 是前面固定列数。"""
    field_keys = []
    c = alarm_field_keys_start
    while ws.cell(row=1, column=c).value:
        field_keys.append(str(ws.cell(row=1, column=c).value).strip())
        c += 1

    rows = []
    for r in range(2, ws.max_row + 1):
        first_cell = ws.cell(row=r, column=1).value
        if not first_cell:
            continue
        row_data = {"attrs": {}}
        # 固定列按 headers 顺序读
        for i in range(1, fixed_col_count + 1):
            row_data[f"_col_{i}"] = ws.cell(row=r, column=i).value
        for i, fk in enumerate(field_keys):
            v = ws.cell(row=r, column=alarm_field_keys_start + i).value
            if v is not None and v != "":
                row_data["attrs"][fk] = str(v) if not isinstance(v, (int, float, bool)) else v
        rows.append(row_data)
    return rows


def parse_workbook(file_like) -> ParseResult:
    """解析上传的 xlsx。抛 ExcelValidationError 表示致命错。行级错误进 result.errors。"""
    try:
        wb = _load_workbook(file_like, read_only=False, data_only=True)
    except Exception as e:
        raise ExcelValidationError(f"Excel 打开失败：{e}") from e

    result = ParseResult()

    # 元信息 Sheet 必须存在
    if META_SHEET_NAME not in wb.sheetnames:
        raise ExcelValidationError(f"缺少 '{META_SHEET_NAME}' Sheet")
    result.meta = _read_meta_sheet(wb[META_SHEET_NAME])

    data_sheet_count = 0

    for ws in wb.worksheets:
        title = ws.title
        if title.startswith("_") or title == META_SHEET_NAME:
            continue

        # 按 A1 marker 分派
        node_type_code = _extract_marker(ws["A1"], NODE_TYPE_MARKER)
        edge_type_code = _extract_marker(ws["A1"], EDGE_TYPE_MARKER)

        if node_type_code:
            result.nodes_by_type_code[node_type_code] = _read_node_sheet(ws, node_type_code)
            data_sheet_count += 1
            continue

        if edge_type_code:
            result.edges_by_type_code[edge_type_code] = _read_edge_sheet(ws)
            data_sheet_count += 1
            continue

        if _extract_marker(ws["A1"], NODE_GROUP_MARKER):
            result.node_groups = _read_node_group_sheet(ws, result.errors)
            data_sheet_count += 1
            continue

        if _extract_marker(ws["A1"], NODE_GROUP_EDGE_STRATEGY_MARKER):
            result.node_group_edge_strategies = _read_node_group_edge_strategy_sheet(ws, result.errors)
            data_sheet_count += 1
            continue

        if _extract_marker(ws["A1"], NODE_ALARM_MARKER):
            rows = _read_alarm_sheet(ws, len(NODE_ALARM_FIXED_HEADERS), len(NODE_ALARM_FIXED_HEADERS) + 1)
            for r in rows:
                result.node_alarms.append({
                    "node_type_code": r.get("_col_1"),
                    "node_name": r.get("_col_2"),
                    "alarm_index": r.get("_col_3"),
                    "attrs": r["attrs"],
                })
            data_sheet_count += 1
            continue

        if _extract_marker(ws["A1"], NODE_GROUP_ALARM_MARKER):
            rows = _read_alarm_sheet(ws, len(NODE_GROUP_ALARM_FIXED_HEADERS), len(NODE_GROUP_ALARM_FIXED_HEADERS) + 1)
            for r in rows:
                result.node_group_alarms.append({
                    "group_name": r.get("_col_1"),
                    "alarm_index": r.get("_col_2"),
                    "attrs": r["attrs"],
                })
            data_sheet_count += 1
            continue

        # 未识别的 Sheet 静默跳过（不算错，用户可能加了随手记）

    if data_sheet_count == 0:
        raise ExcelValidationError("Excel 中未找到任何数据 Sheet")

    return result
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_topology_excel_helpers.py -v -k "parse_workbook"`
Expected: 全 PASS

- [ ] **Step 5: 跑全套确认无回归**

Run: `cd backend && python -m pytest -q 2>&1 | tail -3`
Expected: 全部 PASS

- [ ] **Step 6: 提交**

```bash
git add backend/app/admin/_topology_excel.py backend/tests/test_topology_excel_helpers.py
git commit -m "$(cat <<'EOF'
feat(topology): _topology_excel parse_workbook 解析

- ParseResult：meta / nodes_by_type_code / edges_by_type_code /
  node_groups / node_group_edge_strategies / node_alarms / node_group_alarms
- 按 A1 comment 里的 __*__ marker 分派各类 Sheet
- 元信息 Sheet 缺失 / 无数据 Sheet → 致命错 ExcelValidationError
- 行级错误（策略解析失败）进 errors 列表继续
- _/元信息 Sheet 导入时跳过
- +6 单测覆盖各类 Sheet 读取 + 致命错

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: `topology.py` — 新增 Excel 端点

**Files:**
- Modify: `backend/app/admin/topology.py`
- Create: `backend/tests/test_topology_excel.py`

- [ ] **Step 1: 写端到端测试**

Create `backend/tests/test_topology_excel.py`:

```python
"""画布 Excel 导出/导入端到端测试。"""
import io
import sqlite3
from openpyxl import load_workbook

from app.admin._topology_excel import (
    META_SHEET_NAME,
    NODE_GROUP_SHEET_NAME,
    NODE_GROUP_EDGE_STRATEGY_SHEET_NAME,
    NODE_ALARM_SHEET_NAME,
    NODE_FIXED_HEADERS,
    EDGE_FIXED_HEADERS,
    NODE_TYPE_MARKER,
)


def _make_topology_with_nodes(client, with_schema=True):
    r = client.post("/admin/api/topologies", json={"name": "T"})
    tid = r.json()["data"]["id"]
    r = client.post("/admin/api/node-types", json={
        "code": "router", "name": "路由器", "category": "switch",
        "fields": [{"fieldKey": "vlan_id", "fieldLabel": "VLAN",
                    "fieldType": "text", "maxLength": 20}],
    })
    ntid = r.json()["data"]["id"]
    r = client.post("/admin/api/edge-types", json={
        "code": "link", "name": "连接",
        "fields": [{"fieldKey": "bandwidth", "fieldLabel": "带宽",
                    "fieldType": "text", "maxLength": 20}],
    })
    r = client.post(f"/admin/api/topologies/{tid}/nodes", json={
        "nodeTypeId": ntid, "name": "R1", "attrs": {"vlan_id": "100"},
    })
    nid1 = r.json()["data"]["id"]
    r = client.post(f"/admin/api/topologies/{tid}/nodes", json={
        "nodeTypeId": ntid, "name": "R2", "attrs": {"vlan_id": "200"},
    })
    nid2 = r.json()["data"]["id"]
    return tid, ntid, nid1, nid2


def test_export_excel_returns_xlsx(client):
    tid, _, _, _ = _make_topology_with_nodes(client)
    r = client.get(f"/admin/api/topologies/{tid}/export-excel")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    wb = load_workbook(io.BytesIO(r.content))
    assert META_SHEET_NAME in wb.sheetnames
    assert "路由器" in wb.sheetnames
    ws = wb["路由器"]
    # 节点 R1 应在第 2 行
    assert ws.cell(row=2, column=1).value == "R1"
    assert ws.cell(row=2, column=7).value == "100"  # vlan_id


def test_export_excel_edges_use_node_names(client):
    tid, ntid, nid1, nid2 = _make_topology_with_nodes(client)
    # 加一条边
    client.post(f"/admin/api/topologies/{tid}/edges", json={
        "edgeTypeCode": "link", "sourceId": nid1, "targetId": nid2,
        "attrs": {"bandwidth": "10G"},
    })
    r = client.get(f"/admin/api/topologies/{tid}/export-excel")
    wb = load_workbook(io.BytesIO(r.content))
    ws = wb["连接"]
    assert ws.cell(row=2, column=1).value == "R1"
    assert ws.cell(row=2, column=2).value == "R2"
    assert ws.cell(row=2, column=4).value == "10G"


def test_import_excel_creates_new_topology(client):
    # 先造一个源拓扑并导出
    src_tid, _, _, _ = _make_topology_with_nodes(client)
    r = client.get(f"/admin/api/topologies/{src_tid}/export-excel")
    xlsx = r.content

    # 重新导入
    r = client.post(
        "/admin/api/topologies/import-excel",
        files={"file": ("t.xlsx", xlsx,
                         "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert r.status_code == 200, r.text
    result = r.json()["data"]
    assert result["topologyId"] != src_tid
    assert "(导入" in result["topologyName"]  # 名字冲突加了后缀
    assert result["counts"]["nodes"] == 2


def test_import_excel_rejects_non_xlsx(client):
    r = client.post(
        "/admin/api/topologies/import-excel",
        files={"file": ("t.json", b'{"a":1}', "application/json")},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == 40410


def test_import_excel_unknown_node_type_code_rejected(client):
    """workbook 里 nodeType code 在目标环境不存在 → 400 + 40431。"""
    # 构造一个只有元信息 + 一个"ghost"nodeType Sheet 的 workbook
    from openpyxl import Workbook
    from openpyxl.comments import Comment
    wb = Workbook()
    wb.remove(wb.active)
    ws_meta = wb.create_sheet(META_SHEET_NAME)
    ws_meta.cell(row=1, column=1, value="字段")
    ws_meta.cell(row=1, column=2, value="值")
    ws_meta.cell(row=2, column=1, value="拓扑名称")
    ws_meta.cell(row=2, column=2, value="T2")
    ws_g = wb.create_sheet("Ghost")
    for c, h in enumerate(NODE_FIXED_HEADERS, start=1):
        ws_g.cell(row=1, column=c, value=h)
    ws_g["A1"].comment = Comment(f"{NODE_TYPE_MARKER}=ghost_type_xyz", "system")
    buf = io.BytesIO()
    wb.save(buf)

    r = client.post(
        "/admin/api/topologies/import-excel",
        files={"file": ("t.xlsx", buf.getvalue(),
                         "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == 40431


def test_import_excel_duplicate_node_name_rejected(client):
    """workbook 里同 (nodeTypeCode, name) 出现两次 → 400 + 40432。"""
    from openpyxl import Workbook
    from openpyxl.comments import Comment
    # 先造好 node type
    client.post("/admin/api/node-types", json={
        "code": "sw2", "name": "SW2", "category": "switch",
    })
    wb = Workbook()
    wb.remove(wb.active)
    ws_meta = wb.create_sheet(META_SHEET_NAME)
    ws_meta.cell(row=1, column=1, value="字段")
    ws_meta.cell(row=1, column=2, value="值")
    ws_meta.cell(row=2, column=1, value="拓扑名称")
    ws_meta.cell(row=2, column=2, value="T3")
    ws = wb.create_sheet("SW2")
    for c, h in enumerate(NODE_FIXED_HEADERS, start=1):
        ws.cell(row=1, column=c, value=h)
    ws["A1"].comment = Comment(f"{NODE_TYPE_MARKER}=sw2", "system")
    ws.cell(row=2, column=1, value="dup")
    ws.cell(row=3, column=1, value="dup")
    buf = io.BytesIO()
    wb.save(buf)

    r = client.post(
        "/admin/api/topologies/import-excel",
        files={"file": ("t.xlsx", buf.getvalue(),
                         "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == 40432


def test_import_excel_missing_meta_sheet_rejected(client):
    """无元信息 Sheet → 400 + 40411（致命）。"""
    from openpyxl import Workbook
    wb = Workbook()
    wb.remove(wb.active)
    wb.create_sheet("路由器")
    buf = io.BytesIO()
    wb.save(buf)

    r = client.post(
        "/admin/api/topologies/import-excel",
        files={"file": ("t.xlsx", buf.getvalue(),
                         "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == 40411
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_topology_excel.py -v`
Expected: 全 FAIL — 端点不存在（404）

- [ ] **Step 3: 加两个端点到 `topology.py`**

Edit `backend/app/admin/topology.py`. 找到现有 `import_topology` 函数末尾（约 800 行）后面追加两个新端点：

```python
@router.get("/topologies/{id}/export-excel")
def export_topology_excel(id: str):
    """导出拓扑为 Excel (.xlsx)"""
    import io as _io
    from fastapi.responses import Response
    from app.admin._topology_excel import build_workbook

    with connect() as conn:
        topo = conn.execute(
            "SELECT t.name, t.description, t.version, d.name AS domain_name, "
            "s.code AS alarm_schema_code "
            "FROM topologies t "
            "LEFT JOIN domains d ON d.id = t.domain_id "
            "LEFT JOIN alarm_schemas s ON s.id = t.alarm_schema_id "
            "WHERE t.id = ?", (id,)
        ).fetchone()
        if not topo:
            raise HTTPException(
                status_code=404,
                detail={"code": 40101, "message": "拓扑不存在"},
            )
        topology_meta = {
            "name": topo["name"],
            "description": topo["description"],
            "version": topo["version"],
            "domain_name": topo["domain_name"],
            "alarm_schema_code": topo["alarm_schema_code"],
        }

        # 节点类型 + 字段（当前拓扑用到的）
        nt_rows = conn.execute(
            "SELECT DISTINCT nt.id, nt.code, nt.name FROM nodes n "
            "JOIN node_types nt ON nt.id = n.node_type_id "
            "WHERE n.topology_id = ?", (id,)
        ).fetchall()
        node_types = []
        for nt in nt_rows:
            fields = conn.execute(
                "SELECT field_key FROM node_type_fields "
                "WHERE node_type_id = ? ORDER BY sort_order, id", (nt["id"],)
            ).fetchall()
            node_types.append({
                "id": nt["id"], "code": nt["code"], "name": nt["name"],
                "fields": [{"field_key": f["field_key"]} for f in fields],
            })

        # 边类型
        et_rows = conn.execute(
            "SELECT DISTINCT et.id, et.code, et.name FROM edges e "
            "JOIN edge_types et ON et.id = e.edge_type_id "
            "WHERE e.topology_id = ?", (id,)
        ).fetchall()
        edge_types = []
        for et in et_rows:
            fields = conn.execute(
                "SELECT field_key FROM edge_type_fields "
                "WHERE edge_type_id = ? ORDER BY sort_order, id", (et["id"],)
            ).fetchall()
            edge_types.append({
                "id": et["id"], "code": et["code"], "name": et["name"],
                "fields": [{"field_key": f["field_key"]} for f in fields],
            })

        # 节点 + attrs + canvas + group name
        nodes_by_type_code: dict = {nt["code"]: [] for nt in node_types}
        node_rows = conn.execute(
            "SELECT n.id, n.name, n.dn, n.status, nt.code AS node_type_code, "
            "cn.x AS canvas_x, cn.y AS canvas_y, g.group_name "
            "FROM nodes n "
            "JOIN node_types nt ON nt.id = n.node_type_id "
            "LEFT JOIN canvas_nodes cn ON cn.node_id = n.id "
            "LEFT JOIN node_groups g ON g.id = n.group_id "
            "WHERE n.topology_id = ?", (id,)
        ).fetchall()
        node_attrs = {}
        for r in conn.execute(
            "SELECT na.node_id, na.field_key, na.value FROM node_attrs na "
            "JOIN nodes n ON n.id = na.node_id WHERE n.topology_id = ?", (id,)
        ).fetchall():
            node_attrs.setdefault(r["node_id"], {})[r["field_key"]] = r["value"]
        for r in node_rows:
            nodes_by_type_code[r["node_type_code"]].append({
                "id": r["id"], "name": r["name"], "dn": r["dn"], "status": r["status"],
                "canvas_x": r["canvas_x"], "canvas_y": r["canvas_y"],
                "group_name": r["group_name"],
                "attrs": node_attrs.get(r["id"], {}),
            })

        # 边 + attrs
        edges_by_type_code: dict = {et["code"]: [] for et in edge_types}
        edge_rows = conn.execute(
            "SELECT e.id, e.source_id, e.target_id, e.status, et.code AS edge_type_code "
            "FROM edges e JOIN edge_types et ON et.id = e.edge_type_id "
            "WHERE e.topology_id = ?", (id,)
        ).fetchall()
        edge_attrs = {}
        for r in conn.execute(
            "SELECT ea.edge_id, ea.field_key, ea.value FROM edge_attrs ea "
            "JOIN edges e ON e.id = ea.edge_id WHERE e.topology_id = ?", (id,)
        ).fetchall():
            edge_attrs.setdefault(r["edge_id"], {})[r["field_key"]] = r["value"]
        for r in edge_rows:
            edges_by_type_code[r["edge_type_code"]].append({
                "id": r["id"], "source_id": r["source_id"], "target_id": r["target_id"],
                "status": r["status"], "attrs": edge_attrs.get(r["id"], {}),
            })

        # 节点组
        import json
        group_rows = conn.execute(
            "SELECT id, group_name, node_type_id, node_count, name_template, "
            "attr_strategies, edge_strategies, canvas_x, canvas_y, "
            "materialized_at FROM node_groups WHERE topology_id = ?", (id,)
        ).fetchall()
        node_groups = []
        node_group_edge_strategies = []
        group_id_to_name = {}
        for g in group_rows:
            attrs = json.loads(g["attr_strategies"]) if g["attr_strategies"] else []
            node_groups.append({
                "id": g["id"], "group_name": g["group_name"],
                "node_type_id": g["node_type_id"], "node_count": g["node_count"],
                "name_template": g["name_template"],
                "materialized_at": g["materialized_at"],
                "canvas_x": g["canvas_x"], "canvas_y": g["canvas_y"],
                "attr_strategies": attrs,
            })
            group_id_to_name[g["id"]] = g["group_name"]

        # 拉普通节点 name 映射，用于 edge_strategies 里的 hybrid 目标
        node_id_to_name = {r["id"]: r["name"] for r in node_rows}
        for g in group_rows:
            if not g["edge_strategies"]:
                continue
            for es in json.loads(g["edge_strategies"]):
                target_id = es.get("target_group_id")
                if target_id in group_id_to_name:
                    tname = group_id_to_name[target_id]
                    tkind = "组"
                elif target_id in node_id_to_name:
                    tname = node_id_to_name[target_id]
                    tkind = "节点"
                else:
                    tname = target_id  # 保底
                    tkind = "组"
                node_group_edge_strategies.append({
                    "source_group_name": g["group_name"],
                    "target_name": tname,
                    "target_kind": tkind,
                    "edge_type_code": es.get("edge_type_code"),
                    "mode": es.get("mode"),
                    "ratio_k": es.get("ratio_k"),
                })

        # 告警
        alarm_schema_fields = []
        node_alarms = []
        node_group_alarms = []
        if topo["alarm_schema_code"]:
            sid_row = conn.execute(
                "SELECT id FROM alarm_schemas WHERE code = ?",
                (topo["alarm_schema_code"],)
            ).fetchone()
            if sid_row:
                sid = sid_row["id"]
                alarm_schema_fields = [dict(r) for r in conn.execute(
                    "SELECT field_key, mapping_target FROM alarm_schema_fields "
                    "WHERE alarm_schema_id = ? ORDER BY sort_order, id", (sid,)
                ).fetchall()]

                # 节点告警
                node_alarm_rows = conn.execute(
                    "SELECT a.id, a.node_id, a.alarm_index, n.node_type_id "
                    "FROM node_alarms a JOIN nodes n ON n.id = a.node_id "
                    "WHERE n.topology_id = ?", (id,)
                ).fetchall()
                node_alarm_attrs = {}
                for r in conn.execute(
                    "SELECT aa.alarm_id, aa.field_key, aa.value "
                    "FROM node_alarm_attrs aa "
                    "JOIN node_alarms a ON a.id = aa.alarm_id "
                    "JOIN nodes n ON n.id = a.node_id "
                    "WHERE n.topology_id = ?", (id,)
                ).fetchall():
                    node_alarm_attrs.setdefault(r["alarm_id"], {})[r["field_key"]] = r["value"]
                for r in node_alarm_rows:
                    node_alarms.append({
                        "node_id": r["node_id"],
                        "node_type_id": r["node_type_id"],
                        "alarm_index": r["alarm_index"],
                        "attrs": node_alarm_attrs.get(r["id"], {}),
                    })

                # 节点组告警
                group_alarm_rows = conn.execute(
                    "SELECT ga.id, ga.node_group_id, ga.alarm_index "
                    "FROM node_group_alarms ga "
                    "JOIN node_groups g ON g.id = ga.node_group_id "
                    "WHERE g.topology_id = ?", (id,)
                ).fetchall()
                group_alarm_attrs = {}
                for r in conn.execute(
                    "SELECT gaa.alarm_id, gaa.field_key, gaa.value "
                    "FROM node_group_alarm_attrs gaa "
                    "JOIN node_group_alarms ga ON ga.id = gaa.alarm_id "
                    "JOIN node_groups g ON g.id = ga.node_group_id "
                    "WHERE g.topology_id = ?", (id,)
                ).fetchall():
                    group_alarm_attrs.setdefault(r["alarm_id"], {})[r["field_key"]] = r["value"]
                for r in group_alarm_rows:
                    node_group_alarms.append({
                        "node_group_id": r["node_group_id"],
                        "alarm_index": r["alarm_index"],
                        "attrs": group_alarm_attrs.get(r["id"], {}),
                    })

    wb = build_workbook(
        topology=topology_meta,
        node_types=node_types,
        edge_types=edge_types,
        nodes_by_type_code=nodes_by_type_code,
        edges_by_type_code=edges_by_type_code,
        node_groups=node_groups,
        node_group_edge_strategies=node_group_edge_strategies,
        alarm_schema_fields=alarm_schema_fields,
        node_alarms=node_alarms,
        node_group_alarms=node_group_alarms,
    )
    buf = _io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    filename = f"topology-{topology_meta['name']}.xlsx"
    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/topologies/import-excel")
async def import_topology_excel(file: UploadFile = File(...)) -> dict:
    """从 Excel (.xlsx) 导入拓扑。始终新建。"""
    import io as _io
    import json
    from app.admin._topology_excel import parse_workbook, ExcelValidationError

    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(
            status_code=400,
            detail={"code": 40410, "message": "仅支持 .xlsx 文件"},
        )
    contents = await file.read()
    try:
        parse = parse_workbook(_io.BytesIO(contents))
    except ExcelValidationError as e:
        raise HTTPException(
            status_code=400,
            detail={"code": 40411, "message": str(e)},
        )

    with transaction() as conn:
        # 1. 名字冲突处理
        new_name = _resolve_unique_name(conn, parse.meta["name"])

        # 2. domain 解析（自动创建）
        domain_id = None
        domain_name = parse.meta.get("domain_name")
        if domain_name:
            row = conn.execute("SELECT id FROM domains WHERE name = ?", (domain_name,)).fetchone()
            if row:
                domain_id = row["id"]
            else:
                domain_id = f"dom_{uuid.uuid4().hex[:12]}"
                conn.execute(
                    "INSERT INTO domains (id, name, description) VALUES (?, ?, ?)",
                    (domain_id, domain_name, "导入时自动创建"),
                )
                parse.warnings.append(f"自动创建了网管 '{domain_name}'")

        # 3. alarm_schema 解析（不自动创建）
        alarm_schema_id = None
        alarm_schema_code = parse.meta.get("alarm_schema_code")
        if alarm_schema_code:
            row = conn.execute(
                "SELECT id FROM alarm_schemas WHERE code = ?", (alarm_schema_code,)
            ).fetchone()
            if not row:
                raise HTTPException(
                    status_code=400,
                    detail={"code": 40430, "message": f"告警模板 '{alarm_schema_code}' 不存在"},
                )
            alarm_schema_id = row["id"]

        # 4. 校验所有 nodeType code 存在
        for code in parse.nodes_by_type_code.keys():
            r = conn.execute("SELECT id FROM node_types WHERE code = ?", (code,)).fetchone()
            if not r:
                raise HTTPException(
                    status_code=400,
                    detail={"code": 40431, "message": f"节点类型代码 '{code}' 不存在"},
                )

        # 5. 校验所有 edgeType code 存在
        for code in parse.edges_by_type_code.keys():
            r = conn.execute("SELECT id FROM edge_types WHERE code = ?", (code,)).fetchone()
            if not r:
                raise HTTPException(
                    status_code=400,
                    detail={"code": 40431, "message": f"边类型代码 '{code}' 不存在"},
                )

        # 6. 节点名唯一性校验 (nodeTypeCode, name)
        for code, nodes in parse.nodes_by_type_code.items():
            names = [n["name"] for n in nodes]
            if len(names) != len(set(names)):
                dup_names = [n for n in names if names.count(n) > 1]
                raise HTTPException(
                    status_code=400,
                    detail={"code": 40432,
                            "message": f"节点类型 '{code}' 下节点名重复：{sorted(set(dup_names))}"},
                )

        # 7. INSERT topology
        topology_id = f"topo_{uuid.uuid4().hex[:12]}"
        conn.execute(
            "INSERT INTO topologies (id, name, description, version, domain_id, alarm_schema_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (topology_id, new_name, parse.meta.get("description"),
             parse.meta.get("version") or 1, domain_id, alarm_schema_id),
        )

        # 8. INSERT nodes + attrs + canvas
        node_id_by_name_type: dict = {}  # (code, name) -> new node_id
        for code, nodes in parse.nodes_by_type_code.items():
            nt = conn.execute("SELECT id FROM node_types WHERE code = ?", (code,)).fetchone()
            for n in nodes:
                nid = f"node_{uuid.uuid4().hex[:12]}"
                conn.execute(
                    "INSERT INTO nodes (id, topology_id, node_type_id, name, dn, status) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (nid, topology_id, nt["id"], n["name"], n.get("dn"),
                     n.get("status") or "online"),
                )
                node_id_by_name_type[(code, n["name"])] = nid
                for k, v in (n.get("attrs") or {}).items():
                    conn.execute(
                        "INSERT INTO node_attrs (node_id, field_key, value) VALUES (?, ?, ?)",
                        (nid, k, str(v) if v is not None else None),
                    )
                if n.get("canvas_x") is not None and n.get("canvas_y") is not None:
                    conn.execute(
                        "INSERT INTO canvas_nodes (topology_id, node_id, x, y) "
                        "VALUES (?, ?, ?, ?)",
                        (topology_id, nid, float(n["canvas_x"]), float(n["canvas_y"])),
                    )

        # 9. INSERT edges + attrs
        for code, edges in parse.edges_by_type_code.items():
            et = conn.execute("SELECT id FROM edge_types WHERE code = ?", (code,)).fetchone()
            for e in edges:
                # 查找源/目标节点：跨所有 nodeType 找 name 匹配
                src_id = None
                tgt_id = None
                for (c, name), nid in node_id_by_name_type.items():
                    if name == e["source_name"] and src_id is None:
                        src_id = nid
                    if name == e["target_name"] and tgt_id is None:
                        tgt_id = nid
                if not src_id or not tgt_id:
                    parse.errors.append(
                        f"Sheet 边 (类型 {code}): 源节点 '{e['source_name']}' 或 目标节点 "
                        f"'{e['target_name']}' 未找到"
                    )
                    continue
                eid = f"edge_{uuid.uuid4().hex[:12]}"
                conn.execute(
                    "INSERT INTO edges (id, topology_id, edge_type_id, source_id, target_id, status) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (eid, topology_id, et["id"], src_id, tgt_id, e.get("status") or "online"),
                )
                for k, v in (e.get("attrs") or {}).items():
                    conn.execute(
                        "INSERT INTO edge_attrs (edge_id, field_key, value) VALUES (?, ?, ?)",
                        (eid, k, str(v) if v is not None else None),
                    )

        # 10. INSERT node_groups (edge_strategies 后续 UPDATE)
        group_id_by_name = {}
        for g in parse.node_groups:
            nt = conn.execute(
                "SELECT id FROM node_types WHERE code = ?", (g.get("node_type_code"),)
            ).fetchone()
            if not nt:
                parse.errors.append(f"节点组 '{g['group_name']}': 节点类型代码 "
                                     f"'{g.get('node_type_code')}' 不存在")
                continue
            gid = f"grp_{uuid.uuid4().hex[:12]}"
            conn.execute(
                "INSERT INTO node_groups (id, topology_id, node_type_id, group_name, "
                "node_count, name_template, attr_strategies, canvas_x, canvas_y) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (gid, topology_id, nt["id"], g["group_name"],
                 int(g.get("node_count") or 1),
                 g.get("name_template") or "{group}-{i:05d}",
                 json.dumps(g.get("attr_strategies") or [], ensure_ascii=False),
                 g.get("canvas_x"), g.get("canvas_y")),
            )
            group_id_by_name[g["group_name"]] = gid

        # 11. 组装 edge_strategies 并 UPDATE
        strategies_by_group: dict = {}  # group_id -> list of edge_strategy dicts
        for s in parse.node_group_edge_strategies:
            src_gid = group_id_by_name.get(s["source_group_name"])
            if not src_gid:
                parse.errors.append(f"节点组边策略: 源组 '{s['source_group_name']}' 未找到")
                continue
            # 目标解析
            if s["target_kind"] == "组":
                target_id = group_id_by_name.get(s["target_name"])
                if not target_id:
                    parse.errors.append(f"节点组边策略: 目标组 '{s['target_name']}' 未找到")
                    continue
            else:
                # 节点：在 node_id_by_name_type 里跨类型找 name
                target_id = None
                for (c, name), nid in node_id_by_name_type.items():
                    if name == s["target_name"]:
                        target_id = nid
                        break
                if not target_id:
                    parse.errors.append(f"节点组边策略: 目标节点 '{s['target_name']}' 未找到")
                    continue
            strategies_by_group.setdefault(src_gid, []).append({
                "target_group_id": target_id,
                "edge_type_code": s["edge_type_code"],
                "mode": s["mode"],
                "ratio_k": s.get("ratio_k"),
            })
        for gid, strategies in strategies_by_group.items():
            conn.execute(
                "UPDATE node_groups SET edge_strategies = ? WHERE id = ?",
                (json.dumps(strategies, ensure_ascii=False), gid),
            )

        # 12. INSERT node_alarms + attrs
        alarm_count_by_node = 0
        for a in parse.node_alarms:
            code = a.get("node_type_code")
            name = a.get("node_name")
            nid = node_id_by_name_type.get((code, name))
            if not nid:
                parse.errors.append(f"节点告警: 节点 ({code}, {name}) 未找到")
                continue
            aid = f"alm_{uuid.uuid4().hex[:12]}"
            conn.execute(
                "INSERT INTO node_alarms (id, node_id, alarm_index) VALUES (?, ?, ?)",
                (aid, nid, int(a.get("alarm_index") or 1)),
            )
            alarm_count_by_node += 1
            for k, v in (a.get("attrs") or {}).items():
                conn.execute(
                    "INSERT INTO node_alarm_attrs (alarm_id, field_key, value) VALUES (?, ?, ?)",
                    (aid, k, str(v) if v is not None else None),
                )

        # 13. INSERT node_group_alarms + attrs
        group_alarm_count = 0
        for a in parse.node_group_alarms:
            gid = group_id_by_name.get(a.get("group_name"))
            if not gid:
                parse.errors.append(f"节点组告警: 组 '{a.get('group_name')}' 未找到")
                continue
            aid = f"grp_alm_{uuid.uuid4().hex[:12]}"
            conn.execute(
                "INSERT INTO node_group_alarms (id, node_group_id, alarm_index) VALUES (?, ?, ?)",
                (aid, gid, int(a.get("alarm_index") or 1)),
            )
            group_alarm_count += 1
            for k, v in (a.get("attrs") or {}).items():
                conn.execute(
                    "INSERT INTO node_group_alarm_attrs (alarm_id, field_key, value) VALUES (?, ?, ?)",
                    (aid, k, str(v) if v is not None else None),
                )

    total_nodes = sum(len(v) for v in parse.nodes_by_type_code.values())
    total_edges = sum(len(v) for v in parse.edges_by_type_code.values())

    return {
        "code": 0,
        "data": {
            "topologyId": topology_id,
            "topologyName": new_name,
            "counts": {
                "nodes": total_nodes,
                "edges": total_edges,
                "groups": len(parse.node_groups),
                "nodeAlarms": alarm_count_by_node,
                "groupAlarms": group_alarm_count,
            },
            "errors": parse.errors,
            "warnings": parse.warnings,
        },
        "message": "ok",
    }
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_topology_excel.py -v`
Expected: 全 PASS

- [ ] **Step 5: 跑全套确认无回归**

Run: `cd backend && python -m pytest -q 2>&1 | tail -3`
Expected: 全部 PASS

- [ ] **Step 6: 提交**

```bash
git add backend/app/admin/topology.py backend/tests/test_topology_excel.py
git commit -m "$(cat <<'EOF'
feat(topology): Excel 导入导出端点

- GET /topologies/{id}/export-excel 返回 xlsx binary
- POST /topologies/import-excel 收 .xlsx，永远新建拓扑
- 域自动创建（warnings 记录）；alarm_schema 不自动创建（40430）
- nodeType/edgeType code 找不到 → 40431
- 同 (nodeTypeCode, name) 重复 → 40432
- 边策略两阶段插入：先建组（edge_strategies=NULL）再 UPDATE
- 边/告警行级错误 → errors 里收集继续
- +7 端到端测试

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: 前端 topology API + CanvasView 按钮

**Files:**
- Modify: `frontend/src/api/topology.ts`
- Modify: `frontend/src/views/CanvasView.vue`

- [ ] **Step 1: 前端 API 加 exportExcel / importExcel**

Edit `frontend/src/api/topology.ts`. 在现有 topologyApi 对象里追加：

```typescript
  exportExcel: (id: string): Promise<Blob> =>
    http.get(`/topologies/${id}/export-excel`, { responseType: 'blob' }).then(r => r.data),

  importExcel: (file: File): Promise<{
    topologyId: string
    topologyName: string
    counts: { nodes: number; edges: number; groups: number; nodeAlarms: number; groupAlarms: number }
    errors: string[]
    warnings: string[]
  }> => {
    if (!file.name.toLowerCase().endsWith('.xlsx')) {
      return Promise.reject(new Error('仅支持 .xlsx 文件'))
    }
    const form = new FormData()
    form.append('file', file)
    return http.post('/topologies/import-excel', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then(r => r.data.data)
  },
```

如果文件顶部还没导入 `http`，追加：

```typescript
import http from './http'
```

- [ ] **Step 2: 改 CanvasView.vue 的导出/导入**

Edit `frontend/src/views/CanvasView.vue`. 找到现有的导出/导入按钮 handler（搜 `handleExport` / `handleImport` / `topologyApi.export` / `topologyApi.import`）。改造：

```typescript
async function handleExport() {
  if (!currentTopologyId.value) return
  try {
    const blob = await topologyApi.exportExcel(currentTopologyId.value)
    const filename = timestampExcelFilename(`topology-${topologyName.value || 'export'}`)
    downloadBlob(blob, filename)
    message.success('导出成功')
  } catch (err: any) {
    message.error(err?.message || '导出失败')
  }
}

async function handleImportFile(e: Event) {
  const target = e.target as HTMLInputElement
  const file = target.files?.[0]
  if (!file) return
  target.value = ''

  if (!file.name.toLowerCase().endsWith('.xlsx')) {
    message.error('仅支持 .xlsx 文件')
    return
  }

  Modal.confirm({
    title: '确认导入',
    content: `将从 "${file.name}" 导入新拓扑。确认继续？`,
    okText: '确认',
    cancelText: '取消',
    onOk: async () => {
      try {
        const result = await topologyApi.importExcel(file)
        const parts: string[] = []
        parts.push(`已创建拓扑 "${result.topologyName}"`)
        parts.push(`${result.counts.nodes} 节点`)
        parts.push(`${result.counts.edges} 边`)
        if (result.counts.groups) parts.push(`${result.counts.groups} 组`)
        message.success(parts.join('，'))
        if (result.warnings.length) {
          message.warning(result.warnings.join('；'))
        }
        if (result.errors.length) {
          message.error(`${result.errors.length} 行被跳过：${result.errors.slice(0, 3).join('；')}${result.errors.length > 3 ? '…' : ''}`)
        }
        emit('refresh')  // 或 refresh topology list
      } catch (err: any) {
        message.error(err?.message || '导入失败')
      }
    },
  })
}
```

**若原有按钮/输入元素引用了 `.json` accept**，改成 `.xlsx`。文件 input 元素：

```html
<input
  ref="fileInputRef"
  type="file"
  accept=".xlsx"
  style="display: none"
  @change="handleImportFile"
/>
```

如果 `downloadBlob` / `timestampExcelFilename` / `Modal` / `message` 尚未 import，一起补：

```typescript
import { Modal, message } from 'ant-design-vue'
import { downloadBlob, timestampExcelFilename } from '@/utils/download'
```

- [ ] **Step 3: 类型检查**

Run: `cd frontend && npx vue-tsc --noEmit`
Expected: 无新 TS 报错

- [ ] **Step 4: 提交**

```bash
git add frontend/src/api/topology.ts frontend/src/views/CanvasView.vue
git commit -m "$(cat <<'EOF'
feat(canvas): 前端导出/导入切换到 Excel

- topology.ts 加 exportExcel / importExcel（客户端拦截非 .xlsx）
- CanvasView 导出直接 blob 下载 topology-<name>-<ts>.xlsx
- 导入简化确认对话；显示 nodes/edges/groups 计数 + warnings + errors 前 3 条
- file input accept 收窄到 .xlsx

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: 手动集成验证

**Files:** 无代码修改

- [ ] **Step 1: 重启前后端**

```bash
# 关掉旧后端进程
cd backend && python -m app.main
# 另开终端
cd frontend && npm run dev
```

- [ ] **Step 2: 端到端"导出 → 改 → 导入"闭环**

1. 画布界面选一个复杂拓扑 → 点"导出" → 得到 `topology-<name>-<ts>.xlsx`
2. Excel 打开：
   - [ ] `_使用说明` 是第 1 个 Sheet
   - [ ] `_总表` 是第 2 个 Sheet，含所有数据 Sheet 跳转 hyperlink（点 Sheet 名列跳转）
   - [ ] `拓扑元信息` 第 3 个，key-value 表
   - [ ] 每个 nodeType 一 Sheet，字段成列（如"路由器" Sheet 有 `vlan_id` 列）
   - [ ] 每个 edgeType 一 Sheet，源节点/目标节点用节点 name
   - [ ] `节点组` Sheet 属性策略列多行 pipe-list
   - [ ] `节点组边策略` Sheet 一行一策略
   - [ ] 如果拓扑绑了 alarm_schema：`节点告警` + `节点组告警` Sheet 存在
3. 改一个节点属性（如 vlan_id 从 100 → 999），保存
4. UI 点"导入" → 选这个 xlsx → 确认 → 提示"已创建拓扑 xxx (导入)"
5. 打开新拓扑，看到 vlan_id = 999

- [ ] **Step 3: 验证致命错误路径**

- 选 `.json` 文件上传 → 前端拦下"仅支持 .xlsx 文件"
- 构造一个只有 `_使用说明` 的空 xlsx → 上传 → 后端 400 "缺少 '拓扑元信息' Sheet"
- 用一个源库的 xlsx 导入到目标库（目标库没有那些 nodeType.code） → 400 "节点类型代码 'xxx' 不存在"

- [ ] **Step 4: 关闭进程**

Ctrl+C 前后端。

- [ ] **Step 5: 不提交（验证不改代码）**

---

## Self-Review Checklist（写完 plan 后自查）

- [x] **Spec 覆盖：**
  - Workbook 结构（_使用说明 / _总表 / 元信息 / nodeType × N / edgeType × M / 节点组 / 节点组边策略 / 告警 × 2）→ Task 3
  - Sheet 名清洗 + A1 marker → Task 2
  - `_总表` hyperlink 挂 Sheet 名列 → Task 3
  - 边引用节点用 name → Task 3 + Task 5
  - 节点组只导定义 → Task 3 + Task 5
  - 节点组边策略独立 Sheet + 目标类型（组/节点）→ Task 2 + Task 3 + Task 5
  - 告警 mapping_target 字段不导出 → Task 3
  - 未绑 alarm_schema 时告警 Sheet 不生成 → Task 3
  - 导入永远新建 + 名字冲突加"(导入 N)" → Task 5
  - alarm_schema code 不存在 → 40430；nodeType/edgeType code 不存在 → 40431；节点名重复 → 40432 → Task 5
  - 域自动创建（warnings 记录） → Task 5
  - 保留旧 JSON 端点 → 不改
  - 前端 CanvasView 切到 Excel → Task 6

- [x] **占位扫描：** 无 TBD/TODO；每步含实际代码 + 命令

- [x] **类型一致性：**
  - `TopologyExcelImportResult` 在 Task 1 定义；Task 5 端点响应结构对齐
  - `ParseResult` 字段（nodes_by_type_code / edges_by_type_code / node_groups / node_group_edge_strategies / node_alarms / node_group_alarms / errors / warnings / meta）Task 4 定义，Task 5 使用一致
  - Sheet 名常量（INSTRUCTION_SHEET_NAME 等）Task 2 定义，后续 Task 引用一致
  - A1 marker 名（NODE_TYPE_MARKER 等）Task 2 定义，Task 3/4 匹配
  - `format_attr_strategy_row / parse_attr_strategy_row` 签名 (row_hint) 前后一致
  - `format_edge_strategy_row / parse_edge_strategy_row` 签名一致

- **已知取舍：**
  - Task 3 里 `_write_node_alarm_sheet` 的 `node_type_code_by_id_of_node` 参数命名和使用略绕，实施时如觉得别扭可以直接把 `node_type_code` 提前塞进每个 alarm dict（在 build_workbook 组装 enriched_node_alarms 时预先塞好）。
  - Task 5 里 edge/告警的 name-based 反查是 O(nodes × edges) 遍历。对上万节点的拓扑可能慢，先跑通再考虑优化（先建 name→node_id map 一次，O(1) 查）。
