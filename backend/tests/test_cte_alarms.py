import sqlite3

from app.core.cte_builder import collect_views
from app.db.migrations import run_migrations


def _build_db_with_alarm_data():
    conn = sqlite3.connect(":memory:", isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    run_migrations(conn)
    conn.execute("INSERT INTO topologies (id, name) VALUES ('t1', 'T1')")
    conn.execute("INSERT INTO node_types (id, code, name, category) VALUES ('nt1', 'sw', 'SW', 'switch')")
    conn.execute("INSERT INTO alarm_schemas (id, code, name) VALUES ('as1', 'huawei', 'Huawei')")
    conn.execute(
        "INSERT INTO alarm_schema_fields (alarm_schema_id, field_key, field_label, field_type, sort_order) "
        "VALUES ('as1','severity','级别','select',0),('as1','occurred_at','发生时间','text',1)"
    )
    conn.execute("UPDATE topologies SET alarm_schema_id = 'as1' WHERE id = 't1'")
    conn.execute("INSERT INTO nodes (id, topology_id, node_type_id, name) VALUES ('n1', 't1', 'nt1', 'n-1')")
    conn.execute("INSERT INTO node_alarms (id, node_id, alarm_index) VALUES ('alm_1', 'n1', 1)")
    conn.execute("INSERT INTO node_alarm_attrs (alarm_id, field_key, value) VALUES ('alm_1','severity','critical')")
    conn.execute("INSERT INTO node_alarm_attrs (alarm_id, field_key, value) VALUES ('alm_1','occurred_at','2026-06-10 10:00')")
    return conn


def test_alarms_cte_present_when_topology_has_schema():
    conn = _build_db_with_alarm_data()
    views = collect_views(conn, "t1")
    names = {v["name"] for v in views["generic"]}
    assert "alarms" in names


def test_alarms_cte_absent_when_topology_has_no_schema():
    conn = sqlite3.connect(":memory:", isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    run_migrations(conn)
    conn.execute("INSERT INTO topologies (id, name) VALUES ('t1', 'T1')")
    views = collect_views(conn, "t1")
    names = {v["name"] for v in views["generic"]}
    assert "alarms" not in names


def test_alarms_cte_columns_include_pivots():
    conn = _build_db_with_alarm_data()
    views = collect_views(conn, "t1")
    alarms = next(v for v in views["generic"] if v["name"] == "alarms")
    assert "severity" in alarms["columns"]
    assert "occurred_at" in alarms["columns"]
    assert "node_name" in alarms["columns"]
    assert "alarm_index" in alarms["columns"]


def test_alarms_cte_executes_against_db():
    conn = _build_db_with_alarm_data()
    views = collect_views(conn, "t1")
    generic = {v["name"]: v for v in views["generic"]}
    alarms = generic["alarms"]
    # alarms CTE now UNIONs with group_nodes which itself depends on gn_seq (recursive).
    gn_seq = generic["gn_seq"]
    group_nodes = generic["group_nodes"]
    sql = (
        f"WITH RECURSIVE gn_seq AS ({gn_seq['sql']}),\n"
        f"  group_nodes AS ({group_nodes['sql']}),\n"
        f"  alarms AS ({alarms['sql']})\n"
        f"SELECT * FROM alarms"
    )
    rows = conn.execute(sql, {"__tid__": "t1"}).fetchall()
    assert len(rows) == 1
    r = rows[0]
    assert r["severity"] == "critical"
    assert r["node_name"] == "n-1"


def test_alarms_cte_field_key_collision_skipped():
    conn = _build_db_with_alarm_data()
    # add a field that collides with a fixed column
    conn.execute(
        "INSERT INTO alarm_schema_fields (alarm_schema_id, field_key, field_label, field_type, sort_order) "
        "VALUES ('as1','node_name','节点名','text',5)"
    )
    views = collect_views(conn, "t1")
    alarms = next(v for v in views["generic"] if v["name"] == "alarms")
    # node_name should appear ONCE (as fixed column, not double-pivoted)
    assert alarms["columns"].count("node_name") == 1


def test_alarms_cte_invalid_field_key_skipped():
    conn = _build_db_with_alarm_data()
    conn.execute(
        "INSERT INTO alarm_schema_fields (alarm_schema_id, field_key, field_label, field_type, sort_order) "
        "VALUES ('as1','bad-key','bad','text',9)"
    )
    views = collect_views(conn, "t1")
    alarms = next(v for v in views["generic"] if v["name"] == "alarms")
    assert "bad-key" not in alarms["columns"]


def test_alarms_cte_includes_group_virtual_alarms(client):
    """一个组 2 虚拟节点 + 3 条告警模板 → alarms 视图返回 6 行。"""
    r = client.post("/admin/api/topologies", json={"name": "T"})
    tid = r.json()["data"]["id"]
    r = client.post("/admin/api/alarm-schemas", json={
        "code": "gsch", "name": "GS",
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

    r = client.post("/admin/api/node-types", json={"code": "sw", "name": "Switch", "category": "switch"})
    ntid = r.json()["data"]["id"]
    r = client.post(f"/admin/api/topologies/{tid}/node-groups", json={
        "nodeTypeId": ntid, "groupName": "G", "nodeCount": 2,
    })
    gid = r.json()["data"]["id"]

    for sev in ["critical", "major", "minor"]:
        client.post(f"/admin/api/node-groups/{gid}/alarms", json={"attrs": {"severity": sev}})

    r = client.post("/admin/api/sql/execute", json={
        "topologyId": tid,
        "sql":"SELECT COUNT(*) AS c FROM alarms",
    })
    assert r.status_code == 200, r.text
    rows = r.json()["data"]["items"]
    assert rows[0]["c"] == 6


def test_alarms_cte_group_ids_unique_across_union(client):
    """物理告警和虚拟告警的 id 应各自唯一，UNION 里不冲突。"""
    r = client.post("/admin/api/topologies", json={"name": "T"})
    tid = r.json()["data"]["id"]
    r = client.post("/admin/api/alarm-schemas", json={
        "code": "usch", "name": "US",
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
    r = client.post(f"/admin/api/topologies/{tid}/nodes", json={"nodeTypeId": ntid, "name": "n1"})
    nid = r.json()["data"]["id"]
    client.post(f"/admin/api/nodes/{nid}/alarms", json={})
    r = client.post(f"/admin/api/topologies/{tid}/node-groups", json={
        "nodeTypeId": ntid, "groupName": "G", "nodeCount": 2,
    })
    gid = r.json()["data"]["id"]
    client.post(f"/admin/api/node-groups/{gid}/alarms", json={})

    r = client.post("/admin/api/sql/execute", json={
        "topologyId": tid,
        "sql":"SELECT COUNT(*) c, COUNT(DISTINCT id) d FROM alarms",
    })
    rows = r.json()["data"]["items"]
    # 2 物理（节点创建自动 + 手动 POST）+ 2 虚拟（1 模板 × 2 虚拟节点）= 4
    assert rows[0]["c"] == 4
    assert rows[0]["d"] == 4  # id 全部唯一


def test_alarms_cte_mapping_target_takes_from_virtual_node(client):
    """告警字段配 mapping_target='name' → 每行 name 来自各自虚拟节点。"""
    r = client.post("/admin/api/topologies", json={"name": "T"})
    tid = r.json()["data"]["id"]
    r = client.post("/admin/api/alarm-schemas", json={
        "code": "msch", "name": "MS",
        "fields": [
            {"fieldKey": "device_name", "fieldLabel": "设备名", "fieldType": "text",
             "maxLength": 100, "mappingTarget": "name"},
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
    client.post(f"/admin/api/node-groups/{gid}/alarms", json={})

    r = client.post("/admin/api/sql/execute", json={
        "topologyId": tid,
        "sql":"SELECT device_name FROM alarms ORDER BY device_name",
    })
    rows = r.json()["data"]["items"]
    names = sorted(r["device_name"] for r in rows)
    assert names == ["Sw-01", "Sw-02"]


def test_alarms_cte_no_schema_still_no_cte(client):
    """拓扑无 alarm_schema → alarms CTE 不存在（跟现有一致）。"""
    r = client.post("/admin/api/topologies", json={"name": "T"})
    tid = r.json()["data"]["id"]
    r = client.post("/admin/api/sql/execute", json={
        "topologyId": tid,
        "sql":"SELECT * FROM alarms LIMIT 1",
    })
    assert r.status_code != 200 or "no such table" in r.text.lower() or r.json().get("code", 0) != 0


def test_alarms_cte_group_alarm_index_preserved(client):
    """组模板的 alarm_index 应体现在虚拟告警行的 alarm_index 列。"""
    r = client.post("/admin/api/topologies", json={"name": "T"})
    tid = r.json()["data"]["id"]
    r = client.post("/admin/api/alarm-schemas", json={
        "code": "isch", "name": "IS",
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
        "nodeTypeId": ntid, "groupName": "G", "nodeCount": 1,
    })
    gid = r.json()["data"]["id"]
    client.post(f"/admin/api/node-groups/{gid}/alarms", json={"attrs": {"severity": "critical"}})
    client.post(f"/admin/api/node-groups/{gid}/alarms", json={"attrs": {"severity": "major"}})

    r = client.post("/admin/api/sql/execute", json={
        "topologyId": tid,
        "sql":"SELECT alarm_index, severity FROM alarms ORDER BY alarm_index",
    })
    rows = r.json()["data"]["items"]
    assert [(r["alarm_index"], r["severity"]) for r in rows] == [(1, "critical"), (2, "major")]
