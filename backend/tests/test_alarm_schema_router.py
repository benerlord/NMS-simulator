def test_list_alarm_schemas_empty(client):
    r = client.get("/admin/api/alarm-schemas")
    assert r.status_code == 200
    j = r.json()
    assert j["code"] == 0
    assert j["data"] == []


def test_create_alarm_schema_with_fields(client):
    payload = {
        "code": "huawei",
        "name": "华为告警模板",
        "description": "demo",
        "fields": [
            {"fieldKey": "alarm_id", "fieldLabel": "告警ID", "fieldType": "text", "maxLength": 64, "sortOrder": 0},
            {"fieldKey": "severity", "fieldLabel": "级别", "fieldType": "select", "options": "critical,major,minor", "sortOrder": 1},
        ],
    }
    r = client.post("/admin/api/alarm-schemas", json=payload)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["code"] == 0
    sid = j["data"]["id"]
    assert sid.startswith("as_")
    assert len(j["data"]["fields"]) == 2


def test_get_alarm_schema_detail(client):
    r = client.post("/admin/api/alarm-schemas", json={
        "code": "zte", "name": "中兴", "fields": []
    })
    sid = r.json()["data"]["id"]

    r = client.get(f"/admin/api/alarm-schemas/{sid}")
    assert r.status_code == 200
    assert r.json()["data"]["code"] == "zte"


def test_update_alarm_schema_replaces_fields(client):
    r = client.post("/admin/api/alarm-schemas", json={
        "code": "c1", "name": "n1",
        "fields": [{"fieldKey": "a", "fieldLabel": "A", "fieldType": "text", "maxLength": 50}],
    })
    sid = r.json()["data"]["id"]

    r = client.put(f"/admin/api/alarm-schemas/{sid}", json={
        "name": "new_name",
        "fields": [{"fieldKey": "b", "fieldLabel": "B", "fieldType": "number"}],
    })
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["name"] == "new_name"
    assert [f["fieldKey"] for f in d["fields"]] == ["b"]


def test_delete_unreferenced_alarm_schema_succeeds(client):
    r = client.post("/admin/api/alarm-schemas", json={"code": "x", "name": "X", "fields": []})
    sid = r.json()["data"]["id"]
    r = client.delete(f"/admin/api/alarm-schemas/{sid}")
    assert r.status_code == 200
    assert r.json()["code"] == 0


def test_create_alarm_schema_with_invalid_field_key_rejected(client):
    r = client.post("/admin/api/alarm-schemas", json={
        "code": "c1", "name": "n1",
        "fields": [{"fieldKey": "bad-key!", "fieldLabel": "X", "fieldType": "number"}],
    })
    assert r.status_code == 400


def test_delete_referenced_alarm_schema_rejected(client):
    # create alarm_schema and topology, bind
    r = client.post("/admin/api/alarm-schemas", json={"code": "ref", "name": "Ref", "fields": []})
    sid = r.json()["data"]["id"]
    r = client.post("/admin/api/topologies", json={"name": "RefT1"})
    tid = r.json()["data"]["id"]
    r = client.patch(f"/admin/api/topologies/{tid}/alarm-schema",
                     json={"alarmSchemaId": sid, "clearExisting": False})
    assert r.status_code == 200

    # delete attempt
    r = client.delete(f"/admin/api/alarm-schemas/{sid}")
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert detail["code"] == 40901
    assert "RefT1" in detail["details"]["referencedBy"]
