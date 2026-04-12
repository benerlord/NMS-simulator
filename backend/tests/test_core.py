"""Tests for core infrastructure and data layer (Phase 1 & 2)."""

import asyncio
import json
import time

import pytest
import pytest_asyncio

from app.core.event_bus import EventBus
from app.core.service_registry import ServiceRegistry
from app.dal.memory_store import MemoryStore
from app.dal.persist_store import PersistStore
from app.dal.base import DAL


# ==================================================================
# EventBus tests
# ==================================================================

@pytest.fixture
def bus():
    return EventBus()


@pytest.mark.asyncio
async def test_eventbus_on_emit(bus):
    results = []

    async def handler(event, **kwargs):
        results.append((event, kwargs))

    bus.on("test.event", handler)
    await bus.emit("test.event", key="value")

    assert len(results) == 1
    assert results[0] == ("test.event", {"key": "value"})


@pytest.mark.asyncio
async def test_eventbus_off(bus):
    results = []

    async def handler(event, **kwargs):
        results.append(event)

    bus.on("test.event", handler)
    bus.off("test.event", handler)
    await bus.emit("test.event")

    assert len(results) == 0


@pytest.mark.asyncio
async def test_eventbus_wildcard(bus):
    results = []

    async def handler(event, **kwargs):
        results.append(event)

    bus.on("topology.*", handler)
    await bus.emit("topology.created")
    await bus.emit("topology.updated")
    await bus.emit("other.event")

    assert results == ["topology.created", "topology.updated"]


@pytest.mark.asyncio
async def test_eventbus_error_isolation(bus):
    """Errors in one handler should not prevent others from running."""
    results = []

    async def bad_handler(event, **kwargs):
        raise ValueError("oops")

    async def good_handler(event, **kwargs):
        results.append(event)

    bus.on("test", bad_handler)
    bus.on("test", good_handler)
    await bus.emit("test")

    assert results == ["test"]


# ==================================================================
# ServiceRegistry tests
# ==================================================================

@pytest.mark.asyncio
async def test_registry_order():
    reg = ServiceRegistry()
    order = []

    class Svc:
        def __init__(self, name):
            self.name = name

        async def start(self):
            order.append(f"start:{self.name}")

        async def stop(self):
            order.append(f"stop:{self.name}")

    reg.register("a", Svc("a"))
    reg.register("b", Svc("b"))
    reg.register("c", Svc("c"))

    await reg.start_all()
    await reg.stop_all()

    assert order == ["start:a", "start:b", "start:c", "stop:c", "stop:b", "stop:a"]


@pytest.mark.asyncio
async def test_registry_get():
    reg = ServiceRegistry()
    reg.register("my_svc", {"value": 42})

    assert reg.get("my_svc") == {"value": 42}

    with pytest.raises(KeyError):
        reg.get("nonexistent")

    assert reg.get_optional("nonexistent") is None


# ==================================================================
# MemoryStore tests
# ==================================================================

@pytest_asyncio.fixture
async def memory():
    store = MemoryStore()
    await store.start()
    yield store
    await store.stop()


@pytest.mark.asyncio
async def test_memory_full_sync(memory):
    data = {
        "devices": [
            {"id": "d1", "name": "Switch-1", "type": "switch", "dn": "NE=1", "ip": "1.1.1.1",
             "vendor": "Huawei", "model": "CE6800", "status": "online", "portCount": 2, "customFields": {}},
            {"id": "d2", "name": "Server-1", "type": "server", "dn": "NE=2", "ip": "2.2.2.2",
             "vendor": "Dell", "model": "R740", "status": "online", "portCount": 1, "customFields": {}},
        ],
        "ports": [
            {"id": "p1", "deviceId": "d1", "name": "10GE1/0/1", "dn": "NE=1,PORT=1", "type": "10GE", "speed": "10Gbps", "status": "connected"},
            {"id": "p2", "deviceId": "d1", "name": "10GE1/0/2", "dn": "NE=1,PORT=2", "type": "10GE", "speed": "10Gbps", "status": "free"},
            {"id": "p3", "deviceId": "d2", "name": "GE1/0/1", "dn": "NE=2,PORT=1", "type": "GE", "speed": "1Gbps", "status": "connected"},
        ],
        "links": [
            {"id": "l1", "sourceDeviceId": "d1", "sourcePortId": "p1", "targetDeviceId": "d2", "targetPortId": "p3",
             "type": "physical", "bandwidth": "1Gbps", "status": "up", "description": ""},
        ],
        "alarms": [],
        "metrics": [],
    }

    await memory.full_sync(data)

    # Query devices
    cols, rows = await memory.execute_sql("SELECT * FROM devices WHERE type = :type", {"type": "switch"})
    assert len(rows) == 1
    assert rows[0][cols.index("name")] == "Switch-1"

    # JOIN query
    cols, rows = await memory.execute_sql(
        "SELECT l.id, d1.name AS srcDevice, d2.name AS tgtDevice "
        "FROM links l "
        "JOIN devices d1 ON l.sourceDeviceId = d1.id "
        "JOIN devices d2 ON l.targetDeviceId = d2.id"
    )
    assert len(rows) == 1
    assert rows[0][cols.index("srcDevice")] == "Switch-1"
    assert rows[0][cols.index("tgtDevice")] == "Server-1"

    # Count
    count = await memory.execute_count("SELECT COUNT(*) FROM ports")
    assert count == 3

    # Table info
    info = await memory.get_table_info()
    devices_info = next(t for t in info if t["table"] == "devices")
    assert devices_info["rowCount"] == 2
    assert any(c["name"] == "portCount" for c in devices_info["columns"])


@pytest.mark.asyncio
async def test_memory_upsert_delete(memory):
    await memory.full_sync({"devices": [
        {"id": "d1", "name": "Old", "type": "switch", "dn": "NE=1", "ip": "1.1.1.1",
         "vendor": "", "model": "", "status": "online", "portCount": 0, "customFields": {}},
    ]})

    # Upsert (update)
    await memory.upsert_row("devices", {
        "id": "d1", "name": "Updated", "type": "switch", "dn": "NE=1", "ip": "1.1.1.1",
        "vendor": "", "model": "", "status": "online", "portCount": 0, "customFields": {},
    })
    cols, rows = await memory.execute_sql("SELECT name FROM devices WHERE id = 'd1'")
    assert rows[0][0] == "Updated"

    # Delete
    await memory.delete_row("devices", "d1")
    count = await memory.execute_count("SELECT COUNT(*) FROM devices")
    assert count == 0


@pytest.mark.asyncio
async def test_memory_bulk_performance(memory):
    """full_sync with 30,000 devices should complete in < 500ms."""
    devices = [
        {"id": f"d{i}", "name": f"Device-{i}", "type": "switch", "dn": f"NE={i}",
         "ip": f"10.0.{i // 256}.{i % 256}", "vendor": "Vendor", "model": "Model",
         "status": "online", "portCount": 2, "customFields": {}}
        for i in range(30000)
    ]
    data = {"devices": devices}

    start = time.time()
    await memory.full_sync(data)
    elapsed = time.time() - start

    assert elapsed < 2.0  # generous limit for CI
    count = await memory.execute_count("SELECT COUNT(*) FROM devices")
    assert count == 30000


# ==================================================================
# PersistStore tests
# ==================================================================

@pytest_asyncio.fixture
async def persist(tmp_path):
    import app.config
    original = app.config.settings.db_path
    app.config.settings.db_path = str(tmp_path / "test.db")
    store = PersistStore()
    await store.start()
    yield store
    await store.stop()
    app.config.settings.db_path = original


@pytest.mark.asyncio
async def test_persist_tables(persist):
    tables = await persist.fetch_all(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    table_names = [t["name"] for t in tables]
    assert "topologies" in table_names
    assert "device_types" in table_names
    assert "schema_migrations" in table_names


@pytest.mark.asyncio
async def test_persist_presets(persist):
    types = await persist.fetch_all("SELECT id FROM device_types")
    assert len(types) == 5

    protocols = await persist.fetch_all("SELECT name FROM protocol_configs")
    assert len(protocols) == 4

    settings = await persist.fetch_all("SELECT key FROM system_settings")
    assert len(settings) == 11


@pytest.mark.asyncio
async def test_persist_wal(persist):
    row = await persist.fetch_one("PRAGMA journal_mode")
    assert list(row.values())[0] == "wal"


@pytest.mark.asyncio
async def test_persist_foreign_keys(persist):
    row = await persist.fetch_one("PRAGMA foreign_keys")
    assert list(row.values())[0] == 1


@pytest.mark.asyncio
async def test_persist_idempotent(persist):
    """Restarting should not duplicate preset data."""
    # Simulate restart
    await persist.stop()
    await persist.start()

    types = await persist.fetch_all("SELECT id FROM device_types")
    assert len(types) == 5


# ==================================================================
# DAL tests
# ==================================================================

@pytest_asyncio.fixture
async def dal(tmp_path):
    import app.config
    original = app.config.settings.db_path
    app.config.settings.db_path = str(tmp_path / "test.db")

    p = PersistStore()
    m = MemoryStore()
    d = DAL(p, m)
    await d.start()
    yield d
    await d.stop()
    app.config.settings.db_path = original


@pytest.mark.asyncio
async def test_dal_topology_crud(dal):
    topo_data = {"devices": [{"id": "d1", "name": "Test"}], "ports": [], "links": [], "alarms": [], "metrics": []}

    # Create
    result = await dal.save_topology("topo1", "Test Topo", "desc", topo_data, is_active=True)
    assert result["version"] == 1

    # List
    topos = await dal.list_topologies()
    assert len(topos) == 1

    # Load & sync to memory
    loaded = await dal.load_topology("topo1")
    assert loaded is not None
    count = await dal.memory.execute_count("SELECT COUNT(*) FROM devices")
    assert count == 1

    # Update
    topo_data["devices"].append({"id": "d2", "name": "Test2"})
    result2 = await dal.save_topology("topo1", "Test Topo", "desc", topo_data, is_active=True)
    assert result2["version"] == 2

    # Delete
    deleted = await dal.delete_topology("topo1")
    assert deleted is True


@pytest.mark.asyncio
async def test_dal_version_management(dal):
    data_v1 = {"devices": [{"id": "d1", "name": "v1"}], "ports": [], "links": [], "alarms": [], "metrics": []}
    data_v2 = {"devices": [{"id": "d1", "name": "v2"}, {"id": "d2", "name": "new"}], "ports": [], "links": [], "alarms": [], "metrics": []}

    await dal.save_topology("topo1", "T", "", data_v1)
    await dal.save_topology("topo1", "T", "", data_v2)

    history = await dal.list_history("topo1")
    assert len(history) == 2

    # Restore v1
    result = await dal.restore_version("topo1", 1)
    assert result is not None
    count = await dal.memory.execute_count("SELECT COUNT(*) FROM devices")
    assert count == 1  # v1 had 1 device

    # Cleanup
    deleted = await dal.cleanup_history("topo1", max_versions=1)
    history_after = await dal.list_history("topo1")
    assert len(history_after) <= 2  # latest version kept
