"""节点组告警 CRUD 端到端测试。"""


def _make_topo_group(client, with_schema=True):
    """造 topology + alarm_schema（可选） + node_type + node_group，返回 (tid, gid, sid|None)。"""
    r = client.post("/admin/api/topologies", json={"name": "T"})
    tid = r.json()["data"]["id"]

    sid = None
    if with_schema:
        r = client.post("/admin/api/alarm-schemas", json={
            "code": "sch1", "name": "S1",
            "fields": [
                {"fieldKey": "severity", "fieldLabel": "级别", "fieldType": "text",
                 "maxLength": 20, "defaultValue": "minor"},
                {"fieldKey": "node_dn", "fieldLabel": "设备DN", "fieldType": "text",
                 "maxLength": 100, "mappingTarget": "dn"},
            ],
        })
        sid = r.json()["data"]["id"]
        import sqlite3
        from app.core.config import settings as app_settings
        with sqlite3.connect(str(app_settings.db_path), isolation_level=None) as c:
            c.execute("UPDATE topologies SET alarm_schema_id = ? WHERE id = ?", (sid, tid))

    r = client.post("/admin/api/node-types", json={"code": "dev", "name": "Dev", "category": "switch"})
    ntid = r.json()["data"]["id"]
    r = client.post(f"/admin/api/topologies/{tid}/node-groups", json={
        "nodeTypeId": ntid, "groupName": "G", "nodeCount": 3,
    })
    gid = r.json()["data"]["id"]
    return tid, gid, sid


def test_list_alarms_empty(client):
    _, gid, _ = _make_topo_group(client)
    r = client.get(f"/admin/api/node-groups/{gid}/alarms")
    assert r.status_code == 200
    assert r.json()["data"] == []


def test_create_alarm_success_first_index_is_1(client):
    _, gid, _ = _make_topo_group(client)
    r = client.post(f"/admin/api/node-groups/{gid}/alarms", json={
        "attrs": {"severity": "critical"},
    })
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["id"].startswith("grp_alm_")
    assert d["alarmIndex"] == 1
    assert d["attrs"]["severity"] == "critical"
    # mapping_target 字段（node_dn）不该出现在模板 attrs 里
    assert "node_dn" not in d["attrs"]


def test_create_alarm_fills_default_value(client):
    _, gid, _ = _make_topo_group(client)
    r = client.post(f"/admin/api/node-groups/{gid}/alarms", json={})
    d = r.json()["data"]
    assert d["attrs"]["severity"] == "minor"  # default_value


def test_second_alarm_gets_index_2(client):
    _, gid, _ = _make_topo_group(client)
    client.post(f"/admin/api/node-groups/{gid}/alarms", json={})
    r = client.post(f"/admin/api/node-groups/{gid}/alarms", json={})
    assert r.json()["data"]["alarmIndex"] == 2


def test_update_alarm_attrs(client):
    _, gid, _ = _make_topo_group(client)
    aid = client.post(f"/admin/api/node-groups/{gid}/alarms", json={}).json()["data"]["id"]
    r = client.put(f"/admin/api/node-group-alarms/{aid}/attrs", json={
        "attrs": {"severity": "major"},
    })
    assert r.status_code == 200
    assert r.json()["data"]["attrs"]["severity"] == "major"


def test_delete_alarm(client):
    _, gid, _ = _make_topo_group(client)
    aid = client.post(f"/admin/api/node-groups/{gid}/alarms", json={}).json()["data"]["id"]
    r = client.delete(f"/admin/api/node-group-alarms/{aid}")
    assert r.status_code == 200
    r2 = client.get(f"/admin/api/node-groups/{gid}/alarms")
    assert r2.json()["data"] == []


def test_create_alarm_without_schema_rejected(client):
    """拓扑未绑 alarm_schema 时 POST 应 409 + 40901。"""
    _, gid, _ = _make_topo_group(client, with_schema=False)
    r = client.post(f"/admin/api/node-groups/{gid}/alarms", json={})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == 40901


def test_delete_group_cascades_alarms(client):
    """DELETE 节点组时，告警 + attrs 应一并清（DB 层级联）。"""
    _, gid, _ = _make_topo_group(client)
    client.post(f"/admin/api/node-groups/{gid}/alarms", json={})
    client.delete(f"/admin/api/node-groups/{gid}")
    import sqlite3
    from app.core.config import settings as app_settings
    with sqlite3.connect(str(app_settings.db_path), isolation_level=None) as c:
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys = ON")
        rows = c.execute(
            "SELECT COUNT(*) c FROM node_group_alarms WHERE node_group_id = ?", (gid,)
        ).fetchone()
        assert rows["c"] == 0
