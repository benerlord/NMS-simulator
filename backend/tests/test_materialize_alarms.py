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

    # 新语义：materialize 只按组的告警模板生成告警。加 1 条模板 => 每节点 1 条告警。
    client.post(f"/admin/api/node-groups/{gid}/alarms", json={"attrs": {}})

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


def test_materialize_uses_group_alarm_templates(client):
    """组 3 虚拟节点 + 2 条告警模板 → materialize 后 3 nodes × 2 alarms = 6 条 node_alarms。"""
    r = client.post("/admin/api/topologies", json={"name": "T"})
    tid = r.json()["data"]["id"]
    r = client.post("/admin/api/alarm-schemas", json={
        "code": "msch", "name": "MS",
        "fields": [
            {"fieldKey": "severity", "fieldLabel": "级别", "fieldType": "text",
             "maxLength": 20, "defaultValue": "minor"},
        ],
    })
    sid = r.json()["data"]["id"]

    import sqlite3
    from app.core.config import settings as app_settings
    with sqlite3.connect(str(app_settings.db_path), isolation_level=None) as c:
        c.execute("UPDATE topologies SET alarm_schema_id = ? WHERE id = ?", (sid, tid))

    r = client.post("/admin/api/node-types", json={"code": "sw", "name": "SW", "category": "switch"})
    ntid = r.json()["data"]["id"]
    r = client.post(f"/admin/api/topologies/{tid}/node-groups", json={
        "nodeTypeId": ntid, "groupName": "G", "nodeCount": 3,
    })
    gid = r.json()["data"]["id"]

    client.post(f"/admin/api/node-groups/{gid}/alarms", json={"attrs": {"severity": "critical"}})
    client.post(f"/admin/api/node-groups/{gid}/alarms", json={"attrs": {"severity": "major"}})

    r = client.post(f"/admin/api/node-groups/{gid}/materialize")
    assert r.status_code == 200, r.text

    with sqlite3.connect(str(app_settings.db_path), isolation_level=None) as c:
        c.row_factory = sqlite3.Row
        alarms = c.execute(
            "SELECT COUNT(*) c FROM node_alarms a JOIN nodes n ON n.id = a.node_id "
            "WHERE n.group_id = ?", (gid,),
        ).fetchone()
    assert alarms["c"] == 6


def test_materialize_zero_templates_inserts_zero_alarms(client):
    """组 0 条模板 → materialize 后 每节点 0 告警（跟旧的"自动 1 条"不同）。"""
    r = client.post("/admin/api/topologies", json={"name": "T"})
    tid = r.json()["data"]["id"]
    r = client.post("/admin/api/alarm-schemas", json={
        "code": "zsch", "name": "ZS",
        "fields": [{"fieldKey": "severity", "fieldLabel": "级别", "fieldType": "text",
                    "maxLength": 20, "defaultValue": "minor"}],
    })
    sid = r.json()["data"]["id"]
    import sqlite3
    from app.core.config import settings as app_settings
    with sqlite3.connect(str(app_settings.db_path), isolation_level=None) as c:
        c.execute("UPDATE topologies SET alarm_schema_id = ? WHERE id = ?", (sid, tid))

    r = client.post("/admin/api/node-types", json={"code": "sw", "name": "SW", "category": "switch"})
    ntid = r.json()["data"]["id"]
    r = client.post(f"/admin/api/topologies/{tid}/node-groups", json={
        "nodeTypeId": ntid, "groupName": "G", "nodeCount": 3,
    })
    gid = r.json()["data"]["id"]

    r = client.post(f"/admin/api/node-groups/{gid}/materialize")
    assert r.status_code == 200

    with sqlite3.connect(str(app_settings.db_path), isolation_level=None) as c:
        c.row_factory = sqlite3.Row
        alarms = c.execute(
            "SELECT COUNT(*) c FROM node_alarms a JOIN nodes n ON n.id = a.node_id "
            "WHERE n.group_id = ?", (gid,),
        ).fetchone()
    assert alarms["c"] == 0


def test_materialize_alarm_mapping_target_uses_new_node_value(client):
    """告警字段 mapping_target='name' → materialize 后每节点告警的 attrs 里该字段 = 节点 name。"""
    r = client.post("/admin/api/topologies", json={"name": "T"})
    tid = r.json()["data"]["id"]
    r = client.post("/admin/api/alarm-schemas", json={
        "code": "mmsch", "name": "MMS",
        "fields": [
            {"fieldKey": "device_name", "fieldLabel": "设备名", "fieldType": "text",
             "maxLength": 100, "mappingTarget": "name"},
            {"fieldKey": "severity", "fieldLabel": "级别", "fieldType": "text",
             "maxLength": 20, "defaultValue": "minor"},
        ],
    })
    sid = r.json()["data"]["id"]
    import sqlite3
    from app.core.config import settings as app_settings
    with sqlite3.connect(str(app_settings.db_path), isolation_level=None) as c:
        c.execute("UPDATE topologies SET alarm_schema_id = ? WHERE id = ?", (sid, tid))

    r = client.post("/admin/api/node-types", json={"code": "sw", "name": "SW", "category": "switch"})
    ntid = r.json()["data"]["id"]
    r = client.post(f"/admin/api/topologies/{tid}/node-groups", json={
        "nodeTypeId": ntid, "groupName": "Sw", "nodeCount": 2,
        "nameTemplate": "{group}-{i:02d}",
    })
    gid = r.json()["data"]["id"]

    client.post(f"/admin/api/node-groups/{gid}/alarms", json={"attrs": {"severity": "major"}})

    r = client.post(f"/admin/api/node-groups/{gid}/materialize")
    assert r.status_code == 200

    with sqlite3.connect(str(app_settings.db_path), isolation_level=None) as c:
        c.row_factory = sqlite3.Row
        rows = c.execute(
            "SELECT n.name, aa.value FROM node_alarms a "
            "JOIN nodes n ON n.id = a.node_id "
            "JOIN node_alarm_attrs aa ON aa.alarm_id = a.id AND aa.field_key = 'device_name' "
            "WHERE n.group_id = ? ORDER BY n.name", (gid,),
        ).fetchall()
    pairs = [(r["name"], r["value"]) for r in rows]
    assert pairs == [("Sw-01", "Sw-01"), ("Sw-02", "Sw-02")]
