"""Integration tests for Phase 5: API configs and session management."""

import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app, setup_services, setup_logging
from app.core.service_registry import registry


@pytest.fixture(autouse=True)
async def setup_app():
    setup_logging()
    setup_services()
    await registry.start_all()
    # Clean api_configs table for test isolation
    dal = registry.get("dal")
    await dal.persist.execute("DELETE FROM api_configs")
    await dal.persist.commit()
    yield
    await registry.stop_all()
    registry._services.clear()
    registry._order.clear()


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ==== API Configs ====

async def test_api_config_crud(client: AsyncClient):
    # Create
    r = await client.post("/api/api-configs", json={
        "name": "设备查询",
        "method": "GET",
        "path": "/rest/v1/devices",
        "dataSource": {"type": "sql", "sql": "SELECT * FROM devices"},
    })
    assert r.json()["code"] == 0
    cfg = r.json()["data"]
    cfg_id = cfg["id"]
    assert cfg["name"] == "设备查询"
    assert cfg["method"] == "GET"

    # List
    r = await client.get("/api/api-configs")
    assert r.json()["data"]["total"] >= 1

    # Get
    r = await client.get(f"/api/api-configs/{cfg_id}")
    assert r.json()["data"]["name"] == "设备查询"

    # Update
    r = await client.put(f"/api/api-configs/{cfg_id}", json={
        "name": "设备查询-更新",
        "method": "GET",
        "path": "/rest/v1/devices",
    })
    assert r.json()["data"]["name"] == "设备查询-更新"

    # Toggle enabled
    r = await client.put(f"/api/api-configs/{cfg_id}/enabled", json={"enabled": False})
    assert r.json()["data"]["enabled"] == 0

    # Delete
    r = await client.delete(f"/api/api-configs/{cfg_id}")
    assert r.json()["code"] == 0


async def test_api_config_route_uniqueness(client: AsyncClient):
    # Create first
    await client.post("/api/api-configs", json={
        "name": "Test1", "method": "GET", "path": "/test/unique",
        "dataSource": {"type": "sql", "sql": "SELECT 1"},
    })
    # Duplicate should fail
    r = await client.post("/api/api-configs", json={
        "name": "Test2", "method": "GET", "path": "/test/unique",
        "dataSource": {"type": "sql", "sql": "SELECT 1"},
    })
    assert r.json()["code"] != 0


async def test_api_config_groups(client: AsyncClient):
    await client.post("/api/api-configs", json={
        "name": "G1", "method": "GET", "path": "/g/1",
        "group": "GroupA",
        "dataSource": {"type": "sql", "sql": "SELECT 1"},
    })
    await client.post("/api/api-configs", json={
        "name": "G2", "method": "GET", "path": "/g/2",
        "group": "GroupA",
        "dataSource": {"type": "sql", "sql": "SELECT 1"},
    })
    r = await client.get("/api/api-configs/groups")
    groups = r.json()["data"]
    group_a = [g for g in groups if g["name"] == "GroupA"]
    assert len(group_a) == 1
    assert group_a[0]["count"] == 2


async def test_default_sql(client: AsyncClient):
    for collection in ["devices", "ports", "links", "alarms", "metrics"]:
        r = await client.get(f"/api/api-configs/default-sql/{collection}")
        data = r.json()["data"]
        assert data["collection"] == collection
        assert "SELECT" in data["sql"]


async def test_api_config_import_export(client: AsyncClient):
    # Create config
    await client.post("/api/api-configs", json={
        "name": "ExportTest", "method": "POST", "path": "/export/test",
        "dataSource": {"type": "static", "body": {"ok": True}},
    })

    # Export
    r = await client.get("/api/api-configs/export")
    assert r.status_code == 200
    configs = r.json()
    assert len(configs) >= 1

    # Import (skip existing)
    r = await client.post("/api/api-configs/import", json={"configs": configs, "overwrite": False})
    assert r.json()["data"]["skipped"] >= 1


# ==== Sessions ====

async def test_session_config(client: AsyncClient):
    # Get config
    r = await client.get("/api/sessions/config")
    assert r.json()["code"] == 0

    # Update config
    r = await client.put("/api/sessions/config", json={
        "tokenExpiry": 3600,
        "credentials": [{"username": "admin", "password": "admin123"}],
    })
    assert r.json()["data"]["tokenExpiry"] == 3600


async def test_session_token_lifecycle(client: AsyncClient):
    # Set up credentials
    await client.put("/api/sessions/config", json={
        "tokenExpiry": 3600,
        "credentials": [{"username": "test", "password": "test123"}],
    })

    # Issue token by authenticating through session manager directly
    from app.services.session_manager import SessionManager
    mgr: SessionManager = registry.get("session_manager")
    # Reload config
    await mgr.start()
    token = mgr.authenticate("test", "test123")
    assert token is not None
    assert token.startswith("x-")

    # Validate token
    assert mgr.validate_token(token) is True

    # List tokens
    r = await client.get("/api/sessions")
    assert r.json()["data"]["total"] >= 1

    # Invalid credentials
    bad_token = mgr.authenticate("test", "wrong")
    assert bad_token is None

    # Invalidate token
    r = await client.delete(f"/api/sessions/{token}")
    assert r.json()["code"] == 0
    assert mgr.validate_token(token) is False

    # Clear all
    token2 = mgr.authenticate("test", "test123")
    r = await client.delete("/api/sessions")
    assert r.json()["code"] == 0
    assert mgr.validate_token(token2) is False
