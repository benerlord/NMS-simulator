import sqlite3
from app.core.config import settings as _app_settings


def _setup_topology_with_schema_and_node(client):
    # 1. create schema
    r = client.post("/admin/api/alarm-schemas", json={
        "code": "demo", "name": "DemoTpl",
        "fields": [
            {"fieldKey": "alarm_id", "fieldLabel": "ID", "fieldType": "text", "maxLength": 64, "defaultValue": "AID-000"},
            {"fieldKey": "severity", "fieldLabel": "级别", "fieldType": "select", "options": "critical,major", "defaultValue": "minor"},
        ],
    })
    sid = r.json()["data"]["id"]

    # 2. create topology
    r = client.post("/admin/api/topologies", json={"name": "T"})
    tid = r.json()["data"]["id"]

    # 3. bind alarm_schema via direct SQL (PATCH endpoint built in Task 6)
    with sqlite3.connect(str(_app_settings.db_path), isolation_level=None) as c:
        c.execute("UPDATE topologies SET alarm_schema_id = ? WHERE id = ?", (sid, tid))

    # 4. create node_type + node
    r = client.post("/admin/api/node-types", json={
        "code": "sw", "name": "交换机", "category": "switch"
    })
    ntid = r.json()["data"]["id"]
    r = client.post(f"/admin/api/topologies/{tid}/nodes", json={
        "nodeTypeId": ntid, "name": "n1"
    })
    nid = r.json()["data"]["id"]
    return tid, ntid, nid


def test_list_node_alarms(client):
    tid, ntid, nid = _setup_topology_with_schema_and_node(client)
    r = client.get(f"/admin/api/nodes/{nid}/alarms")
    assert r.status_code == 200
    # Node creation does NOT auto-insert yet (Task 7 adds that). Expect 0.
    assert isinstance(r.json()["data"], list)


def test_create_node_alarm_uses_default_value(client):
    tid, ntid, nid = _setup_topology_with_schema_and_node(client)
    r = client.post(f"/admin/api/nodes/{nid}/alarms", json={})
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["id"].startswith("alm_")
    assert d["attrs"]["alarm_id"] == "AID-000"
    assert d["attrs"]["severity"] == "minor"


def test_create_node_alarm_with_partial_attrs(client):
    tid, ntid, nid = _setup_topology_with_schema_and_node(client)
    r = client.post(f"/admin/api/nodes/{nid}/alarms", json={
        "attrs": {"alarm_id": "CUSTOM-1"}
    })
    d = r.json()["data"]
    assert d["attrs"]["alarm_id"] == "CUSTOM-1"
    assert d["attrs"]["severity"] == "minor"


def test_create_node_alarm_without_schema_rejected(client):
    # topology with no alarm_schema bound
    r = client.post("/admin/api/topologies", json={"name": "T2"})
    tid = r.json()["data"]["id"]
    r = client.post("/admin/api/node-types", json={"code": "sw2", "name": "SW", "category": "switch"})
    ntid = r.json()["data"]["id"]
    r = client.post(f"/admin/api/topologies/{tid}/nodes", json={"nodeTypeId": ntid, "name": "n"})
    nid = r.json()["data"]["id"]

    r = client.post(f"/admin/api/nodes/{nid}/alarms", json={})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == 40901


def test_update_node_alarm_attrs(client):
    tid, ntid, nid = _setup_topology_with_schema_and_node(client)
    r = client.post(f"/admin/api/nodes/{nid}/alarms", json={})
    aid = r.json()["data"]["id"]

    r = client.put(f"/admin/api/alarms/{aid}/attrs", json={
        "attrs": {"alarm_id": "UPDATED", "severity": "critical"}
    })
    assert r.status_code == 200
    assert r.json()["data"]["attrs"]["severity"] == "critical"


def test_update_node_alarm_max_length_rejected(client):
    tid, ntid, nid = _setup_topology_with_schema_and_node(client)
    r = client.post(f"/admin/api/nodes/{nid}/alarms", json={})
    aid = r.json()["data"]["id"]

    too_long = "x" * 100  # maxLength is 64
    r = client.put(f"/admin/api/alarms/{aid}/attrs", json={
        "attrs": {"alarm_id": too_long}
    })
    assert r.status_code == 400


def test_delete_node_alarm(client):
    tid, ntid, nid = _setup_topology_with_schema_and_node(client)
    r = client.post(f"/admin/api/nodes/{nid}/alarms", json={})
    aid = r.json()["data"]["id"]
    r = client.delete(f"/admin/api/alarms/{aid}")
    assert r.status_code == 200
    r = client.get(f"/admin/api/nodes/{nid}/alarms")
    assert all(a["id"] != aid for a in r.json()["data"])


def test_alarm_index_auto_increment(client):
    tid, ntid, nid = _setup_topology_with_schema_and_node(client)
    a1 = client.post(f"/admin/api/nodes/{nid}/alarms", json={}).json()["data"]
    a2 = client.post(f"/admin/api/nodes/{nid}/alarms", json={}).json()["data"]
    a3 = client.post(f"/admin/api/nodes/{nid}/alarms", json={}).json()["data"]
    assert a2["alarmIndex"] == a1["alarmIndex"] + 1
    assert a3["alarmIndex"] == a2["alarmIndex"] + 1
