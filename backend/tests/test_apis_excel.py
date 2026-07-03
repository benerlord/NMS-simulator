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
