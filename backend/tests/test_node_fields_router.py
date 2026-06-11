import sqlite3
from app.core.config import settings as _s


def _add_field(node_type_id: str, field_key: str):
    """Direct SQL insert to add a custom field to a node_type (bypasses fields endpoint to avoid path coupling)."""
    with sqlite3.connect(str(_s.db_path), isolation_level=None) as c:
        c.execute(
            "INSERT INTO node_type_fields (node_type_id, field_key, field_label, field_type, max_length) "
            "VALUES (?, ?, ?, 'text', 50)",
            (node_type_id, field_key, field_key.upper()),
        )


def test_node_fields_available_returns_system_fields(client):
    r = client.get("/admin/api/node-fields/available")
    assert r.status_code == 200
    data = r.json()["data"]
    assert set(data["systemFields"]) == {"name", "dn", "id", "status", "group_id"}


def test_node_fields_available_returns_custom_fields(client):
    ntid = client.post("/admin/api/node-types", json={"code": "sw", "name": "SW", "category": "switch"}).json()["data"]["id"]
    _add_field(ntid, "ip")
    _add_field(ntid, "manufacturer")

    r = client.get("/admin/api/node-fields/available")
    data = r.json()["data"]
    assert "ip" in data["customFields"]
    assert "manufacturer" in data["customFields"]


def test_node_fields_available_dedupes_custom(client):
    nt1 = client.post("/admin/api/node-types", json={"code": "sw", "name": "SW", "category": "switch"}).json()["data"]["id"]
    nt2 = client.post("/admin/api/node-types", json={"code": "rt", "name": "RT", "category": "router"}).json()["data"]["id"]
    _add_field(nt1, "ip")
    _add_field(nt2, "ip")

    r = client.get("/admin/api/node-fields/available")
    customs = r.json()["data"]["customFields"]
    assert customs.count("ip") == 1


def test_node_fields_available_system_fields_always_present(client):
    # Seed data populates node_type_fields; we only verify system fields are correct.
    r = client.get("/admin/api/node-fields/available")
    assert r.status_code == 200
    data = r.json()["data"]
    assert set(data["systemFields"]) == {"name", "dn", "id", "status", "group_id"}
    assert len(data["systemFields"]) == 5
    # customFields comes from node_type_fields — seed populates some; list may be non-empty
    assert isinstance(data["customFields"], list)
