"""边类型字段整批同步测试。

覆盖 §3.3 diff 算法（insert/update/delete）+ §3.4 delete-impact +
旧 3 个单字段端点已移除（镜像 test_node_type_field_sync.py）。
"""


def _create_node_type(client, code="host", name="主机"):
    r = client.post("/admin/api/node-types", json={
        "code": code, "name": name, "category": "physical",
    })
    assert r.status_code == 200, r.text
    return r.json()["data"]["id"]


def _create_edge_type(client, code, name, fields=None):
    payload = {"code": code, "name": name}
    if fields is not None:
        payload["fields"] = fields
    r = client.post("/admin/api/edge-types", json=payload)
    assert r.status_code == 200, r.text
    return r.json()["data"]["id"]


def _create_topology(client, name="T"):
    r = client.post("/admin/api/topologies", json={"name": name})
    assert r.status_code == 200, r.text
    return r.json()["data"]["id"]


def _create_node(client, topo_id, node_type_id, name="n1"):
    r = client.post(f"/admin/api/topologies/{topo_id}/nodes", json={
        "nodeTypeId": node_type_id, "name": name,
    })
    assert r.status_code == 200, r.text
    return r.json()["data"]["id"]


def _create_edge(client, topo_id, edge_type_id, source_id, target_id):
    r = client.post(f"/admin/api/topologies/{topo_id}/edges", json={
        "edgeTypeId": edge_type_id,
        "sourceId": source_id,
        "targetId": target_id,
    })
    assert r.status_code == 200, r.text
    return r.json()["data"]["id"]


def _set_edge_attrs(client, edge_id, attrs):
    r = client.put(f"/admin/api/edges/{edge_id}/attrs", json=attrs)
    assert r.status_code == 200, r.text


def test_create_edge_type_with_fields(client):
    """POST /edge-types body 含 fields[] → 类型 + 字段一次性落库。"""
    payload = {
        "code": "fiber_link",
        "name": "光纤链路",
        "fields": [
            {"fieldKey": "bandwidth", "fieldLabel": "带宽", "fieldType": "number"},
            {"fieldKey": "latency", "fieldLabel": "延迟", "fieldType": "number"},
        ],
    }
    r = client.post("/admin/api/edge-types", json=payload)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["code"] == 0
    type_id = j["data"]["id"]

    # 验证字段已落库
    r = client.get(f"/admin/api/edge-types/{type_id}")
    assert r.status_code == 200
    fields = r.json()["data"]["fields"]
    assert [f["fieldKey"] for f in fields] == ["bandwidth", "latency"]


def test_update_edge_sync_fields_insert_only(client):
    """PUT 加新字段 → 旧字段保留，新字段加入。"""
    tid = _create_edge_type(client, "eth_link", "以太链路", fields=[
        {"fieldKey": "old_f", "fieldLabel": "旧", "fieldType": "number"},
    ])

    r = client.put(f"/admin/api/edge-types/{tid}", json={
        "fields": [
            {"fieldKey": "old_f", "fieldLabel": "旧", "fieldType": "number"},
            {"fieldKey": "new_f", "fieldLabel": "新", "fieldType": "number"},
        ],
    })
    assert r.status_code == 200, r.text

    r = client.get(f"/admin/api/edge-types/{tid}")
    keys = [f["fieldKey"] for f in r.json()["data"]["fields"]]
    assert keys == ["old_f", "new_f"]


def test_update_edge_sync_fields_update_only(client):
    """PUT 改字段 label / sort → field_key 不变，UPDATE 生效。"""
    tid = _create_edge_type(client, "eth_link2", "以太链路2", fields=[
        {"fieldKey": "a", "fieldLabel": "Old A", "fieldType": "number"},
        {"fieldKey": "b", "fieldLabel": "Old B", "fieldType": "number"},
    ])

    r = client.put(f"/admin/api/edge-types/{tid}", json={
        "fields": [
            {"fieldKey": "b", "fieldLabel": "New B", "fieldType": "number"},  # 调到前
            {"fieldKey": "a", "fieldLabel": "New A", "fieldType": "number"},  # 调到后
        ],
    })
    assert r.status_code == 200, r.text

    fields = client.get(f"/admin/api/edge-types/{tid}").json()["data"]["fields"]
    assert [f["fieldKey"] for f in fields] == ["b", "a"]
    assert [f["fieldLabel"] for f in fields] == ["New B", "New A"]


def test_update_edge_sync_fields_delete_cleans_orphan_attrs(client):
    """PUT 删字段 + 该字段在 edge_attrs 有数据 → edge_attrs 中同类型边的孤儿一并清理。"""
    tid = _create_edge_type(client, "link_dc", "数据中心链路", fields=[
        {"fieldKey": "speed", "fieldLabel": "速率", "fieldType": "number"},
        {"fieldKey": "vendor", "fieldLabel": "厂家", "fieldType": "text", "maxLength": 50},
    ])
    nt_id = _create_node_type(client, code="srv", name="服务器")
    topo_id = _create_topology(client, "T-orphan")
    n1 = _create_node(client, topo_id, nt_id, "srv-01")
    n2 = _create_node(client, topo_id, nt_id, "srv-02")
    edge_id = _create_edge(client, topo_id, tid, n1, n2)
    _set_edge_attrs(client, edge_id, [
        {"fieldKey": "speed", "value": "10G"},
        {"fieldKey": "vendor", "value": "huawei"},
    ])

    # PUT 删除 vendor 字段
    r = client.put(f"/admin/api/edge-types/{tid}", json={
        "fields": [{"fieldKey": "speed", "fieldLabel": "速率", "fieldType": "number"}],
    })
    assert r.status_code == 200, r.text

    # 验证 speed 还在，vendor 已清
    from app.db.connection import connect
    with connect() as c:
        rows = c.execute(
            "SELECT field_key FROM edge_attrs WHERE edge_id = ?", (edge_id,)
        ).fetchall()
    keys = sorted(r["field_key"] for r in rows)
    assert keys == ["speed"]


def test_update_edge_sync_fields_duplicate_field_key_rejected(client):
    """incoming 重复 field_key → 400。"""
    tid = _create_edge_type(client, "dup_edge_test", "重复测试", fields=[])

    r = client.put(f"/admin/api/edge-types/{tid}", json={
        "fields": [
            {"fieldKey": "same", "fieldLabel": "A", "fieldType": "number"},
            {"fieldKey": "same", "fieldLabel": "B", "fieldType": "number"},
        ],
    })
    assert r.status_code == 400


def test_update_edge_omit_fields_preserves_existing(client):
    """PUT body 不含 fields → 字段不变。"""
    tid = _create_edge_type(client, "keep_edge", "保持字段", fields=[
        {"fieldKey": "x", "fieldLabel": "X", "fieldType": "number"},
    ])

    r = client.put(f"/admin/api/edge-types/{tid}", json={"name": "保持字段V2"})
    assert r.status_code == 200, r.text

    fields = client.get(f"/admin/api/edge-types/{tid}").json()["data"]["fields"]
    assert [f["fieldKey"] for f in fields] == ["x"]


def test_edge_delete_impact_returns_affected_counts(client):
    """POST delete-impact → 每个 field_key 受影响边数正确。"""
    tid = _create_edge_type(client, "impact_edge", "影响测试", fields=[
        {"fieldKey": "speed", "fieldLabel": "速率", "fieldType": "number"},
        {"fieldKey": "proto", "fieldLabel": "协议", "fieldType": "number"},
    ])
    nt_id = _create_node_type(client, code="sw_impact", name="交换机")
    topo_id = _create_topology(client, "T-impact")

    # 创建 4 个节点 + 3 条边，每条边都设置 speed 和 proto 属性
    nodes = [_create_node(client, topo_id, nt_id, f"sw-{i}") for i in range(4)]
    for i in range(3):
        eid = _create_edge(client, topo_id, tid, nodes[i], nodes[i + 1])
        _set_edge_attrs(client, eid, [
            {"fieldKey": "speed", "value": f"{i}G"},
            {"fieldKey": "proto", "value": f"vlan{i}"},
        ])

    r = client.post(
        f"/admin/api/edge-types/{tid}/fields/delete-impact",
        json={"fieldKeys": ["speed", "proto"]},
    )
    assert r.status_code == 200
    items = r.json()["data"]["items"]
    counts = {it["fieldKey"]: it["affectedNodeCount"] for it in items}
    assert counts == {"speed": 3, "proto": 3}


def test_edge_delete_impact_empty_for_unused_field(client):
    """未引用字段 → affectedNodeCount=0。"""
    tid = _create_edge_type(client, "unused_edge", "未使用字段", fields=[
        {"fieldKey": "unused_field", "fieldLabel": "U", "fieldType": "number"},
    ])

    r = client.post(
        f"/admin/api/edge-types/{tid}/fields/delete-impact",
        json={"fieldKeys": ["unused_field"]},
    )
    assert r.status_code == 200
    items = r.json()["data"]["items"]
    assert items == [{"fieldKey": "unused_field", "affectedNodeCount": 0}]


def test_edge_legacy_single_field_endpoints_removed(client):
    """旧 3 个单字段端点应已删除，返回 404 或 405。"""
    tid = _create_edge_type(client, "legacy_edge_test", "旧端点测试")

    r = client.post(f"/admin/api/edge-types/{tid}/fields", json={
        "fieldKey": "x", "fieldLabel": "X", "fieldType": "number",
    })
    assert r.status_code in (404, 405), f"POST /fields 应已移除，实际 {r.status_code}"

    r = client.put(f"/admin/api/edge-types/{tid}/fields/1", json={
        "fieldLabel": "Y",
    })
    assert r.status_code in (404, 405)

    r = client.delete(f"/admin/api/edge-types/{tid}/fields/1")
    assert r.status_code in (404, 405)


def test_edge_update_empty_body_rejected(client):
    """PUT 完全空 body → 400（I-1 防御）。"""
    tid = _create_edge_type(client, "empty_edge_test", "空 body 测试")

    r = client.put(f"/admin/api/edge-types/{tid}", json={})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == 40303
