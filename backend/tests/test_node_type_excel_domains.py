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
