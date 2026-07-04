# 跨网管同名接口设计（放宽 UNIQUE 约束）

**日期：** 2026-07-04
**状态：** 已批准，待写实施计划

---

## 目标

允许不同网管/设备（domain）下存在同 `(method, path)` 的接口，例如 `PUT /rest/plat/smapp/v1/oauth/token` 可以在 "华为 ManageOne" 和 "H3C iMC" 各有一份、返回各自的响应。当前 `api_configs.UNIQUE(method, path)` 全局约束阻止这一场景。

---

## 设计原则

- **数据模型往"按域唯一"移**：从全局唯一改为 `UNIQUE(domain_id, method, path)`
- **admin 端口 8080 停用 mock 服务**：mock 一律走实例端口，端口天然按域隔离
- **Excel 导入不再支持"跨 Sheet 移动 = 换域"**：源域接口保留，目标域 upsert；跨域迁移改由 UI 手动完成
- **前端无需改动**：`ApiConfigTable.vue` 已是按域分组视图，重复接口在各自目录下自然显示

---

## 数据模型

### 迁移

`api_configs` 表约束从 `UNIQUE(method, path)` 改为 `UNIQUE(domain_id, method, path)`。SQLite 不支持 `DROP CONSTRAINT`，需要通过重建表迁移：

```sql
BEGIN;
CREATE TABLE api_configs_new (
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
);
INSERT INTO api_configs_new SELECT
  id, name, method, path, enabled, group_name, data_source, topology_id,
  sql_text, config, created_at, updated_at, domain_id, category
FROM api_configs;
DROP TABLE api_configs;
ALTER TABLE api_configs_new RENAME TO api_configs;
-- 重建原有索引
CREATE INDEX IF NOT EXISTS idx_apis_enabled ON api_configs(enabled);
CREATE INDEX IF NOT EXISTS idx_apis_topo    ON api_configs(topology_id);
CREATE INDEX IF NOT EXISTS idx_apis_group   ON api_configs(group_name);
CREATE INDEX IF NOT EXISTS idx_apis_domain  ON api_configs(domain_id);
COMMIT;
```

放进 `backend/app/db/migrations.py` 幂等段，用 `PRAGMA user_version` 或"表是否已有新约束"来判定。

**未归类接口（`domain_id IS NULL`）：** SQLite 的 UNIQUE 视 NULL 互异，多条 `未归类` 接口可以共享 `(method, path)`。属于"临时未分类"状态，不做额外校验。用户归类到某个网管时，会走该网管内的唯一性检查。

**迁移风险：** 几乎为零。约束仅"放宽"，任何原来合法的数据仍合法。开发环境当前查询 `SELECT method, path, COUNT(*) c FROM api_configs GROUP BY method, path HAVING c > 1` 返回 0 行，迁移前后行数不变。

---

## Admin 端口 8080 的 mock 行为

**完全停用 admin 8080 的 mock 服务。** admin 端口 8080 只剩 `/admin/api/*` 管理面 + `/admin/ws`；mock 一律走实例端口（`InstanceRunner` 起的子进程，一网管一端口）。

### 改动点

- `backend/app/main.py`：删除 lifespan 里的 `mock_registry.bind(app)` 与 `mock_registry.load_all()` 两行
- `backend/app/admin/api_config.py`：删除 5 处 `mock_registry.register / unregister / update` 调用：
  - `create_api`（成功后 register 新路由）
  - `update_api`（path/method 变更后 update）
  - `delete_api`（删除时 unregister）
  - `duplicate_api`（复制新增时 register）
  - `import_apis`（导入新建时批量 register）
- `backend/app/admin/settings.py`（如果有 `mock_path_prefix` 触发 `mock_registry.reload()` 的逻辑）：一并删除
- `backend/app/mock/registry.py` 本身：**保留为死代码**，避免连坐；后续单独 PR 清理

### UI "测试" 按钮

`POST /admin/api/apis/{id}/test` 是内部直接调用 pipeline，不走 HTTP 路由，**继续可用**。

---

## Mock 实例运行时（instance_app）

**无需改动。** `backend/app/mock/instance_app.py` 已经按 `domain_id` 加载接口：

```python
rows = conn.execute(
    "SELECT id, method, path FROM api_configs "
    "WHERE domain_id = ? AND enabled = 1",
    (domain_id,),
).fetchall()
```

每个实例是独立 uvicorn 子进程，只挂自己域下的接口，端口天然隔离。放宽全局约束后，两个域下的同名接口分别在自己实例端口上服务，各不干扰。

---

## Excel 导入匹配键变更

### 匹配条件

从 `WHERE method=? AND path=?` 改成 `WHERE domain_id IS ? AND method=? AND path=?`。用 `IS` 而不是 `=` 是为了正确处理 NULL（未归类）。

### 跨 Sheet 移动的语义变化

**之前（全局唯一）：** 剪切一行从 Sheet A 粘到 Sheet B，导入 = 同一个 API 换域。

**之后（按域唯一）：** 剪切粘贴意味着"在 Sheet B 对应域里 upsert 这个 (method, path)"，**源域里的旧接口保留不动**。

| 场景 | 行为 |
|---|---|
| Sheet B 域下已有同 (method, path) | UPDATE 那条 |
| Sheet B 域下没有 | INSERT 一条新的到 B 域 |
| 副作用：源 A 域的旧接口 | **保留不动**（跟"未在 Excel 中出现的接口保留不删"一致） |

Excel 层面不再支持"移动接口"。用户想真正"把接口从 A 域搬到 B 域"，得到 UI 手动删除 A 域下那条。

### `_使用说明` Sheet 更新

`_write_instruction_sheet` 中第 6 条改成：

> 匹配规则：按 (网管, 方法, 路径) 匹配；命中 → 更新，未命中 → 新建。
>
> 从一个 Sheet 剪切行粘到另一个 Sheet 只会在目标网管里新增/更新，**源网管里的接口不动**。若想真正"跨网管迁移"，请到 UI 手动删除源网管下那条。

### 导入端点响应

无字段变化。`{created, updated, errors, warnings, autoCreatedDomains}` 保持。

---

## CRUD 唯一性校验

如果 `create_api` / `update_api` 内有"全局 (method, path) 唯一性预检"逻辑，改成按 `(domain_id, method, path)` 检查。（否则依赖 DB 层 UNIQUE 抛 IntegrityError 也可以，但预检可以给出更友好的错误码/消息。）

---

## 前端

**无改动。**

- `ApiConfigTable.vue` 已按域分组显示，两个域下的同 `(method, path)` 接口自然出现在各自网管的目录下
- `ApiConfigModal.vue` 的创建/编辑弹窗不做前端唯一性预检（依赖后端返回错误提示），本次也不动

---

## 测试计划

### 迁移测试（`backend/tests/test_migrations_*.py` 或新增 `test_migrations_cross_domain_apis.py`）

1. 迁移前造 3 条数据（其中两条跨域同 `(method, path)`，两条 `domain_id=NULL` 同 `(method, path)`）→ 跑迁移 → 全部保留
2. 迁移后：`INSERT` 一条已存在域下同 `(method, path)` → 抛 `IntegrityError`
3. 迁移后：`INSERT` 两条 `domain_id=NULL` 同 `(method, path)` → 都成功

### CRUD 测试（`backend/tests/test_api_config_router.py` 或新增）

4. 同域重复：POST 两个同域同 `(method, path)` → 第二个 400（错误码含"已存在"提示）
5. 跨域重复：POST 两个跨域同 `(method, path)` → 都 200
6. 未归类重复：POST 两个 `domain_id=NULL` 同 `(method, path)` → 都 200

### Excel 导入测试（`backend/tests/test_apis_excel.py`）

7. 跨 Sheet 同名"移动"：源域已有 `PUT /token`，Excel 里 Sheet=目标域 有同 `PUT /token` → 导入后源域接口保留、目标域新建
8. 同 Sheet 内 (method, path) 命中：正常 UPDATE 该 Sheet 域下那条
9. 跨域不冲突验证：预置两个 `PUT /token`（分属 A、B 两域），导入 Sheet=A 修改 A 的 name → 只改 A、B 未动

### Mock 路由测试（`backend/tests/test_smoke.py` 或新增）

10. admin 8080 启动后：任一 mock 路径打 8080 → 404（因为路由不再挂）

### 实例运行时

11. 因为 `instance_app.py` 未改动，不新增测试；现有测试（如果有）保持绿。

---

## 上线切换

- **迁移自动执行**：下次 `python -m app.main` 启动时触发 `run_migrations`，无需人工操作
- **无 UI 灰度**：管理端行为不变；调用方需知悉 mock 已只走实例端口（历史上如果有人 curl 8080 打 mock，需切到实例端口）
- **回滚**：如果有问题，回退代码即可；数据库层面因为只是"放宽"约束，回退时若无跨域重复数据则可继续用；有跨域重复数据则回退失败（需人工清理重复）
