# 网管系统模拟工具 - API 接口设计

## 文档说明

| 项目 | 内容 |
|------|------|
| 文档版本 | v1.2 |
| 创建日期 | 2026-04-15 |
| 最后更新 | 2026-05-01 |
| 适用范围 | MVP 阶段 |
| 关联文档 | `系统架构设计.md`、`数据库表设计.md` v2.3 |

---

## 1. 总览

系统对外暴露两类 HTTP 通道，共用同一个 FastAPI 进程，通过路径前缀区分：

| 通道 | 路径前缀 | 消费者 | 鉴权 |
|------|---------|--------|------|
| **管理 API** | `/admin/api/**` | 前端 SPA | 无（内网信任） |
| **WebSocket** | `/admin/ws` | 前端 SPA | 无 |
| **模拟接口** | `<api_configs.path>` | MindOps 采集插件 | 按每个接口配置 |

模拟接口默认**无统一前缀**，每条接口的路径以 `api_configs.path` 原样挂载在根路径下（例：`GET /rest/openapi/network/v1/devices`），调用方可直接复刻原系统的 URL 进行测试。如需统一前缀（如内网约束要求 `/mock/**`），改 `settings.mock_path_prefix` 即可生效（默认空串）。

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

### 1.3 HTTP 状态码语义

| 状态码 | 语义 | 使用场景 |
|--------|------|----------|
| `200 OK` | 成功 | GET、PUT、PATCH 返回资源 |
| `201 Created` | 创建成功 | POST 创建资源（应含 `Location` 头） |
| `204 No Content` | 删除成功 | DELETE 无返回体 |
| `400 Bad Request` | 参数错误 | 缺少必填字段、JSON 格式错误 |
| `401 Unauthorized` | 未认证 | Token 缺失或无效 |
| `403 Forbidden` | 无权限 | 已认证但无权限访问 |
| `404 Not Found` | 资源不存在 | ID 查不到记录 |
| `409 Conflict` | 冲突 | 重复名称、状态冲突、被引用无法删除 |
| `422 Unprocessable Entity` | 语义校验失败 | 字段格式正确但语义非法（如 ID 格式不符） |
| `429 Too Many Requests` | 限流 | 应返回 `Retry-After` 头 |
| `500 Internal Server Error` | 内部错误 | 绝不暴露堆栈或 SQL 原文 |

### 1.4 错误码约定

| 区间 | 含义 |
|------|------|
| `0` | 成功 |
| `40000–40099` | 通用参数错误 |
| `40100–40199` | 拓扑 / 节点 / 边相关错误 |
| `40200–40299` | 类型（节点类型 / 边类型）相关错误 |
| `40300–40399` | 接口配置相关错误 |
| `40400–40499` | 认证 / Token 相关错误 |
| `50000–59999` | 服务器内部错误 |

### 1.5 错误响应结构

基础错误（字段级验证错误）：

```json
{
  "code": 40001,
  "message": "请求参数校验失败",
  "details": [
    {
      "field": "name",
      "message": "name 不得为空",
      "code": "required"
    },
    {
      "field": "name",
      "message": "name 长度不能超过 100",
      "code": "max_length"
    }
  ]
}
```

资源不存在错误：

```json
{
  "code": 40101,
  "message": "拓扑不存在",
  "details": { "topologyId": "topo_abc" }
}
```

冲突错误（重复名称、被引用）：

```json
{
  "code": 40103,
  "message": "拓扑被接口配置引用，无法删除",
  "details": { "topologyId": "topo_abc", "apiConfigIds": ["api_001"] }
}
```

内部错误（不暴露详情）：

```json
{
  "code": 50000,
  "message": "服务器内部错误",
  "details": null
}
```

### 1.6 字段过滤（Sparse Fieldsets）

用于减少响应体体积：

```
GET /admin/api/topologies?fields=id,name,version
```

响应只包含指定字段：

```json
{
  "code": 0,
  "data": {
    "items": [
      { "id": "topo_abc", "name": "场景A", "version": 1 }
    ]
  }
}
```

### 1.7 限流（Rate Limiting）

所有管理 API 启用基础限流：

```
HTTP/1.1 200 OK
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 998
X-RateLimit-Reset: 1744886400
```

限流触发时：

```
HTTP/1.1 429 Too Many Requests
Retry-After: 60
{
  "code": 40002,
  "message": "请求过于频繁，请稍后重试",
  "details": { "retryAfter": 60 }
}
```

---

## 2. 管理 API 清单（分模块）

### 2.1 拓扑场景（Topology）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/admin/api/topologies` | 分页列出拓扑；可按 `name` 模糊、`sort` 排序 |
| GET | `/admin/api/topologies/{id}` | 获取拓扑详情（不含节点和边，仅元数据 + 统计） |
| POST | `/admin/api/topologies` | 新建拓扑 |
| PUT | `/admin/api/topologies/{id}` | 修改拓扑元数据（name / description） |
| DELETE | `/admin/api/topologies` | 批量删除全部拓扑；自动解绑引用的 api_configs，返回 `{deletedCount, unboundApiCount}` — LEGACY-07 |
| DELETE | `/admin/api/topologies/{id}` | 删除单个拓扑；自动解绑引用的 api_configs，返回 `{unboundApiCount}` — LEGACY-07 |
| GET | `/admin/api/topologies/{id}/delete-impact` | 删除前预扫描，返回 `{topologyId, topologyName, affectedApiCount, affectedApis[]}` — LEGACY-07 |
| GET | `/admin/api/topologies/{id}/graph` | 一次性获取拓扑完整图数据（节点 + 边 + 画布坐标），供画布加载 |
| POST | `/admin/api/topologies/{id}/export` | 导出场景为 JSON 文件 |
| POST | `/admin/api/topologies/import` | 导入场景文件（冲突时新建副本） |
| GET | `/admin/api/topologies/{id}/stats` | 获取统计（按节点类型、边类型分组计数） |

**新建请求体**：

```json
{ "name": "场景A", "description": "测试ManageOne的Token认证流程" }
```

**异常场景**：

| 场景 | HTTP 状态码 | code | message |
|------|------------|------|---------|
| 新建时 name 为空 | 400 | 40001 | name 不得为空 |
| 新建时 name 超过 100 字符 | 400 | 40001 | name 长度不能超过 100 |
| 新建时 name 重复 | 409 | 40003 | 拓扑名称已存在 |
| 更新时 topology 不存在 | 404 | 40101 | 拓扑不存在 |
| 更新时 name 为空 | 400 | 40001 | name 不得为空 |
| 更新时无任何更新字段 | 400 | 40001 | 无更新字段 |
| 删除单个时 topology 不存在 | 404 | 40101 | 拓扑不存在 |
| 获取 graph 时 topology 不存在 | 404 | 40101 | 拓扑不存在 |
| ~~删除时被 api_configs 引用~~ | ~~409~~ | ~~40103~~ | LEGACY-07 后不再触发；自动解绑接口配置（保留备用错误码） |

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

**异常场景**：

| 场景 | HTTP 状态码 | code | message |
|------|------------|------|---------|
| 新建时 code 已存在 | 409 | 40201 | 节点类型 code 已存在 |
| 新建时缺少必填字段 | 400 | 40001 | {field} 不得为空 |
| 更新时 node-type 不存在 | 404 | 40201 | 节点类型不存在 |
| 删除时被节点引用 | 409 | 40202 | 节点类型被节点引用，无法删除 |

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

**异常场景**：

| 场景 | HTTP 状态码 | code | message |
|------|------------|------|---------|
| 新建时 code 已存在 | 409 | 40201 | 边类型 code 已存在 |
| 删除时被边引用 | 409 | 40202 | 边类型被边引用，无法删除 |

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

**异常场景**：

| 场景 | HTTP 状态码 | code | message |
|------|------------|------|---------|
| 新建时 topology 不存在 | 404 | 40101 | 拓扑不存在 |
| 新建时 nodeTypeCode 不存在 | 400 | 40001 | 节点类型不存在 |
| 新建时缺少必填字段 | 400 | 40001 | {field} 不得为空 |
| 批量创建时 parentId 不存在 | 400 | 40104 | 父节点不存在 |
| 更新时 node 不存在 | 404 | 40102 | 节点不存在 |
| 删除时 node 不存在 | 404 | 40102 | 节点不存在 |
| 批量删除时拓扑不匹配 | 400 | 40105 | 节点不属于该拓扑 |

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

**异常场景**：

| 场景 | HTTP 状态码 | code | message |
|------|------------|------|---------|
| 新建时 topology 不存在 | 404 | 40101 | 拓扑不存在 |
| 新建时 edgeTypeCode 不存在 | 400 | 40001 | 边类型不存在 |
| 新建时 source/target 不存在 | 404 | 40102/40106 | 源/目标节点不存在 |
| 新建时 source/target 不同拓扑 | 400 | 40107 | 源节点和目标节点不在同一拓扑 |
| 新建时 exclusive_target 冲突 | 409 | 40108 | 该目标节点已存在相同类型的边 |
| 新建时节点类型不在白名单 | 400 | 40109 | 源/目标节点类型不在允许范围内 |
| 更新时 edge 不存在 | 404 | 40106 | 边不存在 |
| 删除时 edge 不存在 | 404 | 40106 | 边不存在 |

### 2.6 接口配置（ApiConfig）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/admin/api/apis` | 分页列出；可按 `groupName` / `enabled` / `topologyId` / `method` / `path` 过滤 |
| GET | `/admin/api/apis/{id}` | 详情 |
| POST | `/admin/api/apis` | 新建（method + path 冲突返回 409） |
| PUT | `/admin/api/apis/{id}` | 更新 |
| PATCH | `/admin/api/apis/{id}/enabled` | 切换启用开关（body: `{ "enabled": true }`） |
| PATCH | `/admin/api/apis/{id}/topology` | 切换绑定拓扑（body: `{ "topologyId": "topo_xxx" }`，同值幂等不更新 updated_at — LEGACY-06） |
| GET | `/admin/api/apis/{id}/topology-switch-preview?targetTopologyId=xxx` | 切换前预扫描：返回 `{missingViews, availableViews, currentSqlReferences, warning}` — LEGACY-06 |
| DELETE | `/admin/api/apis/{id}` | 删除 |
| POST | `/admin/api/apis/{id}/test` | 测试执行（只读、不写库） |
| POST | `/admin/api/apis/export` | 批量导出（body: `{ "ids": [...] }`，不传则全部） |
| POST | `/admin/api/apis/import` | 批量导入 |

**异常场景**：

| 场景 | HTTP 状态码 | code | message |
|------|------------|------|---------|
| 新建时 method + path 冲突 | 409 | 40301 | 接口路径已存在 |
| 新建时缺少必填字段 | 400 | 40001 | {field} 不得为空 |
| 新建时 topology 不存在 | 404 | 40101 | 拓扑不存在 |
| 更新时 api 不存在 | 404 | 40301 | 接口配置不存在 |
| 切换 topology 时 topology 不存在 | 404 | 40101 | 拓扑不存在 |
| 测试执行 SQL 语法错误 | 400 | 40302 | SQL 执行失败 |
| 测试执行 SQL 含非 SELECT 语句 | 400 | 40303 | 仅允许 SELECT 查询 |
| 导入时 JSON 格式错误 | 400 | 40001 | 无效的 JSON 格式 |

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
    "request": {
      "headers": [
        { "name": "X-Tenant-Id", "required": true, "expectValue": null, "example": "t-001", "description": "租户 ID" }
      ],
      "query": [
        { "name": "status", "type": "string", "required": false, "example": "online", "description": "按状态过滤" },
        { "name": "pageNo", "type": "int", "required": false, "example": "1", "description": "页码" }
      ],
      "body": {
        "contentType": "application/json",
        "required": false,
        "example": "{\"userName\": \"admin\"}",
        "description": "请求体示例"
      }
    },
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

**响应模板占位符列表**（M6-01 LEGACY-05 Phase 1 新增派生变量；M6-02 Phase 2 将增加表达式语法，详见《开发方案》§2.12）：

| 占位符 | 类型 | 说明 |
|---|---|---|
| `{{items}}` | list | SQL 执行结果（当前页行数组） |
| `{{total}}` | int | 总行数 `COUNT(*)` |
| `{{page}}` / `{{pageNo}}` | int | 当前页（别名） |
| `{{pageSize}}` | int | 每页大小 |
| `{{totalPageNo}}` / `{{totalPages}}` | int | 总页数 = `ceil(total/pageSize)`，pageSize=0 时为 0（别名） |
| `{{hasNext}}` | bool | `page < totalPageNo` |
| `{{hasPrev}}` | bool | `page > 1 且 total > 0` |
| `{{offset}}` | int | `(page-1) * pageSize` |
| `{{count}}` | int | 当前页实际行数 = `len(items)`，末页可能小于 pageSize |
| `{{uuid}}` | string | uuid4（含连字符） |
| `{{now}}` | string | 当前 UTC 时间，ISO-8601 秒精度，结尾 `Z` |

**ManageOne CMDB 风格响应模板示范**（适配 `objList / totalNum / totalPageNo / currentPage` 字段命名）：

```json
{
  "objList": "{{items}}",
  "totalNum": "{{total}}",
  "pageSize": "{{pageSize}}",
  "totalPageNo": "{{totalPageNo}}",
  "currentPage": "{{pageNo}}"
}
```

调用 `?pageNo=1&pageSize=100` 在 28 行测试数据下渲染结果：

```json
{ "objList": [...], "totalNum": 28, "pageSize": 100, "totalPageNo": 1, "currentPage": 1 }
```

**表达式语法（M6-02 LEGACY-05 Phase 2 新增）**：

`{{ }}` 内的内容若不是单一标识符，则按算术表达式求值。语法（EBNF）：

```ebnf
expression  = term { ("+" | "-") term } ;
term        = factor { ("*" | "/" | "%") factor } ;
factor      = ("+" | "-") factor | primary ;
primary     = NUMBER | IDENTIFIER | function_call | "(" expression ")" ;
function_call = IDENTIFIER "(" [ expression { "," expression } ] ")" ;
```

函数白名单（7 个，严格元数）：

| 函数 | 元数 | 说明 |
|---|---|---|
| `ceil(x)` | 1 | 向上取整 |
| `floor(x)` | 1 | 向下取整 |
| `round(x)` | 1 | 四舍六入五取偶（Python 默认） |
| `abs(x)` | 1 | 绝对值 |
| `int(x)` | 1 | 截断为整数 |
| `min(a, b)` | 2 | 严格 2 元，不支持 3+ |
| `max(a, b)` | 2 | 严格 2 元，不支持 3+ |

资源上限：表达式串 ≤ 200 字符；AST 节点 ≤ 50；结果绝对值 ≤ 10¹⁵。

**正向示例**：

| 表达式 | 上下文 | 结果 |
|---|---|---|
| `{{ceil(total / pageSize)}}` | total=28, pageSize=100 | `1` |
| `{{(pageNo - 1) * pageSize}}` | pageNo=2, pageSize=100 | `100` |
| `{{min(pageNo * pageSize, total)}}` | pageNo=1, pageSize=100, total=28 | `28` |
| `{{max(0, total - pageNo * pageSize)}}` | pageNo=1, pageSize=100, total=28 | `0` |
| `{{int(total / pageSize) + 1}}` | total=28, pageSize=100 | `1` |

**反例**（全部抛 `40303`）：

| 表达式 | 错误码 / 错误类型 |
|---|---|
| `{{__import__('os')}}` | 字符串字面量被拒（'os'） |
| `{{open(0)}}` | 未授权函数 `open` |
| `{{1 / 0}}` | 表达式除零 |
| `{{2 ** 100}}` | 禁用运算符 `Pow` |
| `{{a.b}}` | 禁用语法 `Attribute` |

**类型保留**：whole-string 占位（`"x": "{{total + 1}}"`）保留原生 int/float；in-string 占位（`"page {{pageNo + 1}} / {{ceil(total/pageSize)}}"`）按 `_stringify` 拼字符串。

**错误码**：所有表达式失败统一映射 `TemplateRenderError` → HTTP 400 + `code: 40303`，无新增错误码。

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

**`config.request` 字段说明**（M5 新增，可选 — 缺省时不做请求校验）：

`config.request` 缺省或为 `null` 时完全跳过请求校验，行为与 M4 一致（向后兼容）。

**headers 声明**（`request.headers: HeaderSpec[]`）：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | string | 是 | 请求头名称（大小写不敏感） |
| `required` | boolean | 是 | 缺少时返回 400 + 40020 |
| `expectValue` | string | 否 | 精确匹配值；留空仅校验存在性；不匹配返回 400 + 40021 |
| `example` | string | 否 | 文档示例值，不做校验 |
| `description` | string | 否 | 字段说明 |

> **注意**：headers **不做严格白名单**。HTTP 标准头（`User-Agent` / `Accept` / `Host` / `Connection` 等）由浏览器/curl 自动注入，强制白名单会使所有调用失败。仅校验声明字段的存在性与 expectValue。

**query 声明**（`request.query: QuerySpec[]`）：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | string | 是 | 参数名 |
| `type` | `"string"` / `"int"` / `"bool"` | 是 | 声明类型；传值不匹配返回 400 + 40023 |
| `required` | boolean | 是 | 缺少时返回 400 + 40022 |
| `example` | string | 否 | 文档示例值 |
| `description` | string | 否 | 字段说明 |

> **严格白名单触发条件**：`config.request` 中**显式包含 `query` 字段**（即便数组为空）即启用白名单——调用方传入任何未声明的 query 参数返回 400 + 40025。若 `config.request` 完全缺省 `query` 字段则为自由模式（任意 query 放过）。

**body 声明**（`request.body: BodySpec`）：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `contentType` | `"application/json"` / `"application/x-www-form-urlencoded"` / `"text/plain"` | 是 | 声明 Content-Type（content-type 严格匹配延后到 LEGACY-02） |
| `required` | boolean | 是 | body 必填且请求体为空时返回 400 + 40026 |
| `example` | string | 否 | JSON 示例字符串，仅文档展示，不做 schema 校验 |
| `description` | string | 否 | 字段说明 |

**`config.auth` 字段说明**（M5 新增，可选 — 缺省或 `type=none` 时不做鉴权）：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `type` | `"none"` / `"xtoken"` / `"basic"` | 是 | `none` 视为未启用 |
| `headerName` | string | 否 | 仅 xtoken 模式有效，默认 `X-Auth-Token` |

**鉴权模式说明**：

| 模式 | 调用方携带方式 | 后端验证 |
|------|--------------|---------|
| `none` | 无需携带 | 跳过 step 3 |
| `xtoken` | header `{headerName}: <token>` | 查 `tokens` 表：`token` 存在 AND `revoked=0` AND `expires_at > now`；失败返回 401 + 40401/40402/40403 |
| `basic` | header `Authorization: Basic base64(token:password)` | token 作为 username，`meta.password` 校验；失败返回 401 + 40404 |

---

**mock 端请求校验错误码**（M5 新增，HTTP 400，段位 40020-40029）：

| 错误码 | HTTP | 含义 | 触发条件 |
|--------|------|------|---------|
| 40020 | 400 | 缺少必填请求头 | 声明 `required: true` 的 header 未出现在请求中 |
| 40021 | 400 | 请求头值不匹配 | header 存在但 `expectValue` 与声明不同 |
| 40022 | 400 | 缺少必填 query 参数 | 声明 `required: true` 的 query 参数未出现在请求中 |
| 40023 | 400 | query 参数类型错误 | 声明 `int` 但传 `abc`，声明 `bool` 但传非 true/false/1/0/yes/no |
| 40024 | 415 | （**预留** LEGACY-02） | content-type 严格匹配 |
| 40025 | 400 | 未声明的 query 参数 | 严格白名单启用时传入未声明字段 |
| 40026 | 400 | 请求体必填但为空 | `body.required=true` 但请求体为空 |

**鉴权错误码**（M3-06 已有）：

| 错误码 | HTTP | 含义 |
|--------|------|------|
| 40401 | 401 | 未提供 Token / Token 不存在 |
| 40402 | 401 | Token 已过期 |
| 40403 | 401 | Token 已被撤销 |
| 40404 | 401 | Basic 认证失败（凭证错误 / 格式错误） |

> **管道执行顺序**：step 2 (enabled) → step 3 (authenticate) → step 3.5 (validate_request) → step 4 (fault) → step 5 (execute) → step 6 (render)。鉴权先于请求校验——即使 request 参数也缺，无有效 token 时返回 401 而非 400（最小信息泄露）。

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

> **说明**：Token 注册表服务于 Pipeline 认证校验。ManageOne / eSight 等系统的鉴权接口本身是用户配置的 mock API（`POST /rest/manage/user/login` 等），本模块仅管理"哪些 token 有效"的注册记录，由工程师手动录入。

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/admin/api/tokens` | 分页列出（可按 `revoked` / 未过期过滤） |
| POST | `/admin/api/tokens` | 手动录入 Token（见请求体示例） |
| POST | `/admin/api/tokens/{token}/revoke` | 手动撤销 |
| DELETE | `/admin/api/tokens/expired` | 清理所有已过期 Token |

**POST /admin/api/tokens 请求体**：

```json
{
  "token": "manageone-token-abc123",
  "expires_at": "2026-12-31T23:59:59",
  "auth_type": "xtoken",
  "issued_by_api": "/rest/manage/user/login",
  "meta": { "name": "ManageOne 测试 Token" }
}
```

**POST /admin/api/tokens/{token}/revoke 请求体**：无

**响应**：操作成功返回 `200`，body 为更新后的 Token 对象。

### 2.9 系统设置

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/admin/api/settings` | 返回全部键值 |
| PUT | `/admin/api/settings` | 批量更新（body: `{ "autosave_interval": 60, "mock_path_prefix": "" }`） |
| GET | `/admin/api/settings/{key}` | 单个读取 |

### 2.10 系统状态

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/admin/api/health` | 健康检查（Liveness） |

---

## 3. WebSocket 事件

### 3.1 连接

- 路径：`/admin/ws`
- 连接后，前端可通过发送 `{"type":"subscribe","topics":["api.registered","topology.saved"]}` 订阅感兴趣的事件
- 服务端心跳：每 30s 发送 `{"type":"ping"}`，客户端回 `{"type":"pong"}`

### 3.2 事件清单

| 事件 type | 方向 | 载荷示例 | 用途 |
|-----------|------|---------|------|
| `topology.saved` | S→C | `{ "topologyId": "topo_abc", "ts": "..." }` | 自动保存完成通知 |
| `topology.changed` | S→C | `{ "topologyId": "topo_abc", "by": "other-tab" }` | 提示其他 Tab 修改了同一拓扑 |
| `api.registered` | S→C | `{ "apiId": "api_001", "method":"GET", "path":"..." }` | 接口新增 / 更新 / 删除时刷新列表 |
| `api.enabledChanged` | S→C | `{ "apiId":"api_001", "enabled": true }` | 启用开关状态同步 |
| `token.issued` | S→C | `{ "token":"x-..." }` | Token 变动 |
| `token.revoked` | S→C | `{ "token":"x-..." }` | Token 撤销 |
| `subscribe` / `unsubscribe` | C→S | `{ "topics":["api.registered"] }` | 订阅 / 退订 |
| `ping` / `pong` | 双向 | — | 心跳 |

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
| v1.1 | 2026-04-17 | 完善异常场景：HTTP 状态码语义、字段级验证错误、稀疏字段集、限流响应、各模块异常码表 |
| v1.2 | 2026-05-01 | M5：新增 `config.request`（headers/query/body）+ `config.auth` 字段文档；mock 端错误码 40020-40026；鉴权错误码 40401-40404；管道顺序说明 |

---

## 7. API 设计检查清单

新增或修改接口时逐项核对：

- [ ] 资源 URL 符合命名规范（复数名词、kebab-case、无动词）
- [ ] HTTP 方法使用正确（GET 读取、POST 创建、PUT 全量更新、PATCH 部分更新、DELETE 删除）
- [ ] 返回正确的 HTTP 状态码（不是所有接口都返回 200）
- [ ] 请求参数有 Pydantic/Zod 等 Schema 校验
- [ ] 错误响应格式统一，包含 code 和 message
- [ ] 字段级验证错误包含 details 数组
- [ ] 分页接口有 page + pageSize + total
- [ ] 列表支持 sort 排序
- [ ] 删除资源时检查被引用情况
- [ ] 敏感信息不暴露在错误详情中
- [ ] 符合已有接口的 camelCase/snake_case 映射约定
- [ ] OpenAPI 文档已更新
