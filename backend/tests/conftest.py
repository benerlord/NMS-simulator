import os
import sqlite3
from pathlib import Path

import pytest

# 在导入 app 之前设置 DB_PATH，避免污染开发库
os.environ.setdefault("APP_PORT", "0")


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """每个测试一个独立的临时 SQLite 文件。"""
    return tmp_path / "test.db"


@pytest.fixture
def conn(db_path: Path):
    """已跑完 migrations 的连接。"""
    from app.db.migrations import run_migrations

    c = sqlite3.connect(str(db_path), isolation_level=None)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    run_migrations(c)
    yield c
    c.close()


@pytest.fixture
def client(monkeypatch, db_path: Path):
    """FastAPI TestClient with isolated DB。

    使用 context manager 触发 lifespan（会绑定 mock_registry / 启动 InstanceRunner）。
    """
    from app.core.config import settings as app_settings

    monkeypatch.setattr(app_settings, "db_path", db_path)

    from app.db.connection import init_db
    from app.main import app
    from fastapi.testclient import TestClient

    init_db()
    with TestClient(app) as c:
        yield c


@pytest.fixture
def seed_topology(conn):
    """种入一个最小拓扑 + 一个节点类型，返回 (topology_id, node_type_id)。"""
    conn.execute(
        "INSERT INTO topologies (id, name) VALUES ('topo_test', 'TestTopo')"
    )
    conn.execute(
        "INSERT INTO node_types (id, code, name, category) "
        "VALUES ('ntype_test', 'test_dev', '测试设备', 'switch')"
    )
    return ("topo_test", "ntype_test")
