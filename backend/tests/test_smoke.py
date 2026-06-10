def test_pytest_runs():
    assert 1 + 1 == 2


def test_migrations_create_tables(conn):
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    names = {r["name"] for r in rows}
    assert "topologies" in names
    assert "nodes" in names
