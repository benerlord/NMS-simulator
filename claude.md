## 注意事项
- 每个任务完成之后记录任务进度
- 前后端测试完成后，要关闭进程，释放端口
- 回答使用中文

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
│       │   ├── node_type.py               # 节点类型 + 边类型 CRUD + fields + Excel 导入导出（表头匹配 + 字段校验）
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
│       │   ├── http.ts                    # axios 实例 + camelize/snakeize 拦截器 + FastAPI detail 错误提取
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
- **Excel 导入按表头名匹配** — `_build_header_map(ws)` 读取第 1 行构建 `{表头名: 列索引}` 字典，`_col(headers, name, row)` 按名称取值。列顺序可任意调换，只要表头名一致即可
- **Python 3.9 类型注解** — 不可使用 `str | None`（PEP 604，需 3.10+），必须用 `Optional[str]`
- **必填校验 + 自动滚动模式** — 校验失败后设置 `fieldErrors`，`await nextTick()` 等待 DOM 更新，`querySelector('.ant-form-item-has-error')` 查找报错元素，`scrollIntoView({ behavior: 'smooth', block: 'center' })` 滚动 + `focus()` 聚焦输入框
- **网管/设备作用域（Domain）** — `domains` 表代表网管环境，`topologies.domain_id` 绑定拓扑，`domain_node_types` M2M 绑定节点类型。白名单模式：域有绑定时只展示绑定类型，无绑定则默认全部可用。前端菜单/页面显示为"网管/设备"而非"域"，代码层面使用 `domain` 命名

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
- ✅ 画布属性面板按钮固定底部：NodeAttrsPanel / EdgeAttrsPanel 的保存删除按钮从滚动区域内移到 flex 布局固定底部，NodeAttrsModal 的 Modal body 添加 max-height + overflow-y 限制
- ✅ 类型管理导出 Excel：节点类型批量导出从 JSON 改为 .xlsx 多 Sheet（类型汇总 + 每个类型独立 Sheet），新增 `openpyxl` 依赖，前端改为 blob 下载；导出不含 ID（内部字段）
- ✅ 类型管理导入 Excel：新增 POST /node-types/import + /import/preview 端点，读取与导出同格式 xlsx，以 code 匹配（新建/覆盖），**覆盖前弹窗二次确认**，前端文件选择 + 预览 + 导入提示
- ✅ 类型管理导入兼容性优化（commit c9323dd）：
  - 导入按表头名匹配列位置（`_build_header_map` + `_col`），不依赖固定列顺序
  - 遇空行自动结束当前 Sheet 解析（`all(v is None or v == '' for v in row)` → break）
  - 字段类型白名单校验 + 规范化（`str().strip().lower()`），非法值给出明确错误而非 500
  - HTTP 400 错误信息从 FastAPI `detail` 字段提取（前端 `http.ts` 错误拦截器兼容）
- ✅ 节点名称系统内置（commit 05e5c68）：`name` 是所有节点类型的系统属性，映射到 `nodes.name` 列。创建节点时自动生成默认名称，编辑面板可内联修改名称，画布标签实时同步
- ✅ 拓扑管理点击拓扑名称进入画布（非编辑弹窗）
- ✅ 节点组创建体验优化（commit c9323dd）：
  - 选择节点类型后组名称自动填充，命名模板使用 `{group}` 占位符联动
  - 属性策略步骤：必填字段未配置时阻止跳转 + 自动滚动聚焦到报错行
  - 提交时自动过滤未配置的非必填字段策略（避免后端 422）
- ✅ 画布创建节点必填校验：点击"创建"时自动滚动 + 聚焦第一个未填写的必填字段（`NodeAttrsModal.vue`）
- ✅ 网管/设备作用域 + 画布面板搜索/折叠优化（commit a9ebb14）：
  - 新增 domains / domain_node_types 表 + topologies.domain_id 列，网管/设备 CRUD API
  - 节点类型与网管/设备批量/单个关联 API，list_node_types 支持 domain_id 过滤
  - 拓扑绑定网管/设备，画布面板仅展示当前拓扑所属网管/设备的节点类型
  - TypePalette AutoComplete 搜索 + 分类标题折叠 + 单分类内容区独立滚动（max-height: 240px）
  - NodeTypeTable 批量操作合并为 Dropdown（关联网管/设备 / 解除关联 / 批量删除）+ 所属网管/设备 Tag 列
  - TopologyModal 新增所属网管/设备选择器
  - 左侧面板 overflow 约束防止画布被推动滚动
- ✅ 接口分类优化（commit 3145ece）：api_configs 新增 domain_id / category 列，接口管理页面改为网管/设备目录式分组视图（可折叠 + 搜索跨目录过滤 + 目录自动同步）
- ✅ 多端口实例管理（commit 待提交）：
  - 新增 mock_instances 表 + CRUD API + 前端实例管理页面
  - 实例绑定拓扑（而非直接绑域），自动继承拓扑下所有接口
  - InstanceRunner 进程管理器：启用实例自动启动 uvicorn 子进程，禁用/删除自动终止
  - `instance_app.py` 子进程入口：按 topology_id 过滤接口，不暴露管理 API
- ✅ 接口导出/导入：JSON 格式导出（全部/按目录/按勾选）+ 导入预览确认框
- ✅ SQL 列名格式统一：SqlRunner 测试运行后自动提取 snake_case 列名，响应模板提示列名格式，参数映射 bindTo 改为 AutoComplete
- ✅ 修复接口页面切其他页时旧视图锁死：`ApiConfigTable.vue` 的 `groupedDomains` computed 在 `domainMap.get(dId)!` 处用非空断言，当 api 引用的 domain 不在 `props.domains`（数据不一致 / fetchApis 早于 fetchDomains 返回的竞态）时抛 `Cannot read properties of undefined (reading 'totalCount')`，污染 Vue patch 队列导致后续 RouterView 切换全部失败（`emitsOptions/parentNode is null`）。改为 `dg` 取不到时与 `!dId` 走同一条兜底路径，归入"未归类"
- ✅ 实例管理支持 HTTPS 协议（commit f10a45f..8d34370，共 9 个 commit）：
  - `mock_instances` 新增 `ssl_enabled` 列（幂等 ALTER，默认 0 兼容既有）
  - `InstanceRunner` 全套方法加 `ssl_enabled` 参数；父进程 `ensure_cert` 提前生成证书，避免子进程并发竞态；`_check_and_restart` 从单阶段改成"锁内收集 to_restart + 锁外重启"两阶段，修 Lock 非可重入的潜在死锁
  - `except BaseException` 兜底 cert_utils 的 `sys.exit` 逃逸，避免单实例证书问题拖垮 admin 父进程
  - `instance_app.py` argparse +2 参数，uvicorn 按需 `ssl_certfile/ssl_keyfile`
  - CRUD 端点 `_build_url(port, ssl_enabled)` 拼 `http/https://localhost:port`，list 响应带 `url` 字段
  - Modal 加 `Radio.Group` 协议字段（HTTP/HTTPS，选 HTTPS 显示"客户端需跳过证书校验"提示）
  - 列表加协议 Tag 列 + 可复制访问地址列（`Typography.Text copyable code`，禁用态灰色 + tooltip）
  - 设计方案：`docs/superpowers/specs/2026-07-02-mock-instance-https-design.md`；实施计划：`docs/superpowers/plans/2026-07-02-mock-instance-https.md`

### 待开发
- 编辑组定义打开 GroupCreateModal（目前右键"编辑组定义"已 emit 事件但 CanvasView 尚未接入 editGroupId）
- 大规模节点组性能测试（10 万+ 虚拟节点 CTE 查询耗时）
