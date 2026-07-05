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
