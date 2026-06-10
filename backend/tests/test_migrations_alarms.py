import sqlite3

import pytest


def test_alarm_schemas_table_created(conn):
    """Test that all 4 new alarm tables are created."""
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name IN ('alarm_schemas','alarm_schema_fields','node_alarms','node_alarm_attrs')"
    ).fetchall()
    names = {r["name"] for r in rows}
    assert names == {"alarm_schemas", "alarm_schema_fields", "node_alarms", "node_alarm_attrs"}


def test_topologies_has_alarm_schema_id_column(conn):
    """Test that topologies has alarm_schema_id column."""
    rows = conn.execute("PRAGMA table_info(topologies)").fetchall()
    cols = {r["name"] for r in rows}
    assert "alarm_schema_id" in cols


def test_alarm_schema_fields_check_constraint(conn):
    """Test that field_type CHECK constraint works."""
    conn.execute(
        "INSERT INTO alarm_schemas (id, code, name) VALUES ('as_x', 'cx', 'X')"
    )
    # field_type non-valid value should be intercepted by CHECK
    raised = False
    try:
        conn.execute(
            "INSERT INTO alarm_schema_fields (alarm_schema_id, field_key, field_label, field_type) "
            "VALUES ('as_x', 'k1', 'L1', 'bogus')"
        )
    except sqlite3.IntegrityError:
        raised = True
    assert raised


def test_node_alarms_cascade_delete(conn):
    """Test that node_alarms are cascade deleted when node is deleted."""
    conn.execute("INSERT INTO topologies (id, name) VALUES ('t1', 'T1')")
    conn.execute(
        "INSERT INTO node_types (id, code, name, category) VALUES ('nt1', 'sw', 'sw', 'switch')"
    )
    conn.execute(
        "INSERT INTO nodes (id, topology_id, node_type_id, name) VALUES ('n1', 't1', 'nt1', 'n1')"
    )
    conn.execute(
        "INSERT INTO node_alarms (id, node_id, alarm_index) VALUES ('alm_1', 'n1', 1)"
    )
    conn.execute("DELETE FROM nodes WHERE id = 'n1'")
    cnt = conn.execute("SELECT COUNT(*) AS c FROM node_alarms").fetchone()["c"]
    assert cnt == 0
