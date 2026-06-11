def test_create_with_mapping_target_and_display_field_key(client):
    payload = {
        "code": "huawei",
        "name": "华为",
        "displayFieldKey": "alarm_id",
        "fields": [
            {"fieldKey": "alarm_id", "fieldLabel": "ID", "fieldType": "text", "maxLength": 64, "sortOrder": 0},
            {"fieldKey": "node_ip", "fieldLabel": "网元IP", "fieldType": "text", "maxLength": 50, "mappingTarget": "ip", "sortOrder": 1},
        ],
    }
    r = client.post("/admin/api/alarm-schemas", json=payload)
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["displayFieldKey"] == "alarm_id"
    node_ip_field = next(f for f in d["fields"] if f["fieldKey"] == "node_ip")
    assert node_ip_field["mappingTarget"] == "ip"


def test_create_with_invalid_mapping_target_returns_400(client):
    r = client.post("/admin/api/alarm-schemas", json={
        "code": "c1", "name": "n1",
        "fields": [{"fieldKey": "x", "fieldLabel": "X", "fieldType": "number", "mappingTarget": "bad-key!"}],
    })
    assert r.status_code == 422


def test_get_alarm_schema_returns_new_fields(client):
    r = client.post("/admin/api/alarm-schemas", json={
        "code": "c2", "name": "n2",
        "displayFieldKey": "k1",
        "fields": [{"fieldKey": "k1", "fieldLabel": "L1", "fieldType": "number", "mappingTarget": "name"}],
    })
    sid = r.json()["data"]["id"]
    r = client.get(f"/admin/api/alarm-schemas/{sid}")
    d = r.json()["data"]
    assert d["displayFieldKey"] == "k1"
    assert d["fields"][0]["mappingTarget"] == "name"


def test_update_replaces_mapping_target_and_display_field_key(client):
    r = client.post("/admin/api/alarm-schemas", json={
        "code": "c3", "name": "n3",
        "displayFieldKey": "k1",
        "fields": [{"fieldKey": "k1", "fieldLabel": "L1", "fieldType": "number", "mappingTarget": "name"}],
    })
    sid = r.json()["data"]["id"]
    r = client.put(f"/admin/api/alarm-schemas/{sid}", json={
        "displayFieldKey": "k2",
        "fields": [{"fieldKey": "k2", "fieldLabel": "L2", "fieldType": "number", "mappingTarget": "status"}],
    })
    d = r.json()["data"]
    assert d["displayFieldKey"] == "k2"
    assert d["fields"][0]["mappingTarget"] == "status"


def test_create_without_new_fields_works(client):
    """Backward compat — schemas without mapping_target / display_field_key still work."""
    r = client.post("/admin/api/alarm-schemas", json={
        "code": "c4", "name": "n4",
        "fields": [{"fieldKey": "k", "fieldLabel": "K", "fieldType": "number"}],
    })
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["displayFieldKey"] is None
    assert d["fields"][0]["mappingTarget"] is None
