"""NodeType Create/Update 通过 payload 一次性处理 domain_ids。"""


def _seed_domain(client, name: str) -> str:
    r = client.post("/admin/api/domains", json={"name": name})
    assert r.status_code == 200, r.text
    return r.json()["data"]["id"]


def test_create_node_type_with_domain_ids(client):
    """POST /node-types 带 domainIds → 类型创建时自动关联网管。"""
    dom_a = _seed_domain(client, "网管A")
    dom_b = _seed_domain(client, "网管B")

    r = client.post("/admin/api/node-types", json={
        "code": "sw_bind", "name": "交换机绑定", "category": "physical",
        "domainIds": [dom_a, dom_b],
    })
    assert r.status_code == 200, r.text
    type_id = r.json()["data"]["id"]

    detail = client.get(f"/admin/api/node-types/{type_id}").json()["data"]
    assert set(detail["domainIds"]) == {dom_a, dom_b}
    assert set(detail["domainNames"]) == {"网管A", "网管B"}


def test_update_node_type_domain_ids_replace(client):
    """PUT /node-types/{id} 带 domainIds 数组 → 覆盖式 replace 关联。"""
    dom_a = _seed_domain(client, "网管A")
    dom_b = _seed_domain(client, "网管B")

    r = client.post("/admin/api/node-types", json={
        "code": "sw_upd", "name": "交换机", "category": "physical",
        "domainIds": [dom_a],
    })
    type_id = r.json()["data"]["id"]

    r = client.put(f"/admin/api/node-types/{type_id}", json={"domainIds": [dom_b]})
    assert r.status_code == 200, r.text

    detail = client.get(f"/admin/api/node-types/{type_id}").json()["data"]
    assert detail["domainIds"] == [dom_b]


def test_update_node_type_domain_ids_empty_clears(client):
    """PUT /node-types/{id} 带 domainIds=[] → 清空关联。"""
    dom_a = _seed_domain(client, "网管A")
    r = client.post("/admin/api/node-types", json={
        "code": "sw_clear", "name": "交换机", "category": "physical",
        "domainIds": [dom_a],
    })
    type_id = r.json()["data"]["id"]

    r = client.put(f"/admin/api/node-types/{type_id}", json={"domainIds": []})
    assert r.status_code == 200, r.text

    detail = client.get(f"/admin/api/node-types/{type_id}").json()["data"]
    assert detail["domainIds"] == []


def test_update_node_type_without_domain_ids_leaves_binding(client):
    """PUT /node-types/{id} 不带 domainIds 只改 name → 关联保持不动。"""
    dom_a = _seed_domain(client, "网管A")
    r = client.post("/admin/api/node-types", json={
        "code": "sw_keep", "name": "交换机", "category": "physical",
        "domainIds": [dom_a],
    })
    type_id = r.json()["data"]["id"]

    r = client.put(f"/admin/api/node-types/{type_id}", json={"name": "改名"})
    assert r.status_code == 200, r.text

    detail = client.get(f"/admin/api/node-types/{type_id}").json()["data"]
    assert detail["name"] == "改名"
    assert detail["domainIds"] == [dom_a]


def test_get_node_type_no_legacy_fields(client):
    """GET /node-types/{id} 不再返回 icon/color/shape/renderMode/dnTemplate。"""
    r = client.post("/admin/api/node-types", json={
        "code": "sw_nl", "name": "交换机", "category": "physical",
    })
    type_id = r.json()["data"]["id"]

    detail = client.get(f"/admin/api/node-types/{type_id}").json()["data"]
    for k in ("icon", "color", "shape", "renderMode", "dnTemplate"):
        assert k not in detail, f"响应不应包含死字段 {k}"
