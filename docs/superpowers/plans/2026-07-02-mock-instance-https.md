# 实例管理支持 HTTPS 协议 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 `mock_instances` 每个实例独立选择 HTTP / HTTPS 启动，复用主服务已有的自签证书兜底，前端展示可复制的完整访问 URL。

**Architecture:** 后端 5 文件改动（1 迁移列 + 1 Schema + 1 Runner + 1 子进程入口 + 1 CRUD 端点），前端 3 文件改动（类型 + Modal + 列表）。证书 bootstrap 放父进程避免并发竞态；子进程只接受 ssl 文件路径当哑角色；URL 后端拼好统一返回。

**Tech Stack:** FastAPI + Pydantic v2 CamelModel / SQLite 幂等 ALTER TABLE / uvicorn ssl_certfile+ssl_keyfile / cryptography 或 openssl / Vue 3.5 `<script setup>` + Ant Design Vue 4（`Radio.Group` + `Typography.Text copyable` + `Tag`）+ TypeScript。

**Spec：** `docs/superpowers/specs/2026-07-02-mock-instance-https-design.md`

---

## File Structure

| 文件 | Task | 责任 |
|------|------|------|
| `backend/app/db/migrations.py` | T1 | 幂等 ALTER TABLE 加 `ssl_enabled` 列 |
| `backend/app/admin/schemas/mock_instance.py` | T2 | Pydantic Schema 加 `ssl_enabled` / `url` 字段 |
| `backend/app/core/instance_runner.py` | T3 | `start/restart/sync_all/_check_and_restart` 加 `ssl_enabled` 参数；父进程 `ensure_cert` |
| `backend/app/mock/instance_app.py` | T3 | argparse +2 参数；uvicorn 按需传 ssl kwargs |
| `backend/app/admin/mock_instance.py` | T4 | CRUD 端点收/发 `ssl_enabled`；list 拼 `url` |
| `frontend/src/api/mockInstance.ts` | T5 | TS 类型加 `sslEnabled` / `url` |
| `frontend/src/components/mockInstance/MockInstanceModal.vue` | T6 | +Radio.Group 协议字段 + formState + payload |
| `frontend/src/views/MockInstancesView.vue` | T7 | +协议列 + 访问地址列（可复制） |

---

## 工作环境约定

- 主仓直接工作：`C:/Users/benerlord/Desktop/InterfaceTest`（不开 worktree）
- 分支：`main`
- 后端 smoke test：`cd /c/Users/benerlord/Desktop/InterfaceTest/backend && python -c "from app.main import app; print('OK')"` — 必须 exit 0，输出 `OK`
- 前端 smoke test：`cd /c/Users/benerlord/Desktop/InterfaceTest/frontend && npx tsc --noEmit` — 必须 exit 0
- 每个 Task 完成后 commit 一次；commit message 用 Conventional Commits 中文说明
- 每次 commit 尾部保留 Co-Authored-By

---

## Task 1: 数据库迁移 —— 加 ssl_enabled 列

**Files:**
- Modify: `backend/app/db/migrations.py`（在第 432 行既有 mock_instances.status 幂等 ALTER 后追加）

- [ ] **Step 1: 追加幂等迁移语句**

在 `backend/app/db/migrations.py` 第 432 行的 `pass` 之后、"请求日志：request_logs 新增 instance_id 列" 注释之前插入：

```python
    # 实例协议：mock_instances 新增 ssl_enabled 列
    try:
        conn.execute("ALTER TABLE mock_instances ADD COLUMN ssl_enabled INTEGER NOT NULL DEFAULT 0")
    except sqlite3.OperationalError:
        pass
```

- [ ] **Step 2: Smoke test —— 后端模块可正常 import**

```bash
cd /c/Users/benerlord/Desktop/InterfaceTest/backend && python -c "from app.db.migrations import run_migrations; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: 验证迁移实际生效**

启动后端一次让迁移执行：

```bash
cd /c/Users/benerlord/Desktop/InterfaceTest/backend && python -c "
from app.db.connection import init_db, connect
init_db()
with connect() as c:
    cols = [r['name'] for r in c.execute('PRAGMA table_info(mock_instances)').fetchall()]
    assert 'ssl_enabled' in cols, f'missing ssl_enabled, got {cols}'
    print('OK columns:', cols)
"
```

Expected: 输出包含 `ssl_enabled` 的列名列表，无 AssertionError

- [ ] **Step 4: 再运行一次确认幂等**

重复 Step 3 命令，不应抛任何异常。

- [ ] **Step 5: Commit**

```bash
git add backend/app/db/migrations.py
git commit -m "$(cat <<'EOF'
feat(db): mock_instances 新增 ssl_enabled 列

幂等 ALTER TABLE，默认 0（HTTP），既有实例迁移后行为零变化。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: 后端 Schema —— MockInstance 加 ssl_enabled / url 字段

**Files:**
- Modify: `backend/app/admin/schemas/mock_instance.py`

- [ ] **Step 1: 全量替换 schemas 文件内容**

用下面的内容覆盖 `backend/app/admin/schemas/mock_instance.py`：

```python
from typing import Optional

from pydantic import Field

from ._base import CamelModel


class MockInstanceCreate(CamelModel):
    name: str = Field(..., min_length=1, max_length=100)
    topology_id: str = Field(..., min_length=1)
    port: int = Field(..., ge=1, le=65535)
    description: Optional[str] = Field(default=None, max_length=200)
    enabled: bool = True
    ssl_enabled: bool = False


class MockInstanceUpdate(CamelModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    topology_id: Optional[str] = None
    port: Optional[int] = Field(default=None, ge=1, le=65535)
    description: Optional[str] = Field(default=None, max_length=200)
    enabled: Optional[bool] = None
    ssl_enabled: Optional[bool] = None


class MockInstanceItem(CamelModel):
    id: str
    name: str
    topology_id: str
    topology_name: str
    port: int
    description: Optional[str]
    enabled: bool
    ssl_enabled: bool
    url: str
    api_count: int = 0
    created_at: str
    updated_at: str


class RequestLogItem(CamelModel):
    id: int
    ts: str
    api_id: Optional[str] = None
    method: str
    path: str
    query: Optional[str] = None
    status_code: int
    duration_ms: int
    client_ip: Optional[str] = None
    error_message: Optional[str] = None
    instance_id: Optional[str] = None
```

- [ ] **Step 2: Smoke test —— Schema 可实例化**

```bash
cd /c/Users/benerlord/Desktop/InterfaceTest/backend && python -c "
from app.admin.schemas.mock_instance import MockInstanceCreate, MockInstanceItem
c = MockInstanceCreate(name='x', topologyId='t', port=8081, sslEnabled=True)
assert c.ssl_enabled is True, 'ssl_enabled not set'
i = MockInstanceItem(id='inst_x', name='x', topologyId='t', topologyName='T', port=8081, description=None, enabled=True, sslEnabled=True, url='https://localhost:8081', apiCount=0, createdAt='2026-07-02', updatedAt='2026-07-02')
assert i.model_dump(mode='json', by_alias=True)['sslEnabled'] is True
assert i.model_dump(mode='json', by_alias=True)['url'] == 'https://localhost:8081'
print('OK')
"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/admin/schemas/mock_instance.py
git commit -m "$(cat <<'EOF'
feat(schemas): MockInstance 加 sslEnabled 与 url 字段

CamelModel 自动驼峰互转，前后端零手工映射。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: 后端启动链改造 —— InstanceRunner + instance_app.py

**Files:**
- Modify: `backend/app/core/instance_runner.py`（全量替换）
- Modify: `backend/app/mock/instance_app.py`（uvicorn.run 分支）

- [ ] **Step 1: 全量替换 instance_runner.py**

用下面的内容覆盖 `backend/app/core/instance_runner.py`：

```python
import subprocess
import sys
import time
from threading import Lock, Thread

from app.core.cert_utils import ensure_cert
from app.core.config import settings
from app.db.connection import connect


def _update_status(inst_id: str, status: str) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE mock_instances SET status = ?, updated_at = datetime('now') WHERE id = ?",
            (status, inst_id),
        )


class InstanceRunner:
    def __init__(self):
        self._processes: dict[str, subprocess.Popen] = {}
        self._restart_counts: dict[str, list[float]] = {}
        self._lock = Lock()
        self._stop_monitor = False

    def sync_all(self):
        with connect() as conn:
            rows = conn.execute(
                "SELECT id, port, topology_id, ssl_enabled FROM mock_instances WHERE enabled = 1"
            ).fetchall()
        for r in rows:
            self.start_instance(r["id"], r["port"], r["topology_id"], bool(r["ssl_enabled"]))

    def start_instance(self, inst_id: str, port: int, topology_id: str, ssl_enabled: bool):
        with self._lock:
            if inst_id in self._processes:
                return
            _update_status(inst_id, "starting")
            ssl_args: list[str] = []
            if ssl_enabled:
                try:
                    cert, key = ensure_cert(settings.ssl_certfile, settings.ssl_keyfile)
                    ssl_args = ["--ssl-certfile", cert, "--ssl-keyfile", key]
                except Exception:
                    _update_status(inst_id, "error")
                    return
            try:
                kwargs = {}
                if sys.platform == 'win32':
                    kwargs['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
                proc = subprocess.Popen(
                    [
                        sys.executable, "-m", "app.mock.instance_app",
                        "--topology-id", topology_id,
                        "--port", str(port),
                        "--instance-id", inst_id,
                        *ssl_args,
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    **kwargs,
                )
                self._processes[inst_id] = proc
                _update_status(inst_id, "running")
            except Exception:
                _update_status(inst_id, "error")

    def stop_instance(self, inst_id: str):
        with self._lock:
            proc = self._processes.pop(inst_id, None)
            if proc:
                proc.kill()
                proc.wait(timeout=3)
            _update_status(inst_id, "stopped")

    def restart_instance(self, inst_id: str, port: int, topology_id: str, ssl_enabled: bool):
        self.stop_instance(inst_id)
        self.start_instance(inst_id, port, topology_id, ssl_enabled)

    def shutdown_all(self):
        with self._lock:
            for inst_id in list(self._processes.keys()):
                self.stop_instance(inst_id)
        self._stop_monitor = True

    def _check_and_restart(self):
        with self._lock:
            for inst_id, proc in list(self._processes.items()):
                if proc.poll() is None:
                    continue
                # 限流：1 分钟内超过 3 次重启则标记 error
                now = time.time()
                self._restart_counts.setdefault(inst_id, []).append(now)
                self._restart_counts[inst_id] = [
                    t for t in self._restart_counts[inst_id] if now - t < 60
                ]
                if len(self._restart_counts[inst_id]) > 3:
                    _update_status(inst_id, "error")
                    self._processes.pop(inst_id, None)
                    continue
                self._processes.pop(inst_id, None)
                # 从 DB 读取最新配置后重启
                with connect() as conn:
                    row = conn.execute(
                        "SELECT port, topology_id, ssl_enabled FROM mock_instances WHERE id = ? AND enabled = 1",
                        (inst_id,),
                    ).fetchone()
                if row:
                    self.start_instance(inst_id, row["port"], row["topology_id"], bool(row["ssl_enabled"]))

    def start_monitor(self):
        """后台线程：每 15 秒检查子进程健康状态"""
        def _loop():
            while not self._stop_monitor:
                time.sleep(15)
                self._check_and_restart()
        t = Thread(target=_loop, daemon=True)
        t.start()
```

注意：
- `_check_and_restart` 内部持有 `self._lock`，其中 `self.start_instance` 会再次尝试获取 `self._lock`；`Lock` 非可重入，会**死锁**
- 需要修正：`_check_and_restart` 里最后那次 `start_instance` 调用应在**释放锁之后**再调（既有实现就已经这样，但因为方法内部又拿锁会死锁）。仔细看现有代码——`self._check_and_restart` 里 `self.start_instance(...)` 在 `with self._lock:` 内部，确实会死锁

- [ ] **Step 2: 修正 `_check_and_restart` 的死锁**

由于既有实现中已有此问题（把 `start_instance` 放在 `with self._lock:` 内部），本次改造顺便修：把 `_check_and_restart` 改为**两阶段**：先在锁内收集要重启的实例 id + 配置，锁外再逐个 `start_instance`。用下面的 `_check_and_restart` 方法覆盖上一步刚写的版本：

```python
    def _check_and_restart(self):
        to_restart: list[tuple[str, int, str, bool]] = []
        with self._lock:
            for inst_id, proc in list(self._processes.items()):
                if proc.poll() is None:
                    continue
                now = time.time()
                self._restart_counts.setdefault(inst_id, []).append(now)
                self._restart_counts[inst_id] = [
                    t for t in self._restart_counts[inst_id] if now - t < 60
                ]
                self._processes.pop(inst_id, None)
                if len(self._restart_counts[inst_id]) > 3:
                    _update_status(inst_id, "error")
                    continue
                with connect() as conn:
                    row = conn.execute(
                        "SELECT port, topology_id, ssl_enabled FROM mock_instances WHERE id = ? AND enabled = 1",
                        (inst_id,),
                    ).fetchone()
                if row:
                    to_restart.append((inst_id, row["port"], row["topology_id"], bool(row["ssl_enabled"])))
        for inst_id, port, topo, ssl_enabled in to_restart:
            self.start_instance(inst_id, port, topo, ssl_enabled)
```

- [ ] **Step 3: 修改 `instance_app.py` 支持 ssl 参数**

用下面的内容覆盖 `backend/app/mock/instance_app.py`：

```python
"""
每实例子进程的入口模块。
用法: python -m app.mock.instance_app --topology-id topo_xxx --port 8081 --instance-id inst_xxx [--ssl-certfile cert.pem --ssl-keyfile key.pem]
"""


def create_app(topology_id: str, instance_id: str = None):
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from app.db.connection import connect
    from app.mock.handler import make_handler

    app = FastAPI(title=f"Mock Instance [{topology_id}]")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    with connect() as conn:
        rows = conn.execute(
            "SELECT id, method, path FROM api_configs WHERE topology_id = ? AND enabled = 1",
            (topology_id,),
        ).fetchall()

    for row in rows:
        handler = make_handler(row["id"], instance_id=instance_id)
        app.add_api_route(
            path=row["path"],
            endpoint=handler,
            methods=[row["method"]],
        )

    return app


if __name__ == "__main__":
    import argparse
    import uvicorn
    from app.db.connection import init_db

    parser = argparse.ArgumentParser()
    parser.add_argument("--topology-id", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--instance-id", default=None)
    parser.add_argument("--ssl-certfile", default=None)
    parser.add_argument("--ssl-keyfile", default=None)
    args = parser.parse_args()

    init_db()
    app = create_app(args.topology_id, instance_id=args.instance_id)

    kwargs = {"host": "0.0.0.0", "port": args.port, "log_level": "warning"}
    if args.ssl_certfile and args.ssl_keyfile:
        kwargs["ssl_certfile"] = args.ssl_certfile
        kwargs["ssl_keyfile"] = args.ssl_keyfile
    uvicorn.run(app, **kwargs)
```

- [ ] **Step 4: Smoke test —— 主服务可 import**

```bash
cd /c/Users/benerlord/Desktop/InterfaceTest/backend && python -c "from app.main import app; from app.core.instance_runner import InstanceRunner; r = InstanceRunner(); print('OK')"
```

Expected: `OK`

- [ ] **Step 5: Smoke test —— instance_app 参数解析可用**

```bash
cd /c/Users/benerlord/Desktop/InterfaceTest/backend && python -m app.mock.instance_app --help
```

Expected: `--help` 输出里包含 `--ssl-certfile` 和 `--ssl-keyfile` 两行

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/instance_runner.py backend/app/mock/instance_app.py
git commit -m "$(cat <<'EOF'
feat(instance): 启动链支持 HTTPS 协议

- InstanceRunner 全套方法加 ssl_enabled 参数
- 父进程 ensure_cert 提前生成证书，避免并发竞态
- 子进程 argparse +2 参数，uvicorn 按需传 ssl_certfile/keyfile
- 顺手修 _check_and_restart 潜在死锁（Lock 非可重入，改成两阶段收集）

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: CRUD 端点联动 —— mock_instance.py

**Files:**
- Modify: `backend/app/admin/mock_instance.py`

- [ ] **Step 1: 全量替换 mock_instance.py**

用下面的内容覆盖 `backend/app/admin/mock_instance.py`：

```python
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request

from app.db.connection import connect, transaction
from app.admin.schemas.mock_instance import (
    MockInstanceCreate,
    MockInstanceUpdate,
    MockInstanceItem,
    RequestLogItem,
)

router = APIRouter(prefix="/admin/api", tags=["实例"])


def _new_id() -> str:
    return f"inst_{uuid.uuid4().hex[:12]}"


def _get_runner(request: Request):
    return request.app.state.instance_runner


def _build_url(port: int, ssl_enabled: bool) -> str:
    proto = "https" if ssl_enabled else "http"
    return f"{proto}://localhost:{port}"


@router.get("/mock-instances")
def list_mock_instances() -> dict:
    with connect() as conn:
        rows = conn.execute("""
            SELECT m.*, t.name AS topology_name,
                   (SELECT COUNT(*) FROM api_configs a WHERE a.topology_id = m.topology_id) AS api_count
            FROM mock_instances m
            LEFT JOIN topologies t ON t.id = m.topology_id
            ORDER BY m.name
        """).fetchall()
        items = [
            MockInstanceItem(
                id=r["id"],
                name=r["name"],
                topology_id=r["topology_id"],
                topology_name=r["topology_name"],
                port=r["port"],
                description=r["description"],
                enabled=bool(r["enabled"]),
                ssl_enabled=bool(r["ssl_enabled"]),
                url=_build_url(r["port"], bool(r["ssl_enabled"])),
                api_count=r["api_count"],
                created_at=r["created_at"],
                updated_at=r["updated_at"],
            ).model_dump(mode="json", by_alias=True)
            for r in rows
        ]
    return {"code": 0, "data": {"items": items, "total": len(items)}, "message": "ok"}


@router.post("/mock-instances")
def create_mock_instance(data: MockInstanceCreate, request: Request) -> dict:
    with transaction() as conn:
        dup = conn.execute(
            "SELECT id, name FROM mock_instances WHERE port = ?", (data.port,)
        ).fetchone()
        if dup:
            raise HTTPException(
                status_code=409,
                detail={"code": 40301, "message": f"端口 {data.port} 已被实例\"{dup['name']}\"占用"},
            )
        inst_id = _new_id()
        conn.execute(
            "INSERT INTO mock_instances (id, name, topology_id, port, description, enabled, ssl_enabled, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 'stopped')",
            (inst_id, data.name, data.topology_id, data.port, data.description,
             1 if data.enabled else 0, 1 if data.ssl_enabled else 0),
        )
    if data.enabled:
        _get_runner(request).start_instance(inst_id, data.port, data.topology_id, data.ssl_enabled)
    return {"code": 0, "data": {"id": inst_id}, "message": "ok"}


@router.put("/mock-instances/{inst_id}")
def update_mock_instance(inst_id: str, data: MockInstanceUpdate, request: Request) -> dict:
    with transaction() as conn:
        existing = conn.execute(
            "SELECT id FROM mock_instances WHERE id = ?", (inst_id,)
        ).fetchone()
        if not existing:
            raise HTTPException(
                status_code=404,
                detail={"code": 40401, "message": "实例不存在"},
            )
        if data.port is not None:
            dup = conn.execute(
                "SELECT id, name FROM mock_instances WHERE port = ? AND id != ?",
                (data.port, inst_id),
            ).fetchone()
            if dup:
                raise HTTPException(
                    status_code=409,
                    detail={"code": 40301, "message": f"端口 {data.port} 已被实例\"{dup['name']}\"占用"},
                )
        updates, params = [], []
        if data.name is not None:
            updates.append("name = ?"); params.append(data.name)
        if data.topology_id is not None:
            updates.append("topology_id = ?"); params.append(data.topology_id)
        if data.port is not None:
            updates.append("port = ?"); params.append(data.port)
        if data.description is not None:
            updates.append("description = ?"); params.append(data.description)
        if data.enabled is not None:
            updates.append("enabled = ?"); params.append(1 if data.enabled else 0)
        if data.ssl_enabled is not None:
            updates.append("ssl_enabled = ?"); params.append(1 if data.ssl_enabled else 0)
        if updates:
            updates.append("updated_at = datetime('now')")
            params.append(inst_id)
            conn.execute(f"UPDATE mock_instances SET {', '.join(updates)} WHERE id = ?", params)
        # 读取更新后的配置，决定是否重启
        row = conn.execute(
            "SELECT port, topology_id, enabled, ssl_enabled FROM mock_instances WHERE id = ?", (inst_id,)
        ).fetchone()
    if row and row["enabled"]:
        _get_runner(request).restart_instance(inst_id, row["port"], row["topology_id"], bool(row["ssl_enabled"]))
    else:
        _get_runner(request).stop_instance(inst_id)
    return {"code": 0, "data": {"id": inst_id}, "message": "ok"}


@router.delete("/mock-instances/{inst_id}")
def delete_mock_instance(inst_id: str, request: Request) -> dict:
    _get_runner(request).stop_instance(inst_id)
    with transaction() as conn:
        existing = conn.execute(
            "SELECT id FROM mock_instances WHERE id = ?", (inst_id,)
        ).fetchone()
        if not existing:
            raise HTTPException(
                status_code=404,
                detail={"code": 40401, "message": "实例不存在"},
            )
        conn.execute("DELETE FROM mock_instances WHERE id = ?", (inst_id,))
    return {"code": 0, "data": {"id": inst_id}, "message": "ok"}


@router.patch("/mock-instances/{inst_id}/enabled")
def patch_instance_enabled(inst_id: str, data: dict, request: Request) -> dict:
    enabled = data.get("enabled", True)
    with transaction() as conn:
        existing = conn.execute(
            "SELECT id FROM mock_instances WHERE id = ?", (inst_id,)
        ).fetchone()
        if not existing:
            raise HTTPException(
                status_code=404,
                detail={"code": 40401, "message": "实例不存在"},
            )
        conn.execute(
            "UPDATE mock_instances SET enabled = ?, updated_at = datetime('now') WHERE id = ?",
            (1 if enabled else 0, inst_id),
        )
        row = conn.execute(
            "SELECT port, topology_id, ssl_enabled FROM mock_instances WHERE id = ?", (inst_id,)
        ).fetchone()
    if row:
        if enabled:
            _get_runner(request).start_instance(inst_id, row["port"], row["topology_id"], bool(row["ssl_enabled"]))
        else:
            _get_runner(request).stop_instance(inst_id)
    return {"code": 0, "data": {"id": inst_id}, "message": "ok"}


@router.get("/mock-instances/{inst_id}/logs")
def get_instance_logs(
    inst_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    before: Optional[str] = Query(default=None),
) -> dict:
    with connect() as conn:
        inst = conn.execute("SELECT id FROM mock_instances WHERE id = ?", (inst_id,)).fetchone()
        if not inst:
            raise HTTPException(status_code=404, detail="实例不存在")

        conditions = ["instance_id = ?"]
        params: list = [inst_id]
        if before:
            conditions.append("ts < ?")
            params.append(before)
        where = " AND ".join(conditions)

        rows = conn.execute(
            f"SELECT * FROM request_logs WHERE {where} ORDER BY ts DESC LIMIT ?",
            params + [limit + 1],
        ).fetchall()

    has_more = len(rows) > limit
    items = [dict(r) for r in rows[:limit]]
    return {"code": 0, "data": {"items": items, "has_more": has_more}, "message": "ok"}


@router.delete("/mock-instances/{inst_id}/logs")
def clear_instance_logs(inst_id: str) -> dict:
    with connect() as conn:
        inst = conn.execute("SELECT id FROM mock_instances WHERE id = ?", (inst_id,)).fetchone()
        if not inst:
            raise HTTPException(status_code=404, detail="实例不存在")
        conn.execute("DELETE FROM request_logs WHERE instance_id = ?", (inst_id,))
    return {"code": 0, "data": {"id": inst_id}, "message": "ok"}
```

- [ ] **Step 2: Smoke test —— 后端主服务能起**

```bash
cd /c/Users/benerlord/Desktop/InterfaceTest/backend && python -c "from app.main import app; print(len(app.routes), 'routes')"
```

Expected: 打印 `N routes`，无异常

- [ ] **Step 3: Commit**

```bash
git add backend/app/admin/mock_instance.py
git commit -m "$(cat <<'EOF'
feat(mock-instance): CRUD 端点联动 ssl_enabled 与 url 拼接

- POST/PUT 接收 sslEnabled 写库
- PATCH enabled 从 DB 读 ssl_enabled 传给 runner
- list 拼 http/https URL 返回给前端

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: 前端 TS 类型 —— mockInstance.ts

**Files:**
- Modify: `frontend/src/api/mockInstance.ts`

- [ ] **Step 1: 修改 MockInstanceItem / Create / Update 接口**

用下面的内容覆盖 `frontend/src/api/mockInstance.ts`：

```typescript
import { apiGet, apiPost, apiPut, apiPatch, apiDelete } from './http'

export interface MockInstanceItem {
  id: string
  name: string
  topologyId: string
  topologyName: string
  port: number
  description: string | null
  enabled: boolean
  sslEnabled: boolean
  url: string
  apiCount: number
  createdAt: string
  updatedAt: string
}

export interface MockInstanceCreate {
  name: string
  topologyId: string
  port: number
  description?: string | null
  enabled?: boolean
  sslEnabled?: boolean
}

export interface MockInstanceUpdate {
  name?: string | null
  topologyId?: string | null
  port?: number
  description?: string | null
  enabled?: boolean
  sslEnabled?: boolean
}

export const mockInstanceApi = {
  list: (): Promise<{ items: MockInstanceItem[]; total: number }> =>
    apiGet('/mock-instances'),

  create: (data: MockInstanceCreate): Promise<{ id: string }> =>
    apiPost('/mock-instances', data),

  update: (id: string, data: MockInstanceUpdate): Promise<{ id: string }> =>
    apiPut(`/mock-instances/${id}`, data),

  delete: (id: string): Promise<{ id: string }> =>
    apiDelete(`/mock-instances/${id}`),

  patchEnabled: (id: string, enabled: boolean): Promise<{ id: string }> =>
    apiPatch(`/mock-instances/${id}/enabled`, { enabled }),
}

export interface RequestLogItem {
  id: number
  ts: string
  apiId: string | null
  method: string
  path: string
  query: string | null
  statusCode: number
  durationMs: number
  clientIp: string | null
  errorMessage: string | null
  instanceId: string | null
}

export interface RequestLogResponse {
  items: RequestLogItem[]
  hasMore: boolean
}

export const requestLogApi = {
  fetchLogs: (instId: string, params?: { limit?: number; before?: string }): Promise<RequestLogResponse> =>
    apiGet(`/mock-instances/${instId}/logs`, params),

  clearLogs: (instId: string): Promise<{ id: string }> =>
    apiDelete(`/mock-instances/${instId}/logs`),
}
```

- [ ] **Step 2: Smoke test —— tsc 通过**

```bash
cd /c/Users/benerlord/Desktop/InterfaceTest/frontend && npx tsc --noEmit
```

Expected: exit 0，无输出

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/mockInstance.ts
git commit -m "$(cat <<'EOF'
feat(api): MockInstance 类型加 sslEnabled 与 url

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: MockInstanceModal 加"协议"字段

**Files:**
- Modify: `frontend/src/components/mockInstance/MockInstanceModal.vue`

- [ ] **Step 1: 全量替换 MockInstanceModal.vue**

用下面的内容覆盖 `frontend/src/components/mockInstance/MockInstanceModal.vue`：

```vue
<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { Modal, Form, Input, InputNumber, Select, Radio } from 'ant-design-vue'
import { apiGet } from '@/api/http'
import type { MockInstanceItem } from '@/api/mockInstance'
import type { TopologyListItem } from '@/api/topology'

interface Props {
  open: boolean
  editing: MockInstanceItem | null
}

const props = defineProps<Props>()
const emit = defineEmits<{
  (e: 'update:open', v: boolean): void
  (e: 'create', data: { name: string; topologyId: string; port: number; description?: string | null; sslEnabled: boolean }): void
  (e: 'update', data: { name?: string | null; topologyId?: string | null; port?: number; description?: string | null; sslEnabled?: boolean }): void
}>()

const loading = ref(false)
const formRef = ref<{ validateFields?: () => Promise<void> } | null>(null)
const topologies = ref<TopologyListItem[]>([])

const formState = ref<{ name: string; topologyId: string; port: number | undefined; description: string; sslEnabled: boolean }>({
  name: '',
  topologyId: '',
  port: undefined,
  description: '',
  sslEnabled: false,
})

const isEdit = computed(() => !!props.editing)
const title = computed(() => (isEdit.value ? '编辑实例' : '新建实例'))

onMounted(async () => {
  try {
    const res = await apiGet<{ items: TopologyListItem[] }>('/topologies', { page: 1, pageSize: 500 })
    topologies.value = res.items
  } catch {}
})

watch(
  () => props.open,
  (open) => {
    if (open) {
      formState.value = {
        name: props.editing?.name ?? '',
        topologyId: props.editing?.topologyId ?? '',
        port: props.editing?.port ?? undefined,
        description: props.editing?.description ?? '',
        sslEnabled: props.editing?.sslEnabled ?? false,
      }
    }
  },
)

function close() {
  emit('update:open', false)
}

async function handleSubmit() {
  try {
    if (formRef.value?.validateFields) await formRef.value.validateFields()
    loading.value = true
    if (isEdit.value) {
      await emit('update', { ...formState.value })
    } else {
      await emit('create', { ...formState.value, port: formState.value.port! })
    }
    close()
  } catch {
    // validation failed
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <Modal
    :open="open"
    :title="title"
    :confirm-loading="loading"
    ok-text="确定"
    cancel-text="取消"
    @ok="handleSubmit"
    @cancel="close"
  >
    <Form ref="formRef" :model="formState" layout="vertical">
      <Form.Item
        label="名称"
        name="name"
        :rules="[{ required: true, message: '请输入实例名称' }]"
      >
        <Input v-model:value="formState.name" placeholder="如：北京-设备查询" :maxlength="100" />
      </Form.Item>

      <Form.Item
        label="端口"
        name="port"
        :rules="[{ required: true, message: '请输入端口号' }]"
      >
        <InputNumber
          v-model:value="formState.port"
          :min="1"
          :max="65535"
          placeholder="1 ~ 65535"
          style="width: 100%"
        />
      </Form.Item>

      <Form.Item
        label="协议"
        name="sslEnabled"
        :extra="formState.sslEnabled ? '使用系统自签证书，客户端需跳过证书校验' : undefined"
      >
        <Radio.Group v-model:value="formState.sslEnabled">
          <Radio :value="false">HTTP</Radio>
          <Radio :value="true">HTTPS</Radio>
        </Radio.Group>
      </Form.Item>

      <Form.Item
        label="所属拓扑"
        name="topologyId"
        :rules="[{ required: true, message: '请选择拓扑' }]"
      >
        <Select
          v-model:value="formState.topologyId"
          placeholder="选择拓扑"
          show-search
          option-filter-prop="label"
        >
          <Select.Option
            v-for="t in topologies"
            :key="t.id"
            :value="t.id"
            :label="t.name"
          >
            {{ t.name }}
          </Select.Option>
        </Select>
      </Form.Item>

      <Form.Item label="描述" name="description">
        <Input.TextArea
          v-model:value="formState.description"
          placeholder="可选描述"
          :rows="3"
          :maxlength="200"
        />
      </Form.Item>
    </Form>
  </Modal>
</template>
```

- [ ] **Step 2: Smoke test —— tsc 通过**

```bash
cd /c/Users/benerlord/Desktop/InterfaceTest/frontend && npx tsc --noEmit
```

Expected: exit 0

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/mockInstance/MockInstanceModal.vue
git commit -m "$(cat <<'EOF'
feat(mock-instance): Modal 加协议字段（HTTP / HTTPS）

Radio.Group 单选，HTTPS 选中显示自签证书提示。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: MockInstancesView 加协议列 + 访问地址列

**Files:**
- Modify: `frontend/src/views/MockInstancesView.vue`

- [ ] **Step 1: 全量替换 MockInstancesView.vue**

用下面的内容覆盖 `frontend/src/views/MockInstancesView.vue`：

```vue
<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Card, Button, Space, Table, Tag, Switch, Popconfirm, Typography, Tooltip, message } from 'ant-design-vue'
import { PlusOutlined, EditOutlined, DeleteOutlined, FileTextOutlined } from '@ant-design/icons-vue'
import { mockInstanceApi, type MockInstanceItem } from '@/api/mockInstance'
import MockInstanceModal from '@/components/mockInstance/MockInstanceModal.vue'
import InstanceLogsDrawer from '@/components/mockInstance/InstanceLogsDrawer.vue'

const instances = ref<MockInstanceItem[]>([])
const loading = ref(false)
const modalOpen = ref(false)
const editingInstance = ref<MockInstanceItem | null>(null)
const logsDrawerOpen = ref(false)
const logsInstance = ref<MockInstanceItem | null>(null)

function openLogs(item: MockInstanceItem) {
  logsInstance.value = item
  logsDrawerOpen.value = true
}

async function fetchInstances() {
  loading.value = true
  try {
    const res = await mockInstanceApi.list()
    instances.value = res.items
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editingInstance.value = null
  modalOpen.value = true
}

function openEdit(item: MockInstanceItem) {
  editingInstance.value = item
  modalOpen.value = true
}

async function handleCreate(data: { name: string; topologyId: string; port: number; description?: string | null; sslEnabled: boolean }) {
  await mockInstanceApi.create(data)
  message.success('实例创建成功')
  modalOpen.value = false
  fetchInstances()
}

async function handleUpdate(data: { name?: string | null; topologyId?: string | null; port?: number; description?: string | null; sslEnabled?: boolean }) {
  if (!editingInstance.value) return
  await mockInstanceApi.update(editingInstance.value.id, data)
  message.success('实例更新成功')
  modalOpen.value = false
  fetchInstances()
}

async function handleDelete(item: MockInstanceItem) {
  await mockInstanceApi.delete(item.id)
  message.success('实例已删除')
  fetchInstances()
}

async function handleToggleEnabled(item: MockInstanceItem, checked: boolean) {
  await mockInstanceApi.patchEnabled(item.id, checked)
  message.success(checked ? '已启用' : '已禁用')
  fetchInstances()
}

const columns = [
  { title: '名称', dataIndex: 'name', key: 'name', width: 180 },
  { title: '端口', dataIndex: 'port', key: 'port', width: 80 },
  { title: '协议', key: 'protocol', width: 80, align: 'center' as const },
  { title: '访问地址', key: 'url', width: 240 },
  { title: '所属拓扑', dataIndex: 'topologyName', key: 'topologyName', width: 160 },
  { title: '启用', key: 'enabled', width: 90, align: 'center' as const },
  { title: '接口数', key: 'apiCount', width: 80, align: 'center' as const },
  { title: '创建时间', dataIndex: 'createdAt', key: 'createdAt', width: 180 },
  { title: '操作', key: 'action', width: 150, fixed: 'right' as const },
]

function formatDate(iso: string): string {
  if (!iso) return '-'
  const d = new Date(iso)
  return d.toLocaleString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

onMounted(fetchInstances)
</script>

<template>
  <Card title="实例管理" :bordered="false">
    <template #extra>
      <Button type="primary" @click="openCreate">
        <template #icon><PlusOutlined /></template>
        新建实例
      </Button>
    </template>

    <Table
      :data-source="instances"
      :columns="columns"
      :loading="loading"
      :pagination="false"
      row-key="id"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'topologyName'">
          <Tag color="blue">{{ record.topologyName }}</Tag>
        </template>
        <template v-else-if="column.key === 'protocol'">
          <Tag :color="record.sslEnabled ? 'green' : 'blue'">
            {{ record.sslEnabled ? 'HTTPS' : 'HTTP' }}
          </Tag>
        </template>
        <template v-else-if="column.key === 'url'">
          <Tooltip v-if="!record.enabled" title="实例未启用，当前不可访问">
            <Typography.Text copyable code type="secondary">{{ record.url }}</Typography.Text>
          </Tooltip>
          <Typography.Text v-else copyable code>{{ record.url }}</Typography.Text>
        </template>
        <template v-else-if="column.key === 'enabled'">
          <Switch
            :checked="record.enabled"
            checked-children="启用"
            un-checked-children="禁用"
            @change="(v: boolean) => handleToggleEnabled(record, v)"
          />
        </template>
        <template v-else-if="column.key === 'apiCount'">
          <Tag :color="record.apiCount > 0 ? 'green' : 'default'">{{ record.apiCount }}</Tag>
        </template>
        <template v-else-if="column.key === 'createdAt'">
          {{ formatDate(record.createdAt) }}
        </template>
        <template v-else-if="column.key === 'action'">
          <Space>
            <a @click="openEdit(record)"><EditOutlined /></a>
            <a @click="openLogs(record)" title="请求日志"><FileTextOutlined /></a>
            <Popconfirm
              title="确定删除该实例？"
              ok-text="确定"
              cancel-text="取消"
              @confirm="handleDelete(record)"
            >
              <a style="color: #ff4d4f"><DeleteOutlined /></a>
            </Popconfirm>
          </Space>
        </template>
      </template>
    </Table>
  </Card>

  <MockInstanceModal
    v-model:open="modalOpen"
    :editing="editingInstance"
    @create="handleCreate"
    @update="handleUpdate"
  />

  <InstanceLogsDrawer
    v-if="logsInstance"
    v-model:open="logsDrawerOpen"
    :instance-id="logsInstance.id"
    :instance-name="logsInstance.name"
    :instance-port="logsInstance.port"
  />
</template>
```

- [ ] **Step 2: Smoke test —— tsc 通过**

```bash
cd /c/Users/benerlord/Desktop/InterfaceTest/frontend && npx tsc --noEmit
```

Expected: exit 0

- [ ] **Step 3: Commit**

```bash
git add frontend/src/views/MockInstancesView.vue
git commit -m "$(cat <<'EOF'
feat(mock-instance): 列表加协议列 + 可复制的访问地址列

- 协议列：Tag 显示 HTTP/HTTPS
- 访问地址列：Typography.Text copyable code 可一键复制
- 禁用态显示灰色 + tooltip 提示"实例未启用，当前不可访问"

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: 手工联调验收

**Files:** 无改动，纯手工验收

- [ ] **Step 1: 启动后端**

```bash
cd /c/Users/benerlord/Desktop/InterfaceTest/backend && python -m app.main
```

后台运行，确保输出无 stack trace。

- [ ] **Step 2: 启动前端**

```bash
cd /c/Users/benerlord/Desktop/InterfaceTest/frontend && npm run dev
```

- [ ] **Step 3: 用例 1 —— 迁移兼容性**

浏览器打开 `http://localhost:5173/mock-instances`，既有实例应显示：
- 协议列 = HTTP（Tag 蓝色）
- 访问地址 = `http://localhost:<port>`

- [ ] **Step 4: 用例 2 —— 新建 HTTPS 实例**

点"新建实例" → 填名字 + 端口（如 9443）+ 选 HTTPS + 选拓扑 → 确定。

列表刷新后新实例应：
- 协议 Tag 绿色 HTTPS
- URL 显示 `https://localhost:9443`
- enabled=true

- [ ] **Step 5: 用例 3 —— curl 直接访问 HTTPS**

拿实例下一个 mock 接口路径（如 `/api/v1/xxx`）：

```bash
curl -k -sS -o /dev/null -w "%{http_code}\n" https://localhost:9443/<some-mock-path>
```

Expected: 非 000 的 HTTP 状态码（200/40x/50x 都行，说明 TLS 握手 & 服务响应正常）

- [ ] **Step 6: 用例 4 —— 证书首次生成**

停后端 → 删除 `backend/data/ssl/` 整个目录 → 重启后端 → 新建 HTTPS 实例 → `backend/data/ssl/cert.pem` 与 `key.pem` 应被重新生成

```bash
ls backend/data/ssl/
```

Expected: 输出 `cert.pem  key.pem`

- [ ] **Step 7: 用例 5 —— HTTP ↔ HTTPS 热切换**

编辑一个 HTTP 实例，改为 HTTPS，保存 → 列表刷新，URL 前缀变 https；`curl` 老端口的 HTTP 应连不上（错误），HTTPS 能通。

反向操作同理。

- [ ] **Step 8: 用例 6 —— 禁用 HTTPS 实例**

关闭 enabled 开关：
- URL 单元格变灰
- `curl -k https://localhost:port/...` 连接被拒
- Hover URL 看到 tooltip

- [ ] **Step 9: 用例 7 —— 端口占用冲突**

试图创建一个 port 与既有实例重复的实例（无论协议），应弹出 409 错误"端口 X 已被实例 Y 占用"。

- [ ] **Step 10: 用例 8 —— 复制 URL**

点击 URL 右侧的复制图标 → 粘贴到别处 → 得到完整的 `http(s)://localhost:port` 字符串。

- [ ] **Step 11: 用例 9 —— 健康监控自愈（验证 T3 死锁修复）**

拿一个已启用的 HTTPS 实例的子进程 PID：

```bash
netstat -ano | grep :<port> | grep LISTENING
```

强杀该 PID：

```powershell
powershell -Command "Stop-Process -Id <pid> -Force"
```

等 ~20 秒后再查 netstat，端口应重新有 node/python 进程 LISTENING（说明 `_check_and_restart` 拉起来了，且没有在两阶段锁改造里死锁）。

也可以用 `curl -k https://localhost:<port>/<some-path>` 再打一次，能拿到响应。

- [ ] **Step 12: 关闭进程释放端口**

按 CLAUDE.md 约定，测试完成后关掉后端和前端 dev server：

```bash
# 找到并 kill 后端
netstat -ano | grep :8080 | grep LISTENING
# 找到 PID 后 taskkill /F /PID <pid>

# 找到并 kill 前端
netstat -ano | grep :5173 | grep LISTENING
```

- [ ] **Step 13: 更新 CLAUDE.md 开发进度**

在"已完成"章节末尾追加一条：

```markdown
- ✅ 实例管理支持 HTTPS 协议（commit 待提交）：
  - `mock_instances` 新增 `ssl_enabled` 列（幂等 ALTER，默认 0 兼容既有）
  - `InstanceRunner` 父进程 `ensure_cert` 提前生成证书，避免子进程并发竞态；顺手修 `_check_and_restart` Lock 非可重入的潜在死锁
  - `instance_app.py` argparse +2 参数，uvicorn 按需 `ssl_certfile/ssl_keyfile`
  - Modal 加 `Radio.Group` 协议字段（HTTP/HTTPS，选 HTTPS 提示需跳过校验）
  - 列表加协议 Tag 列 + 可复制访问地址列（`Typography.Text copyable code`，禁用态灰色 + tooltip）
```

- [ ] **Step 14: Commit**

```bash
git add CLAUDE.md
git commit -m "$(cat <<'EOF'
docs(claude): 记录实例管理 HTTPS 协议支持完成

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## 完成标准

- ✅ 所有 Task 1-8 的 checkbox 全打勾
- ✅ Task 8 的 9 个用例全部通过
- ✅ `git log` 有 8 条对应 commit（T1-T7 + T8 CLAUDE.md 更新）
- ✅ `netstat` 确认后端 / 前端端口已释放
