"""CRUD + 导入的跨域同名接口行为测试。"""


def test_create_same_method_path_different_domains_ok(client):
    d1 = client.post("/admin/api/domains", json={"name": "网管A"}).json()["data"]["id"]
    d2 = client.post("/admin/api/domains", json={"name": "网管B"}).json()["data"]["id"]

    r1 = client.post("/admin/api/apis", json={
        "method": "PUT", "path": "/rest/token", "name": "A-token",
        "domainId": d1, "dataSource": "static", "config": {},
    })
    assert r1.status_code == 200, r1.text

    r2 = client.post("/admin/api/apis", json={
        "method": "PUT", "path": "/rest/token", "name": "B-token",
        "domainId": d2, "dataSource": "static", "config": {},
    })
    assert r2.status_code == 200, r2.text
    assert r1.json()["data"]["id"] != r2.json()["data"]["id"]


def test_create_same_method_path_same_domain_blocked(client):
    d = client.post("/admin/api/domains", json={"name": "网管A"}).json()["data"]["id"]
    r1 = client.post("/admin/api/apis", json={
        "method": "GET", "path": "/dup", "name": "first",
        "domainId": d, "dataSource": "static", "config": {},
    })
    assert r1.status_code == 200

    r2 = client.post("/admin/api/apis", json={
        "method": "GET", "path": "/dup", "name": "second",
        "domainId": d, "dataSource": "static", "config": {},
    })
    assert r2.status_code == 409
    assert r2.json()["detail"]["code"] == 40301


def test_create_null_domain_duplicates_allowed(client):
    """未归类接口不做重复预检——跟 SQLite NULL 语义一致。"""
    r1 = client.post("/admin/api/apis", json={
        "method": "GET", "path": "/orphan", "name": "o1",
        "dataSource": "static", "config": {},
    })
    assert r1.status_code == 200
    r2 = client.post("/admin/api/apis", json={
        "method": "GET", "path": "/orphan", "name": "o2",
        "dataSource": "static", "config": {},
    })
    assert r2.status_code == 200
    assert r1.json()["data"]["id"] != r2.json()["data"]["id"]


def test_update_moving_path_within_same_domain_conflict_blocked(client):
    d = client.post("/admin/api/domains", json={"name": "网管A"}).json()["data"]["id"]
    a1 = client.post("/admin/api/apis", json={
        "method": "GET", "path": "/a", "name": "a",
        "domainId": d, "dataSource": "static", "config": {},
    }).json()["data"]["id"]
    client.post("/admin/api/apis", json={
        "method": "GET", "path": "/b", "name": "b",
        "domainId": d, "dataSource": "static", "config": {},
    })

    r = client.put(f"/admin/api/apis/{a1}", json={"path": "/b"})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == 40301


def test_update_moving_path_across_domain_ok(client):
    """A 域下 /x → 更新 path 为 /y，B 域下已有 /y 不应阻挡。"""
    dA = client.post("/admin/api/domains", json={"name": "网管A"}).json()["data"]["id"]
    dB = client.post("/admin/api/domains", json={"name": "网管B"}).json()["data"]["id"]
    aA = client.post("/admin/api/apis", json={
        "method": "GET", "path": "/x", "name": "xA",
        "domainId": dA, "dataSource": "static", "config": {},
    }).json()["data"]["id"]
    client.post("/admin/api/apis", json={
        "method": "GET", "path": "/y", "name": "yB",
        "domainId": dB, "dataSource": "static", "config": {},
    })

    r = client.put(f"/admin/api/apis/{aA}", json={"path": "/y"})
    assert r.status_code == 200, r.text


def test_duplicate_api_generates_unique_path_within_domain(client):
    """复制接口时生成 _copy 后缀，冲突判断按域，不看其它域。"""
    dA = client.post("/admin/api/domains", json={"name": "网管A"}).json()["data"]["id"]
    dB = client.post("/admin/api/domains", json={"name": "网管B"}).json()["data"]["id"]
    aA = client.post("/admin/api/apis", json={
        "method": "GET", "path": "/foo", "name": "fooA",
        "domainId": dA, "dataSource": "static", "config": {},
    }).json()["data"]["id"]
    # B 域下预置一个 /foo_copy，确保复制时 A 域的判定不会误参考它
    client.post("/admin/api/apis", json={
        "method": "GET", "path": "/foo_copy", "name": "fooB_copy",
        "domainId": dB, "dataSource": "static", "config": {},
    })

    r = client.post(f"/admin/api/apis/{aA}/duplicate")
    assert r.status_code == 200
    new_id = r.json()["data"]["id"]
    detail = client.get(f"/admin/api/apis/{new_id}").json()["data"]
    # 因为 A 域下不存在 /foo_copy，直接可用（不应因为 B 域的 /foo_copy 而变成 /foo_copy2）
    assert detail["path"] == "/foo_copy"
    assert detail["domainId"] == dA
