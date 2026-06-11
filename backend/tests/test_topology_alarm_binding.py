def _create_topo_and_schema(client):
    r = client.post("/admin/api/alarm-schemas", json={"code": "x", "name": "X", "fields": []})
    sid = r.json()["data"]["id"]
    r = client.post("/admin/api/topologies", json={"name": "T"})
    tid = r.json()["data"]["id"]
    return tid, sid


def test_bind_alarm_schema_empty_topology(client):
    tid, sid = _create_topo_and_schema(client)
    r = client.patch(f"/admin/api/topologies/{tid}/alarm-schema", json={
        "alarmSchemaId": sid, "clearExisting": False
    })
    assert r.status_code == 200
    detail = client.get(f"/admin/api/topologies/{tid}").json()["data"]
    assert detail["alarmSchemaId"] == sid


def test_unbind_alarm_schema_when_empty(client):
    tid, sid = _create_topo_and_schema(client)
    client.patch(f"/admin/api/topologies/{tid}/alarm-schema", json={
        "alarmSchemaId": sid, "clearExisting": False
    })
    r = client.patch(f"/admin/api/topologies/{tid}/alarm-schema", json={
        "alarmSchemaId": None, "clearExisting": False
    })
    assert r.status_code == 200


def test_switch_schema_with_alarms_requires_clear(client):
    tid, sid = _create_topo_and_schema(client)
    # bind
    client.patch(f"/admin/api/topologies/{tid}/alarm-schema", json={
        "alarmSchemaId": sid, "clearExisting": False
    })
    # create node + alarm
    nt = client.post("/admin/api/node-types", json={"code": "sw", "name": "SW", "category": "switch"}).json()["data"]
    n = client.post(f"/admin/api/topologies/{tid}/nodes", json={"nodeTypeId": nt["id"], "name": "n"}).json()["data"]
    client.post(f"/admin/api/nodes/{n['id']}/alarms", json={})

    # create another schema
    r = client.post("/admin/api/alarm-schemas", json={"code": "y", "name": "Y", "fields": []})
    sid2 = r.json()["data"]["id"]

    # switch without clearExisting → 409
    r = client.patch(f"/admin/api/topologies/{tid}/alarm-schema", json={
        "alarmSchemaId": sid2, "clearExisting": False
    })
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == 40902
    assert r.json()["detail"]["details"]["nodeAlarmCount"] >= 1

    # with clearExisting → 200 + clears old alarms
    r = client.patch(f"/admin/api/topologies/{tid}/alarm-schema", json={
        "alarmSchemaId": sid2, "clearExisting": True
    })
    assert r.status_code == 200

    r = client.get(f"/admin/api/nodes/{n['id']}/alarms")
    assert r.json()["data"] == []


def test_topology_detail_includes_node_alarm_count(client):
    tid, sid = _create_topo_and_schema(client)
    client.patch(f"/admin/api/topologies/{tid}/alarm-schema", json={
        "alarmSchemaId": sid, "clearExisting": False
    })
    nt = client.post("/admin/api/node-types", json={"code": "sw", "name": "SW", "category": "switch"}).json()["data"]
    n = client.post(f"/admin/api/topologies/{tid}/nodes", json={"nodeTypeId": nt["id"], "name": "n"}).json()["data"]
    client.post(f"/admin/api/nodes/{n['id']}/alarms", json={})
    client.post(f"/admin/api/nodes/{n['id']}/alarms", json={})

    detail = client.get(f"/admin/api/topologies/{tid}").json()["data"]
    assert detail["nodeAlarmCount"] >= 2
