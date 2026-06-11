def test_create_node_auto_inserts_default_alarm(client):
    # setup: schema + topology + binding
    r = client.post("/admin/api/alarm-schemas", json={
        "code": "x", "name": "X",
        "fields": [
            {"fieldKey": "aid", "fieldLabel": "AID", "fieldType": "text", "maxLength": 50, "defaultValue": "ALM-DEF"}
        ],
    })
    sid = r.json()["data"]["id"]
    r = client.post("/admin/api/topologies", json={"name": "T"})
    tid = r.json()["data"]["id"]
    client.patch(f"/admin/api/topologies/{tid}/alarm-schema", json={
        "alarmSchemaId": sid, "clearExisting": False
    })
    r = client.post("/admin/api/node-types", json={"code": "sw", "name": "SW", "category": "switch"})
    ntid = r.json()["data"]["id"]

    # create node
    r = client.post(f"/admin/api/topologies/{tid}/nodes", json={
        "nodeTypeId": ntid, "name": "node-1"
    })
    nid = r.json()["data"]["id"]

    # alarms list should have 1
    r = client.get(f"/admin/api/nodes/{nid}/alarms")
    alarms = r.json()["data"]
    assert len(alarms) == 1
    assert alarms[0]["attrs"]["aid"] == "ALM-DEF"
    assert alarms[0]["alarmIndex"] == 1


def test_create_node_without_topology_schema_no_auto_alarm(client):
    r = client.post("/admin/api/topologies", json={"name": "T2"})
    tid = r.json()["data"]["id"]
    r = client.post("/admin/api/node-types", json={"code": "sw", "name": "SW", "category": "switch"})
    ntid = r.json()["data"]["id"]
    r = client.post(f"/admin/api/topologies/{tid}/nodes", json={
        "nodeTypeId": ntid, "name": "node-2"
    })
    nid = r.json()["data"]["id"]

    r = client.get(f"/admin/api/nodes/{nid}/alarms")
    assert r.json()["data"] == []
