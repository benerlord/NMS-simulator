"""节点类型字段整批同步测试。

覆盖 §3.3 diff 算法（insert/update/delete）+ §3.4 delete-impact +
旧 3 个单字段端点已移除。
"""


def test_create_node_type_with_fields(client):
    """POST /node-types body 含 fields[] → 类型 + 字段一次性落库。"""
    payload = {
        "code": "router_v2",
        "name": "路由器V2",
        "category": "physical",
        "fields": [
            {"fieldKey": "ip", "fieldLabel": "IP", "fieldType": "text", "maxLength": 15},
            {"fieldKey": "ports", "fieldLabel": "端口数", "fieldType": "number"},
        ],
    }
    r = client.post("/admin/api/node-types", json=payload)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["code"] == 0
    type_id = j["data"]["id"]

    # 验证字段已落库
    r = client.get(f"/admin/api/node-types/{type_id}")
    assert r.status_code == 200
    fields = r.json()["data"]["fields"]
    assert [f["fieldKey"] for f in fields] == ["ip", "ports"]
    assert fields[0]["maxLength"] == 15


def test_update_sync_fields_insert_only(client):
    """PUT 加新字段 → 旧字段保留，新字段加入。"""
    r = client.post("/admin/api/node-types", json={
        "code": "sw", "name": "交换机", "category": "physical",
        "fields": [{"fieldKey": "old_f", "fieldLabel": "旧", "fieldType": "number"}],
    })
    tid = r.json()["data"]["id"]

    r = client.put(f"/admin/api/node-types/{tid}", json={
        "fields": [
            {"fieldKey": "old_f", "fieldLabel": "旧", "fieldType": "number"},
            {"fieldKey": "new_f", "fieldLabel": "新", "fieldType": "number"},
        ],
    })
    assert r.status_code == 200, r.text

    r = client.get(f"/admin/api/node-types/{tid}")
    keys = [f["fieldKey"] for f in r.json()["data"]["fields"]]
    assert keys == ["old_f", "new_f"]


def test_update_sync_fields_update_only(client):
    """PUT 改字段 label / sort → field_key 不变，UPDATE 生效。"""
    r = client.post("/admin/api/node-types", json={
        "code": "sw2", "name": "S2", "category": "physical",
        "fields": [
            {"fieldKey": "a", "fieldLabel": "Old A", "fieldType": "number"},
            {"fieldKey": "b", "fieldLabel": "Old B", "fieldType": "number"},
        ],
    })
    tid = r.json()["data"]["id"]

    r = client.put(f"/admin/api/node-types/{tid}", json={
        "fields": [
            {"fieldKey": "b", "fieldLabel": "New B", "fieldType": "number"},  # 调到前
            {"fieldKey": "a", "fieldLabel": "New A", "fieldType": "number"},  # 调到后
        ],
    })
    assert r.status_code == 200, r.text

    fields = client.get(f"/admin/api/node-types/{tid}").json()["data"]["fields"]
    assert [f["fieldKey"] for f in fields] == ["b", "a"]
    assert [f["fieldLabel"] for f in fields] == ["New B", "New A"]


def test_update_sync_fields_delete_cleans_orphan_attrs(conn, client):
    """PUT 删字段 + 该字段在 node_attrs 有数据 → node_attrs 中同类型节点的孤儿一并清理。"""
    r = client.post("/admin/api/node-types", json={
        "code": "ap", "name": "AP", "category": "physical",
        "fields": [
            {"fieldKey": "ip", "fieldLabel": "IP", "fieldType": "text", "maxLength": 15},
            {"fieldKey": "vendor", "fieldLabel": "厂家", "fieldType": "text", "maxLength": 50},
        ],
    })
    tid = r.json()["data"]["id"]

    # 创建拓扑 + 节点 + 灌 attrs
    r = client.post("/admin/api/topologies", json={"name": "T1"})
    topo_id = r.json()["data"]["id"]
    r = client.post(f"/admin/api/topologies/{topo_id}/nodes", json={
        "nodeTypeId": tid, "name": "ap-01",
    })
    node_id = r.json()["data"]["id"]
    r = client.put(f"/admin/api/nodes/{node_id}/attrs", json=[
        {"fieldKey": "ip", "value": "10.0.0.1"},
        {"fieldKey": "vendor", "value": "huawei"},
    ])
    assert r.status_code == 200, r.text

    # PUT 删除 vendor 字段
    r = client.put(f"/admin/api/node-types/{tid}", json={
        "fields": [{"fieldKey": "ip", "fieldLabel": "IP", "fieldType": "text", "maxLength": 15}],
    })
    assert r.status_code == 200, r.text

    # 验证 ip 还在，vendor 已清
    from app.db.connection import connect
    with connect() as c:
        rows = c.execute(
            "SELECT field_key FROM node_attrs WHERE node_id = ?", (node_id,)
        ).fetchall()
    keys = sorted(r["field_key"] for r in rows)
    assert keys == ["ip"]


def test_update_sync_fields_delete_keeps_other_type_attrs(client):
    """同名 field_key 在不同 node_type 的节点 attrs 不受波及。"""
    # 两个类型都有 fieldKey="ip"
    r = client.post("/admin/api/node-types", json={
        "code": "type_a", "name": "A", "category": "physical",
        "fields": [{"fieldKey": "ip", "fieldLabel": "IP", "fieldType": "text", "maxLength": 15}],
    })
    type_a = r.json()["data"]["id"]
    r = client.post("/admin/api/node-types", json={
        "code": "type_b", "name": "B", "category": "physical",
        "fields": [{"fieldKey": "ip", "fieldLabel": "IP", "fieldType": "text", "maxLength": 15}],
    })
    type_b = r.json()["data"]["id"]

    r = client.post("/admin/api/topologies", json={"name": "T2"})
    topo_id = r.json()["data"]["id"]
    r = client.post(f"/admin/api/topologies/{topo_id}/nodes", json={
        "nodeTypeId": type_b, "name": "b-01",
    })
    node_b = r.json()["data"]["id"]
    client.put(f"/admin/api/nodes/{node_b}/attrs", json=[{"fieldKey": "ip", "value": "192.168.1.1"}])

    # 删 type_a 的 ip 字段
    r = client.put(f"/admin/api/node-types/{type_a}", json={"fields": []})
    assert r.status_code == 200

    # type_b 节点的 ip attr 必须还在
    from app.db.connection import connect
    with connect() as c:
        row = c.execute(
            "SELECT value FROM node_attrs WHERE node_id = ? AND field_key = 'ip'",
            (node_b,),
        ).fetchone()
    assert row is not None
    assert row["value"] == "192.168.1.1"


def test_update_sync_fields_duplicate_field_key_rejected(client):
    """incoming 重复 field_key → 400。"""
    r = client.post("/admin/api/node-types", json={
        "code": "dup_test", "name": "D", "category": "physical",
        "fields": [],
    })
    tid = r.json()["data"]["id"]

    r = client.put(f"/admin/api/node-types/{tid}", json={
        "fields": [
            {"fieldKey": "same", "fieldLabel": "A", "fieldType": "number"},
            {"fieldKey": "same", "fieldLabel": "B", "fieldType": "number"},
        ],
    })
    assert r.status_code == 400


def test_update_omit_fields_preserves_existing(client):
    """PUT body 不含 fields → 字段不变。"""
    r = client.post("/admin/api/node-types", json={
        "code": "keep_test", "name": "K", "category": "physical",
        "fields": [{"fieldKey": "x", "fieldLabel": "X", "fieldType": "number"}],
    })
    tid = r.json()["data"]["id"]

    r = client.put(f"/admin/api/node-types/{tid}", json={"name": "K2"})
    assert r.status_code == 200, r.text

    fields = client.get(f"/admin/api/node-types/{tid}").json()["data"]["fields"]
    assert [f["fieldKey"] for f in fields] == ["x"]


def test_delete_impact_returns_affected_counts(client):
    """POST delete-impact → 每个 field_key 受影响节点数正确。"""
    r = client.post("/admin/api/node-types", json={
        "code": "impact_test", "name": "I", "category": "physical",
        "fields": [
            {"fieldKey": "ip", "fieldLabel": "IP", "fieldType": "text", "maxLength": 15},
            {"fieldKey": "mac", "fieldLabel": "MAC", "fieldType": "text", "maxLength": 17},
        ],
    })
    tid = r.json()["data"]["id"]

    r = client.post("/admin/api/topologies", json={"name": "T3"})
    topo_id = r.json()["data"]["id"]
    for i in range(3):
        rr = client.post(f"/admin/api/topologies/{topo_id}/nodes", json={
            "nodeTypeId": tid, "name": f"n{i}",
        })
        nid = rr.json()["data"]["id"]
        client.put(f"/admin/api/nodes/{nid}/attrs", json=[
            {"fieldKey": "ip", "value": f"10.0.0.{i}"},
            {"fieldKey": "mac", "value": f"aa:bb:cc:00:00:0{i}"},
        ])

    r = client.post(
        f"/admin/api/node-types/{tid}/fields/delete-impact",
        json={"fieldKeys": ["ip", "mac"]},
    )
    assert r.status_code == 200
    items = r.json()["data"]["items"]
    counts = {it["fieldKey"]: it["affectedNodeCount"] for it in items}
    assert counts == {"ip": 3, "mac": 3}


def test_delete_impact_empty_for_unused_field(client):
    """未引用字段 → affectedNodeCount=0。"""
    r = client.post("/admin/api/node-types", json={
        "code": "unused", "name": "U", "category": "physical",
        "fields": [{"fieldKey": "unused_field", "fieldLabel": "U", "fieldType": "number"}],
    })
    tid = r.json()["data"]["id"]

    r = client.post(
        f"/admin/api/node-types/{tid}/fields/delete-impact",
        json={"fieldKeys": ["unused_field"]},
    )
    assert r.status_code == 200
    items = r.json()["data"]["items"]
    assert items == [{"fieldKey": "unused_field", "affectedNodeCount": 0}]


def test_legacy_single_field_endpoints_removed(client):
    """旧 3 个单字段端点应已删除，返回 404 或 405。"""
    r = client.post("/admin/api/node-types", json={
        "code": "legacy_test", "name": "L", "category": "physical",
    })
    tid = r.json()["data"]["id"]

    r = client.post(f"/admin/api/node-types/{tid}/fields", json={
        "fieldKey": "x", "fieldLabel": "X", "fieldType": "number",
    })
    assert r.status_code in (404, 405), f"POST /fields 应已移除，实际 {r.status_code}"

    r = client.put(f"/admin/api/node-types/{tid}/fields/1", json={
        "fieldLabel": "Y",
    })
    assert r.status_code in (404, 405)

    r = client.delete(f"/admin/api/node-types/{tid}/fields/1")
    assert r.status_code in (404, 405)
