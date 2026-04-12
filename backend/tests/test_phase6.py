"""Integration tests for Phase 6: HTTP Mock Server."""

import json
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app, setup_services, setup_logging
from app.core.service_registry import registry


@pytest.fixture(autouse=True)
async def setup_app():
    setup_logging()
    setup_services()
    await registry.start_all()
    # Clean api_configs and request_logs for test isolation
    dal = registry.get("dal")
    await dal.persist.execute("DELETE FROM api_configs")
    await dal.persist.execute("DELETE FROM request_logs")
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


# ==== Protocol Management ====

async def test_protocol_list(client: AsyncClient):
    r = await client.get("/api/protocols")
    assert r.json()["code"] == 0
    protos = r.json()["data"]
    assert len(protos) >= 1
    names = [p["name"] for p in protos]
    assert "http-mock" in names


async def test_protocol_start_stop(client: AsyncClient):
    # Start
    r = await client.post("/api/protocols/http-mock/start")
    assert r.json()["code"] == 0
    assert r.json()["data"]["status"] == "running"

    # Health check
    r = await client.get("/api/protocols/http-mock/health")
    assert r.json()["data"]["healthy"] is True

    # Stop
    r = await client.post("/api/protocols/http-mock/stop")
    assert r.json()["code"] == 0
    assert r.json()["data"]["status"] == "stopped"


async def test_mock_routes(client: AsyncClient):
    # Create an API config
    await client.post("/api/api-configs", json={
        "name": "TestRoute", "method": "GET", "path": "/test/route",
        "enabled": True,
        "dataSource": {"type": "static", "body": {"hello": "world"}},
    })

    # Start mock server
    r = await client.post("/api/protocols/http-mock/start")
    assert r.json()["code"] == 0

    # Check routes
    r = await client.get("/api/protocols/http-mock/routes")
    routes = r.json()["data"]["items"]
    assert any(rt["path"] == "/test/route" for rt in routes)

    # Stop
    await client.post("/api/protocols/http-mock/stop")


# ==== QueryPipeline ====

async def test_query_pipeline_static(client: AsyncClient):
    """Test static mode data source."""
    await client.post("/api/api-configs", json={
        "name": "StaticTest", "method": "GET", "path": "/test/static",
        "dataSource": {
            "type": "static",
            "body": {"id": "{{uuid}}", "time": "{{timestamp}}", "date": "{{date}}", "rand": "{{random}}"},
        },
    })

    # Test via config test endpoint
    r = await client.get("/api/api-configs")
    cfg_id = r.json()["data"]["items"][0]["id"]

    r = await client.post(f"/api/api-configs/{cfg_id}/test", json={"params": {}})
    data = r.json()["data"]
    rendered = data.get("renderedResponse", {})
    assert "id" in rendered
    assert len(rendered["id"]) > 0  # UUID should be non-empty
    assert "time" in rendered
    assert "date" in rendered


async def test_query_pipeline_sql(client: AsyncClient):
    """Test SQL mode data source with in-memory database."""
    # First load a topology so memory store has data
    topo_r = await client.post("/api/topologies", json={"name": "SQLTest"})
    topo_id = topo_r.json()["data"]["id"]
    await client.post(f"/api/topologies/{topo_id}/load")

    # Create some devices
    await client.post(f"/api/topologies/{topo_id}/devices", json={
        "name": "SW1", "type": "switch",
        "portConfig": {"count": 2, "type": "GE", "speed": "1Gbps"},
    })
    await client.post(f"/api/topologies/{topo_id}/devices", json={
        "name": "SW2", "type": "switch",
    })
    await client.post(f"/api/topologies/{topo_id}/devices", json={
        "name": "RT1", "type": "router",
    })

    # Create SQL API config
    await client.post("/api/api-configs", json={
        "name": "DeviceQuery", "method": "GET", "path": "/api/devices",
        "dataSource": {
            "type": "sql",
            "sql": "SELECT * FROM devices WHERE (:type IS NULL OR type = :type)",
        },
        "query": {
            "params": [{"param": "type", "sqlParam": ":type", "default": None}],
            "pagination": {"enabled": True, "pageNoParam": "pageNo", "pageSizeParam": "pageSize", "defaultPageSize": 10},
        },
        "response": {
            "contentType": "application/json",
            "template": {"code": 0, "data": "{{items}}", "total": "{{total}}"},
        },
    })

    r = await client.get("/api/api-configs")
    cfg_id = [c for c in r.json()["data"]["items"] if c["name"] == "DeviceQuery"][0]["id"]

    # Test with no filter
    r = await client.post(f"/api/api-configs/{cfg_id}/test", json={"params": {}})
    data = r.json()["data"]
    qr = data.get("queryResult", {})
    assert qr.get("total", 0) == 3

    # Test with type filter
    r = await client.post(f"/api/api-configs/{cfg_id}/test", json={"params": {"type": "switch"}})
    data = r.json()["data"]
    qr = data.get("queryResult", {})
    assert qr.get("total", 0) == 2


# ==== ResponseRenderer ====

async def test_response_renderer(client: AsyncClient):
    """Test template rendering with placeholders."""
    # Setup topology with data
    topo_r = await client.post("/api/topologies", json={"name": "RenderTest"})
    topo_id = topo_r.json()["data"]["id"]
    await client.post(f"/api/topologies/{topo_id}/load")
    await client.post(f"/api/topologies/{topo_id}/devices", json={"name": "D1", "type": "router"})

    # Create config with template
    await client.post("/api/api-configs", json={
        "name": "RenderedQuery", "method": "GET", "path": "/api/rendered",
        "dataSource": {"type": "sql", "sql": "SELECT * FROM devices"},
        "query": {
            "params": [],
            "pagination": {"enabled": True, "pageNoParam": "pageNo", "pageSizeParam": "pageSize", "defaultPageSize": 100},
        },
        "response": {
            "contentType": "application/json",
            "template": {"code": 0, "data": "{{items}}", "total": "{{total}}", "pageNo": "{{pageNo}}", "pageSize": "{{pageSize}}"},
        },
    })

    r = await client.get("/api/api-configs")
    cfg_id = [c for c in r.json()["data"]["items"] if c["name"] == "RenderedQuery"][0]["id"]

    r = await client.post(f"/api/api-configs/{cfg_id}/test", json={"params": {}})
    data = r.json()["data"]
    # The renderedResponse should be in the pipeline result
    assert "queryResult" in data
    assert data["queryResult"]["total"] >= 1


# ==== Auth Middleware ====

async def test_auth_middleware(client: AsyncClient):
    """Test auth check logic directly via SessionManager."""
    from app.services.session_manager import SessionManager
    from app.protocols.http_mock.middleware import AuthMiddleware

    mgr: SessionManager = registry.get("session_manager")
    await mgr.update_config({
        "tokenExpiry": 3600,
        "credentials": [{"username": "admin", "password": "pass123"}],
    })
    await mgr.start()

    auth = AuthMiddleware(mgr)

    # No auth required
    ok, code, msg = auth.check({"auth": '{"type":"none"}'}, {})
    assert ok is True

    # xtoken: missing
    ok, code, msg = auth.check({"auth": '{"type":"xtoken","headerName":"X-Auth-Token"}'}, {})
    assert ok is False
    assert code == 401

    # xtoken: valid
    token = mgr.authenticate("admin", "pass123")
    ok, code, msg = auth.check(
        {"auth": '{"type":"xtoken","headerName":"X-Auth-Token"}'},
        {"X-Auth-Token": token},
    )
    assert ok is True

    # xtoken: invalid
    ok, code, msg = auth.check(
        {"auth": '{"type":"xtoken","headerName":"X-Auth-Token"}'},
        {"X-Auth-Token": "invalid-token"},
    )
    assert ok is False


# ==== FaultInjector ====

async def test_fault_injector():
    from app.protocols.http_mock.middleware import FaultInjector
    injector = FaultInjector()

    # No fault
    err, code = await injector.apply({"fault": '{"delay":0,"errorRate":0,"errorStatus":500}'})
    assert err is False

    # 100% error rate
    err, code = await injector.apply({"fault": '{"delay":0,"errorRate":1.0,"errorStatus":503}'})
    assert err is True
    assert code == 503


# ==== RequestLogger ====

async def test_request_logger(client: AsyncClient):
    """Test that request logging works."""
    from app.protocols.http_mock.server import HttpMockServer
    mock: HttpMockServer = registry.get("protocol_manager").get_plugin("http-mock")

    await mock.request_logger.log(
        method="GET", path="/test/log", status_code=200, duration=42,
    )

    r = await client.get("/api/protocols/http-mock/logs")
    logs = r.json()["data"]
    assert logs["total"] >= 1
    assert any(l["path"] == "/test/log" for l in logs["items"])

    # Clear
    r = await client.delete("/api/protocols/http-mock/logs")
    assert r.json()["data"]["deleted"] >= 1


# ==== Default SQL ====

async def test_default_sql_has_joins(client: AsyncClient):
    """Verify links default SQL contains JOINs."""
    r = await client.get("/api/api-configs/default-sql/links")
    sql = r.json()["data"]["sql"]
    assert "JOIN" in sql
    assert "sourceDeviceName" in sql
