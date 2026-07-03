import pytest

from app.admin._api_excel import (
    ExcelValidationError,
    format_cell_list,
    parse_cell_list,
    sanitize_sheet_name,
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


def test_parse_cell_list_value_with_pipe_raises():
    # 第 3 个字段（expectValue）含 |，会被 split 成多余字段 → 字段数超限报错
    with pytest.raises(ExcelValidationError) as exc:
        parse_cell_list("A|是|foo|bar||", HEADER_COLUMNS, row_hint="第 5 行 请求头")
    assert "第 5 行" in str(exc.value)


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


def test_sanitize_sheet_name_empty_or_whitespace_falls_back():
    used: set[str] = set()
    assert sanitize_sheet_name("", used) == "未命名"
    # 第二次调用同样触发 fallback，然后走 dedupe
    assert sanitize_sheet_name("   ", used) == "未命名~2"
    # 全非法字符也走 fallback（清洗后只剩 _ 也算"非空白"，仍然是 _；这个测保底空白路径）
    used2: set[str] = set()
    assert sanitize_sheet_name(" \t\n", used2) == "未命名"


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
