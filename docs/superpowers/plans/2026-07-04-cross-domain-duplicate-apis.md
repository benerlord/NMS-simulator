# 跨网管同名接口 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 放宽 `api_configs.UNIQUE(method, path)` 到 `UNIQUE(domain_id, method, path)`，并停用 admin 8080 的 mock 路由挂载。让不同网管下能各自存一份同 (method, path) 的接口，各自在自己实例端口上返回不同响应。

**Architecture:** 通过"表重建"迁移替换 UNIQUE 约束（SQLite 不支持 DROP CONSTRAINT）；CRUD 里的路径重复预检从"全局"改为"按域"；Excel 导入匹配键加上 `domain_id`；main.py + api_config.py + settings.py 里 6 处 `mock_registry` 调用点全部移除。前端 / instance_app.py / `mock/registry.py` 模块本身不动。

**Tech Stack:** Python 3.9 / FastAPI / SQLite / pytest

**Spec:** `docs/superpowers/specs/2026-07-04-cross-domain-duplicate-apis-design.md`

---

## 文件清单

**修改：**
- `backend/app/db/migrations.py` — 新增 `_rebuild_api_configs_domain_unique()` + 在 `run_migrations` 中调用
- `backend/app/admin/api_config.py` — 3 处路径重复预检 (`create_api` / `update_api` / `duplicate_api`) 加上 domain_id 条件；1 处导入匹配 (`import_apis`) 加上 domain_id；6 处 `mock_registry.*` 调用及 5 处 `from app.mock.registry import ...` 内嵌 import 全部删除
- `backend/app/admin/settings.py` — 删除 `mock_registry.reload()` 调用 + 相关 import
- `backend/app/main.py` — 删除 `mock_registry.bind(app)` + `mock_registry.load_all()` + 顶部 import
- `backend/app/admin/_api_excel.py` — 更新 `_write_instruction_sheet` 中第 6 条文案

**新增：**
- `backend/tests/test_migrations_cross_domain.py` — 迁移测试（重建 + 数据保留 + 幂等）
- `backend/tests/test_apis_cross_domain.py` — CRUD + import 相关端到端测试

**不改：**
- `backend/app/mock/registry.py` — 保留为死代码
- `backend/app/mock/instance_app.py` — 已按 domain 过滤，天然正确
- `frontend/**/*` — 前端已按域分组显示，无需改动

---

## Task 1: 迁移 — 重建 api_configs 表

**Files:**
- Modify: `backend/app/db/migrations.py`（新增迁移函数 + 在 `run_migrations` 中调用）
- Create: `backend/tests/test_migrations_cross_domain.py`

- [ ] **Step 1: 写失败测试**

Create `backend/tests/test_migrations_cross_domain.py`:

```python
import sqlite3

import pytest

from app.db.migrations import run_migrations


def _fresh_conn(tmp_path):
    c = sqlite3.connect(str(tmp_path / "t.db"), isolation_level=None)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    return c


def _read_table_sql(conn, table):
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row["sql"] if row else ""


def test_migration_rewrites_api_configs_to_domain_unique(tmp_path):
    """迁移后 api_configs 应带 UNIQUE(domain_id, method, path)，且不再有 UNIQUE(method, path)。"""
    conn = _fresh_conn(tmp_path)
    run_migrations(conn)
    sql = _read_table_sql(conn, "api_configs")
    assert "UNIQUE (domain_id, method, path)" in sql or "UNIQUE(domain_id, method, path)" in sql
    # 旧约束不能残留（用括号形式匹配避免误匹配子串）
    assert "UNIQUE (method, path)" not in sql
    assert "UNIQUE(method, path)" not in sql
    conn.close()


def test_migration_is_idempotent(tmp_path):
    """连续跑两次 run_migrations 不应报错、也不应重复处理。"""
    conn = _fresh_conn(tmp_path)
    run_migrations(conn)
    sql1 = _read_table_sql(conn, "api_configs")
    run_migrations(conn)
    sql2 = _read_table_sql(conn, "api_configs")
    assert sql1 == sql2
    conn.close()


def test_migration_preserves_cross_domain_rows(tmp_path):
    """老库里跨域同 (method, path) 的合法数据必须保留（本次改动仅"放宽"约束）。"""
    # 模拟一个"仍是老约束"的库：先跑一次拿到新表，再"造老库"
    # 简化：先跑一次拿到新表；两个域下各插一条同名接口，确认可插入 & 迁移是幂等的
    conn = _fresh_conn(tmp_path)
    run_migrations(conn)

    # 造两个域
    conn.execute("INSERT INTO domains (id, name) VALUES ('dA', 'A')")
    conn.execute("INSERT INTO domains (id, name) VALUES ('dB', 'B')")
    # 跨域插两条同 (method, path)
    conn.execute(
        "INSERT INTO api_configs (id, name, method, path, data_source, domain_id, config) "
        "VALUES ('api_a', 'A-token', 'PUT', '/token', 'static', 'dA', '{}')"
    )
    conn.execute(
        "INSERT INTO api_configs (id, name, method, path, data_source, domain_id, config) "
        "VALUES ('api_b', 'B-token', 'PUT', '/token', 'static', 'dB', '{}')"
    )
    # 再跑一次迁移，数据不应丢
    run_migrations(conn)
    rows = conn.execute("SELECT id FROM api_configs ORDER BY id").fetchall()
    assert [r["id"] for r in rows] == ["api_a", "api_b"]
    conn.close()


def test_migration_blocks_same_domain_duplicate(tmp_path):
    """迁移后同域插两条同 (method, path) 应被 UNIQUE 拦下。"""
    conn = _fresh_conn(tmp_path)
    run_migrations(conn)
    conn.execute("INSERT INTO domains (id, name) VALUES ('dA', 'A')")
    conn.execute(
        "INSERT INTO api_configs (id, name, method, path, data_source, domain_id, config) "
        "VALUES ('api_a1', 'A1', 'PUT', '/token', 'static', 'dA', '{}')"
    )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO api_configs (id, name, method, path, data_source, domain_id, config) "
            "VALUES ('api_a2', 'A2', 'PUT', '/token', 'static', 'dA', '{}')"
        )
    conn.close()


def test_migration_allows_null_domain_duplicate(tmp_path):
    """迁移后 domain_id=NULL 的未归类接口可以有重复 (method, path)——SQLite NULL 语义。"""
    conn = _fresh_conn(tmp_path)
    run_migrations(conn)
    conn.execute(
        "INSERT INTO api_configs (id, name, method, path, data_source, config) "
        "VALUES ('api_n1', 'N1', 'GET', '/foo', 'static', '{}')"
    )
    conn.execute(
        "INSERT INTO api_configs (id, name, method, path, data_source, config) "
        "VALUES ('api_n2', 'N2', 'GET', '/foo', 'static', '{}')"
    )
    rows = conn.execute("SELECT COUNT(*) c FROM api_configs WHERE path='/foo'").fetchone()
    assert rows["c"] == 2
    conn.close()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_migrations_cross_domain.py -v`
Expected: 5 tests FAIL — old `UNIQUE (method, path)` still in place

- [ ] **Step 3: 实现迁移函数**

Modify `backend/app/db/migrations.py`. Find the end of `_expand_field_type_check` (near line 383) and insert a new function right above `def run_migrations`:

```python
def _rebuild_api_configs_domain_unique(conn: sqlite3.Connection) -> None:
    """把 api_configs 的 UNIQUE(method, path) 放宽成 UNIQUE(domain_id, method, path)。

    幂等：通过读取 sqlite_master 里的 CREATE TABLE 语句判断当前是老约束还是新约束。
    仅当仍是老约束（UNIQUE(method, path)）时才重建表。
    """
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='api_configs'"
    ).fetchone()
    if row is None:
        return
    table_sql = row[0] or ""
    # 新约束特征：包含 domain_id, method, path 的 UNIQUE 元组
    if "UNIQUE (domain_id, method, path)" in table_sql or "UNIQUE(domain_id, method, path)" in table_sql:
        return  # 已经是新约束

    # 关外键、重建、迁数据、切回
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        cols_info = conn.execute("PRAGMA table_info(api_configs)").fetchall()
        col_names = [c[1] for c in cols_info]
        cols_csv = ", ".join(col_names)

        conn.execute("ALTER TABLE api_configs RENAME TO api_configs_bak_domain_unique")

        conn.execute("""
            CREATE TABLE api_configs (
              id              TEXT PRIMARY KEY,
              name            TEXT NOT NULL,
              method          TEXT NOT NULL,
              path            TEXT NOT NULL,
              enabled         INTEGER NOT NULL DEFAULT 1,
              group_name      TEXT,
              data_source     TEXT NOT NULL CHECK (data_source IN ('sql','static')),
              topology_id     TEXT,
              sql_text        TEXT,
              config          TEXT NOT NULL,
              created_at      TEXT NOT NULL DEFAULT (datetime('now')),
              updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
              domain_id       TEXT,
              category        TEXT,
              FOREIGN KEY (topology_id) REFERENCES topologies(id),
              UNIQUE (domain_id, method, path)
            )
        """)

        conn.execute(
            f"INSERT INTO api_configs ({cols_csv}) SELECT {cols_csv} FROM api_configs_bak_domain_unique"
        )
        conn.execute("DROP TABLE api_configs_bak_domain_unique")

        # 重建原有索引（SCHEMA_SQL 里那几条 CREATE INDEX 后续会由 executescript 幂等重放，
        # 但这里显式补一遍以防万一）
        conn.execute("CREATE INDEX IF NOT EXISTS idx_apis_enabled ON api_configs(enabled)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_apis_topo    ON api_configs(topology_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_apis_group   ON api_configs(group_name)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_apis_domain  ON api_configs(domain_id)")
    finally:
        conn.execute("PRAGMA foreign_keys = ON")
```

Then in `run_migrations`, add a call to it near the end of the function (right before the `return` if any, or at the end of the body). Find the last existing `_expand_field_type_check(...)` call (there are 3 in a row for node_type_fields / edge_type_fields / alarm_schema_fields) and add the new call immediately after them:

```python
    # 跨网管同名接口：api_configs 的 UNIQUE(method, path) 放宽为 UNIQUE(domain_id, method, path)
    _rebuild_api_configs_domain_unique(conn)
```

Also update the SCHEMA_SQL string at the top of `migrations.py` — find the `CREATE TABLE IF NOT EXISTS api_configs` block (around line 141) and change the line `UNIQUE (method, path)` to `UNIQUE (domain_id, method, path)`. This ensures brand-new databases start with the new constraint directly.

However, the SCHEMA_SQL uses `domain_id` which is added later via `ALTER TABLE`. So the CREATE TABLE in SCHEMA_SQL doesn't have `domain_id` column yet. Check current SCHEMA_SQL carefully.

Look at `backend/app/db/migrations.py:141-159` to see the current `api_configs` CREATE TABLE. If it doesn't have `domain_id` column, then keeping SCHEMA_SQL with `UNIQUE (method, path)` is fine — the migration function adds `domain_id` via ALTER TABLE first, then `_rebuild_api_configs_domain_unique` rebuilds. Just make sure `_rebuild_api_configs_domain_unique` runs AFTER the `ALTER TABLE api_configs ADD COLUMN domain_id` (which is at line 420).

The call order in `run_migrations` should be:
1. `conn.executescript(SCHEMA_SQL)` — creates old-style table with `UNIQUE(method, path)` on fresh DB
2. `ALTER TABLE api_configs ADD COLUMN domain_id` (line 420) — adds domain_id column
3. `ALTER TABLE api_configs ADD COLUMN category` (line 424) — adds category column
4. `CREATE INDEX idx_apis_domain` (line 427)
5. `_expand_field_type_check(...)` calls (existing)
6. **NEW:** `_rebuild_api_configs_domain_unique(conn)` — rebuilds with new UNIQUE

**Do NOT modify SCHEMA_SQL's `UNIQUE (method, path)` line.** Leave it as-is; the rebuild handles both fresh and old databases uniformly.

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_migrations_cross_domain.py -v`
Expected: 5 tests PASS

- [ ] **Step 5: 跑全套测试确认无回归**

Run: `cd backend && python -m pytest -q 2>&1 | tail -5`
Expected: 全部 PASS

- [ ] **Step 6: 提交**

```bash
git add backend/app/db/migrations.py backend/tests/test_migrations_cross_domain.py
git commit -m "$(cat <<'EOF'
feat(db): api_configs UNIQUE 放宽为 (domain_id, method, path)

- 新增 _rebuild_api_configs_domain_unique 迁移函数，
  从 sqlite_master 判断是否需要重建，幂等
- 老库中的跨域同 (method, path) 数据保留（本次改动仅放宽约束）
- 同域内 UNIQUE 仍生效；未归类（domain_id=NULL）走 SQLite NULL 语义可重复
- +5 单测覆盖：新约束存在 / 幂等 / 数据保留 / 同域拦截 / NULL 允许

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: CRUD 路径重复预检改为按域

**Files:**
- Modify: `backend/app/admin/api_config.py`（3 处路径重复预检）
- Create: `backend/tests/test_apis_cross_domain.py`

- [ ] **Step 1: 写失败测试**

Create `backend/tests/test_apis_cross_domain.py`:

```python
"""CRUD + 导入的跨域同名接口行为测试。"""


def test_create_same_method_path_different_domains_ok(client):
    d1 = client.post("/admin/api/domains", json={"name": "网管A"}).json()["data"]["id"]
    d2 = client.post("/admin/api/domains", json={"name": "网管B"}).json()["data"]["id"]

    r1 = client.post("/admin/api/apis", json={
        "method": "PUT", "path": "/rest/token", "name": "A-token",
        "domainId": d1, "dataSource": "static", "config": {},
    })
    assert r1.status_code == 200, r1.text

    r2 = client.post("/admin/api/apis", json={
        "method": "PUT", "path": "/rest/token", "name": "B-token",
        "domainId": d2, "dataSource": "static", "config": {},
    })
    assert r2.status_code == 200, r2.text
    assert r1.json()["data"]["id"] != r2.json()["data"]["id"]


def test_create_same_method_path_same_domain_blocked(client):
    d = client.post("/admin/api/domains", json={"name": "网管A"}).json()["data"]["id"]
    r1 = client.post("/admin/api/apis", json={
        "method": "GET", "path": "/dup", "name": "first",
        "domainId": d, "dataSource": "static", "config": {},
    })
    assert r1.status_code == 200

    r2 = client.post("/admin/api/apis", json={
        "method": "GET", "path": "/dup", "name": "second",
        "domainId": d, "dataSource": "static", "config": {},
    })
    assert r2.status_code == 409
    assert r2.json()["detail"]["code"] == 40301


def test_create_null_domain_duplicates_allowed(client):
    """未归类接口不做重复预检——跟 SQLite NULL 语义一致。"""
    r1 = client.post("/admin/api/apis", json={
        "method": "GET", "path": "/orphan", "name": "o1",
        "dataSource": "static", "config": {},
    })
    assert r1.status_code == 200
    r2 = client.post("/admin/api/apis", json={
        "method": "GET", "path": "/orphan", "name": "o2",
        "dataSource": "static", "config": {},
    })
    assert r2.status_code == 200
    assert r1.json()["data"]["id"] != r2.json()["data"]["id"]


def test_update_moving_path_within_same_domain_conflict_blocked(client):
    d = client.post("/admin/api/domains", json={"name": "网管A"}).json()["data"]["id"]
    a1 = client.post("/admin/api/apis", json={
        "method": "GET", "path": "/a", "name": "a",
        "domainId": d, "dataSource": "static", "config": {},
    }).json()["data"]["id"]
    client.post("/admin/api/apis", json={
        "method": "GET", "path": "/b", "name": "b",
        "domainId": d, "dataSource": "static", "config": {},
    })

    r = client.put(f"/admin/api/apis/{a1}", json={"path": "/b"})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == 40301


def test_update_moving_path_across_domain_ok(client):
    """A 域下 /x → 更新 path 为 /y，B 域下已有 /y 不应阻挡。"""
    dA = client.post("/admin/api/domains", json={"name": "网管A"}).json()["data"]["id"]
    dB = client.post("/admin/api/domains", json={"name": "网管B"}).json()["data"]["id"]
    aA = client.post("/admin/api/apis", json={
        "method": "GET", "path": "/x", "name": "xA",
        "domainId": dA, "dataSource": "static", "config": {},
    }).json()["data"]["id"]
    client.post("/admin/api/apis", json={
        "method": "GET", "path": "/y", "name": "yB",
        "domainId": dB, "dataSource": "static", "config": {},
    })

    r = client.put(f"/admin/api/apis/{aA}", json={"path": "/y"})
    assert r.status_code == 200, r.text


def test_duplicate_api_generates_unique_path_within_domain(client):
    """复制接口时生成 _copy 后缀，冲突判断按域，不看其它域。"""
    dA = client.post("/admin/api/domains", json={"name": "网管A"}).json()["data"]["id"]
    dB = client.post("/admin/api/domains", json={"name": "网管B"}).json()["data"]["id"]
    aA = client.post("/admin/api/apis", json={
        "method": "GET", "path": "/foo", "name": "fooA",
        "domainId": dA, "dataSource": "static", "config": {},
    }).json()["data"]["id"]
    # B 域下预置一个 /foo_copy，确保复制时 A 域的判定不会误参考它
    client.post("/admin/api/apis", json={
        "method": "GET", "path": "/foo_copy", "name": "fooB_copy",
        "domainId": dB, "dataSource": "static", "config": {},
    })

    r = client.post(f"/admin/api/apis/{aA}/duplicate")
    assert r.status_code == 200
    new_id = r.json()["data"]["id"]
    detail = client.get(f"/admin/api/apis/{new_id}").json()["data"]
    # 因为 A 域下不存在 /foo_copy，直接可用（不应因为 B 域的 /foo_copy 而变成 /foo_copy2）
    assert detail["path"] == "/foo_copy"
    assert detail["domainId"] == dA
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_apis_cross_domain.py -v`
Expected: 4 tests FAIL — 现有 CRUD 全局唯一预检把跨域场景当冲突拦下（`test_create_same_method_path_different_domains_ok` / `test_update_moving_path_across_domain_ok` / `test_duplicate_api_generates_unique_path_within_domain` 会失败）；`test_update_moving_path_within_same_domain_conflict_blocked` 应仍能过（同域冲突仍会被拦，只是错误号是否 40301 要确认）。

- [ ] **Step 3: 改 `create_api` 的路径重复预检（backend/app/admin/api_config.py:249-261）**

Find (approx lines 249-261):

```python
        dup = conn.execute(
            "SELECT id FROM api_configs WHERE method = ? AND path = ?",
            (body.method, body.path),
        ).fetchone()
        if dup:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": 40301,
                    "message": "接口路径已存在",
                    "details": {"method": body.method, "path": body.path},
                },
            )
```

Replace with:

```python
        # 按 (domain_id, method, path) 匹配；domain_id 为 NULL 时不做重复预检
        # （SQLite NULL 语义允许多条未归类接口共享 path；用户归类后再受同域约束）
        if body.domain_id is not None:
            dup = conn.execute(
                "SELECT id FROM api_configs WHERE domain_id = ? AND method = ? AND path = ?",
                (body.domain_id, body.method, body.path),
            ).fetchone()
            if dup:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": 40301,
                        "message": "接口路径在该网管下已存在",
                        "details": {"method": body.method, "path": body.path, "domainId": body.domain_id},
                    },
                )
```

- [ ] **Step 4: 改 `update_api` 的路径重复预检（backend/app/admin/api_config.py:373-391）**

Find (approx lines 373-391) — the block that starts with `if body.method is not None or body.path is not None:`:

```python
        new_method = body.method if body.method is not None else existing["method"]
        new_path = body.path if body.path is not None else existing["path"]
        if body.method is not None or body.path is not None:
            dup = conn.execute(
                """
                SELECT id FROM api_configs
                WHERE method = ? AND path = ? AND id != ?
                """,
                (new_method, new_path, api_id),
            ).fetchone()
            if dup:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": 40301,
                        "message": "接口路径已存在",
                        "details": {"method": new_method, "path": new_path},
                    },
                )
```

Replace with:

```python
        new_method = body.method if body.method is not None else existing["method"]
        new_path = body.path if body.path is not None else existing["path"]
        # 允许 body.domain_id 覆盖 existing 的 domain_id（LEGACY-06 已允许更新绑定）
        new_domain_id = body.domain_id if "domain_id" in body.model_fields_set else existing["domain_id"]
        if body.method is not None or body.path is not None or body.domain_id is not None:
            # 未归类接口（新域为 NULL）不做重复预检
            if new_domain_id is not None:
                dup = conn.execute(
                    """
                    SELECT id FROM api_configs
                    WHERE domain_id = ? AND method = ? AND path = ? AND id != ?
                    """,
                    (new_domain_id, new_method, new_path, api_id),
                ).fetchone()
                if dup:
                    raise HTTPException(
                        status_code=409,
                        detail={
                            "code": 40301,
                            "message": "接口路径在该网管下已存在",
                            "details": {"method": new_method, "path": new_path, "domainId": new_domain_id},
                        },
                    )
```

Note: `body.model_fields_set` returns the set of fields the client explicitly sent in the PUT body (Pydantic v2). If `domain_id` isn't in the request, we preserve existing.

- [ ] **Step 5: 改 `duplicate_api` 的冲突查找（backend/app/admin/api_config.py:216-224）**

Find (approx lines 216-224):

```python
        suffix = 2
        while True:
            conflict = conn.execute(
                "SELECT id FROM api_configs WHERE method = ? AND path = ?",
                (row["method"], new_path),
            ).fetchone()
            if not conflict:
                break
            new_path = f"{original_path}_copy{suffix}"
            suffix += 1
```

Replace with:

```python
        suffix = 2
        while True:
            # 冲突判定：同域内不能同 (method, path)；未归类（domain_id=NULL）不受约束
            if row["domain_id"] is None:
                # 未归类接口的复制不做重复预检（跟 create/update 一致）
                break
            conflict = conn.execute(
                "SELECT id FROM api_configs WHERE domain_id = ? AND method = ? AND path = ?",
                (row["domain_id"], row["method"], new_path),
            ).fetchone()
            if not conflict:
                break
            new_path = f"{original_path}_copy{suffix}"
            suffix += 1
```

- [ ] **Step 6: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_apis_cross_domain.py -v`
Expected: 6 tests PASS

- [ ] **Step 7: 跑全套确认无回归**

Run: `cd backend && python -m pytest -q 2>&1 | tail -5`
Expected: 全部 PASS

- [ ] **Step 8: 提交**

```bash
git add backend/app/admin/api_config.py backend/tests/test_apis_cross_domain.py
git commit -m "$(cat <<'EOF'
feat(apis): CRUD 路径重复预检改为按域

- create_api / update_api / duplicate_api 的 (method, path) 重复检查
  统一加上 domain_id 条件
- 未归类接口 (domain_id=NULL) 不做重复预检，跟 SQLite NULL 语义一致
- 错误消息细化为"在该网管下已存在"
- +6 单测覆盖跨域可行 / 同域拦截 / NULL 允许 / update 换 path / duplicate 生成后缀

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Excel 导入按域匹配 + 更新 `_使用说明`

**Files:**
- Modify: `backend/app/admin/api_config.py`（import_apis 的匹配 SQL）
- Modify: `backend/app/admin/_api_excel.py`（`_write_instruction_sheet` 第 6 条文案）
- Modify: `backend/tests/test_apis_cross_domain.py`（追加 3 个导入相关测试）

- [ ] **Step 1: 写失败测试**

Append to `backend/tests/test_apis_cross_domain.py`:

```python
import io
from openpyxl import Workbook
from app.admin._api_excel import MAIN_HEADERS, UNCATEGORIZED_SHEET_NAME


def _build_xlsx(builder) -> bytes:
    wb = Workbook()
    wb.remove(wb.active)
    builder(wb)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _upload_xlsx(client, xlsx_bytes: bytes):
    return client.post(
        "/admin/api/apis/import",
        files={"file": ("t.xlsx", xlsx_bytes,
                         "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )


def test_import_cross_sheet_move_leaves_source_untouched(client):
    """Sheet A 有 /token；Excel 里 Sheet B 也有 /token → 导入后 A 保留、B 新建。"""
    dA = client.post("/admin/api/domains", json={"name": "网管A"}).json()["data"]["id"]
    dB = client.post("/admin/api/domains", json={"name": "网管B"}).json()["data"]["id"]
    a_id = client.post("/admin/api/apis", json={
        "method": "PUT", "path": "/rest/token", "name": "A-token",
        "domainId": dA, "dataSource": "static", "config": {},
    }).json()["data"]["id"]

    def build(wb):
        ws = wb.create_sheet("网管B")
        for i, h in enumerate(MAIN_HEADERS, start=1):
            ws.cell(row=1, column=i, value=h)
        ws.cell(row=2, column=1, value="PUT")
        ws.cell(row=2, column=2, value="/rest/token")
        ws.cell(row=2, column=3, value="B-token-from-excel")
        ws.cell(row=2, column=7, value="static")
    data = _build_xlsx(build)

    r = _upload_xlsx(client, data)
    assert r.status_code == 200
    result = r.json()["data"]
    assert result["created"] == 1
    assert result["updated"] == 0

    # 源 A 域接口不动
    a_detail = client.get(f"/admin/api/apis/{a_id}").json()["data"]
    assert a_detail["name"] == "A-token"
    assert a_detail["domainId"] == dA

    # 目标 B 域新建了一份
    b_apis = client.get(f"/admin/api/apis?domainId={dB}").json()["data"]["items"]
    assert any(a["path"] == "/rest/token" and a["name"] == "B-token-from-excel" for a in b_apis)


def test_import_same_domain_same_path_updates_that_row(client):
    """Excel Sheet=网管A 且行 (method, path) 命中 A 域下已有接口 → UPDATE 该行。"""
    dA = client.post("/admin/api/domains", json={"name": "网管A"}).json()["data"]["id"]
    a_id = client.post("/admin/api/apis", json={
        "method": "PUT", "path": "/rest/token", "name": "旧名",
        "domainId": dA, "dataSource": "static", "config": {},
    }).json()["data"]["id"]

    def build(wb):
        ws = wb.create_sheet("网管A")
        for i, h in enumerate(MAIN_HEADERS, start=1):
            ws.cell(row=1, column=i, value=h)
        ws.cell(row=2, column=1, value="PUT")
        ws.cell(row=2, column=2, value="/rest/token")
        ws.cell(row=2, column=3, value="新名")
        ws.cell(row=2, column=7, value="static")
    data = _build_xlsx(build)

    r = _upload_xlsx(client, data)
    assert r.json()["data"]["updated"] == 1
    detail = client.get(f"/admin/api/apis/{a_id}").json()["data"]
    assert detail["name"] == "新名"


def test_import_cross_domain_does_not_affect_other_domain(client):
    """A/B 两域各有 /token；Excel Sheet=A 只改 A 的 name → B 不受影响。"""
    dA = client.post("/admin/api/domains", json={"name": "网管A"}).json()["data"]["id"]
    dB = client.post("/admin/api/domains", json={"name": "网管B"}).json()["data"]["id"]
    aA = client.post("/admin/api/apis", json={
        "method": "PUT", "path": "/rest/token", "name": "A-orig",
        "domainId": dA, "dataSource": "static", "config": {},
    }).json()["data"]["id"]
    aB = client.post("/admin/api/apis", json={
        "method": "PUT", "path": "/rest/token", "name": "B-orig",
        "domainId": dB, "dataSource": "static", "config": {},
    }).json()["data"]["id"]

    def build(wb):
        ws = wb.create_sheet("网管A")
        for i, h in enumerate(MAIN_HEADERS, start=1):
            ws.cell(row=1, column=i, value=h)
        ws.cell(row=2, column=1, value="PUT")
        ws.cell(row=2, column=2, value="/rest/token")
        ws.cell(row=2, column=3, value="A-new")
        ws.cell(row=2, column=7, value="static")
    data = _build_xlsx(build)

    r = _upload_xlsx(client, data)
    assert r.json()["data"]["updated"] == 1

    assert client.get(f"/admin/api/apis/{aA}").json()["data"]["name"] == "A-new"
    assert client.get(f"/admin/api/apis/{aB}").json()["data"]["name"] == "B-orig"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_apis_cross_domain.py -v -k import_`
Expected: 3 new tests FAIL — 现有 `import_apis` 走全局 `(method, path)` 匹配，会把 A 域的接口更新掉 / 把 B 的接口拉过来做 UPDATE

- [ ] **Step 3: 改 `import_apis` 的匹配 SQL（backend/app/admin/api_config.py:873-876）**

Find (approx line 873):

```python
            existing = conn.execute(
                "SELECT id, config FROM api_configs WHERE method = ? AND path = ?",
                (method, path),
            ).fetchone()
```

Replace with:

```python
            # 按 (domain_id, method, path) 匹配；用 IS 而非 = 处理 NULL（未归类）
            existing = conn.execute(
                "SELECT id, config FROM api_configs WHERE domain_id IS ? AND method = ? AND path = ?",
                (domain_id, method, path),
            ).fetchone()
```

Note: `domain_id` is already resolved from `row.get("domain_id")` + auto-created-domain lookup a few lines above; that variable is already in scope in the same for-loop.

- [ ] **Step 4: 更新 `_write_instruction_sheet` 里的匹配规则文案（backend/app/admin/_api_excel.py）**

Find `_write_instruction_sheet` (search for `INSTRUCTION_SHEET_NAME`). Locate the numbered list — line 6 currently reads:

```python
        "6. 匹配规则：按 (方法, 路径) 全局匹配；命中 → 更新（含换域），未命中 → 新建。",
```

Replace with the following **two** lines (line 6 gets more explanation, and re-number is not needed since we replace inline):

```python
        "6. 匹配规则：按 (网管, 方法, 路径) 匹配；命中 → 更新，未命中 → 新建。",
        "   从一个 Sheet 剪切行粘到另一个 Sheet 只在目标网管里新增/更新，源网管里的接口不动；",
        "   若想真正跨网管迁移，请到 UI 手动删除源网管下那条。",
```

Adjust numbering of subsequent lines if needed (compare against current file — if the original 6th line was followed by 7, 8, 9, the added lines are un-numbered continuations of item 6, so 7/8/9 stay).

- [ ] **Step 5: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_apis_cross_domain.py -v`
Expected: 全部 9 tests PASS (6 from Task 2 + 3 new)

- [ ] **Step 6: 跑全套确认无回归**

Run: `cd backend && python -m pytest -q 2>&1 | tail -5`
Expected: 全部 PASS

- [ ] **Step 7: 提交**

```bash
git add backend/app/admin/api_config.py backend/app/admin/_api_excel.py backend/tests/test_apis_cross_domain.py
git commit -m "$(cat <<'EOF'
feat(apis): Excel 导入按 (domain, method, path) 匹配

- import_apis 的 upsert 查询加上 domain_id 条件（用 IS 处理 NULL）
- 跨 Sheet"移动"语义变更：源域接口保留，目标域 upsert
- _使用说明 Sheet 第 6 条更新，明确新匹配规则和迁移方式
- +3 单测覆盖跨 Sheet 移动 / 同域 UPDATE / 跨域不干扰

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: 停用 admin 8080 的 mock 路由挂载

**Files:**
- Modify: `backend/app/main.py`（删 lifespan 里两行 + 顶部 import）
- Modify: `backend/app/admin/api_config.py`（删 6 处 mock_registry 调用 + 内嵌 import）
- Modify: `backend/app/admin/settings.py`（删 1 处 reload 调用 + 顶部 import）

- [ ] **Step 1: 写失败测试（admin 8080 上 mock 路径应 404）**

Append to `backend/tests/test_apis_cross_domain.py`:

```python
def test_admin_8080_no_longer_mounts_mock_routes(client):
    """admin 端口停用 mock 服务后，任何 mock 路径打 admin 都应 404。"""
    d = client.post("/admin/api/domains", json={"name": "网管A"}).json()["data"]["id"]
    client.post("/admin/api/apis", json={
        "method": "GET", "path": "/api/some-mock", "name": "m",
        "domainId": d, "dataSource": "static",
        "config": {"staticBody": '{"ok":true}'},
    })
    # 直接打 mock 路径应 404（admin 上不再挂载）
    r = client.get("/api/some-mock")
    assert r.status_code == 404


def test_admin_still_serves_admin_api(client):
    """删掉 mock_registry 后 admin API 本身仍然可用。"""
    r = client.get("/admin/api/health")
    assert r.status_code == 200
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_apis_cross_domain.py::test_admin_8080_no_longer_mounts_mock_routes -v`
Expected: FAIL — 现在 admin 8080 仍然会通过 `mock_registry.load_all()` + `create_api` 里的 `register` 把 `/api/some-mock` 挂上，请求返回 200

- [ ] **Step 3: 删 `backend/app/main.py` 里的挂载**

Find and delete these lines:

```python
from app.mock.registry import registry as mock_registry
```

And in `lifespan`:

```python
    mock_registry.bind(app)
    mock_registry.load_all()
```

The resulting `lifespan` body should look like:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _runner
    init_db()

    _runner = InstanceRunner()
    _runner.start_monitor()
    app.state.instance_runner = _runner

    yield

    _cleanup()
```

- [ ] **Step 4: 删 `backend/app/admin/api_config.py` 里的 6 处 mock_registry 调用**

Search the file for `from app.mock.registry import registry as mock_registry` — there are 5 internal (function-scope) imports plus their usage. Also delete the following blocks:

**Location 1 — `duplicate_api` (approx lines 236-237):**

Delete:
```python
    from app.mock.registry import registry as mock_registry
    mock_registry.register(new_id, new_method, new_path)
```

**Location 2 — `create_api` (approx lines 314-316):**

Delete:
```python
    from app.mock.registry import registry as mock_registry
    mock_registry.register(detail.id, detail.method, detail.path)
```

**Location 3 — `update_api` (approx lines 426-428):**

Delete:
```python
    if route_changed:
        from app.mock.registry import registry as mock_registry
        mock_registry.update(detail.id, detail.method, detail.path)
```

Also remove the now-dead `route_changed` local variable a few lines above (line 424 `route_changed = body.method is not None or body.path is not None`).

**Location 4 — `delete_api` (approx lines 542-543):**

Delete:
```python
    from app.mock.registry import registry as mock_registry
    mock_registry.unregister(api_id)
```

**Location 5 — `import_apis` (approx lines 917-924):**

Delete this block:
```python
    # 事务成功后再挂载路由，避免回滚时留下幽灵路由
    if new_routes:
        from app.mock.registry import registry as mock_registry
        for rid, rmethod, rpath in new_routes:
            mock_registry.register(rid, rmethod, rpath)
```

Also remove `new_routes: list[tuple[str, str, str]] = []` list initialization and the `new_routes.append((api_id, method, path))` line inside the loop.

**Location 6 — `delete_directory` (approx lines 967-969):**

Delete:
```python
    if deleted_api_ids:
        from app.mock.registry import registry as mock_registry
        for aid in deleted_api_ids:
            mock_registry.unregister(aid)
```

Also remove `deleted_api_ids = [r["id"] for r in rows_to_delete]` and `rows_to_delete = conn.execute(...).fetchall()` a few lines up if now unused.

- [ ] **Step 5: 删 `backend/app/admin/settings.py` 里的 mock_registry.reload()**

Find and delete:
```python
from app.mock.registry import registry as mock_registry
```

And find the `mock_registry.reload()` call (approx line 169). It's inside a branch that handles `mock_path_prefix` changes. Delete the reload line but keep the surrounding logic (it may still do other things like updating DB). If the reload was the ONLY action inside a conditional block, remove the block entirely and add a comment:

```python
# mock_path_prefix 变更不再需要热重载 admin 8080 的路由——admin 不再挂载 mock 路由
```

Consult the surrounding code before applying to avoid breaking siblings.

- [ ] **Step 6: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_apis_cross_domain.py -v`
Expected: 全部 11 tests PASS (9 from Task 2-3 + 2 new)

- [ ] **Step 7: 跑全套确认无回归**

Run: `cd backend && python -m pytest -q 2>&1 | tail -5`
Expected: 全部 PASS

如果有个别测试依赖 `mock_registry` 或 `admin 8080 上 mock 路径可用`，属于旧行为的死忠测试，应删除或改造。

- [ ] **Step 8: 提交**

```bash
git add backend/app/main.py backend/app/admin/api_config.py backend/app/admin/settings.py backend/tests/test_apis_cross_domain.py
git commit -m "$(cat <<'EOF'
feat(apis): 停用 admin 8080 的 mock 路由挂载

- main.py lifespan 删掉 mock_registry.bind/load_all
- api_config.py 6 处 mock_registry.register/unregister/update 调用移除
  (duplicate/create/update/delete/import/delete_directory)
- settings.py 删除 mock_registry.reload 触发点
- mock 一律走实例端口（instance_app 按 domain_id 加载）
- mock/registry.py 模块保留为死代码，后续可清理
- +2 单测覆盖 mock 路径 404 / admin API 仍可用

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: 手动集成验证

**Files:** 无代码修改

- [ ] **Step 1: 停掉旧的开发后端进程，重启新版**

在 CLAUDE.md 里也提到：前后端测试完成后要关闭进程、释放端口。

```bash
# 先关掉当前 8080 上的旧后端（Ctrl+C 或结束进程）
cd backend && python -m app.main
# 前端如果没起
cd frontend && npm run dev
```

- [ ] **Step 2: 验证 admin 8080 上 mock 路径 404**

浏览器打开 http://localhost:8080/api/some-existing-mock-path — 应该 404。以前该路径能直接返回 mock 响应。

- [ ] **Step 3: 验证跨网管同名接口可创建**

UI 里：
1. 建两个网管 `网管A` / `网管B`
2. 在 `网管A` 下创建接口 `PUT /rest/plat/smapp/v1/oauth/token`
3. 在 `网管B` 下创建同 `PUT /rest/plat/smapp/v1/oauth/token`
4. 保存成功，两条接口都在

- [ ] **Step 4: 验证实例端口能正确返回**

1. 在 `网管A` 的拓扑上启一个实例，端口 6531
2. 在 `网管B` 的拓扑上启一个实例，端口 6532
3. `curl -X PUT http://localhost:6531/rest/plat/smapp/v1/oauth/token` 应返回 A 的响应
4. `curl -X PUT http://localhost:6532/rest/plat/smapp/v1/oauth/token` 应返回 B 的响应
5. 两个响应内容不同（因为 A/B 接口的 staticBody 不同）

- [ ] **Step 5: 验证 Excel 导入的跨 Sheet "移动"不再迁移**

1. 导出全量 Excel
2. 找到 `网管A` Sheet 里的 `PUT /rest/plat/.../token` 行，剪切
3. 粘到 `网管B` Sheet 底部
4. 保存 → 导入
5. 期望：**`网管A` 下 `token` 接口保留不动，`网管B` 下多了一份**（或 UPDATE 到 B 已有的那份）

- [ ] **Step 6: 关闭进程**

Ctrl+C 前后端；确认 `netstat -ano | findstr :8080` 无输出。

- [ ] **Step 7: 无代码变更，不提交**

---

## Self-Review Checklist（写完 plan 后自查记录）

- [x] **Spec 覆盖**：
  - 数据模型改动（UNIQUE 迁移）→ Task 1
  - Admin 8080 停用 mock 服务 → Task 4
  - Mock 实例运行时不改 → 由 Task 4 保护（instance_app 未在 diff 范围）
  - Excel 导入按域匹配 + 说明 Sheet 文案 → Task 3
  - CRUD 按域唯一性预检 → Task 2
  - 前端无改动 → 无 Task
  - 测试覆盖 11 条 → Task 1-4 分别覆盖

- [x] **占位扫描**：无 TBD / TODO；每步含实际代码/命令；一步一动作

- [x] **类型一致性**：
  - `domain_id` 参数类型 `Optional[str]` 贯穿 create_api / update_api / duplicate_api / import_apis
  - 迁移函数 `_rebuild_api_configs_domain_unique` 命名跟已有 `_expand_field_type_check` 风格一致
  - 40301 错误码贯穿 create/update 的重复预检
  - 测试文件命名 `test_apis_cross_domain.py` 跟 `test_apis_excel.py` 风格一致
