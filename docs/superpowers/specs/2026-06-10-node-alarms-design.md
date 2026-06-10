# 节点告警数据 — 设计方案

> **状态：** 设计稿 / 待实施
> **日期：** 2026-06-10
> **关联文档：** `docs/数据库表设计.md`、`docs/系统架构设计.md`、`CLAUDE.md`

---

## 1. 背景与目标

NMS Mock 当前在画布上模拟拓扑（节点 + 边）并通过 mock 接口对外提供节点/边数据。**告警**是真实网管系统接口里几乎必须的一类数据，本期补足这一空白。

**用户需求三条：**
1. 画布中每个节点默认有 1 条告警数据，支持自定义新增和删除
2. 不同网管系统返回的告警数据结构不一样，需要支持多种结构定义
3. 在画布加告警数据后，要能在 API 配置页面新建接口、通过 SQL 查询拿到告警

**设计目标：**
- 告警结构可参数化（适配不同 NMS 系统）
- 告警数据使用与现有节点属性一致的"K-V + CTE pivot"模式，复用现有能力
- 告警通过通用 CTE `alarms` 暴露给 SQL 编辑器，用户自由写 SELECT

---

## 2. 关键设计决策（已对齐）

| # | 决策点 | 选择 | 理由 |
|---|--------|------|------|
| 1 | 告警结构差异性的颗粒度 | **全局告警模板，独立 CRUD（路径 C）** | 模板可复用，类似节点类型 |
| 2 | 告警模板挂在哪一层 | **拓扑级别** | 1 拓扑 = 1 NMS 系统，最贴合现实 |
| 3 | "默认 1 条告警" 语义 | **节点创建时自动 INSERT 1 行**（按 default_value 填充） | 直观可见、可删可改 |
| 4 | 告警字段类型 | **复用现有 4 种：text / number / select / boolean** | YAGNI，复用 FieldEditor |
| 5 | 告警数据存储 | **K-V 表 + CTE pivot**（同节点属性） | 一致性高，CTE 列推导无缝复用 |
| 6 | API 生成方式 | **仅暴露 `alarms` CTE，用户在 SQL 编辑器手写** | 简单、灵活、低实现成本 |
| 7 | 节点属性面板 UI | **顶部 Tab 切换："属性" / "告警(N)"** | 隔离清晰 |
| 8 | 切换模板 + 已有告警 | **X3 — 清空已有告警（带二次确认）** | 避免 CTE 列与数据不一致 |
| 9 | 删除被引用的模板 | **Y1 — 禁删**（仿 node_types/node_groups） | 与现有引用检查一致 |
| 10 | 模板字段增删改 | **Z1 — 与 node_type_fields 同策略**（宽松） | 避免引入"已有数据"特殊路径 |
| 11 | 实现路径 | **路径 1：新建独立表** | 概念干净，长期可扩展 |

---

## 3. 数据模型

### 3.1 新表

#### `alarm_schemas` — 告警模板主表
| 列 | 类型 | 说明 |
|----|------|------|
| `id` | TEXT PK | 前缀 `as_` |
| `code` | TEXT UNIQUE NOT NULL | SQL 标识符（暂不用于 CTE 名，CTE 固定 `alarms`，留作未来扩展） |
| `name` | TEXT NOT NULL | 模板显示名 |
| `description` | TEXT | 备注 |
| `created_at` | TEXT NOT NULL DEFAULT datetime('now') | |
| `updated_at` | TEXT NOT NULL DEFAULT datetime('now') | |

#### `alarm_schema_fields` — 告警字段定义
结构对齐 `node_type_fields`：

| 列 | 类型 | 说明 |
|----|------|------|
| `id` | INTEGER PK AUTOINCREMENT | |
| `alarm_schema_id` | TEXT NOT NULL | FK → `alarm_schemas(id)` ON DELETE CASCADE |
| `field_key` | TEXT NOT NULL | SQL 列名，需 `is_valid_ident` 校验 |
| `field_label` | TEXT NOT NULL | UI 显示名 |
| `field_type` | TEXT NOT NULL | CHECK IN (`text`, `number`, `select`, `boolean`) |
| `default_value` | TEXT | 自动插入默认告警时使用 |
| `options` | TEXT | select 类型逗号分隔选项 |
| `required` | INTEGER NOT NULL DEFAULT 0 | |
| `max_length` | INTEGER | text 类型字符长度上限 |
| `sort_order` | INTEGER NOT NULL DEFAULT 0 | |
| UNIQUE (`alarm_schema_id`, `field_key`) | | |

#### `node_alarms` — 告警实例
| 列 | 类型 | 说明 |
|----|------|------|
| `id` | TEXT PK | 前缀 `alm_` |
| `node_id` | TEXT NOT NULL | FK → `nodes(id)` ON DELETE CASCADE |
| `alarm_index` | INTEGER NOT NULL | 节点内自增序号 (1, 2, 3…)，决定排序和摘要显示 |
| `created_at` | TEXT NOT NULL DEFAULT datetime('now') | |
| `updated_at` | TEXT NOT NULL DEFAULT datetime('now') | |
| INDEX (`node_id`) | | |

#### `node_alarm_attrs` — 告警字段值 K-V
| 列 | 类型 | 说明 |
|----|------|------|
| `alarm_id` | TEXT NOT NULL | FK → `node_alarms(id)` ON DELETE CASCADE |
| `field_key` | TEXT NOT NULL | |
| `value` | TEXT | |
| PRIMARY KEY (`alarm_id`, `field_key`) | | |
| INDEX (`field_key`) | | |

### 3.2 现有表改动

`topologies` 新增列：
- `alarm_schema_id TEXT` — FK → `alarm_schemas(id)`，可空（NULL 表示未启用告警）

**迁移**：使用幂等 `ALTER TABLE` 模式（沿用现有约定）。

### 3.3 关键不变量

- 一个拓扑最多挂一个告警模板（FK 单值）
- 删除节点 → 级联删除告警（FK CASCADE）
- 删除告警模板前必须检查 `topologies.alarm_schema_id` 引用，被引用则禁删
- 拓扑切换 / 解绑模板时清空该拓扑下所有节点的告警（带二次确认）
- 节点告警字段值的 `field_key` 必须存在于绑定模板的 `alarm_schema_fields` 中

### 3.4 ID 前缀新增

| 前缀 | 实体 |
|------|------|
| `as_` | 告警模板 |
| `alm_` | 告警实例 |

---

## 4. 后端 API

### 4.1 告警模板 CRUD（新 router `admin/alarm_schema.py`）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/admin/api/alarm-schemas` | 列表 |
| GET | `/admin/api/alarm-schemas/{id}` | 详情（含 fields） |
| POST | `/admin/api/alarm-schemas` | 新建（含 fields） |
| PUT | `/admin/api/alarm-schemas/{id}` | 更新（fields 全量替换，沿用 node_type 策略） |
| DELETE | `/admin/api/alarm-schemas/{id}` | 删除 — 引用检查 |

### 4.2 拓扑挂载告警模板（在 `admin/topology.py` 加端点）

```
PATCH /admin/api/topologies/{id}/alarm-schema
body: { alarmSchemaId: string | null, clearExisting: boolean }
```

**逻辑：**
- 拓扑没绑任何模板 / 没告警数据 → 直接更新 FK
- 拓扑已有 `node_alarms` 数据 + 切换 / 解绑 → 必须 `clearExisting=true` 否则返 409
- `clearExisting=true` → 事务内：
  1. `DELETE FROM node_alarms WHERE node_id IN (SELECT id FROM nodes WHERE topology_id = ?)`
  2. 更新 `topologies.alarm_schema_id`

**`GET /admin/api/topologies/{id}`** 返回值附加：
- `alarmSchemaId`
- `nodeAlarmCount`（用于前端判断是否需要二次确认）

### 4.3 节点告警增删改（新 router `admin/node_alarm.py`）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/admin/api/nodes/{node_id}/alarms` | 列出节点告警（按 alarm_index 排序，含 attrs） |
| POST | `/admin/api/nodes/{node_id}/alarms` | 新增 1 条（用模板 default_value 填充未传字段） |
| PUT | `/admin/api/alarms/{alarm_id}/attrs` | 更新告警属性（沿用 set_node_attrs 的 max_length 校验） |
| DELETE | `/admin/api/alarms/{alarm_id}` | 删除一条告警 |

### 4.4 节点创建路径自动插入默认告警

**改造 `admin/node.py` 的 `POST /admin/api/topologies/{id}/nodes`：**
- 创建节点成功 → 检查拓扑 `alarm_schema_id`
- 已挂模板 → 同事务内 INSERT 1 条 `node_alarms` + 用模板 `default_value` 填充 `node_alarm_attrs`

**改造 `admin/node_group.py` 的 `materialize`：**
- 每个物化产生的实体节点 → 同样 +1 条默认告警
- 批量场景沿用现有 5000 条 batch flush 策略

### 4.5 引用检查与错误格式

沿用现有 `node_groups` 引用检查的响应结构：

```json
{
  "code": 40901,
  "message": "告警模板被以下拓扑引用，无法删除",
  "details": { "referencedBy": ["拓扑A", "拓扑B"] }
}
```

切换模板未带 `clearExisting`：

```json
{
  "code": 40902,
  "message": "拓扑下有告警数据，请确认是否清空",
  "details": { "nodeAlarmCount": 132 }
}
```

---

## 5. CTE 暴露：`alarms` 视图

### 5.1 动态生成规则

`cte_builder.py` 新增 `_build_alarms_cte(conn, topology_id) -> dict | None`：

- 查拓扑的 `alarm_schema_id` → 若为 NULL → 返回 None（不发射 CTE）
- 查模板的 fields → 用 `is_valid_ident` 过滤
- 字段名与固定列冲突时跳过该字段 pivot（不报错），固定列优先
- 加入 `collect_views(...)` 返回的 `generic` 列表

### 5.2 固定列

| 列 | 来源 |
|----|------|
| `id` | `node_alarms.id` |
| `node_id` | `node_alarms.node_id` |
| `node_name` | JOIN `nodes.name` |
| `node_dn` | JOIN `nodes.dn` |
| `alarm_index` | `node_alarms.alarm_index` |
| `created_at` | `node_alarms.created_at` |
| `updated_at` | `node_alarms.updated_at` |

### 5.3 Pivot 列

每个 `field_key` 通过 `MAX(CASE WHEN aa.field_key = 'xxx' THEN aa.value END) AS xxx` 拉宽。

### 5.4 SQL 形态

```sql
WITH alarms AS (
  SELECT a.id, a.node_id, n.name AS node_name, n.dn AS node_dn,
         a.alarm_index, a.created_at, a.updated_at,
         MAX(CASE WHEN aa.field_key = 'alarm_id'    THEN aa.value END) AS alarm_id,
         MAX(CASE WHEN aa.field_key = 'severity'    THEN aa.value END) AS severity,
         MAX(CASE WHEN aa.field_key = 'occurred_at' THEN aa.value END) AS occurred_at
    FROM node_alarms a
    JOIN nodes n ON n.id = a.node_id
    LEFT JOIN node_alarm_attrs aa ON aa.alarm_id = a.id
   WHERE n.topology_id = :__tid__
   GROUP BY a.id
)
SELECT * FROM alarms WHERE severity = 'critical' LIMIT 100
```

### 5.5 SQL 编辑器视图清单（`admin/sql_helper.py`）

- `GET /admin/api/sql/views/{topology_id}` 返回的视图清单里，自动加入 `alarms` 视图 + 它的动态列定义
- 未挂模板的拓扑：不展示 `alarms` 项

---

## 6. 前端 UI

### 6.1 告警模板管理（类型管理页第 3 Tab）

**`TypesView.vue`** 加 Tab "告警模板"。复用骨架：

- `components/alarmSchemas/AlarmSchemaTable.vue`
- `components/alarmSchemas/AlarmSchemaModal.vue`
- `components/alarmSchemas/AlarmSchemaFieldEditor.vue`（复制自 `NodeTypeFieldEditor.vue`）
- `composables/useAlarmSchemas.ts` + `api/alarmSchema.ts`

删除模板被引用 → 弹错提示 + 列出引用拓扑名。

### 6.2 拓扑绑定告警模板

**`TopologyModal.vue`** 新增"告警模板"下拉（可空）：

- 新建拓扑：直接选择 → 一并保存
- 编辑拓扑：变更模板 → 前端根据 `nodeAlarmCount` 决定
  - = 0：直接 PATCH
  - \> 0：Modal 二次确认 → 确认后带 `clearExisting=true` PATCH

### 6.3 节点属性面板 Tab 化

**`NodeAttrsPanel.vue`** 顶部加 Antd `Tabs`：

| Tab | 内容 |
|-----|------|
| 属性 | 现有节点名 + 属性表单原封不动 |
| 告警(N) | `NodeAlarmsTab.vue` 子组件 |

**`NodeAlarmsTab.vue`：**
- 拓扑未挂模板：Tab 禁用 + 灰底提示
- 已挂模板：
  - **"+ 新增告警" 按钮** —— 点击立即 POST 创建（与节点创建时自动 +1 行为一致），后端用 `default_value` 填充，前端拿到新 `alarm_id` 后插入列表展开编辑
  - 告警列表：每条 Antd `Collapse` 折叠卡片
    - 标题 = 第一个字段值（sort_order 最小）+ `#{alarm_index}` 后缀
    - 展开后表单按模板字段渲染（4 种类型组件，与节点属性表单逻辑一致）
    - 卡片右上角 × 删除 —— 点击立即 DELETE
    - required + max_length 校验，沿用 NodeAttrsPanel 的滚动聚焦体验

**保存语义（点击底部"保存"按钮）：**
- 当前面板的节点名、节点属性、所有 dirty 告警按"逐个 PUT"顺序提交（不是原子事务）
- 实现：先 PUT 节点名（如有变更）→ 再 PUT 节点属性 → 再按 alarm_id 遍历 PUT 每条 dirty 告警的 attrs
- 任意一步失败：前序成功的不回滚；前端弹错并保留未提交的 dirty 状态（与现有 NodeAttrsPanel 行为一致）
- 删除告警 / 新增告警是即时操作（不走"保存"按钮），无需在 Save 里处理

### 6.4 SQL 编辑器集成

`ApisView.vue` 的 SQL 编辑器左侧"可用视图"自动展示 `alarms` 视图 + 列定义（已挂模板时）。

### 6.5 自动告警可见性

节点拖到画布生成 → 立刻刷新画布 → 选中节点 → 告警 Tab 已有 1 条默认告警，用户能直接看到。

---

## 7. 错误处理边界

| 场景 | 后端响应 | 前端体验 |
|------|----------|----------|
| 删除被引用模板 | 409 + `referencedBy` | 弹错 + 列出引用拓扑 |
| 切换/解绑未带 `clearExisting` 但有告警 | 409 + `nodeAlarmCount` | 弹二次确认 Modal，确认后重发 |
| `field_key` 非法（特殊字符） | 400 | FieldEditor 输入框报错 + 滚动聚焦 |
| `field_key` 与固定列冲突 | 400 + 中文说明 | 同上 |
| 告警属性值超 `max_length` | 400 | 告警字段标红 |
| 拓扑未挂模板时 POST `/nodes/{id}/alarms` | 409 | 提示"本拓扑未配置告警模板" |
| 自动插入默认告警失败 | 节点创建事务回滚 | 节点未创建，提示报错 |

---

## 8. 测试策略

### 8.1 后端 pytest（必须）

- `alarm_schema` CRUD + 引用检查（删被引用返 409）
- 节点创建（拓扑挂模板）→ 自动 +1 告警 + 默认值填充正确
- 节点组 materialize 5000 节点 → 5000 条告警批量写入符合性能预期
- `cte_builder.collect_views(conn, tid)` 返回 generic 列表包含 `alarms`（已挂模板）/ 不包含（未挂）
- `is_valid_ident` 拦截非法 `field_key`；固定列名冲突时该字段不进 pivot
- 拓扑切换模板（带 / 不带 `clearExisting`）行为符合预期

### 8.2 前端手动 smoke 测试

按 CLAUDE.md "测试完成后关闭进程"原则执行：

1. 类型管理页 → 新建告警模板（3 个字段：alarm_id text、severity select、occurred_at text）
2. 拓扑编辑 Modal → 绑定模板 → 保存
3. 画布拖一个节点 → 节点属性面板 → 告警 Tab 显示 1 条
4. 新增告警 / 编辑 / 删除一气呵成
5. 切换模板 → 弹二次确认 → 确认后告警清空
6. 删除已被拓扑引用的模板 → 弹引用提示
7. API 页面新建 mock 接口 → SQL `SELECT * FROM alarms WHERE severity = 'critical'` → 返回正确数据
8. 节点组 materialize 100 节点 → 100 条告警全部生成

---

## 9. 实施顺序

1. **DB + Schema** — `migrations.py` 加 4 张新表 + topologies 列；Pydantic CamelModel
2. **后端 CRUD** — `alarm_schema.py` + `node_alarm.py` router；拓扑挂载 PATCH；引用检查；挂 `main.py`
3. **自动插入 + CTE 集成** — 改 `node.py` 创建路径；改 `node_group.py` materialize；`cte_builder.py` 加 `_build_alarms_cte`；`sql_helper.py` 视图清单
4. **前端管理界面** — 告警模板 CRUD 页 + 拓扑编辑挂载下拉 + 二次确认 Modal
5. **画布集成** — `NodeAttrsPanel` 加 Tab + `NodeAlarmsTab` 组件

---

## 10. 受影响文件清单

**后端：**
- `backend/app/db/migrations.py` — 4 张新表 + topologies 列
- `backend/app/main.py` — 挂载 2 个新 router
- `backend/app/admin/alarm_schema.py` — **新文件**
- `backend/app/admin/node_alarm.py` — **新文件**
- `backend/app/admin/topology.py` — PATCH `/topologies/{id}/alarm-schema`；详情附带告警计数
- `backend/app/admin/node.py` — 创建节点时自动插告警
- `backend/app/admin/node_group.py` — materialize 时为产物节点插告警
- `backend/app/admin/sql_helper.py` — schema views 返回 `alarms`
- `backend/app/admin/schemas/` — 新增告警相关 Pydantic 模型
- `backend/app/core/cte_builder.py` — 新增 `_build_alarms_cte`；集成 `collect_views`

**前端：**
- `frontend/src/views/TypesView.vue` — 第 3 Tab "告警模板"
- `frontend/src/components/alarmSchemas/` — **新目录**（Table / Modal / FieldEditor）
- `frontend/src/components/canvas/NodeAttrsPanel.vue` — 加 Tabs
- `frontend/src/components/canvas/NodeAlarmsTab.vue` — **新文件**
- `frontend/src/components/topology/TopologyModal.vue` — 加模板下拉 + 切换二次确认
- `frontend/src/api/alarmSchema.ts` — **新文件**
- `frontend/src/api/nodeAlarm.ts` — **新文件**
- `frontend/src/api/topology.ts` — 加 `bindAlarmSchema` 方法
- `frontend/src/composables/useAlarmSchemas.ts` — **新文件**

---

## 11. 后续可扩展点（不在本期范围）

- 画布上一键生成告警 API（路径 6 的选项 A，作为 SQL 暴露的便利层）
- `severity` 字段联动节点角标颜色
- 告警字段类型扩展 `datetime`（日期时间选择器）
- 批量告警生成（按概率分布 / 时间偏移）
- 告警 WebSocket 推送（实时告警流）
