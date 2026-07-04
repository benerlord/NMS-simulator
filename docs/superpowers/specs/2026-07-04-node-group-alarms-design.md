# 节点组告警设计

**日期：** 2026-07-04
**状态：** 已批准，待写实施计划

---

## 目标

让节点组支持告警配置。用户在 GroupCreateModal 的第 4 步"告警"里手工加 N 条告警模板；所有虚拟节点共享同一份模板，但接口查询时按 `虚拟节点数 × N` 展开成独立告警行。同时打通"编辑现有节点组"的能力，让告警可在事后添加/修改。

**本 spec 是父项目"画布 Excel 导入导出（含节点组数据 + 告警数据）"的 Sub-project A**——先把节点组告警数据模型立住，然后 Sub-project B 的画布 Excel 导入导出才能包含完整数据。

---

## 设计原则

- **节点和节点组共用拓扑上的同一个 `alarm_schema_id`** — 不给节点组单独绑 schema
- **组告警是"模板"** — 所有虚拟节点共享；无"给个别虚拟节点覆盖"的能力
- **数据分层跟单节点告警严格对称** — 新建 `node_group_alarms` + `node_group_alarm_attrs` 镜像表；CRUD 端点、schema、行为一致
- **`mapping_target` 字段在 CTE 展开时从虚拟节点取值** — 不存到模板 attrs 里
- **UI 复用** — GroupCreateModal 加第 4 步，直接复用现有 `NodeAlarmsTab.vue` 组件

---

## 数据模型

### 新增两张表

```sql
CREATE TABLE IF NOT EXISTS node_group_alarms (
  id              TEXT PRIMARY KEY,               -- grp_alm_ + 12hex
  node_group_id   TEXT NOT NULL,
  alarm_index     INTEGER NOT NULL,               -- 在组内的序号（1, 2, 3, ...）
  created_at      TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (node_group_id) REFERENCES node_groups(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_group_alarms_grp ON node_group_alarms(node_group_id);

CREATE TABLE IF NOT EXISTS node_group_alarm_attrs (
  alarm_id        TEXT NOT NULL,
  field_key       TEXT NOT NULL,
  value           TEXT,
  PRIMARY KEY (alarm_id, field_key),
  FOREIGN KEY (alarm_id) REFERENCES node_group_alarms(id) ON DELETE CASCADE
);
```

### 为什么这样

- 跟 `node_alarms` / `node_alarm_attrs` 完全对称，CRUD 代码几乎能复用
- `alarm_index` 语义跟 `node_alarms.alarm_index` 一致（组内第 N 条模板）
- **不给 `node_groups` 加 `alarm_schema_id` 列**——用拓扑的 `topologies.alarm_schema_id`

### 级联删除

- 拓扑删 → `node_groups` 删（现有）→ `node_group_alarms` 删（新级联）→ `node_group_alarm_attrs` 删
- 拓扑换 alarm_schema → 节点组告警 attrs 里字段 key 可能失效（跟节点级告警一样的问题，同样处理，不做特殊清理）

### 迁移

幂等追加两条 `CREATE TABLE IF NOT EXISTS` + 索引，放在 `run_migrations` 中。无表重建，无风险。

---

## CTE 视图和查询语义

### 现状

`_build_alarms_cte` 生成 `alarms` CTE：`node_alarms JOIN nodes LEFT JOIN node_alarm_attrs`，按 `alarm_schema_fields` pivot 成列，`WHERE n.topology_id = :__tid__` 过滤。只覆盖物理节点告警。

### 改动

**扩展 `alarms` CTE 走 UNION ALL：物理节点告警 + 节点组虚拟告警。**

对使用方（SQL 数据源接口）透明——同一张 `alarms` 表能查到两类告警行，字段列完全一致。

### 节点组虚拟告警的 SQL 展开

概念：
```
group_nodes（虚拟节点视图，1 行/虚拟节点）
  CROSS JOIN node_group_alarms（组的告警模板，N 行/组）
  LEFT JOIN node_group_alarm_attrs（模板字段值）
  = 每虚拟节点 × 组告警条数 行
```

具体字段：
- **id** 用合成键：`'gna_' || group_node_id || '_' || alarm_index`，保证 UNION 里唯一
- **node_id** = `group_nodes.id`（虚拟节点 id，跟 `topology_nodes` 里一致）
- **node_name** / **node_dn** = 虚拟节点的 name / dn
- **alarm_index** = `node_group_alarms.alarm_index`
- **created_at** / **updated_at** = `node_group_alarms.created_at / updated_at`

### `mapping_target` 兼容

`alarm_schema_fields.mapping_target` 现有语义：告警字段的值来自节点某个属性，创建单节点告警时 INSERT 自动代入。

对**组告警模板**：
- 模板里就**不存**这些映射字段的值（值是"运行时"的）
- CTE 构建时（`_build_alarms_cte`）读 `alarm_schema_fields.mapping_target` 元数据，字段一条一条决定 SELECT 表达式：

```sql
-- 无 mapping_target 的字段（如"告警描述"）：从模板取
MAX(CASE WHEN gaa.field_key='desc' THEN gaa.value END) AS desc

-- 有 mapping_target='node.dn' 的字段（如"设备DN"）：从虚拟节点取
gn.dn AS device_dn
```

单节点告警走原路径不变。

---

## CRUD 端点

镜像现有 `/nodes/{id}/alarms`，前缀换成 `/node-groups/{id}/alarms`：

| Method | Path | 说明 |
|---|---|---|
| `GET` | `/admin/api/node-groups/{gid}/alarms` | 列出该组所有告警模板（按 `alarm_index` 排序） |
| `POST` | `/admin/api/node-groups/{gid}/alarms` | 新增一条告警模板 |
| `PUT` | `/admin/api/node-group-alarms/{aid}` | 更新告警模板的 attrs |
| `DELETE` | `/admin/api/node-group-alarms/{aid}` | 删除一条告警模板 |

响应/请求 schema 参照现有 `node_alarm.py` 直接改名并把 `node_id → node_group_id`。字段值仍是 `attrs: dict[str, Any]`。

### 行为细节（跟节点级严格一致）

- **拓扑未绑 alarm_schema 时创建告警** → 409 + `code=40901`，"该拓扑未绑定告警模板"
- **默认值填充**：POST 时，缺失的字段 key 从 `alarm_schema_fields.default_value` 取。复用 `_alarm_utils.py::resolve_default_attrs`
- **`mapping_target` 字段**：POST/PUT 时**不接受**这些字段的值（服务端拒绝或静默丢弃）——理由：这些字段在 CTE 展开时从节点取，模板里存了也没用；跟单节点告警一致
- **必填校验**：`required=1` 的字段缺值时报 422，跟单节点告警一致
- **`alarm_index` 编号**：POST 时后端自动分配 = 当前最大 index + 1；删除中间的告警时 index 不重排（跟单节点行为一致）

### 新增文件

- `backend/app/admin/node_group_alarm.py` — 新 router，仿照 `node_alarm.py`
- `backend/app/main.py` — `include_router`

### 不改

- `alarm_schema.py`（schema 定义不动）
- `node_alarm.py`（单节点告警不动）
- `_alarm_utils.py`（复用 `resolve_default_attrs` 之类）

---

## UI 改动

### GroupCreateModal 加第 4 步"告警"

| # | Step 名 | 内容 |
|---|---|---|
| 1 | 基础信息 | node_type / 组名 / 数量 / 命名模板 |
| 2 | 属性策略 | attr_strategies |
| 3 | 连接规则 | edge_strategies |
| **4** | **告警** | **告警模板列表（新增）** |

**第 4 步内容：**

- 顶部提示"当前拓扑绑定的告警模板：`<schema.name>`"（拉 `topologies.alarm_schema_id → alarm_schemas.name`）
- 若拓扑未绑 schema：整个 step 显示提示"当前拓扑未绑定告警模板，请先到拓扑管理页面绑定"，禁用"新增告警"按钮；**允许用户直接提交表单不加告警**（等同零条告警模板）
- 列表 UI：**直接复用现有 `NodeAlarmsTab.vue`**（已实现字段折叠、逐条编辑、mapping_target 字段禁用等能力），数据源从 `nodeId` 换成 `nodeGroupId`
- 提交时：整份告警数组随 form 一起 POST；如果是"编辑现有组"模式，走告警的独立 CRUD（对比新旧告警数组算 diff → 分别调用 POST/PUT/DELETE）

**跳步：** step 4 无强校验（允许零告警）。"下一步" step 4 转成"确定"按钮触发最终提交。step 1 的必填校验保持不变。

### 编辑现有组的入口打通

- CanvasView 右键菜单里"编辑组定义"已 emit `edit-group` 事件——接进 `editingGroupId` state；打开 Modal 时 `mode='edit'` + 载入现有值
- Modal 标题：新建"创建节点组"，编辑"编辑节点组"

**编辑模式下字段可改性：**

| 字段 | 可改？ | 理由 |
|---|---|---|
| 基础信息 · 节点类型 (`node_type_id`) | ❌ 只读 | 改了会破坏已配的 attr_strategies（字段 key 全变） |
| 基础信息 · 组名 / 数量 / 命名模板 | ✅ | 无 side-effect（数量变更不物化就是虚拟节点数变化，CTE 自动跟上） |
| 属性策略 | ✅ | 直接改 attr_strategies |
| 连接规则 | ✅ | 直接改 edge_strategies |
| 告警 | ✅ | 走 diff → CRUD |

**已被 materialize 的组**：编辑不会回溯改动到已生成的物理节点。给一个警告 banner："该组已展开，编辑不会影响已生成的实体节点"。

### API 层（前端 `@/api/`）

- `nodeGroup.ts` 加 alarm 子对象：`listAlarms(groupId)` / `createAlarm(groupId, body)` / `updateAlarm(alarmId, body)` / `deleteAlarm(alarmId)`
- `NodeAlarmsTab.vue` 加 prop `context: 'node' | 'group'` 决定调哪套 API（复用组件，不拆两份）

---

## Materialize 行为

现有 `POST /node-groups/{id}/materialize` 把组展开成实体节点（N 个 `nodes` + attrs 行）。**扩展：为每个新建物理节点，把组的 M 条告警模板 copy 成 M 条 `node_alarms` + `node_alarm_attrs`**，用组模板的字段值 + mapping_target 从新物理节点 attrs 代入。

**关键行为：**

- 复用现有 `node_alarm.py` 的 INSERT 路径（同时 apply `resolve_default_attrs` + `mapping_target`）
- 事务边界：materialize 现有事务扩展，把 alarms 插入包在同一个事务里；任一失败整体回滚
- 进度上报（WS `group.materialize.progress`）：现有的 5000 批量刷新粒度里加"当前批次告警插入完成 X 条"
- 空告警组：materialize 时按 0 条告警处理，跟今天完全一样

---

## 测试计划

### 后端 CRUD 测试

新文件 `backend/tests/test_node_group_alarm_router.py`：

1. GET 空列表（新组无告警）→ `[]`
2. POST 一条告警 → 成功；`alarm_index=1`；attrs 里 default_value 已填；mapping_target 字段不接受
3. POST 第二条 → `alarm_index=2`
4. PUT 更新 attrs → 覆盖；未改字段保留
5. DELETE 一条 → CASCADE 清 attrs
6. 拓扑未绑 alarm_schema 时 POST → 409 + 40901
7. 删除节点组 → 告警 + attrs 全部 CASCADE 清

### CTE 视图测试

追加到 `backend/tests/test_cte_alarms.py`：

8. 一个组 2 虚拟节点 + 3 条告警模板 → `SELECT * FROM alarms` 返回 6 行（2×3）
9. 告警字段配 mapping_target='node.dn' → 每行的 device_dn 是各自虚拟节点的 dn
10. 混合场景：3 个物理节点各 1 条告警 + 1 组 100 虚拟节点 × 2 条告警 → 总共 3 + 200 = 203 行
11. 拓扑无 alarm_schema → alarms CTE 不生成（跟现有一致）
12. UNION ALL 里 id 唯一性：物理告警 `alm_xxx` vs 虚拟 `gna_<vnode_id>_<index>`

### Materialize 测试

追加到 `backend/tests/test_materialize_alarms.py`：

13. 组 5 虚拟节点 + 2 条告警模板 → materialize → 5 个 `nodes` + 10 条 `node_alarms`
14. 组 0 条告警 → materialize → 5 个 `nodes` + 0 条告警（跟今天一致）
15. Materialize 期间告警 INSERT 失败 → 事务回滚，物化前状态

### 前端手工验证

- 新建节点组：走完 4 步流程，告警字段能填、mapping_target 灰置 + 提示；提交后画布上宏节点显示（如果有告警角标 UX）
- 编辑现有组：右键"编辑组定义"能进 Modal；节点类型只读；告警可增删改；提交后 CTE 查得到新数据
- 拓扑未绑 schema 场景：告警 step 显示提示 + 禁用按钮 + 允许无告警提交

---

## 实施边界（本次改的 / 不改的）

**改：**

- `backend/app/db/migrations.py` — 追加两张表 + 索引
- 新 `backend/app/admin/node_group_alarm.py` — router
- `backend/app/main.py` — `include_router`
- `backend/app/admin/node_group.py::materialize` — 扩展插告警
- `backend/app/core/cte_builder.py::_build_alarms_cte` — UNION ALL 虚拟告警
- `frontend/src/api/nodeGroup.ts` — 加 alarm CRUD
- `frontend/src/components/canvas/GroupCreateModal.vue` — 4th step + 编辑模式
- `frontend/src/components/canvas/NodeAlarmsTab.vue` — 加 `context` prop
- `frontend/src/views/CanvasView.vue` — 接入 `editingGroupId`

**不改：**

- `node_alarm.py` / 单节点告警数据路径
- `alarm_schema.py` / schema 定义
- 前端 `NodeAlarmsPanel` / 节点级告警 UI

---

## 上线切换

- **迁移自动执行**：下次 `python -m app.main` 启动时触发 `run_migrations`，无需人工操作
- **无 UI 灰度**：直接切换到 GroupCreateModal 4-step 版本
- **回滚**：代码回退即可；新表若已有数据，回退后代码不再访问（不影响）
