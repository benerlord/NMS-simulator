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
    alarms = next(v for v in views["generic"] if v["name"] == "alarms")
    sql = f"WITH alarms AS ({alarms['sql']}) SELECT * FROM alarms"
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
