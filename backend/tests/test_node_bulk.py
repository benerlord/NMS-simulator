"""画布批量 JSON 导入节点 — 端点集成测试。

对应 spec: docs/superpowers/specs/2026-07-06-canvas-bulk-json-import-design.md
"""
import pytest
from typing import Optional


def _make_topology(client) -> str:
    r = client.post("/admin/api/topologies", json={"name": "TestTopo"})
    return r.json()["data"]["id"]


def _make_node_type(client, code: str = "sw", fields: Optional[list] = None) -> str:
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
