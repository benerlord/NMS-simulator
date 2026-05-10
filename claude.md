## 注意事项
- 每个任务完成之后记录任务进度
- 前后端测试完成后，要关闭进程，释放端口

---

## 项目概述

**NMS Mock** — 网管系统本地模拟工具。在画布上创建拓扑（节点 + 边），配置 HTTP Mock 接口（SQL 数据源），采集插件通过调用 Mock 接口获取拓扑数据。

**技术栈：**
- 后端：`FastAPI` + `SQLite`（WAL 模式，文件 `backend/data/app.db`）+ `uvicorn`
- 前端：`Vue 3.5`（`<script setup>` + Composition API）+ `Vite 8` + `Ant Design Vue 4` + `AntV X6 3`（拓扑画布）+ `Vue Router 5`
- 包管理：前端 `pnpm`，后端 `pip`
- Python 3.9 / SQLite 3.37

---

## 启动命令

```bash
# 后端（默认 http://0.0.0.0:8080）
cd backend && python -m app.main

# 前端（默认 http://localhost:5173，代理 /admin/api → 后端）
cd frontend && npm run dev
```

后端 `.env` 关键配置：`APP_PORT=8080`，`APP_SSL_ENABLED=false`（本地开发用 HTTP），`DB_PATH=./data/app.db`

---

## 项目目录结构

```
InterfaceTest/
├── backend/
│   ├── .env
│   ├── data/app.db                        # SQLite 数据库（运行时生成）
│   └── app/
│       ├── main.py                        # FastAPI app + lifespan + 10 个 router 挂载
│       ├── core/
│       │   ├── config.py                  # Settings（从 .env 读取）
│       │   ├── ws_hub.py                  # WebSocket pub/sub
│       │   ├── request_pipeline.py        # Mock 请求 6 步流水线
│       │   ├── response_template.py       # 响应模板引擎（{{items}} + 表达式）
│       │   ├── sql_executor.py            # 只读 SQL 执行器（CTE + 分页）
│       │   ├── cte_builder.py             # 动态 CTE 视图生成
│       │   └── cert_utils.py              # 自签 TLS 证书
│       ├── db/
│       │   ├── connection.py              # connect() / transaction()（WAL + FK）
│       │   ├── migrations.py              # 15 表 DDL + 幂等 ALTER TABLE
│       │   └── seed.py                    # 11 节点类型 + 5 边类型 + 3 设置
│       ├── admin/                         # 管理 API（/admin/api）
│       │   ├── routes.py                  # GET /health
│       │   ├── topology.py                # 拓扑 CRUD + canvas + graph + import/export
│       │   ├── node.py / edge.py          # 节点/边 CRUD + position + attrs
│       │   ├── node_type.py               # 节点类型 + 边类型 CRUD + fields
│       │   ├── api_config.py              # API 配置 CRUD + test
│       │   ├── sql_helper.py              # SQL 视图 / 预览 / 执行
│       │   ├── token.py                   # Token 管理
│       │   ├── settings.py                # 系统设置（含 mock_path_prefix 热重载）
│       │   ├── node_group.py              # 节点组 CRUD + 展开 + group-graph + 位置
│       │   └── schemas/                   # Pydantic v2 CamelModel
│       └── mock/
│           ├── registry.py                # 动态路由注册（从 api_configs 表）
│           └── handler.py                 # 每个 mock 端点的 handler 闭包
├── frontend/
│   ├── vite.config.ts                     # 代理 /admin/api → http://localhost:8080
│   └── src/
│       ├── App.vue / main.ts              # createApp + Pinia + Router + Antd
│       ├── router/index.ts                # 6 路由，menuItems 导出
│       ├── layouts/AppLayout.vue          # 侧边栏 + 顶栏布局
│       ├── api/                           # Axios SDK（http.ts + 各域模块）
│       │   ├── http.ts                    # axios 实例 + camelize/snakeize 拦截器
│       │   ├── case.ts                    # camelizeKeys / snakeizeKeys
│       │   ├── nodeGroup.ts              # 节点组 API + TS 接口
│       │   └── types.ts, topology.ts, node.ts, edge.ts, api_config.ts, sql.ts, token.ts, settings.ts
│       ├── composables/                   # Vue composables
│       │   ├── useCanvas.ts              # 画布数据加载 + 位置保存 + dirty 追踪
│       │   ├── useNodeGroups.ts           # 节点组 CRUD + 展开进度（provide/inject 单例）
│       │   └── useTopologies.ts, useApiConfigs.ts, useTokens.ts, useTypes.ts
│       ├── views/                         # 6 个页面
│       │   ├── TopologiesView.vue         # 拓扑列表
│       │   ├── CanvasView.vue              # 拓扑画布（核心页面）
│       │   ├── TypesView.vue              # 类型管理
│       │   ├── ApisView.vue               # API 配置
│       │   ├── TokensView.vue             # Token 管理
│       │   └── SettingsView.vue           # 系统设置
│       ├── components/
│       │   ├── canvas/                    # 画布组件（TypePalette, GroupPalette, GroupCreateModal, TopologyCanvas, CanvasToolbar, NodeAttrsPanel/Modal, EdgeAttrsPanel）
│       │   ├── apis/                      # API 配置组件（ApiConfigModal/Table, AuthConfigPanel, SqlEditor/Runner 等 10 个）
│       │   ├── types/                     # 类型管理组件（NodeType/EdgeType Modal/Table/FieldEditor）
│       │   ├── topology/                  # 拓扑组件（TopologyModal/Table）
│       │   └── tokens/                    # Token 组件（TokenCreateModal/Table）
│       ├── ws/client.ts                   # WebSocket 客户端（自动重连 + 心跳）
│       └── utils/
│           ├── nodeShape.ts               # X6 节点 Shape 注册（infra-node + macro-node）
│           └── nodeIcons.ts               # 设备 SVG 图标
└── docs/                                  # 设计文档
    └── 节点组-重写设计方案.md
```

---

## 数据库表（15 张）

| 表 | 用途 |
|----|------|
| `topologies` | 拓扑场景 |
| `node_types`, `node_type_fields` | 节点类型定义 + 自定义字段 |
| `edge_types`, `edge_type_fields` | 边类型定义 + 自定义字段 |
| `nodes`, `node_attrs` | 拓扑中的节点 + K-V 属性 |
| `edges`, `edge_attrs` | 拓扑中的边 + K-V 属性 |
| `canvas_nodes` | 节点画布位置（x, y） |
| `api_configs` | Mock API 配置 |
| `tokens` | 认证令牌 |
| `request_logs` | 请求日志 |
| `settings` | 系统设置（key-value） |
| `node_groups` | 节点组定义（模板 + 策略 + canvas_x/y） |

**幂等列：** `nodes.group_id`（FK → node_groups），`node_groups.canvas_x`，`node_groups.canvas_y`

**ID 前缀规则：** `topo_` / `node_` / `edge_` / `api_` / `ntype_` / `etype_` / `grp_` / `tok_` + uuid12

---

## API 响应格式

**所有管理 API** 返回 `{"code": 0, "data": ..., "message": "ok"}`。前端 `http.ts` 拦截器自动解包返回 `data`。`code !== 0` 时抛出 `ApiError`。CamelCase ↔ snake_case 自动转换（前端 `snakeizeKeys` 请求 / `camelizeKeys` 响应，后端 `CamelModel`）。

---

## 节点组功能（最新提交 9f53324）

### 概念模型
- **节点组** — 参数化定义：节点类型 + 数量 + 属性策略 + 边策略。画布上显示为**宏节点**（双线边框占位符）
- **不需要展开** — 画布只展示宏节点，SQL 查询通过 CTE 虚拟生成行

### 后端关键模块

**`node_group.py` — CRUD + 展开引擎：**
- `GET /topologies/{id}/node-groups` — 列出组
- `POST /topologies/{id}/node-groups` — 创建组
- `PUT/DELETE /node-groups/{id}` — 更新/删除
- `POST /node-groups/{id}/materialize` — 展开为实体节点（4 种属性策略 + 4 种边模式，5000 批量刷新，并发锁）
- `PATCH /node-groups/{id}/position` — 宏节点位置持久化到 canvas_x/y
- `GET /topologies/{id}/group-graph` — macroNodes + macroEdges（画布渲染用）

**`cte_builder.py` — 8 个通用 CTE 视图：**
- `nodes`, `edges`, `children` — 基础视图
- `node_groups` — 节点组元数据
- `group_nodes` — 虚拟节点（递归 CTE，上限 10 万/组，name_template 渲染）
- `group_edges` — 边策略元数据（json_each 解析）
- `topology_nodes` — **统一节点视图**（physical UNION ALL group_node）
- `topology_edges` — **统一关系视图**（physical UNION ALL group_strategy UNION ALL hybrid）

### 前端关键组件

**CanvasView.vue** — 核心页面，集成了：
- 连线模式 4 种组合（普通↔普通 创建实体边 / 宏↔宏 创建边策略 / 混合 创建 all_to_all 策略）
- 画布删除（单击选中 → Delete/Backspace 删除任意元素）
- 拖拽分发（`application/node-type` / `application/node-group` MIME）
- 自动保存 + 位置防抖

**GroupPalette.vue** — 左侧面板节点组列表，拖拽到画布定位，右键菜单（编辑/缩放/删除）

**GroupCreateModal.vue** — 三步创建向导：基础信息（含命名预览）→ 属性策略（4 种）→ 连接规则（4 种模式）

**TopologyCanvas.vue** — X6 画布：注册 macro-node Shape + 渲染宏边（橙色虚线）+ 混合边（蓝色点划线 `8 4 2 4`）

**nodeShape.ts** — `registerMacroNodeShape()`（try/catch 防 HMR 重复），`buildMacroNodeAttrs()`（200×88px 双线边框 + 状态条）

### 边类型视觉区分

| 类型 | 线型 | 颜色 |
|------|------|------|
| 普通边 | 实线 | 默认 |
| 宏边（macro↔macro） | 虚线 `6 4` | `#faad14` |
| 混合边（macro↔normal） | 点划线 `8 4 2 4` | `#1890ff` |

---

## Mock API 请求流水线（6 步）

1. 路由匹配（FastAPI 处理）
2. 检查启用状态（enabled=false → 40404）
3. 认证（none / xtoken / basic）
3.5. 请求校验（headers required+expectValue / query required+类型+白名单 / body required） — 缺 `config.request` 整段跳过
4. 故障注入（延迟 + 概率错误）
5. 执行（SQL → `execute_paged` with CTE / static → noop）
6. 渲染（模板引擎 `{{items}}` `{{total}}` + 算术表达式）

---

## 关键模式与注意事项

- **CanvasView 是核心页面** — 所有画布交互逻辑集中在此，约 900 行 `<script setup>`
- **provide/inject 单例** — `useNodeGroups(topologyId, fetchGraph)` 在 CanvasView 中首次调用并 provide，子组件 inject 共享同一实例
- **宏节点 ≠ 普通节点** — 宏节点 ID 以 `grp_` 开头，不存入 `nodes` 表。画布保存时需 filter 掉 `grp_` 前缀避免 FK 约束失败
- **graphData 与画布同步** — 通过 `g.addNode()` 添加的节点不回写到 `graphData` ref。任何触发 `initGraph()` 重新渲染的操作必须先 `await fetchGraph()` 刷新 `graphData`，再触发 `fetchGroupGraph()`
- **CTE 构建** — `collect_views(conn, topology_id)` 根据已使用的 node_type/edge_type 动态生成类型专属 CTE，通用 CTE 始终可用
- **SQLite 版本限制** — 当前 3.37.2，不支持 `->>` 运算符，使用 `json_extract()` 替代
- **WebSocket** — 路径 `/admin/ws`，前端 `WsClient` 单例（自动重连 + 30s 心跳），已订阅 `topology.saved` 和 `group.materialize.progress`
- **热重载** — `mock_path_prefix` 变更触发 `RouteRegistry.reload()`，无需重启进程

---

## 开发进度

### 已完成
- ✅ M1-M2：基础架构（FastAPI + SQLite + Vue3 + X6）
- ✅ M3：Mock API 流水线（认证 + 故障注入 + SQL 执行 + 模板渲染）
- ✅ M5：请求契约校验（headers/query/body）
- ✅ LEGACY-01：鉴权 UI 整合
- ✅ LEGACY-05：响应模板表达式引擎 + 派生分页变量
- ✅ LEGACY-06：API 拓扑绑定可在编辑模式下修改
- ✅ LEGACY-07：拓扑删除自动解绑 api_configs
- ✅ **节点组完整功能**（D1-D6，commit 9f53324）：
  - D1 数据层：node_groups 表 + Schema + CRUD 端点
  - D2 物化引擎：4 属性策略 + 4 边模式 + WS 进度
  - D3 前端 API 层：nodeGroup.ts + useNodeGroups
  - D4 前端组件：GroupPalette + GroupCreateModal
  - D5 画布集成：macro-node Shape + 连线自适应 + 画布删除 + CanvasView 重构
  - D6 联调测试：7 个用户旅程 + 性能测试 + 零回归
- ✅ 统一查询视图：topology_nodes + topology_edges
- ✅ 类型字段文本最大长度：node_type_fields / edge_type_fields 新增 max_length 列，类型管理可配置；画布上编辑节点/边属性时前后端双重校验（前端 `:maxlength` + `:showCount` 字符计数 + 后端 `set_node_attrs` / `set_edge_attrs` 长度校验）

### 待开发
- 编辑组定义打开 GroupCreateModal（目前右键"编辑组定义"已 emit 事件但 CanvasView 尚未接入 editGroupId）
- 大规模节点组性能测试（10 万+ 虚拟节点 CTE 查询耗时）
