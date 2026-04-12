"""Integration tests for topology management API."""

import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app, setup_services, setup_logging
from app.core.service_registry import registry


@pytest.fixture(autouse=True)
async def setup_app():
    """Setup services before each test and cleanup after."""
    setup_logging()
    setup_services()
    await registry.start_all()
    yield
    await registry.stop_all()
    registry._services.clear()
    registry._order.clear()


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_health(client: AsyncClient):
    r = await client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


async def test_topology_crud(client: AsyncClient):
    # Create
    r = await client.post("/api/topologies", json={"name": "Test Topo", "description": "desc"})
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == 0
    topo_id = body["data"]["id"]
    assert topo_id.startswith("topo_")

    # List
    r = await client.get("/api/topologies")
    assert r.json()["data"]["total"] >= 1

    # Get
    r = await client.get(f"/api/topologies/{topo_id}")
    assert r.json()["data"]["name"] == "Test Topo"

    # Update
    r = await client.put(f"/api/topologies/{topo_id}", json={"name": "Updated"})
    assert r.json()["code"] == 0

    # Load
    r = await client.post(f"/api/topologies/{topo_id}/load")
    assert r.json()["code"] == 0

    # Delete
    r = await client.delete(f"/api/topologies/{topo_id}")
    assert r.json()["code"] == 0


async def test_device_crud(client: AsyncClient):
    # Create topology and load it
    r = await client.post("/api/topologies", json={"name": "DevTopo"})
    topo_id = r.json()["data"]["id"]
    await client.post(f"/api/topologies/{topo_id}/load")

    # Create device
    r = await client.post(f"/api/topologies/{topo_id}/devices", json={
        "name": "Router1", "type": "router",
        "portConfig": {"count": 4, "type": "GE", "speed": "1Gbps"}
    })
    assert r.json()["code"] == 0
    dev = r.json()["data"]
    dev_id = dev["id"]
    assert dev["name"] == "Router1"

    # List devices
    r = await client.get(f"/api/topologies/{topo_id}/devices")
    assert r.json()["data"]["total"] == 1

    # Get device
    r = await client.get(f"/api/topologies/{topo_id}/devices/{dev_id}")
    assert r.json()["data"]["id"] == dev_id

    # Update device
    r = await client.put(f"/api/topologies/{topo_id}/devices/{dev_id}", json={"name": "Router1-Updated"})
    assert r.json()["code"] == 0
    assert r.json()["data"]["name"] == "Router1-Updated"

    # Delete
    r = await client.delete(f"/api/topologies/{topo_id}/devices/{dev_id}")
    assert r.json()["code"] == 0


async def test_ports(client: AsyncClient):
    r = await client.post("/api/topologies", json={"name": "PortTopo"})
    topo_id = r.json()["data"]["id"]
    await client.post(f"/api/topologies/{topo_id}/load")

    # Create device with 2 ports
    r = await client.post(f"/api/topologies/{topo_id}/devices", json={
        "name": "SW1", "type": "switch",
        "portConfig": {"count": 2, "type": "GE", "speed": "1Gbps"}
    })
    dev_id = r.json()["data"]["id"]

    # List ports
    r = await client.get(f"/api/topologies/{topo_id}/devices/{dev_id}/ports")
    assert r.json()["data"]["total"] == 2

    # Create additional port
    r = await client.post(f"/api/topologies/{topo_id}/devices/{dev_id}/ports", json={
        "name": "GE0/0/3", "type": "GE", "speed": "1Gbps"
    })
    assert r.json()["code"] == 0
    port_id = r.json()["data"]["id"]

    # Update port
    r = await client.put(f"/api/topologies/{topo_id}/ports/{port_id}", json={"name": "GE0/0/99"})
    assert r.json()["data"]["name"] == "GE0/0/99"

    # Delete port
    r = await client.delete(f"/api/topologies/{topo_id}/ports/{port_id}")
    assert r.json()["code"] == 0


async def test_links(client: AsyncClient):
    r = await client.post("/api/topologies", json={"name": "LinkTopo"})
    topo_id = r.json()["data"]["id"]
    await client.post(f"/api/topologies/{topo_id}/load")

    # Create 2 devices with ports
    r = await client.post(f"/api/topologies/{topo_id}/devices", json={
        "name": "Dev1", "type": "router",
        "portConfig": {"count": 2, "type": "GE", "speed": "1Gbps"}
    })
    dev1_id = r.json()["data"]["id"]

    r = await client.post(f"/api/topologies/{topo_id}/devices", json={
        "name": "Dev2", "type": "router",
        "portConfig": {"count": 2, "type": "GE", "speed": "1Gbps"}
    })
    dev2_id = r.json()["data"]["id"]

    # Get ports for both devices
    r1 = await client.get(f"/api/topologies/{topo_id}/devices/{dev1_id}/ports")
    r2 = await client.get(f"/api/topologies/{topo_id}/devices/{dev2_id}/ports")
    port1_id = r1.json()["data"]["items"][0]["id"]
    port2_id = r2.json()["data"]["items"][0]["id"]

    # Create link
    r = await client.post(f"/api/topologies/{topo_id}/links", json={
        "sourceDeviceId": dev1_id, "sourcePortId": port1_id,
        "targetDeviceId": dev2_id, "targetPortId": port2_id,
    })
    assert r.json()["code"] == 0
    link_id = r.json()["data"]["id"]

    # Verify ports are now connected
    r = await client.get(f"/api/topologies/{topo_id}/devices/{dev1_id}/ports")
    connected = [p for p in r.json()["data"]["items"] if p["id"] == port1_id]
    assert connected[0]["status"] == "connected"

    # List links
    r = await client.get(f"/api/topologies/{topo_id}/links")
    assert r.json()["data"]["total"] == 1

    # Delete link
    r = await client.delete(f"/api/topologies/{topo_id}/links/{link_id}")
    assert r.json()["code"] == 0


async def test_save_load_versions(client: AsyncClient):
    r = await client.post("/api/topologies", json={"name": "VerTopo"})
    topo_id = r.json()["data"]["id"]
    await client.post(f"/api/topologies/{topo_id}/load")

    # Add a device
    await client.post(f"/api/topologies/{topo_id}/devices", json={
        "name": "D1", "type": "switch"
    })

    # Save
    r = await client.post(f"/api/topologies/{topo_id}/save")
    assert r.json()["code"] == 0

    # List versions
    r = await client.get(f"/api/topologies/{topo_id}/versions")
    assert r.json()["data"]["total"] >= 1


async def test_validate(client: AsyncClient):
    r = await client.post("/api/topologies", json={"name": "ValTopo"})
    topo_id = r.json()["data"]["id"]
    await client.post(f"/api/topologies/{topo_id}/load")

    r = await client.post(f"/api/topologies/{topo_id}/validate")
    assert r.json()["code"] == 0
    assert "issues" in r.json()["data"]


async def test_layout(client: AsyncClient):
    r = await client.post("/api/topologies", json={"name": "LayTopo"})
    topo_id = r.json()["data"]["id"]
    await client.post(f"/api/topologies/{topo_id}/load")

    # Create devices for layout
    await client.post(f"/api/topologies/{topo_id}/devices", json={"name": "L1", "type": "switch"})
    await client.post(f"/api/topologies/{topo_id}/devices", json={"name": "L2", "type": "switch"})

    r = await client.post(f"/api/topologies/{topo_id}/layout", json={
        "algorithm": "grid", "options": {}
    })
    assert r.json()["code"] == 0
    assert "nodePositions" in r.json()["data"]


async def test_alarms(client: AsyncClient):
    r = await client.post("/api/topologies", json={"name": "AlmTopo"})
    topo_id = r.json()["data"]["id"]
    await client.post(f"/api/topologies/{topo_id}/load")

    r = await client.post(f"/api/topologies/{topo_id}/devices", json={"name": "AD1", "type": "router"})
    dev_id = r.json()["data"]["id"]

    # Create alarm
    r = await client.post(f"/api/topologies/{topo_id}/alarms", json={
        "deviceId": dev_id, "level": "critical", "type": "linkDown", "content": "port down"
    })
    assert r.json()["code"] == 0
    alarm_id = r.json()["data"]["id"]

    # List alarms
    r = await client.get(f"/api/topologies/{topo_id}/alarms")
    assert r.json()["data"]["total"] == 1

    # Clear alarm
    r = await client.post(f"/api/topologies/{topo_id}/alarms/{alarm_id}/clear")
    assert r.json()["data"]["status"] == "cleared"

    # Delete alarm
    r = await client.delete(f"/api/topologies/{topo_id}/alarms/{alarm_id}")
    assert r.json()["code"] == 0


async def test_metrics(client: AsyncClient):
    r = await client.post("/api/topologies", json={"name": "MetTopo"})
    topo_id = r.json()["data"]["id"]
    await client.post(f"/api/topologies/{topo_id}/load")

    r = await client.post(f"/api/topologies/{topo_id}/devices", json={"name": "MD1", "type": "router"})
    dev_id = r.json()["data"]["id"]

    # Create metric
    r = await client.post(f"/api/topologies/{topo_id}/metrics", json={
        "deviceId": dev_id, "name": "cpu_usage", "value": "75.5", "unit": "%"
    })
    assert r.json()["code"] == 0
    metric_id = r.json()["data"]["id"]

    # List metrics
    r = await client.get(f"/api/topologies/{topo_id}/metrics")
    assert r.json()["data"]["total"] == 1

    # Delete metric
    r = await client.delete(f"/api/topologies/{topo_id}/metrics/{metric_id}")
    assert r.json()["code"] == 0


async def test_device_types(client: AsyncClient):
    # List built-in device types
    r = await client.get("/api/device-types")
    assert r.json()["code"] == 0
    # Should have preset types
    items = r.json()["data"]["items"]
    assert len(items) > 0

    # Create custom type
    r = await client.post("/api/device-types", json={"name": "MyDevice", "icon": "custom"})
    assert r.json()["code"] == 0
    type_id = r.json()["data"]["id"]

    # Update
    r = await client.put(f"/api/device-types/{type_id}", json={"icon": "updated"})
    assert r.json()["code"] == 0

    # Delete
    r = await client.delete(f"/api/device-types/{type_id}")
    assert r.json()["code"] == 0
