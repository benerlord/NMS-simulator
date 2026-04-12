# 网管系统模拟工具 - API 接口设计文档

## 1. 概述

### 1.1 设计原则

- **RESTful 风格**：资源为中心，HTTP 方法语义明确
- **统一响应格式**：所有接口统一返回结构
- **分模块组织**：按业务域划分路由前缀
- **WebSocket 补充**：实时推送使用 WebSocket，与 REST 互补

### 1.2 基础信息

| 项目 | 说明 |
|------|------|
| 基础路径 | `/api` |
| WebSocket | `/ws` |
| 内容类型 | `application/json` |
| 字符编码 | UTF-8 |

### 1.3 统一响应格式

**成功响应：**

```json
{
  "code": 0,
  "message": "success",
  "data": {}
}
```

**分页响应：**

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [],
    "total": 100,
    "pageNo": 1,
    "pageSize": 20
  }
}
```

**错误响应：**

```json
{
  "code": 40001,
  "message": "设备名称已存在",
  "detail": "设备名称 'Switch-01' 已被使用"
}
```

### 1.4 错误码规范

| 范围 | 模块 |
|------|------|
| 10000-19999 | 通用错误 |
| 20000-29999 | 拓扑模块 |
| 30000-39999 | 接口配置模块 |
| 40000-49999 | 协议模块 |
| 50000-59999 | 数据/日志模块 |

**通用错误码：**

| 错误码 | HTTP 状态码 | 说明 |
|--------|------------|------|
| 10001 | 400 | 请求参数无效 |
| 10002 | 404 | 资源不存在 |
| 10003 | 409 | 资源冲突（如名称重复） |
| 10004 | 422 | 数据校验失败 |
| 10005 | 500 | 服务器内部错误 |

### 1.5 通用查询参数

适用于所有列表查询接口：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `pageNo` | int | 否 | 页码，默认 1 |
| `pageSize` | int | 否 | 每页条数，默认 20，最大 1000 |
| `keyword` | string | 否 | 模糊搜索关键词 |
| `sortBy` | string | 否 | 排序字段 |
| `sortOrder` | string | 否 | `asc` / `desc`，默认 `desc` |

---

## 2. 拓扑管理

### 2.1 拓扑图

拓扑图是顶层资源，包含设备、端口、链路等子资源的完整快照。

---

#### `GET /api/topologies`

获取拓扑图列表。

**查询参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `keyword` | string | 否 | 按名称模糊搜索 |
| `sortBy` | string | 否 | 排序字段，可选 `name` / `createdAt` / `updatedAt` |
| `sortOrder` | string | 否 | `asc` / `desc` |

**响应：**

```json
{
  "code": 0,
  "data": {
    "items": [
      {
        "id": "topo_001",
        "name": "默认拓扑",
        "description": "测试环境拓扑",
        "deviceCount": 100,
        "linkCount": 150,
        "portCount": 2400,
        "version": 5,
        "createdAt": "2026-04-12T10:00:00Z",
        "updatedAt": "2026-04-12T15:20:00Z"
      }
    ],
    "total": 3
  }
}
```

---

#### `POST /api/topologies`

创建拓扑图。

**请求体：**

```json
{
  "name": "新拓扑",
  "description": "用于 ManageOne 测试"
}
```

**响应：** 返回创建的拓扑图摘要信息（同列表项结构）。

---

#### `GET /api/topologies/{topologyId}`

获取拓扑图完整数据（包含所有设备、端口、链路、画布状态）。

**响应：**

```json
{
  "code": 0,
  "data": {
    "id": "topo_001",
    "name": "默认拓扑",
    "description": "",
    "version": 5,
    "devices": [],
    "ports": [],
    "links": [],
    "canvas": {
      "zoom": 1.0,
      "offset": { "x": 0, "y": 0 },
      "nodePositions": {}
    },
    "metadata": {
      "deviceCount": 100,
      "linkCount": 150,
      "portCount": 2400
    },
    "createdAt": "2026-04-12T10:00:00Z",
    "updatedAt": "2026-04-12T15:20:00Z"
  }
}
```

---

#### `PUT /api/topologies/{topologyId}`

更新拓扑图基本信息（名称、描述）。

**请求体：**

```json
{
  "name": "更新后的名称",
  "description": "更新后的描述"
}
```

---

#### `DELETE /api/topologies/{topologyId}`

删除拓扑图。

---

#### `POST /api/topologies/{topologyId}/save`

手动保存拓扑图到数据库（持久化当前内存状态）。

**响应：**

```json
{
  "code": 0,
  "data": {
    "version": 6,
    "savedAt": "2026-04-12T15:30:00Z"
  }
}
```

---

#### `POST /api/topologies/{topologyId}/load`

加载拓扑图到内存（切换当前活跃拓扑）。

**说明：** 加载前自动保存当前拓扑。

---

#### `GET /api/topologies/{topologyId}/versions`

获取拓扑图版本历史列表。

**响应：**

```json
{
  "code": 0,
  "data": {
    "items": [
      {
        "version": 5,
        "createdAt": "2026-04-12T15:20:00Z",
        "deviceCount": 100,
        "linkCount": 150
      }
    ],
    "total": 5
  }
}
```

---

#### `POST /api/topologies/{topologyId}/versions/{version}/restore`

回退到指定版本。

---

#### `GET /api/topologies/{topologyId}/export`

导出拓扑图为 JSON 文件。

**响应：** `Content-Type: application/octet-stream`，文件下载。

---

#### `POST /api/topologies/import`

导入拓扑图（JSON 文件上传）。

**请求：** `Content-Type: multipart/form-data`

| 字段 | 类型 | 说明 |
|------|------|------|
| `file` | file | JSON 文件 |
| `name` | string | 导入后的拓扑名称（可选，默认使用文件中的名称） |

---

#### `POST /api/topologies/{topologyId}/validate`

验证拓扑配置的正确性。

**响应：**

```json
{
  "code": 0,
  "data": {
    "valid": false,
    "summary": {
      "deviceCount": 100,
      "portCount": 2400,
      "linkCount": 150,
      "errorCount": 3,
      "warningCount": 2
    },
    "issues": [
      {
        "level": "error",
        "type": "duplicate_name",
        "message": "设备名称重复: 'Switch-01'",
        "target": { "type": "device", "id": "dev_003" },
        "fixable": true,
        "suggestion": "重命名为 'Switch-01-2'"
      }
    ]
  }
}
```

---

#### `POST /api/topologies/{topologyId}/validate/fix`

一键修复可自动修复的拓扑问题。

**请求体：**

```json
{
  "issueTypes": ["duplicate_name", "orphan_port"]
}
```

**响应：** 返回修复结果（修复数量、失败项）。

---

#### `POST /api/topologies/{topologyId}/layout`

应用自动布局算法。

**请求体：**

```json
{
  "algorithm": "hierarchical",
  "options": {
    "nodeSpacing": 100,
    "levelSpacing": 150,
    "direction": "TB"
  }
}
```

**`algorithm` 可选值：** `hierarchical` / `force-directed` / `circular` / `grid`

**响应：** 返回计算后的节点位置映射。

```json
{
  "code": 0,
  "data": {
    "nodePositions": {
      "dev_001": { "x": 100, "y": 50 },
      "dev_002": { "x": 300, "y": 50 }
    }
  }
}
```

---

### 2.2 设备

设备是拓扑图的子资源。以下接口操作的是当前活跃拓扑中的设备（内存数据）。

---

#### `GET /api/topologies/{topologyId}/devices`

获取设备列表。

**查询参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `keyword` | string | 否 | 按名称/DN 模糊搜索 |
| `type` | string | 否 | 设备类型筛选 |
| `status` | string | 否 | 状态筛选：`online` / `offline` |
| `pageNo` | int | 否 | 页码 |
| `pageSize` | int | 否 | 每页条数 |

**响应：**

```json
{
  "code": 0,
  "data": {
    "items": [
      {
        "id": "dev_001",
        "name": "交换机-01",
        "type": "switch",
        "dn": "NE=34603401",
        "ip": "192.168.1.1",
        "vendor": "华为",
        "model": "CE6800",
        "status": "online",
        "portCount": 24,
        "connectedPortCount": 5,
        "customFields": {}
      }
    ],
    "total": 100
  }
}
```

---

#### `POST /api/topologies/{topologyId}/devices`

创建设备。

**请求体：**

```json
{
  "name": "交换机-01",
  "type": "switch",
  "dnTemplate": "NE={id}",
  "ip": "192.168.1.1",
  "vendor": "华为",
  "model": "CE6800",
  "status": "online",
  "position": { "x": 200, "y": 150 },
  "portConfig": {
    "count": 24,
    "prefix": "10GE1/0/",
    "indexPlaceholder": "{index}",
    "type": "10GE",
    "speed": "10Gbps",
    "dnTemplate": "{deviceDn},PORT={index}"
  },
  "customFields": {
    "rack": "A01",
    "floor": "3F"
  }
}
```

**说明：**
- `portConfig` 可选。提供时自动生成端口列表。
- `dnTemplate` 中的 `{id}` 由系统自动替换为设备 ID 数字部分。

**响应：** 返回创建的设备（含生成的 id、dn、端口列表）。

---

#### `GET /api/topologies/{topologyId}/devices/{deviceId}`

获取设备详情（含端口列表）。

---

#### `PUT /api/topologies/{topologyId}/devices/{deviceId}`

更新设备属性。

**请求体：** 与创建相同，只传需要更新的字段（partial update）。

---

#### `DELETE /api/topologies/{topologyId}/devices/{deviceId}`

删除设备。同时删除关联的端口和链路。

---

#### `PUT /api/topologies/{topologyId}/devices/batch`

批量更新设备属性。

**请求体：**

```json
{
  "deviceIds": ["dev_001", "dev_002", "dev_003"],
  "updates": {
    "status": "offline",
    "vendor": "华为"
  }
}
```

---

#### `DELETE /api/topologies/{topologyId}/devices/batch`

批量删除设备。

**请求体：**

```json
{
  "deviceIds": ["dev_001", "dev_002"]
}
```

---

### 2.3 端口

端口是设备的子资源。

---

#### `GET /api/topologies/{topologyId}/devices/{deviceId}/ports`

获取设备的端口列表。

**查询参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `keyword` | string | 否 | 按名称/DN 搜索 |
| `status` | string | 否 | `connected` / `free` / `down` |
| `type` | string | 否 | 端口类型筛选 |

**响应：**

```json
{
  "code": 0,
  "data": {
    "items": [
      {
        "id": "port_001",
        "deviceId": "dev_001",
        "name": "10GE1/0/1",
        "dn": "NE=34603401,PORT=1",
        "type": "10GE",
        "speed": "10Gbps",
        "status": "connected",
        "connectedTo": {
          "deviceId": "dev_002",
          "deviceName": "服务器-01",
          "portId": "port_050",
          "portName": "eth0",
          "linkId": "link_001"
        }
      }
    ],
    "total": 24
  }
}
```

---

#### `POST /api/topologies/{topologyId}/devices/{deviceId}/ports`

手动添加单个端口。

**请求体：**

```json
{
  "name": "10GE1/0/25",
  "dnTemplate": "{deviceDn},PORT=25",
  "type": "10GE",
  "speed": "10Gbps",
  "status": "free"
}
```

---

#### `POST /api/topologies/{topologyId}/devices/{deviceId}/ports/generate`

批量生成端口。

**请求体：**

```json
{
  "count": 24,
  "prefix": "10GE1/0/",
  "startIndex": 1,
  "type": "10GE",
  "speed": "10Gbps",
  "dnTemplate": "{deviceDn},PORT={index}",
  "overwrite": false
}
```

| 字段 | 说明 |
|------|------|
| `overwrite` | `true` 清空已有端口后重新生成，`false` 追加到已有端口列表 |

**响应：** 返回生成的端口列表。

---

#### `PUT /api/topologies/{topologyId}/ports/{portId}`

更新单个端口。

---

#### `PUT /api/topologies/{topologyId}/devices/{deviceId}/ports/batch`

批量更新端口属性。

**请求体：**

```json
{
  "portIds": ["port_001", "port_002"],
  "updates": {
    "type": "25GE",
    "speed": "25Gbps"
  }
}
```

---

#### `DELETE /api/topologies/{topologyId}/ports/{portId}`

删除端口。如果端口已连接，同时删除关联链路。

---

#### `GET /api/topologies/{topologyId}/devices/{deviceId}/ports/export`

导出设备的端口数据。

**响应：** JSON 文件下载。

---

#### `POST /api/topologies/{topologyId}/devices/{deviceId}/ports/import`

导入端口数据。

**请求：** `Content-Type: multipart/form-data`

---

### 2.4 链路

---

#### `GET /api/topologies/{topologyId}/links`

获取链路列表。

**查询参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `keyword` | string | 否 | 按设备名称/DN 搜索 |
| `type` | string | 否 | 链路类型：`physical` / `logical` / `aggregate` |
| `status` | string | 否 | `up` / `down` |
| `deviceId` | string | 否 | 筛选与指定设备相关的链路 |

**响应：**

```json
{
  "code": 0,
  "data": {
    "items": [
      {
        "id": "link_001",
        "sourceDeviceId": "dev_001",
        "sourceDeviceName": "交换机-01",
        "sourceDeviceDn": "NE=34603401",
        "sourcePortId": "port_001",
        "sourcePortName": "10GE1/0/1",
        "sourcePortDn": "NE=34603401,PORT=1",
        "targetDeviceId": "dev_002",
        "targetDeviceName": "服务器-01",
        "targetDeviceDn": "NE=34603402",
        "targetPortId": "port_050",
        "targetPortName": "eth0",
        "targetPortDn": "NE=34603402,PORT=1",
        "type": "physical",
        "bandwidth": "10Gbps",
        "status": "up",
        "description": ""
      }
    ],
    "total": 150
  }
}
```

---

#### `POST /api/topologies/{topologyId}/links`

创建链路（建立连接）。

**请求体：**

```json
{
  "sourceDeviceId": "dev_001",
  "sourcePortId": "port_001",
  "targetDeviceId": "dev_002",
  "targetPortId": "port_050",
  "type": "physical",
  "bandwidth": "10Gbps",
  "status": "up",
  "description": ""
}
```

**副作用：** 自动将两端端口状态标记为 `connected`。

---

#### `PUT /api/topologies/{topologyId}/links/{linkId}`

更新链路属性。

---

#### `DELETE /api/topologies/{topologyId}/links/{linkId}`

删除链路（断开连接）。

**副作用：** 自动将两端端口状态恢复为 `free`。

---

#### `DELETE /api/topologies/{topologyId}/links/batch`

批量删除链路。

**请求体：**

```json
{
  "linkIds": ["link_001", "link_002"]
}
```

---

### 2.5 告警数据

告警数据挂在拓扑下，关联到设备。

---

#### `GET /api/topologies/{topologyId}/alarms`

获取告警列表。

**查询参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `keyword` | string | 否 | 按内容搜索 |
| `level` | string | 否 | `critical` / `major` / `minor` / `warning` |
| `deviceId` | string | 否 | 按设备筛选 |
| `status` | string | 否 | `active` / `cleared` |
| `pageNo` | int | 否 | 页码 |
| `pageSize` | int | 否 | 每页条数 |

**响应：**

```json
{
  "code": 0,
  "data": {
    "items": [
      {
        "id": "alarm_001",
        "deviceId": "dev_001",
        "deviceName": "交换机-01",
        "deviceDn": "NE=34603401",
        "level": "critical",
        "type": "linkDown",
        "content": "接口 10GE1/0/1 链路中断",
        "status": "active",
        "occurTime": "2026-04-12T14:00:00Z",
        "clearTime": null
      }
    ],
    "total": 50,
    "summary": {
      "critical": 5,
      "major": 12,
      "minor": 20,
      "warning": 13
    }
  }
}
```

---

#### `POST /api/topologies/{topologyId}/alarms`

手动创建告警。

**请求体：**

```json
{
  "deviceId": "dev_001",
  "level": "critical",
  "type": "linkDown",
  "content": "接口 10GE1/0/1 链路中断"
}
```

---

#### `PUT /api/topologies/{topologyId}/alarms/{alarmId}`

更新告警。

---

#### `DELETE /api/topologies/{topologyId}/alarms/{alarmId}`

删除告警。

---

#### `POST /api/topologies/{topologyId}/alarms/{alarmId}/clear`

清除告警（标记为 cleared，记录 clearTime）。

---

#### `POST /api/topologies/{topologyId}/alarms/batch`

批量创建告警。

**请求体：**

```json
{
  "alarms": [
    { "deviceId": "dev_001", "level": "major", "type": "cpuHigh", "content": "CPU 使用率超过 90%" }
  ]
}
```

---

#### `DELETE /api/topologies/{topologyId}/alarms/batch`

批量删除告警。

---

### 2.6 指标数据

---

#### `GET /api/topologies/{topologyId}/metrics`

获取指标数据列表。

**查询参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `deviceId` | string | 否 | 按设备筛选 |
| `metricName` | string | 否 | 指标名称筛选 |
| `pageNo` | int | 否 | 页码 |
| `pageSize` | int | 否 | 每页条数 |

**响应：**

```json
{
  "code": 0,
  "data": {
    "items": [
      {
        "id": "metric_001",
        "deviceId": "dev_001",
        "deviceName": "交换机-01",
        "deviceDn": "NE=34603401",
        "name": "cpuUsage",
        "value": 45.2,
        "unit": "%",
        "collectTime": "2026-04-12T15:00:00Z",
        "collectInterval": 300
      }
    ],
    "total": 500
  }
}
```

---

#### `POST /api/topologies/{topologyId}/metrics`

创建/更新指标数据。

---

#### `POST /api/topologies/{topologyId}/metrics/batch`

批量创建/更新指标数据。

---

#### `DELETE /api/topologies/{topologyId}/metrics/batch`

批量删除指标数据。

---

### 2.7 设备类型

设备类型是全局资源，不属于某个特定拓扑。

---

#### `GET /api/device-types`

获取设备类型列表（含预定义 + 自定义）。

**响应：**

```json
{
  "code": 0,
  "data": {
    "items": [
      {
        "id": "switch",
        "name": "网络交换机",
        "icon": "switch",
        "color": "#1890ff",
        "shape": "rect",
        "builtIn": true,
        "capabilities": {
          "hasPorts": true,
          "canConnectNetwork": true,
          "canConnectServer": true
        },
        "fields": [
          {
            "name": "vendor",
            "label": "厂商",
            "type": "text",
            "required": false,
            "default": ""
          },
          {
            "name": "model",
            "label": "型号",
            "type": "text",
            "required": false,
            "default": ""
          }
        ]
      }
    ]
  }
}
```

---

#### `POST /api/device-types`

创建自定义设备类型。

---

#### `PUT /api/device-types/{typeId}`

更新设备类型。仅允许更新自定义类型。

---

#### `DELETE /api/device-types/{typeId}`

删除自定义设备类型。如果有设备正在使用该类型，返回冲突错误。

---

### 2.8 画布状态

画布状态（缩放、偏移、节点位置）的持久化。

---

#### `PUT /api/topologies/{topologyId}/canvas`

更新画布状态。

**请求体：**

```json
{
  "zoom": 1.2,
  "offset": { "x": -50, "y": 30 },
  "nodePositions": {
    "dev_001": { "x": 100, "y": 100 },
    "dev_002": { "x": 300, "y": 200 }
  }
}
```

**说明：** 前端通过防抖策略调用此接口保存画布状态。

---

## 3. HTTP 接口配置

管理用户配置的模拟 HTTP 接口。

---

#### `GET /api/api-configs`

获取接口配置列表。

**查询参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `keyword` | string | 否 | 按名称/路径搜索 |
| `group` | string | 否 | 按分组筛选 |
| `enabled` | boolean | 否 | 按启用状态筛选 |
| `dataSourceType` | string | 否 | `sql` / `static` |

**响应：**

```json
{
  "code": 0,
  "data": {
    "items": [
      {
        "id": "api_001",
        "name": "设备查询接口",
        "group": "ManageOne",
        "method": "GET",
        "path": "/rest/openapi/network/v1/devices",
        "dataSourceType": "sql",
        "enabled": true,
        "createdAt": "2026-04-12T10:00:00Z",
        "updatedAt": "2026-04-12T15:00:00Z"
      }
    ],
    "total": 10
  }
}
```

---

#### `GET /api/api-configs/groups`

获取分组列表及各分组接口数量。

**响应：**

```json
{
  "code": 0,
  "data": [
    { "name": "ManageOne", "count": 5 },
    { "name": "eSight", "count": 3 }
  ]
}
```

---

#### `POST /api/api-configs`

创建接口配置。

**请求体：**

```json
{
  "name": "设备查询接口",
  "group": "ManageOne",
  "enabled": true,

  "method": "GET",
  "path": "/rest/openapi/network/v1/devices",

  "auth": {
    "type": "xtoken",
    "headerName": "X-Auth-Token"
  },

  "dataSource": {
    "type": "sql",
    "sql": "SELECT * FROM devices WHERE (:type IS NULL OR type = :type) ORDER BY name ASC"
  },

  "query": {
    "params": [
      { "param": "type", "sqlParam": ":type", "default": null }
    ],
    "pagination": {
      "enabled": true,
      "pageNoParam": "pageNo",
      "pageSizeParam": "pageSize",
      "defaultPageSize": 100
    }
  },

  "response": {
    "contentType": "application/json",
    "template": {
      "code": 0,
      "data": "{{items}}",
      "total": "{{total}}",
      "pageNo": "{{pageNo}}",
      "pageSize": "{{pageSize}}"
    }
  },

  "fault": {
    "delay": 0,
    "errorRate": 0,
    "errorStatus": 500
  }
}
```

**说明：** 创建后自动注册动态路由，立即生效。

---

#### `GET /api/api-configs/{configId}`

获取接口配置详情。

---

#### `PUT /api/api-configs/{configId}`

更新接口配置。更新后自动重新注册路由。

---

#### `DELETE /api/api-configs/{configId}`

删除接口配置。同时移除对应动态路由。

---

#### `PUT /api/api-configs/{configId}/enabled`

切换接口启用/禁用状态。

**请求体：**

```json
{
  "enabled": false
}
```

---

#### `POST /api/api-configs/{configId}/test`

测试执行接口配置。模拟一次请求，返回 SQL 执行结果和最终响应。

**请求体：**

```json
{
  "params": {
    "type": "switch",
    "pageNo": 1,
    "pageSize": 10
  },
  "headers": {
    "X-Auth-Token": "test-token"
  }
}
```

**响应：**

```json
{
  "code": 0,
  "data": {
    "executedSql": "SELECT * FROM devices WHERE type = 'switch' ORDER BY name ASC LIMIT 10 OFFSET 0",
    "queryResult": {
      "items": [],
      "total": 5000
    },
    "renderedResponse": {
      "code": 0,
      "data": [],
      "total": 5000,
      "pageNo": 1,
      "pageSize": 10
    },
    "executionTime": 45
  }
}
```

---

#### `GET /api/api-configs/export`

导出所有接口配置为 JSON 文件。

**查询参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `group` | string | 否 | 只导出指定分组 |

---

#### `POST /api/api-configs/import`

导入接口配置。

**请求体：**

```json
{
  "configs": [],
  "overwrite": false
}
```

| 字段 | 说明 |
|------|------|
| `overwrite` | `true` 覆盖同 ID 配置，`false` 跳过已存在的 |

---

#### `GET /api/api-configs/default-sql/{collection}`

获取指定数据集合的默认 SQL。

**路径参数：**

| 参数 | 可选值 |
|------|--------|
| `collection` | `devices` / `ports` / `links` / `alarms` / `metrics` |

**响应：**

```json
{
  "code": 0,
  "data": {
    "collection": "links",
    "sql": "SELECT\n  l.*,\n  d1.name AS sourceDeviceName,\n  d1.dn AS sourceDeviceDn,\n  p1.name AS sourcePortName,\n  p1.dn AS sourcePortDn,\n  d2.name AS targetDeviceName,\n  d2.dn AS targetDeviceDn,\n  p2.name AS targetPortName,\n  p2.dn AS targetPortDn\nFROM links l\n  JOIN devices d1 ON l.sourceDeviceId = d1.id\n  JOIN ports p1 ON l.sourcePortId = p1.id\n  JOIN devices d2 ON l.targetDeviceId = d2.id\n  JOIN ports p2 ON l.targetPortId = p2.id",
    "description": "链路查询（已自动 JOIN 关联设备和端口 DN）"
  }
}
```

---

## 4. Token 认证管理

管理 HTTP Mock Server 的 Token 认证。

---

#### `GET /api/sessions`

获取当前活跃的 Token 列表。

**响应：**

```json
{
  "code": 0,
  "data": {
    "items": [
      {
        "token": "x-abc123...",
        "createdAt": "2026-04-12T15:00:00Z",
        "expiresAt": "2026-04-12T15:30:00Z",
        "isExpired": false
      }
    ],
    "total": 2
  }
}
```

---

#### `DELETE /api/sessions/{token}`

手动使 Token 失效。

---

#### `DELETE /api/sessions`

清空所有 Token。

---

#### `PUT /api/sessions/config`

配置 Token 认证参数。

**请求体：**

```json
{
  "tokenExpiry": 1800,
  "credentials": [
    { "username": "IMOCTest", "password": "Imoc@12345" }
  ]
}
```

---

#### `GET /api/sessions/config`

获取 Token 认证配置。

---

## 5. 协议管理

管理协议插件的生命周期和配置。

### 5.1 协议插件通用操作

---

#### `GET /api/protocols`

获取所有协议插件状态。

**响应：**

```json
{
  "code": 0,
  "data": [
    {
      "name": "http-mock",
      "displayName": "HTTP Mock Server",
      "status": "running",
      "port": 8080,
      "startedAt": "2026-04-12T10:00:00Z",
      "stats": {
        "totalRequests": 1250,
        "activeRoutes": 10
      }
    },
    {
      "name": "snmp-agent",
      "displayName": "SNMP Agent",
      "status": "stopped",
      "port": 161,
      "startedAt": null,
      "stats": null
    },
    {
      "name": "sftp-server",
      "displayName": "SFTP Server",
      "status": "running",
      "port": 2222,
      "startedAt": "2026-04-12T10:00:00Z",
      "stats": {
        "generatedFiles": 48,
        "totalSize": "256MB"
      }
    },
    {
      "name": "kafka-producer",
      "displayName": "Kafka Producer",
      "status": "error",
      "error": "Connection refused: localhost:9092",
      "startedAt": null,
      "stats": null
    }
  ]
}
```

---

#### `POST /api/protocols/{protocolName}/start`

启动协议插件。

**`protocolName` 可选值：** `http-mock` / `snmp-agent` / `sftp-server` / `kafka-producer`

---

#### `POST /api/protocols/{protocolName}/stop`

停止协议插件。

---

#### `POST /api/protocols/{protocolName}/restart`

重启协议插件。

---

#### `GET /api/protocols/{protocolName}/health`

健康检查。

**响应：**

```json
{
  "code": 0,
  "data": {
    "healthy": true,
    "uptime": 18000,
    "lastError": null,
    "checks": {
      "port_available": true,
      "memory_ok": true
    }
  }
}
```

---

#### `POST /api/protocols/start-all`

一键启动所有协议插件。

---

#### `POST /api/protocols/stop-all`

一键停止所有协议插件。

---

### 5.2 HTTP Mock Server 配置

---

#### `GET /api/protocols/http-mock/config`

获取 HTTP Mock Server 配置。

**响应：**

```json
{
  "code": 0,
  "data": {
    "port": 8080,
    "host": "0.0.0.0"
  }
}
```

---

#### `PUT /api/protocols/http-mock/config`

更新 HTTP Mock Server 配置。需要重启后生效。

---

#### `GET /api/protocols/http-mock/routes`

获取当前已注册的动态路由列表。

**响应：**

```json
{
  "code": 0,
  "data": [
    {
      "method": "GET",
      "path": "/rest/openapi/network/v1/devices",
      "configId": "api_001",
      "configName": "设备查询接口",
      "enabled": true
    }
  ]
}
```

---

### 5.3 SNMP 配置

---

#### `GET /api/protocols/snmp-agent/config`

获取 SNMP Agent 配置。

**响应：**

```json
{
  "code": 0,
  "data": {
    "port": 161,
    "host": "0.0.0.0",
    "versions": ["v2c"],
    "v2c": {
      "community": "public"
    },
    "v3": {
      "users": []
    }
  }
}
```

---

#### `PUT /api/protocols/snmp-agent/config`

更新 SNMP Agent 配置。

---

#### `GET /api/protocols/snmp-agent/oids`

获取 OID 配置列表。

**查询参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `keyword` | string | 否 | 按 OID/描述搜索 |
| `group` | string | 否 | 按分组筛选 |
| `deviceType` | string | 否 | 按设备类型筛选 |
| `pageNo` | int | 否 | 页码 |
| `pageSize` | int | 否 | 每页条数 |

**响应：**

```json
{
  "code": 0,
  "data": {
    "items": [
      {
        "id": "oid_001",
        "oid": "1.3.6.1.2.1.1.1.0",
        "name": "sysDescr",
        "group": "system",
        "dataType": "OctetString",
        "valueSource": "topology",
        "valueMapping": "device.description",
        "description": "系统描述"
      }
    ],
    "total": 50
  }
}
```

---

#### `POST /api/protocols/snmp-agent/oids`

创建 OID 配置。

---

#### `PUT /api/protocols/snmp-agent/oids/{oidId}`

更新 OID 配置。

---

#### `DELETE /api/protocols/snmp-agent/oids/{oidId}`

删除 OID 配置。

---

#### `POST /api/protocols/snmp-agent/oids/import`

批量导入 OID。

**请求体：**

```json
{
  "oids": [],
  "overwrite": false
}
```

---

#### `GET /api/protocols/snmp-agent/oids/export`

导出 OID 配置。

---

#### `POST /api/protocols/snmp-agent/oids/{oidId}/test`

测试 OID 查询（模拟 GET 操作）。

**响应：**

```json
{
  "code": 0,
  "data": {
    "oid": "1.3.6.1.2.1.1.1.0",
    "type": "OctetString",
    "value": "Huawei CE6800 Switch"
  }
}
```

---

#### `GET /api/protocols/snmp-agent/trap/config`

获取 Trap 配置。

**响应：**

```json
{
  "code": 0,
  "data": {
    "destinations": [
      {
        "id": "trap_dest_001",
        "host": "192.168.1.100",
        "port": 162,
        "version": "v2c",
        "community": "public"
      }
    ],
    "templates": [
      {
        "id": "trap_tpl_001",
        "name": "告警新增",
        "trapOid": "1.3.6.1.4.1.2011.5.25.219.2.6.0.1",
        "varbinds": [
          { "oid": "1.3.6.1.4.1.2011.5.25.219.2.6.1.1", "type": "OctetString", "valueMapping": "alarm.level" }
        ]
      }
    ]
  }
}
```

---

#### `PUT /api/protocols/snmp-agent/trap/config`

更新 Trap 配置。

---

#### `POST /api/protocols/snmp-agent/trap/send`

手动触发 Trap 发送。

**请求体：**

```json
{
  "templateId": "trap_tpl_001",
  "alarmIds": ["alarm_001", "alarm_002"]
}
```

---

#### `POST /api/protocols/snmp-agent/trap/send-batch`

批量发送 Trap（模拟告警风暴）。

**请求体：**

```json
{
  "templateId": "trap_tpl_001",
  "count": 100,
  "interval": 100
}
```

| 字段 | 说明 |
|------|------|
| `count` | 发送数量 |
| `interval` | 发送间隔（ms） |

---

### 5.4 SFTP 配置

---

#### `GET /api/protocols/sftp-server/config`

获取 SFTP 服务配置。

**响应：**

```json
{
  "code": 0,
  "data": {
    "port": 2222,
    "host": "0.0.0.0",
    "users": [
      { "username": "sftpuser", "authType": "password" }
    ],
    "rootPath": "./data/sftp_files"
  }
}
```

---

#### `PUT /api/protocols/sftp-server/config`

更新 SFTP 服务配置。

---

#### `GET /api/protocols/sftp-server/templates`

获取文件生成模板列表。

**响应：**

```json
{
  "code": 0,
  "data": {
    "items": [
      {
        "id": "tpl_001",
        "name": "网络设备指标文件",
        "deviceTypes": ["switch", "router"],
        "fileType": "csv",
        "nameTemplate": "PM_IGHostPerfStat_5_{timestamp}_partition_{seq}.csv",
        "generateInterval": 300,
        "enabled": true,
        "headers": [
          { "name": "deviceName", "type": "string", "source": "device.name" },
          { "name": "deviceDn", "type": "string", "source": "device.dn" },
          { "name": "cpuUsage", "type": "number", "source": "metric.cpuUsage" }
        ]
      }
    ]
  }
}
```

---

#### `POST /api/protocols/sftp-server/templates`

创建文件生成模板。

---

#### `PUT /api/protocols/sftp-server/templates/{templateId}`

更新文件生成模板。

---

#### `DELETE /api/protocols/sftp-server/templates/{templateId}`

删除文件生成模板。

---

#### `POST /api/protocols/sftp-server/templates/{templateId}/generate`

立即按模板生成测试文件（不等待定时任务）。

**响应：**

```json
{
  "code": 0,
  "data": {
    "filePath": "/20260412/PM_IGHostPerfStat_5_20260412_1520_partition_001.csv",
    "fileSize": 102400,
    "rowCount": 500
  }
}
```

---

#### `GET /api/protocols/sftp-server/files`

浏览已生成的文件。

**查询参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `path` | string | 否 | 目录路径，默认根目录 |
| `date` | string | 否 | 按日期筛选，格式 `YYYYMMDD` |

**响应：**

```json
{
  "code": 0,
  "data": {
    "currentPath": "/20260412",
    "items": [
      {
        "name": "PM_IGHostPerfStat_5_20260412_1520_partition_001.csv",
        "type": "file",
        "size": 102400,
        "createdAt": "2026-04-12T15:20:00Z"
      }
    ]
  }
}
```

---

#### `GET /api/protocols/sftp-server/files/download`

下载文件。

**查询参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `path` | string | 是 | 文件路径 |

**响应：** `Content-Type: application/octet-stream`

---

#### `GET /api/protocols/sftp-server/files/preview`

预览 CSV 文件内容。

**查询参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `path` | string | 是 | CSV 文件路径 |
| `limit` | int | 否 | 预览行数，默认 50 |

**响应：**

```json
{
  "code": 0,
  "data": {
    "headers": ["deviceName", "deviceDn", "cpuUsage"],
    "rows": [
      ["交换机-01", "NE=34603401", "45.2"]
    ],
    "totalRows": 500
  }
}
```

---

#### `DELETE /api/protocols/sftp-server/files`

删除文件。

**请求体：**

```json
{
  "paths": ["/20260412/PM_xxx.csv"]
}
```

---

#### `DELETE /api/protocols/sftp-server/files/clear`

清空所有历史文件。

---

### 5.5 Kafka 配置

---

#### `GET /api/protocols/kafka-producer/config`

获取 Kafka 生产者配置。

**响应：**

```json
{
  "code": 0,
  "data": {
    "bootstrapServers": "localhost:9092",
    "acks": "all",
    "retries": 3,
    "batchSize": 16384,
    "security": {
      "protocol": "PLAINTEXT"
    }
  }
}
```

---

#### `PUT /api/protocols/kafka-producer/config`

更新 Kafka 生产者配置。

---

#### `POST /api/protocols/kafka-producer/test-connection`

测试 Kafka 连接。

**响应：**

```json
{
  "code": 0,
  "data": {
    "connected": true,
    "brokers": ["localhost:9092"],
    "latency": 15
  }
}
```

---

#### `GET /api/protocols/kafka-producer/topics`

获取 Topic 配置列表。

**响应：**

```json
{
  "code": 0,
  "data": {
    "items": [
      {
        "id": "topic_001",
        "topic": "nms.devices",
        "messageType": "device",
        "format": "json",
        "sendMode": "periodic",
        "sendInterval": 300,
        "enabled": true,
        "template": {}
      }
    ]
  }
}
```

---

#### `POST /api/protocols/kafka-producer/topics`

创建 Topic 配置。

**请求体：**

```json
{
  "topic": "nms.devices",
  "messageType": "device",
  "format": "json",
  "sendMode": "periodic",
  "sendInterval": 300,
  "enabled": true,
  "template": {
    "deviceId": "{{device.id}}",
    "deviceName": "{{device.name}}",
    "deviceType": "{{device.type}}",
    "dn": "{{device.dn}}"
  }
}
```

---

#### `PUT /api/protocols/kafka-producer/topics/{topicId}`

更新 Topic 配置。

---

#### `DELETE /api/protocols/kafka-producer/topics/{topicId}`

删除 Topic 配置。

---

#### `POST /api/protocols/kafka-producer/topics/{topicId}/send`

手动触发发送消息。

**请求体（可选）：**

```json
{
  "deviceIds": ["dev_001", "dev_002"],
  "count": 10
}
```

**说明：** 不传 `deviceIds` 时使用全部设备数据。

---

#### `POST /api/protocols/kafka-producer/topics/{topicId}/send-test`

发送测试消息（预览实际消息内容）。

**响应：**

```json
{
  "code": 0,
  "data": {
    "messageCount": 1,
    "sampleMessage": {
      "key": "dev_001",
      "value": {
        "deviceId": "dev_001",
        "deviceName": "交换机-01",
        "deviceType": "switch",
        "dn": "NE=34603401"
      }
    }
  }
}
```

---

#### `GET /api/protocols/kafka-producer/stats`

获取消息发送统计。

**响应：**

```json
{
  "code": 0,
  "data": {
    "totalSent": 5000,
    "totalFailed": 12,
    "sendRate": 3.5,
    "lastSentAt": "2026-04-12T15:20:00Z",
    "byTopic": {
      "nms.devices": { "sent": 2000, "failed": 5 },
      "nms.alarms": { "sent": 3000, "failed": 7 }
    },
    "recentFailures": [
      {
        "topic": "nms.alarms",
        "error": "MessageTooLarge",
        "timestamp": "2026-04-12T15:18:00Z"
      }
    ]
  }
}
```

---

#### `POST /api/protocols/kafka-producer/retry-failed`

重发失败消息。

---

## 6. 数据查询

这些接口用于前端"数据查看"页面，提供格式化的数据视图。与拓扑子资源接口的区别在于：数据查看接口提供更丰富的聚合统计和跨拓扑视图。

---

#### `POST /api/query/sql`

执行自定义 SQL 查询（用于 SQL 编辑器的测试执行功能）。

**请求体：**

```json
{
  "sql": "SELECT type, COUNT(*) AS count FROM devices GROUP BY type ORDER BY count DESC",
  "params": {},
  "limit": 100
}
```

**响应：**

```json
{
  "code": 0,
  "data": {
    "columns": ["type", "count"],
    "rows": [
      { "type": "switch", "count": 50 },
      { "type": "server", "count": 30 }
    ],
    "rowCount": 3,
    "executionTime": 12
  }
}
```

---

#### `GET /api/query/collections`

获取可用的虚拟表信息（供前端 SQL 编辑器自动补全）。

**响应：**

```json
{
  "code": 0,
  "data": [
    {
      "name": "devices",
      "displayName": "设备表",
      "rowCount": 100,
      "columns": [
        { "name": "id", "type": "TEXT" },
        { "name": "name", "type": "TEXT" },
        { "name": "type", "type": "TEXT" },
        { "name": "dn", "type": "TEXT" },
        { "name": "ip", "type": "TEXT" },
        { "name": "vendor", "type": "TEXT" },
        { "name": "model", "type": "TEXT" },
        { "name": "status", "type": "TEXT" }
      ]
    }
  ]
}
```

---

## 7. 日志

---

#### `GET /api/logs/requests`

获取请求日志（HTTP Mock Server 收到的外部请求）。

**查询参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `method` | string | 否 | 请求方法筛选 |
| `path` | string | 否 | 路径模糊搜索 |
| `statusCode` | int | 否 | 状态码筛选 |
| `startTime` | string | 否 | 开始时间 |
| `endTime` | string | 否 | 结束时间 |
| `pageNo` | int | 否 | 页码 |
| `pageSize` | int | 否 | 每页条数 |

**响应：**

```json
{
  "code": 0,
  "data": {
    "items": [
      {
        "id": "req_001",
        "timestamp": "2026-04-12T15:20:00Z",
        "method": "GET",
        "path": "/rest/openapi/network/v1/devices",
        "query": "type=switch&pageNo=1&pageSize=50",
        "statusCode": 200,
        "duration": 45,
        "configId": "api_001",
        "configName": "设备查询接口",
        "clientIp": "192.168.1.100"
      }
    ],
    "total": 1250
  }
}
```

---

#### `GET /api/logs/requests/{requestId}`

获取请求详情（含请求头、请求体、响应体）。

**响应：**

```json
{
  "code": 0,
  "data": {
    "id": "req_001",
    "timestamp": "2026-04-12T15:20:00Z",
    "method": "GET",
    "path": "/rest/openapi/network/v1/devices",
    "query": "type=switch&pageNo=1&pageSize=50",
    "headers": {
      "X-Auth-Token": "x-abc123",
      "Content-Type": "application/json"
    },
    "requestBody": null,
    "statusCode": 200,
    "responseHeaders": { "Content-Type": "application/json" },
    "responseBody": {},
    "duration": 45,
    "configId": "api_001",
    "clientIp": "192.168.1.100"
  }
}
```

---

#### `DELETE /api/logs/requests`

清空请求日志。

---

#### `GET /api/logs/system`

获取系统运行日志。

**查询参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `level` | string | 否 | `info` / `warn` / `error` |
| `module` | string | 否 | `http` / `snmp` / `sftp` / `kafka` / `topology` / `system` |
| `keyword` | string | 否 | 内容搜索 |
| `startTime` | string | 否 | 开始时间 |
| `endTime` | string | 否 | 结束时间 |
| `pageNo` | int | 否 | 页码 |
| `pageSize` | int | 否 | 每页条数 |

**响应：**

```json
{
  "code": 0,
  "data": {
    "items": [
      {
        "id": "log_001",
        "timestamp": "2026-04-12T15:20:00Z",
        "level": "info",
        "module": "http",
        "message": "HTTP Mock Server started on port 8080"
      }
    ],
    "total": 500
  }
}
```

---

#### `GET /api/logs/export`

导出日志文件。

**查询参数：** 同 `GET /api/logs/system` 的筛选参数。

**响应：** 文本文件下载。

---

## 8. 系统设置

---

#### `GET /api/settings`

获取系统设置。

**响应：**

```json
{
  "code": 0,
  "data": {
    "general": {
      "appPort": 8000,
      "logLevel": "info",
      "dataDir": "./data",
      "maxDevices": 50000
    },
    "autoSave": {
      "enabled": true,
      "debounceSeconds": 3,
      "intervalSeconds": 60
    },
    "history": {
      "maxVersions": 10,
      "maxRequestLogs": 10000
    }
  }
}
```

---

#### `PUT /api/settings`

更新系统设置。

**请求体：** 与 GET 响应结构相同（partial update，只传需要修改的部分）。

---

#### `POST /api/settings/reset`

恢复默认设置。

---

#### `GET /api/system/info`

获取系统信息。

**响应：**

```json
{
  "code": 0,
  "data": {
    "version": "1.0.0",
    "python": "3.11.8",
    "platform": "Windows 11",
    "uptime": 86400,
    "activeTopology": {
      "id": "topo_001",
      "name": "默认拓扑"
    },
    "resources": {
      "cpuPercent": 12.5,
      "memoryUsedMB": 512,
      "memoryTotalMB": 8192,
      "diskUsedMB": 128,
      "diskFreeMB": 50000
    }
  }
}
```

---

## 9. WebSocket 接口

### 9.1 连接

**端点：** `ws://localhost:8000/ws`

**连接参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `channels` | string | 否 | 订阅频道，逗号分隔，默认订阅全部 |

**示例：** `ws://localhost:8000/ws?channels=topology,protocol,request_log`

### 9.2 消息格式

**服务端推送（Server → Client）：**

```json
{
  "type": "event",
  "channel": "topology",
  "action": "device.created",
  "payload": {
    "device": { "id": "dev_001", "name": "交换机-01" }
  },
  "timestamp": "2026-04-12T15:20:00Z"
}
```

**客户端命令（Client → Server）：**

```json
{
  "type": "subscribe",
  "channels": ["request_log"]
}
```

```json
{
  "type": "unsubscribe",
  "channels": ["request_log"]
}
```

```json
{
  "type": "ping"
}
```

### 9.3 频道与事件

#### `topology` 频道

| action | 说明 | payload |
|--------|------|---------|
| `loaded` | 拓扑加载完成 | `{ topologyId, name }` |
| `saved` | 拓扑保存完成 | `{ topologyId, version, savedAt }` |
| `device.created` | 设备创建 | `{ device }` |
| `device.updated` | 设备更新 | `{ device, changedFields }` |
| `device.deleted` | 设备删除 | `{ deviceId }` |
| `port.created` | 端口创建 | `{ port }` |
| `port.updated` | 端口更新 | `{ port }` |
| `port.deleted` | 端口删除 | `{ portId }` |
| `link.created` | 链路创建 | `{ link }` |
| `link.deleted` | 链路删除 | `{ linkId }` |
| `alarm.created` | 告警新增 | `{ alarm }` |
| `alarm.cleared` | 告警清除 | `{ alarmId, clearTime }` |
| `validated` | 拓扑验证完成 | `{ valid, issueCount }` |

#### `protocol` 频道

| action | 说明 | payload |
|--------|------|---------|
| `started` | 协议服务启动 | `{ name, port }` |
| `stopped` | 协议服务停止 | `{ name }` |
| `error` | 协议服务异常 | `{ name, error }` |
| `health` | 定时健康状态 | `{ name, healthy, stats }` |

#### `request_log` 频道

| action | 说明 | payload |
|--------|------|---------|
| `new` | 新请求日志 | `{ id, method, path, statusCode, duration }` |

#### `alarm` 频道

| action | 说明 | payload |
|--------|------|---------|
| `created` | 告警产生 | `{ alarm }` |
| `cleared` | 告警清除 | `{ alarmId }` |

#### `system` 频道

| action | 说明 | payload |
|--------|------|---------|
| `auto_saved` | 自动保存完成 | `{ topologyId, version }` |
| `resources` | 资源使用更新 | `{ cpu, memory, disk }` |
| `notification` | 系统通知 | `{ level, message }` |

---

## 10. 接口汇总

### 拓扑管理（22 个）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/topologies` | 拓扑列表 |
| POST | `/api/topologies` | 创建拓扑 |
| GET | `/api/topologies/{id}` | 拓扑详情 |
| PUT | `/api/topologies/{id}` | 更新拓扑信息 |
| DELETE | `/api/topologies/{id}` | 删除拓扑 |
| POST | `/api/topologies/{id}/save` | 手动保存 |
| POST | `/api/topologies/{id}/load` | 加载到内存 |
| GET | `/api/topologies/{id}/versions` | 版本历史 |
| POST | `/api/topologies/{id}/versions/{v}/restore` | 版本回退 |
| GET | `/api/topologies/{id}/export` | 导出拓扑 |
| POST | `/api/topologies/import` | 导入拓扑 |
| POST | `/api/topologies/{id}/validate` | 验证拓扑 |
| POST | `/api/topologies/{id}/validate/fix` | 一键修复 |
| POST | `/api/topologies/{id}/layout` | 自动布局 |
| GET | `/api/device-types` | 设备类型列表 |
| POST | `/api/device-types` | 创建设备类型 |
| PUT | `/api/device-types/{id}` | 更新设备类型 |
| DELETE | `/api/device-types/{id}` | 删除设备类型 |
| PUT | `/api/topologies/{id}/canvas` | 保存画布状态 |
| GET | `/api/topologies/{id}/devices` | 设备列表 |
| POST | `/api/topologies/{id}/devices` | 创建设备 |
| GET | `/api/topologies/{id}/devices/{id}` | 设备详情 |

### 设备/端口/链路操作（16 个）

| 方法 | 路径 | 说明 |
|------|------|------|
| PUT | `/api/topologies/{id}/devices/{id}` | 更新设备 |
| DELETE | `/api/topologies/{id}/devices/{id}` | 删除设备 |
| PUT | `/api/topologies/{id}/devices/batch` | 批量更新设备 |
| DELETE | `/api/topologies/{id}/devices/batch` | 批量删除设备 |
| GET | `/api/topologies/{id}/devices/{id}/ports` | 端口列表 |
| POST | `/api/topologies/{id}/devices/{id}/ports` | 创建端口 |
| POST | `/api/topologies/{id}/devices/{id}/ports/generate` | 批量生成端口 |
| PUT | `/api/topologies/{id}/ports/{id}` | 更新端口 |
| PUT | `/api/topologies/{id}/devices/{id}/ports/batch` | 批量更新端口 |
| DELETE | `/api/topologies/{id}/ports/{id}` | 删除端口 |
| GET | `/api/topologies/{id}/devices/{id}/ports/export` | 导出端口 |
| POST | `/api/topologies/{id}/devices/{id}/ports/import` | 导入端口 |
| GET | `/api/topologies/{id}/links` | 链路列表 |
| POST | `/api/topologies/{id}/links` | 创建链路 |
| PUT | `/api/topologies/{id}/links/{id}` | 更新链路 |
| DELETE | `/api/topologies/{id}/links/{id}` | 删除链路 |

### 告警/指标（9 个）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/topologies/{id}/alarms` | 告警列表 |
| POST | `/api/topologies/{id}/alarms` | 创建告警 |
| PUT | `/api/topologies/{id}/alarms/{id}` | 更新告警 |
| DELETE | `/api/topologies/{id}/alarms/{id}` | 删除告警 |
| POST | `/api/topologies/{id}/alarms/{id}/clear` | 清除告警 |
| POST | `/api/topologies/{id}/alarms/batch` | 批量创建告警 |
| GET | `/api/topologies/{id}/metrics` | 指标列表 |
| POST | `/api/topologies/{id}/metrics` | 创建指标 |
| POST | `/api/topologies/{id}/metrics/batch` | 批量创建指标 |

### HTTP 接口配置（9 个）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/api-configs` | 配置列表 |
| GET | `/api/api-configs/groups` | 分组列表 |
| POST | `/api/api-configs` | 创建配置 |
| GET | `/api/api-configs/{id}` | 配置详情 |
| PUT | `/api/api-configs/{id}` | 更新配置 |
| DELETE | `/api/api-configs/{id}` | 删除配置 |
| PUT | `/api/api-configs/{id}/enabled` | 切换启禁用 |
| POST | `/api/api-configs/{id}/test` | 测试执行 |
| GET | `/api/api-configs/default-sql/{coll}` | 默认 SQL |

### Token 认证（5 个）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/sessions` | Token 列表 |
| DELETE | `/api/sessions/{token}` | 失效 Token |
| DELETE | `/api/sessions` | 清空 Token |
| PUT | `/api/sessions/config` | 认证配置 |
| GET | `/api/sessions/config` | 获取认证配置 |

### 协议管理（30 个）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/protocols` | 全部协议状态 |
| POST | `/api/protocols/{name}/start` | 启动 |
| POST | `/api/protocols/{name}/stop` | 停止 |
| POST | `/api/protocols/{name}/restart` | 重启 |
| GET | `/api/protocols/{name}/health` | 健康检查 |
| POST | `/api/protocols/start-all` | 全部启动 |
| POST | `/api/protocols/stop-all` | 全部停止 |
| GET | `/api/protocols/http-mock/config` | HTTP 配置 |
| PUT | `/api/protocols/http-mock/config` | 更新 HTTP 配置 |
| GET | `/api/protocols/http-mock/routes` | 路由列表 |
| GET | `/api/protocols/snmp-agent/config` | SNMP 配置 |
| PUT | `/api/protocols/snmp-agent/config` | 更新 SNMP 配置 |
| GET | `/api/protocols/snmp-agent/oids` | OID 列表 |
| POST | `/api/protocols/snmp-agent/oids` | 创建 OID |
| PUT | `/api/protocols/snmp-agent/oids/{id}` | 更新 OID |
| DELETE | `/api/protocols/snmp-agent/oids/{id}` | 删除 OID |
| POST | `/api/protocols/snmp-agent/oids/import` | 导入 OID |
| GET | `/api/protocols/snmp-agent/oids/export` | 导出 OID |
| POST | `/api/protocols/snmp-agent/oids/{id}/test` | 测试 OID |
| GET | `/api/protocols/snmp-agent/trap/config` | Trap 配置 |
| PUT | `/api/protocols/snmp-agent/trap/config` | 更新 Trap 配置 |
| POST | `/api/protocols/snmp-agent/trap/send` | 发送 Trap |
| POST | `/api/protocols/snmp-agent/trap/send-batch` | 批量发送 Trap |
| GET | `/api/protocols/sftp-server/config` | SFTP 配置 |
| PUT | `/api/protocols/sftp-server/config` | 更新 SFTP 配置 |
| GET | `/api/protocols/sftp-server/templates` | 文件模板列表 |
| POST | `/api/protocols/sftp-server/templates` | 创建文件模板 |
| GET | `/api/protocols/kafka-producer/config` | Kafka 配置 |
| PUT | `/api/protocols/kafka-producer/config` | 更新 Kafka 配置 |
| GET | `/api/protocols/kafka-producer/stats` | 发送统计 |

### 数据查询（2 个）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/query/sql` | 执行 SQL |
| GET | `/api/query/collections` | 虚拟表信息 |

### 日志（4 个）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/logs/requests` | 请求日志 |
| GET | `/api/logs/requests/{id}` | 请求详情 |
| GET | `/api/logs/system` | 系统日志 |
| GET | `/api/logs/export` | 导出日志 |

### 系统（4 个）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/settings` | 获取设置 |
| PUT | `/api/settings` | 更新设置 |
| POST | `/api/settings/reset` | 恢复默认 |
| GET | `/api/system/info` | 系统信息 |

### WebSocket（1 个）

| 协议 | 路径 | 说明 |
|------|------|------|
| WS | `/ws` | 实时事件推送 |

**合计：102 个 REST 接口 + 1 个 WebSocket 端点**
