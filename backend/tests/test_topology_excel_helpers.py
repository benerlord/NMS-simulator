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
