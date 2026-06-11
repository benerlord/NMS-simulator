"""Tests that the /admin/api/sql/views endpoint surfaces the alarms CTE
conditionally based on whether the topology has an alarm_schema_id bound.
"""


def test_sql_views_includes_alarms_when_bound(client):
    # Create alarm schema with a field
    r = client.post("/admin/api/alarm-schemas", json={
        "code": "x", "name": "X",
        "fields": [{"fieldKey": "severity", "fieldLabel": "S", "fieldType": "text", "maxLength": 30}],
    })
    assert r.status_code == 200, r.text
    sid = r.json()["data"]["id"]

    # Create topology
    r = client.post("/admin/api/topologies", json={"name": "T"})
    assert r.status_code == 200, r.text
    tid = r.json()["data"]["id"]

    # Bind alarm schema to topology
    r = client.patch(f"/admin/api/topologies/{tid}/alarm-schema",
                     json={"alarmSchemaId": sid, "clearExisting": False})
    assert r.status_code == 200, r.text

    # Fetch views — alarms should be present
    r = client.get(f"/admin/api/sql/views", params={"topologyId": tid})
    assert r.status_code == 200, r.text
    views = r.json()["data"]["generic"]
    names = {v["name"] for v in views}
    assert "alarms" in names


def test_sql_views_omits_alarms_when_unbound(client):
    # Create topology without binding any alarm schema
    r = client.post("/admin/api/topologies", json={"name": "T2"})
    assert r.status_code == 200, r.text
    tid = r.json()["data"]["id"]

    # Fetch views — alarms should NOT be present
    r = client.get(f"/admin/api/sql/views", params={"topologyId": tid})
    assert r.status_code == 200, r.text
    views = r.json()["data"]["generic"]
    names = {v["name"] for v in views}
    assert "alarms" not in names
