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


def test_bulk_create_auto_alarm_when_schema_bound(client):
    """拓扑绑定 alarm_schema → 批量创建的每个节点自动产生 1 条默认告警。"""
    # Create alarm schema
    r = client.post("/admin/api/alarm-schemas", json={
        "code": "test_alarm", "name": "TestAlarm",
        "fields": [
            {"fieldKey": "severity", "fieldLabel": "级别", "fieldType": "text", "defaultValue": "warning"},
        ],
    })
    assert r.status_code == 200, r.text
    schema_id = r.json()["data"]["id"]

    # Create topology
    topo = _make_topology(client)

    # Bind alarm schema to topology
    r = client.patch(f"/admin/api/topologies/{topo}/alarm-schema", json={
        "alarmSchemaId": schema_id,
        "clearExisting": False
    })
    assert r.status_code == 200, r.text

    ntype = _make_node_type(client, "sw")

    r = client.post(f"/admin/api/topologies/{topo}/nodes/bulk", json={
        "nodeTypeId": ntype,
        "items": [
            {"name": "sw-01", "x": 0, "y": 0, "attrs": {}},
            {"name": "sw-02", "x": 0, "y": 0, "attrs": {}},
        ],
    })
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert len(data["created"]) == 2

    # Each node should have 1 alarm with severity=warning
    for c in data["created"]:
        r = client.get(f"/admin/api/nodes/{c['id']}/alarms")
        assert r.status_code == 200, r.text
        alarms = r.json()["data"]
        assert len(alarms) == 1, f"Expected 1 alarm for {c['name']}, got {len(alarms)}"
        assert alarms[0]["attrs"].get("severity") == "warning"


def test_bulk_create_multiple_success(client):
    """多条正常创建 → 事务一次提交，x/y 正确写入。"""
    topo = _make_topology(client)
    ntype = _make_node_type(client, "sw")
    r = client.post(f"/admin/api/topologies/{topo}/nodes/bulk", json={
        "nodeTypeId": ntype,
        "items": [
            {"name": "sw-01", "x": 100.0, "y": 200.0, "attrs": {}},
            {"name": "sw-02", "x": 320.0, "y": 200.0, "attrs": {}},
            {"name": "sw-03", "x": 540.0, "y": 200.0, "attrs": {}},
        ],
    })
    assert r.status_code == 200
    data = r.json()["data"]
    assert len(data["created"]) == 3
    assert data["skipped"] == []
    nodes = _fetch_nodes(client, topo)
    assert len(nodes) == 3
    positions = {n["name"]: (n["x"], n["y"]) for n in nodes}
    assert positions["sw-01"] == (100.0, 200.0)
    assert positions["sw-03"] == (540.0, 200.0)


def test_bulk_create_topology_not_found(client):
    """拓扑不存在 → 404，不走行级处理。"""
    ntype = _make_node_type(client, "sw")
    r = client.post("/admin/api/topologies/topo_does_not_exist/nodes/bulk", json={
        "nodeTypeId": ntype,
        "items": [{"name": "x", "x": 0, "y": 0, "attrs": {}}],
    })
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == 40402


def test_bulk_create_node_type_not_found(client):
    """节点类型不存在 → 404。"""
    topo = _make_topology(client)
    r = client.post(f"/admin/api/topologies/{topo}/nodes/bulk", json={
        "nodeTypeId": "ntype_does_not_exist",
        "items": [{"name": "x", "x": 0, "y": 0, "attrs": {}}],
    })
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == 40403


def test_bulk_create_required_field_missing(client):
    """必填字段缺失 → 该行 skipped，其他行成功。"""
    topo = _make_topology(client)
    ntype = _make_node_type(client, "sw", [
        {"fieldKey": "ip", "fieldLabel": "IP", "fieldType": "text", "required": True},
    ])
    r = client.post(f"/admin/api/topologies/{topo}/nodes/bulk", json={
        "nodeTypeId": ntype,
        "items": [
            {"name": "sw-01", "x": 0, "y": 0, "attrs": {"ip": "10.0.0.1"}},
            {"name": "sw-02", "x": 0, "y": 0, "attrs": {}},
        ],
    })
    data = r.json()["data"]
    assert len(data["created"]) == 1 and data["created"][0]["name"] == "sw-01"
    assert len(data["skipped"]) == 1
    assert data["skipped"][0]["name"] == "sw-02"
    assert "IP" in data["skipped"][0]["reason"]


def test_bulk_create_text_max_length_exceeded(client):
    """text 字段超 max_length → 该行 skipped，理由含 fieldLabel + 长度。"""
    topo = _make_topology(client)
    ntype = _make_node_type(client, "sw", [
        {"fieldKey": "ip", "fieldLabel": "IP", "fieldType": "text", "maxLength": 10},
    ])
    r = client.post(f"/admin/api/topologies/{topo}/nodes/bulk", json={
        "nodeTypeId": ntype,
        "items": [
            {"name": "sw-01", "x": 0, "y": 0, "attrs": {"ip": "10.0.0.1"}},
            {"name": "sw-02", "x": 0, "y": 0, "attrs": {"ip": "this-ip-is-way-too-long-1234567890"}},
        ],
    })
    data = r.json()["data"]
    assert len(data["created"]) == 1
    assert len(data["skipped"]) == 1
    assert "IP" in data["skipped"][0]["reason"]
    assert "10" in data["skipped"][0]["reason"]


def test_bulk_create_text_no_max_length_fallback_255(client):
    """text 字段 max_length 未设 → 默认 255（不 skip 250 长度值）。"""
    topo = _make_topology(client)
    ntype = _make_node_type(client, "sw", [
        {"fieldKey": "note", "fieldLabel": "备注", "fieldType": "text"},
    ])
    r = client.post(f"/admin/api/topologies/{topo}/nodes/bulk", json={
        "nodeTypeId": ntype,
        "items": [
            {"name": "sw-01", "x": 0, "y": 0, "attrs": {"note": "x" * 250}},
        ],
    })
    data = r.json()["data"]
    assert len(data["created"]) == 1
    assert data["skipped"] == []


def test_bulk_create_existing_name_skipped(client):
    """画布已有同名 → 该行 skipped。"""
    topo = _make_topology(client)
    ntype = _make_node_type(client, "sw")
    client.post(f"/admin/api/topologies/{topo}/nodes", json={
        "nodeTypeId": ntype, "name": "sw-01", "status": "online",
    })
    r = client.post(f"/admin/api/topologies/{topo}/nodes/bulk", json={
        "nodeTypeId": ntype,
        "items": [
            {"name": "sw-01", "x": 0, "y": 0, "attrs": {}},
            {"name": "sw-02", "x": 0, "y": 0, "attrs": {}},
        ],
    })
    data = r.json()["data"]
    assert len(data["created"]) == 1
    assert data["created"][0]["name"] == "sw-02"
    assert len(data["skipped"]) == 1
    assert "画布已有同名" in data["skipped"][0]["reason"]


def test_bulk_create_batch_duplicate_name_skipped(client):
    """批次内重名 → 第一个 created，后续 skipped。"""
    topo = _make_topology(client)
    ntype = _make_node_type(client, "sw")
    r = client.post(f"/admin/api/topologies/{topo}/nodes/bulk", json={
        "nodeTypeId": ntype,
        "items": [
            {"name": "sw-01", "x": 0, "y": 0, "attrs": {}},
            {"name": "sw-01", "x": 0, "y": 0, "attrs": {}},
            {"name": "sw-02", "x": 0, "y": 0, "attrs": {}},
        ],
    })
    data = r.json()["data"]
    assert len(data["created"]) == 2
    assert {c["name"] for c in data["created"]} == {"sw-01", "sw-02"}
    assert len(data["skipped"]) == 1
    assert "批次内" in data["skipped"][0]["reason"]


def test_bulk_create_empty_items(client):
    """空 items → created=0, skipped=0, HTTP 200。"""
    topo = _make_topology(client)
    ntype = _make_node_type(client, "sw")
    r = client.post(f"/admin/api/topologies/{topo}/nodes/bulk", json={
        "nodeTypeId": ntype, "items": [],
    })
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["created"] == []
    assert data["skipped"] == []


def test_bulk_create_unknown_field_key_silently_ignored(client):
    """items 中包含未定义的 field_key → 静默忽略、不进 node_attrs、不算错。"""
    topo = _make_topology(client)
    ntype = _make_node_type(client, "sw", [
        {"fieldKey": "ip", "fieldLabel": "IP", "fieldType": "text"},
    ])
    r = client.post(f"/admin/api/topologies/{topo}/nodes/bulk", json={
        "nodeTypeId": ntype,
        "items": [{
            "name": "sw-01", "x": 0, "y": 0,
            "attrs": {"ip": "10.0.0.1", "unknown_field": "xxx"},
        }],
    })
    assert r.status_code == 200
    data = r.json()["data"]
    assert len(data["created"]) == 1
    node_id = data["created"][0]["id"]
    r = client.get(f"/admin/api/nodes/{node_id}")
    attrs = r.json()["data"]["attrs"]
    assert attrs.get("ip") == "10.0.0.1"
    assert "unknown_field" not in attrs


def test_bulk_create_name_whitespace_stripped(client):
    """name 前后空格 → 后端 strip。"""
    topo = _make_topology(client)
    ntype = _make_node_type(client, "sw")
    r = client.post(f"/admin/api/topologies/{topo}/nodes/bulk", json={
        "nodeTypeId": ntype,
        "items": [{"name": "  sw-01  ", "x": 0, "y": 0, "attrs": {}}],
    })
    data = r.json()["data"]
    assert data["created"][0]["name"] == "sw-01"
