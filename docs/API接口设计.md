# 网管系统模拟工具 - API 接口设计

## 文档说明

| 项目 | 内容 |
|------|------|
| 文档版本 | v1.0 |
| 创建日期 | 2026-04-15 |
| 适用范围 | MVP 阶段 |
| 关联文档 | `系统架构设计.md`、`数据库表设计.md` v2.3 |

---

## 1. 总览

系统对外暴露两类 HTTP 通道，共用同一个 FastAPI 进程，通过路径前缀区分：

| 通道 | 路径前缀 | 消费者 | 鉴权 |
|------|---------|--------|------|
| **管理 API** | `/admin/api/**` | 前端 SPA | 无（内网信任） |
| **WebSocket** | `/admin/ws` | 前端 SPA | 无 |
| **模拟接口** | `/mock/**` | MindOps 采集插件 | 按每个接口配置 |

本文档仅定义**管理 API** 与 **WebSocket 事件**。模拟接口由用户在运行时动态配置。

### 1.1 通用约定

- **协议**：HTTP/1.1；`Content-Type: application/json; charset=utf-8`
- **时间格式**：ISO 8601（`2026-04-15T08:30:00Z`）
- **ID**：字符串（UUID v4 或业务前缀 + UUID，如 `topo_xxx`、`node_xxx`、`api_xxx`）
- **布尔值**：JSON 原生 `true` / `false`（DB 内存为 0/1 由后端转换）
- **分页**：`page`（从 1 起）+ `pageSize`（默认 20，最大 500）
- **排序**：`sort=field,dir` 形式，如 `sort=updated_at,desc`
- **过滤**：在资源列表接口明确列出支持的 query 参数

### 1.2 统一响应结构

成功：

```json
{
  "code": 0,
  "data": { ... },
  "message": "ok"
}
```

分页列表：

```json
{
  "code": 0,
  "data": {
    "items": [...],
    "total": 123,
    "page": 1,
    "pageSize": 20
  }
}
```

失败：

```json
{
  "code": 40001,
  "message": "topology not found",
  "details": { "topologyId": "topo_abc" }
}
```

### 1.3 错误码约定

| 区间 | 含义 |
|------|------|
| `0` | 成功 |
| `40000–40099` | 通用参数错误 |
| `40100–40199` | 拓扑 / 节点 / 边相关错误 |
| `40200–40299` | 类型（节点类型 / 边类型）相关错误 |
| `40300–40399` | 接口配置相关错误 |
| `40400–40499` | 认证 / Token 相关错误 |
| `50000–59999` | 服务器内部错误 |

HTTP 状态码同时语义化使用：`400` 参数错误、`404` 资源不存在、`409` 冲突、`422` 语义校验失败、`500` 内部错误。

---

## 2. 管理 API 清单（分模块）

### 2.1 拓扑场景（Topology）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/admin/api/topologies` | 分页列出拓扑；可按 `name` 模糊、`sort` 排序 |
| GET | `/admin/api/topologies/{id}` | 获取拓扑详情（不含节点和边，仅元数据 + 统计） |
| POST | `/admin/api/topologies` | 新建拓扑 |
| PUT | `/admin/api/topologies/{id}` | 修改拓扑元数据（name / description） |
| DELETE | `/admin/api/topologies/{id}` | 删除拓扑（被接口绑定时返回 409） |
| GET | `/admin/api/topologies/{id}/graph` | 一次性获取拓扑完整图数据（节点 + 边 + 画布坐标），供画布加载 |
| POST | `/admin/api/topologies/{id}/export` | 导出场景为 JSON 文件 |
| POST | `/admin/api/topologies/import` | 导入场景文件（冲突时新建副本） |
| GET | `/admin/api/topologies/{id}/stats` | 获取统计（按节点类型、边类型分组计数） |

**新建请求体**：

```json
{ "name": "场景A", "description": "测试ManageOne的Token认证流程" }
```

**图数据响应示例**：

```json
{
  "code": 0,
  "data": {
    "topologyId": "topo_abc",
    "nodes": [
      {
        "id": "node_001",
        "nodeTypeCode": "switch",
        "name": "交换机-01",
        "dn": "NE=34603401",
        "status": "online",
        "attrs": { "vendor": "华为", "model": "CE6800", "ip": "192.168.1.1" },
        "canvas": { "x": 100, "y": 200 }
      }
    ],
    "edges": [
      {
        "id": "edge_001",
        "edgeTypeCode": "physical_link",
        "sourceId": "node_001",
        "targetId": "node_002",
        "status": "up",
        "attrs": { "bandwidth": "10Gbps" }
      }
    ]
  }
}
```

### 2.2 节点类型（NodeType）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/admin/api/node-types` | 列出所有节点类型（可按 `category` 过滤） |
| GET | `/admin/api/node-types/{id}` | 详情（含字段定义） |
| POST | `/admin/api/node-types` | 新建 |
| PUT | `/admin/api/node-types/{id}` | 更新（含字段整体替换） |
| DELETE | `/admin/api/node-types/{id}` | 删除（被节点引用时返回 409） |

**请求体示例**：

```json
{
  "code": "custom_device",
  "name": "自定义设备",
  "category": "physical",
  "icon": "device",
  "color": "#1677ff",
  "shape": "rect",
  "renderMode": "none",
  "dnTemplate": "NE={id}",
  "fields": [
    { "fieldKey": "vendor", "fieldLabel": "厂商", "fieldType": "text", "required": true, "sortOrder": 1 },
    { "fieldKey": "model",  "fieldLabel": "型号", "fieldType": "text", "sortOrder": 2 },
    { "fieldKey": "ip",     "fieldLabel": "IP",  "fieldType": "text", "sortOrder": 3 }
  ]
}
```

### 2.3 边类型（EdgeType）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/admin/api/edge-types` | 列出所有边类型 |
| GET | `/admin/api/edge-types/{id}` | 详情 |
| POST | `/admin/api/edge-types` | 新建 |
| PUT | `/admin/api/edge-types/{id}` | 更新 |
| DELETE | `/admin/api/edge-types/{id}` | 删除（被边引用时返回 409） |

**请求体示例**：

```json
{
  "code": "depends_on",
  "name": "依赖",
  "semantic": "connect",
  "directed": true,
  "exclusiveTarget": false,
  "allowSourceTypeCodes": ["app","pod"],
  "allowTargetTypeCodes": ["app","ecs","container"],
  "lineStyle": "dotted",
  "color": "#faad14",
  "fields": []
}
```

### 2.4 节点（Node）

节点从属于某个拓扑；路径前缀 `/topologies/{topologyId}/nodes`。

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/admin/api/topologies/{topologyId}/nodes` | 分页列出；可按 `nodeTypeCode` / `name` / `status` 过滤 |
| GET | `/admin/api/nodes/{id}` | 节点详情（含属性 + 画布坐标） |
| POST | `/admin/api/topologies/{topologyId}/nodes` | 新建单个节点 |
| POST | `/admin/api/topologies/{topologyId}/nodes/batch` | 批量新建（拖入模板 / 快速生成端口） |
| PUT | `/admin/api/nodes/{id}` | 更新节点（名称 / DN / status / attrs / canvas） |
| PATCH | `/admin/api/nodes/{id}/position` | 仅更新画布坐标（拖拽高频调用） |
| DELETE | `/admin/api/nodes/{id}` | 删除节点（不递归删除子节点；级联删除相连边） |
| DELETE | `/admin/api/topologies/{topologyId}/nodes/batch` | 批量删除（body 传 id 数组） |

**新建请求体**：

```json
{
  "nodeTypeCode": "switch",
  "name": "交换机-01",
  "dn": "NE=34603401",
  "status": "online",
  "attrs": { "vendor": "华为", "model": "CE6800", "ip": "192.168.1.1" },
  "canvas": { "x": 100, "y": 200 }
}
```

**批量生成端口示例**：

```json
{
  "nodeTypeCode": "port",
  "count": 48,
  "nameTemplate": "10GE1/0/{index}",
  "dnTemplate": "{parentDn},PORT={index}",
  "parentId": "node_switch_001",
  "parentEdgeTypeCode": "contains",
  "startIndex": 1,
  "attrs": { "type": "10GE", "speed": "10Gbps" }
}
```

说明：批量创建时若指定 `parentId` + `parentEdgeTypeCode`，后端自动为每个新节点创建一条对应边。

### 2.5 边（Edge）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/admin/api/topologies/{topologyId}/edges` | 分页列出；可按 `edgeTypeCode` / `sourceId` / `targetId` 过滤 |
| GET | `/admin/api/edges/{id}` | 边详情 |
| POST | `/admin/api/topologies/{topologyId}/edges` | 新建 |
| PUT | `/admin/api/edges/{id}` | 更新 |
| DELETE | `/admin/api/edges/{id}` | 删除 |

**新建请求体**：

```json
{
  "edgeTypeCode": "physical_link",
  "sourceId": "node_port_a",
  "targetId": "node_port_b",
  "status": "up",
  "attrs": { "bandwidth": "10Gbps" }
}
```

后端校验：
- source/target 必须属于同一 `topologyId`
- 若边类型为 `exclusive_target=1`，同一 `(edge_type_id, target_id)` 已存在则返回 409
- 若定义了 `allow_source_type_codes` / `allow_target_type_codes`，校验节点类型是否在白名单内

### 2.6 接口配置（ApiConfig）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/admin/api/apis` | 分页列出；可按 `groupName` / `enabled` / `topologyId` / `method` / `path` 过滤 |
| GET | `/admin/api/apis/{id}` | 详情 |
| POST | `/admin/api/apis` | 新建（method + path 冲突返回 409） |
| PUT | `/admin/api/apis/{id}` | 更新 |
| PATCH | `/admin/api/apis/{id}/enabled` | 切换启用开关（body: `{ "enabled": true }`） |
| PATCH | `/admin/api/apis/{id}/topology` | 切换绑定拓扑（body: `{ "topologyId": "topo_xxx" }`） |
| DELETE | `/admin/api/apis/{id}` | 删除 |
| POST | `/admin/api/apis/{id}/test` | 测试执行（不计入请求日志） |
| POST | `/admin/api/apis/export` | 批量导出（body: `{ "ids": [...] }`，不传则全部） |
| POST | `/admin/api/apis/import` | 批量导入 |

**接口配置结构**：

```json
{
  "id": "api_001",
  "name": "设备查询接口",
  "method": "GET",
  "path": "/rest/openapi/network/v1/devices",
  "enabled": true,
  "groupName": "ManageOne",
  "dataSource": "sql",
  "topologyId": "topo_abc",
  "sqlText": "SELECT * FROM switches WHERE (:status IS NULL OR status=:status)",
  "config": {
    "auth": { "type": "xtoken", "headerName": "X-Auth-Token" },
    "params": [
      { "param": "status", "sqlParam": ":status", "default": null }
    ],
    "pagination": {
      "enabled": true,
      "pageNoParam": "pageNo",
      "pageSizeParam": "pageSize",
      "defaultPageSize": 100
    },
    "response": {
      "contentType": "application/json",
      "statusCode": 200,
      "template": {
        "code": 0,
        "data": "{{items}}",
        "total": "{{total}}",
        "pageNo": "{{pageNo}}",
        "pageSize": "{{pageSize}}"
      }
    },
    "fault": {
      "delayMs": 0,
      "errorRate": 0,
      "errorStatus": 500
    },
    "staticBody": null
  }
}
```

**测试执行请求体**：

```json
{
  "headers": { "X-Auth-Token": "x-fake-token" },
  "query": { "status": "online", "pageNo": 1, "pageSize": 10 },
  "body": null
}
```

**测试执行响应**：

```json
{
  "code": 0,
  "data": {
    "statusCode": 200,
    "headers": { "Content-Type": "application/json" },
    "body": { "code": 0, "data": [...], "total": 30000, "pageNo": 1, "pageSize": 10 },
    "durationMs": 42,
    "generatedSql": "WITH switches AS (...) SELECT * FROM switches ... LIMIT 10 OFFSET 0",
    "boundParams": { ":status": "online" }
  }
}
```

### 2.7 SQL 辅助（SQL Helper）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/admin/api/sql/views?topologyId={id}` | 返回绑定拓扑下所有可用 CTE 视图名及字段（用于 SQL 编辑器联想） |
| POST | `/admin/api/sql/preview` | 预览生成的 CTE + 用户 SQL 拼接结果，不执行 |
| POST | `/admin/api/sql/execute` | 直接执行 SQL（仅 SELECT / WITH），用于拓扑数据查看页 |

**视图列表响应**：

```json
{
  "code": 0,
  "data": {
    "nodeViews": [
      { "name": "switches", "columns": ["id","name","dn","status","vendor","model","ip"] },
      { "name": "ports",    "columns": ["id","name","dn","status","type","speed"] }
    ],
    "edgeViews": [
      { "name": "physical_links", "columns": ["id","source_id","target_id","status","source_name","target_name"] },
      { "name": "contains",       "columns": ["id","source_id","target_id"] }
    ],
    "generic": ["nodes", "edges", "children"]
  }
}
```

### 2.8 Token 管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/admin/api/tokens` | 分页列出（可按 `revoked` / 未过期过滤） |
| POST | `/admin/api/tokens/{token}/revoke` | 手动撤销 |
| DELETE | `/admin/api/tokens/expired` | 清理所有已过期 Token |

### 2.9 请求日志

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/admin/api/logs/requests` | 分页查询；可按 `apiId` / `method` / `statusCode` / `timeRange` 过滤 |
| GET | `/admin/api/logs/requests/{id}` | 日志详情（含完整 query、错误信息） |
| DELETE | `/admin/api/logs/requests` | 清空日志（可选 `before=<ts>`） |

### 2.10 系统设置

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/admin/api/settings` | 返回全部键值 |
| PUT | `/admin/api/settings` | 批量更新（body: `{ "autosave_interval": 60, "request_log_max": 10000 }`） |
| GET | `/admin/api/settings/{key}` | 单个读取 |

### 2.11 仪表盘 / 系统状态

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/admin/api/health` | 健康检查（Liveness） |
| GET | `/admin/api/dashboard/summary` | 仪表盘聚合：启用接口数、拓扑数、节点总数、今日请求量、近 N 条最新请求 |

**仪表盘响应示例**：

```json
{
  "code": 0,
  "data": {
    "service": { "status": "running", "startedAt": "2026-04-15T08:00:00Z", "mockPort": 8080 },
    "topologyCount": 5,
    "nodeCount": 30123,
    "edgeCount": 58291,
    "apiCount": { "total": 42, "enabled": 38 },
    "requestsToday": 1203,
    "recentRequests": [ ... ]
  }
}
```

---

## 3. WebSocket 事件

### 3.1 连接

- 路径：`/admin/ws`
- 连接后，前端可通过发送 `{"type":"subscribe","topics":["log.request","api.registered","topology.saved"]}` 订阅感兴趣的事件
- 服务端心跳：每 30s 发送 `{"type":"ping"}`，客户端回 `{"type":"pong"}`

### 3.2 事件清单

| 事件 type | 方向 | 载荷示例 | 用途 |
|-----------|------|---------|------|
| `topology.saved` | S→C | `{ "topologyId": "topo_abc", "ts": "..." }` | 自动保存完成通知 |
| `topology.changed` | S→C | `{ "topologyId": "topo_abc", "by": "other-tab" }` | 提示其他 Tab 修改了同一拓扑 |
| `api.registered` | S→C | `{ "apiId": "api_001", "method":"GET", "path":"..." }` | 接口新增 / 更新 / 删除时刷新列表 |
| `api.enabledChanged` | S→C | `{ "apiId":"api_001", "enabled": true }` | 启用开关状态同步 |
| `log.request` | S→C | 见下 | 实时推送模拟请求日志 |
| `token.issued` | S→C | `{ "token":"x-..." }` | Token 变动 |
| `token.revoked` | S→C | `{ "token":"x-..." }` | Token 撤销 |
| `subscribe` / `unsubscribe` | C→S | `{ "topics":["log.request"] }` | 订阅 / 退订 |
| `ping` / `pong` | 双向 | — | 心跳 |

**`log.request` 载荷**：

```json
{
  "type": "log.request",
  "data": {
    "id": 10234,
    "ts": "2026-04-15T09:12:33Z",
    "apiId": "api_001",
    "method": "GET",
    "path": "/rest/openapi/network/v1/devices",
    "statusCode": 200,
    "durationMs": 42,
    "clientIp": "127.0.0.1"
  }
}
```

---

## 4. Pydantic 模型规范（命名约定）

- 请求 DTO：`XxxCreate` / `XxxUpdate`
- 响应 DTO：`XxxDetail` / `XxxListItem`
- 内嵌子结构：以 `Nested` 后缀或直接复用（`AttrKV`、`CanvasPosition`）
- 所有模型字段使用 `camelCase`（前端友好），与数据库字段的 `snake_case` 在服务层做映射

---

## 5. 安全与限流

MVP 阶段不做管理 API 鉴权与限流，仅以下约束由后端校验：

| 约束 | 实施位置 |
|------|----------|
| SQL 仅允许 `SELECT` / `WITH` 开头 | `SqlQueryExecutor` 执行前 |
| 同一 `(method, path)` 唯一 | DB 唯一约束 + 服务层友好提示 |
| 删除拓扑 / 类型前的引用校验 | 服务层 |
| 边 source / target 是否同拓扑 | 服务层 |
| `exclusive_target` 约束 | 服务层 |
| 文件上传大小（导入场景） | 全局 10MB 上限 |

---

## 6. 版本变更

| 版本 | 日期 | 变更 |
|------|------|------|
| v1.0 | 2026-04-15 | 初版：覆盖 11 个资源模块 + WebSocket 事件 |
