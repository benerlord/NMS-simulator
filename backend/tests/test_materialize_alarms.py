def test_materialize_creates_default_alarm_per_node(client):
    # setup
    r = client.post("/admin/api/alarm-schemas", json={
        "code": "x", "name": "X",
        "fields": [{"fieldKey": "aid", "fieldLabel": "AID", "fieldType": "text", "maxLength": 50, "defaultValue": "DEF"}],
    })
    sid = r.json()["data"]["id"]
    r = client.post("/admin/api/topologies", json={"name": "T"})
    tid = r.json()["data"]["id"]
    client.patch(f"/admin/api/topologies/{tid}/alarm-schema", json={"alarmSchemaId": sid, "clearExisting": False})
    r = client.post("/admin/api/node-types", json={"code": "sw", "name": "SW", "category": "switch"})
    ntid = r.json()["data"]["id"]

    # create node group, count = 5
    r = client.post(f"/admin/api/topologies/{tid}/node-groups", json={
        "nodeTypeId": ntid,
        "groupName": "g1",
        "nodeCount": 5,
        "nameTemplate": "{group}-{i:03d}",
        "attrStrategies": [],
        "edgeStrategies": [],
    })
    gid = r.json()["data"]["id"]

    # materialize
    r = client.post(f"/admin/api/node-groups/{gid}/materialize")
    assert r.status_code == 200

    # verify counts via direct SQL
    import sqlite3
    from app.core.config import settings
    with sqlite3.connect(str(settings.db_path)) as c:
        c.row_factory = sqlite3.Row
        n_cnt = c.execute(
            "SELECT COUNT(*) AS c FROM nodes WHERE topology_id = ?", (tid,)
        ).fetchone()["c"]
        a_cnt = c.execute(
            "SELECT COUNT(*) AS c FROM node_alarms a JOIN nodes n ON n.id = a.node_id "
            "WHERE n.topology_id = ?", (tid,)
        ).fetchone()["c"]
    assert n_cnt == 5
    assert a_cnt == 5


def test_materialize_no_alarm_when_schema_unbound(client):
    r = client.post("/admin/api/topologies", json={"name": "T2"})
    tid = r.json()["data"]["id"]
    r = client.post("/admin/api/node-types", json={"code": "sw", "name": "SW", "category": "switch"})
    ntid = r.json()["data"]["id"]
    r = client.post(f"/admin/api/topologies/{tid}/node-groups", json={
        "nodeTypeId": ntid, "groupName": "g", "nodeCount": 3,
        "nameTemplate": "{group}-{i:03d}", "attrStrategies": [], "edgeStrategies": [],
    })
    gid = r.json()["data"]["id"]
    client.post(f"/admin/api/node-groups/{gid}/materialize")

    import sqlite3
    from app.core.config import settings
    with sqlite3.connect(str(settings.db_path)) as c:
        c.row_factory = sqlite3.Row
        a_cnt = c.execute(
            "SELECT COUNT(*) AS c FROM node_alarms a JOIN nodes n ON n.id = a.node_id "
            "WHERE n.topology_id = ?", (tid,)
        ).fetchone()["c"]
    assert a_cnt == 0


def test_materialize_1000_nodes_under_30s(client):
    import time
    r = client.post("/admin/api/alarm-schemas", json={
        "code": "x", "name": "X",
        "fields": [{"fieldKey": "aid", "fieldLabel": "AID", "fieldType": "text", "maxLength": 50, "defaultValue": "X"}],
    })
    sid = r.json()["data"]["id"]
    r = client.post("/admin/api/topologies", json={"name": "T"})
    tid = r.json()["data"]["id"]
    client.patch(f"/admin/api/topologies/{tid}/alarm-schema", json={"alarmSchemaId": sid, "clearExisting": False})
    r = client.post("/admin/api/node-types", json={"code": "sw", "name": "SW", "category": "switch"})
    ntid = r.json()["data"]["id"]

    r = client.post(f"/admin/api/topologies/{tid}/node-groups", json={
        "nodeTypeId": ntid, "groupName": "big", "nodeCount": 1000,
        "nameTemplate": "{group}-{i:05d}", "attrStrategies": [], "edgeStrategies": [],
    })
    gid = r.json()["data"]["id"]

    t0 = time.time()
    r = client.post(f"/admin/api/node-groups/{gid}/materialize")
    elapsed = time.time() - t0
    assert r.status_code == 200
    assert elapsed < 30, f"materialize 1000 nodes took {elapsed:.1f}s"
