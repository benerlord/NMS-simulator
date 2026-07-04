import sqlite3
from app.core.config import settings


def _setup_schema_with_mapping(client):
    r = client.post("/admin/api/alarm-schemas", json={
        "code": "demo", "name": "Demo",
        "fields": [
            {"fieldKey": "alarm_id", "fieldLabel": "ID", "fieldType": "text", "maxLength": 64, "defaultValue": "AID-DEF", "sortOrder": 0},
            {"fieldKey": "node_ip", "fieldLabel": "IP", "fieldType": "text", "maxLength": 50, "mappingTarget": "ip", "sortOrder": 1},
            {"fieldKey": "node_name", "fieldLabel": "Name", "fieldType": "text", "maxLength": 100, "mappingTarget": "name", "sortOrder": 2},
        ],
    })
    return r.json()["data"]["id"]


def _setup_node_type_and_topology(client, sid):
    r = client.post("/admin/api/topologies", json={"name": "T"})
    tid = r.json()["data"]["id"]
    client.patch(f"/admin/api/topologies/{tid}/alarm-schema", json={"alarmSchemaId": sid, "clearExisting": False})
    r = client.post("/admin/api/node-types", json={"code": "sw", "name": "SW", "category": "switch"})
    ntid = r.json()["data"]["id"]
    return tid, ntid


def test_create_node_alarm_fills_mapping_from_system_field(client):
    sid = _setup_schema_with_mapping(client)
    tid, ntid = _setup_node_type_and_topology(client, sid)
    r = client.post(f"/admin/api/topologies/{tid}/nodes", json={
        "nodeTypeId": ntid, "name": "router-01"
    })
    nid = r.json()["data"]["id"]
    alarms = client.get(f"/admin/api/nodes/{nid}/alarms").json()["data"]
    assert len(alarms) == 1
    assert alarms[0]["attrs"]["node_name"] == "router-01"
    assert alarms[0]["attrs"]["alarm_id"] == "AID-DEF"


def test_create_node_alarm_fills_mapping_from_custom_attr(client):
    sid = _setup_schema_with_mapping(client)
    tid, ntid = _setup_node_type_and_topology(client, sid)
    r = client.post(f"/admin/api/topologies/{tid}/nodes", json={
        "nodeTypeId": ntid, "name": "n1"
    })
    nid = r.json()["data"]["id"]
    client.put(f"/admin/api/nodes/{nid}/attrs", json=[{"fieldKey": "ip", "value": "10.0.0.5"}])
    r = client.post(f"/admin/api/nodes/{nid}/alarms", json={})
    assert r.status_code == 200
    assert r.json()["data"]["attrs"]["node_ip"] == "10.0.0.5"


def test_manual_alarm_user_attrs_override_mapping(client):
    sid = _setup_schema_with_mapping(client)
    tid, ntid = _setup_node_type_and_topology(client, sid)
    r = client.post(f"/admin/api/topologies/{tid}/nodes", json={
        "nodeTypeId": ntid, "name": "n2"
    })
    nid = r.json()["data"]["id"]
    r = client.post(f"/admin/api/nodes/{nid}/alarms", json={
        "attrs": {"node_name": "USER-OVERRIDE"}
    })
    assert r.json()["data"]["attrs"]["node_name"] == "USER-OVERRIDE"


def test_materialize_uses_mapping(client):
    sid = _setup_schema_with_mapping(client)
    tid, ntid = _setup_node_type_and_topology(client, sid)
    r = client.post(f"/admin/api/topologies/{tid}/node-groups", json={
        "nodeTypeId": ntid, "groupName": "g", "nodeCount": 3,
        "nameTemplate": "{group}-{i:03d}",
        "attrStrategies": [], "edgeStrategies": [],
    })
    gid = r.json()["data"]["id"]
    # 新语义：materialize 只按组的告警模板生成告警，需先创建模板
    client.post(f"/admin/api/node-groups/{gid}/alarms", json={"attrs": {}})
    client.post(f"/admin/api/node-groups/{gid}/materialize")

    with sqlite3.connect(str(settings.db_path)) as c:
        c.row_factory = sqlite3.Row
        rows = c.execute(
            "SELECT n.name, aa.value AS node_name_val "
            "FROM nodes n "
            "JOIN node_alarms a ON a.node_id = n.id "
            "JOIN node_alarm_attrs aa ON aa.alarm_id = a.id AND aa.field_key = 'node_name' "
            "WHERE n.topology_id = ?",
            (tid,),
        ).fetchall()
    assert len(rows) == 3
    for r in rows:
        assert r["node_name_val"] == r["name"]
