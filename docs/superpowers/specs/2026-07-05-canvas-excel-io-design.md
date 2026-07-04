# 画布 Excel 导入导出设计

**日期：** 2026-07-05
**状态：** 已批准，待写实施计划

---

## 目标

给画布（拓扑）的导出/导入加一个 Excel（.xlsx）格式，方便用户直接在 Excel 里查看和批量修改。同时把当前 JSON 版遗漏的三类数据一并纳入：

1. **节点组定义**（`node_groups`：`groupName / nodeCount / nameTemplate / attrStrategies / edgeStrategies / canvasX / canvasY`）
2. **物理节点告警**（`node_alarms` + `node_alarm_attrs`）
3. **节点组告警模板**（`node_group_alarms` + `node_group_alarm_attrs`，Sub-project A 已建）

**本 spec 是父项目"画布导出扩展"的 Sub-project B**——Sub-project A（节点组告警数据模型）已完成，此处直接消费其表结构。

---

## 设计原则

- **导入永远新建拓扑**（保持 JSON 版语义）——不做"更新已有拓扑"的 upsert
- **节点组只导定义**（不导虚拟展开）——保持组抽象，round-trip 保真；已 materialize 的组，物理节点走 nodes Sheet 正常导出
- **按 nodeType/edgeType 拆 Sheet**——字段成列，可读可批改；告警合并成 2 个 Sheet（拓扑 alarm_schema 唯一）
- **保留旧 JSON 端点** `/topologies/{id}/export` + `/topologies/import`——工程/程序化调用继续走 JSON；前端 UI 切到 Excel
- **不改 DB schema**——本次仅新增编解码 + 端点

---

## Workbook 结构

### Sheet 顺序

| # | Sheet | 内容 | 一致存在？ |
|---|---|---|---|
| 1 | `_使用说明` | 纯说明文档（`_` 开头，导入跳过） | 恒定 |
| 2 | `_总表` | 数据 Sheet 导航目录 | 恒定 |
| 3 | `拓扑元信息` | 拓扑本身的元数据（key-value 表） | 恒定 |
| 4 | `<nodeType 名>` × N | 每种 nodeType 一 Sheet | N = 拓扑用到的 nodeType 数 |
| 5 | `<edgeType 名>` × M | 每种 edgeType 一 Sheet | M = 拓扑用到的 edgeType 数 |
| 6 | `节点组` | 所有 node_groups 定义（一行一组，跨 nodeType） | 恒定 |
| 7 | `节点告警` | 所有物理节点告警 | 仅拓扑绑了 alarm_schema 时 |
| 8 | `节点组告警` | 所有组告警模板 | 仅拓扑绑了 alarm_schema 时 |

### Sheet 名清洗（同接口 Excel）

- Excel 硬性规则：≤ 31 字符、禁 `: \ / ? * [ ]`
- 非法字符替换 `_`，超长右截，重名追加 `~2` / `~3`
- **A1 单元格 comment 存原始 code/marker**（导入时按 code 精确匹配，不受 Sheet 名清洗/用户重命名影响）：
  - nodeType Sheet: `__NODE_TYPE_CODE__=<code>`
  - edgeType Sheet: `__EDGE_TYPE_CODE__=<code>`
  - 节点组 Sheet: `__NODE_GROUP__=1`
  - 节点告警 Sheet: `__NODE_ALARM__=1`
  - 节点组告警 Sheet: `__NODE_GROUP_ALARM__=1`

---

## `_总表` Sheet

**用途：** 导航目录——workbook 里节点/边/节点组/告警 Sheet 多起来后，从总表点名字跳过去。

**只列 5 类数据 Sheet**（不列 `_使用说明` 和 `拓扑元信息`——它们位置固定、易找）：

| 类别 | 列 |
|---|---|
| 类别 | `节点 / 边 / 节点组 / 节点告警 / 节点组告警` |
| 类型代码 | nodeType.code / edgeType.code（节点组和告警行留空） |
| Sheet 名 | 目标 Sheet 名（清洗后的） |
| 行数 | 该 Sheet 里数据行数 |
| 跳转 | Sheet 名列本身作 hyperlink |

**技术实现：** openpyxl 原生 intra-workbook hyperlink（`cell.hyperlink = "#'路由器'!A1"`），"Sheet 名"列 cell 加 Font(color="0563C1", underline="single")。

**动态生成：** `build_workbook` 写完所有数据 Sheet 后**最后一步**扫描 `wb.sheetnames` 生成——只要写了的 Sheet 就出现，未生成的（如没绑 schema 时的告警 Sheet）自动不在。

**总表不接受导入编辑**——是纯导航辅助，导入按 `_` 前缀跳过。

---

## `拓扑元信息` Sheet

两列 key-value：

```
字段              | 值
拓扑名称           | 我的机房拓扑
描述              | 华为核心机房 A 栋
版本              | 3
所属网管/设备      | 华为 ManageOne
告警模板          | dc_alarm_v1
```

**用途：** 导入时后端知道新拓扑叫啥名、绑哪个网管、绑哪个 alarm_schema。

---

## 节点 Sheet（每 nodeType 一份）

| # | 列 | 类型 | 说明 |
|---|---|---|---|
| 1 | 名称 | 字符串 | `nodes.name`（必填） |
| 2 | DN | 字符串 | `nodes.dn`（可空） |
| 3 | 状态 | 枚举 | `online / offline / unknown / warning / error`（空视为 online） |
| 4 | 画布 X | 数字 | `canvas_nodes.x`（可空——未上画布的节点） |
| 5 | 画布 Y | 数字 | 同上 |
| 6 | 所属组 | 字符串 | `nodes.group_id → node_groups.group_name`（组物化后的物理节点才有；未归组的空） |
| 7+ | `<字段名>` × N | 该 nodeType 的字段类型 | 从 `node_type_fields` 展开，一字段一列 |

**表头样式：** 冻结第 1 行 + 加粗 + 浅灰背景。字段列表头 comment 显示字段类型 + 是否必填 + max_length。

**不导出：** `nodes.id`、`node_type_id`、`topology_id`、`created_at`、`updated_at`（内部/派生）。

---

## 边 Sheet（每 edgeType 一份）

| # | 列 | 类型 | 说明 |
|---|---|---|---|
| 1 | 源节点 | 字符串 | 源节点 `name`（在同 workbook 所有 nodeType Sheets 里按 name 定位）|
| 2 | 目标节点 | 字符串 | 同上 |
| 3 | 状态 | 枚举 | `online / offline / ...`（空视为 online） |
| 4+ | `<字段名>` × N | 该 edgeType 的字段类型 | 从 `edge_type_fields` 展开 |

**边引用节点用 name 而非内部 id**——用户看得懂 + 可手改。

**校验：** 一 topology 里 (nodeTypeCode, name) 组合必须唯一——不唯一直接 400 + 40432。

---

## `节点组` Sheet

一行一组（跨 nodeType，因为组数量通常少）：

| # | 列 | 类型 | 说明 |
|---|---|---|---|
| 1 | 组名 | 字符串 | `node_groups.group_name` |
| 2 | 节点类型代码 | 字符串 | `node_types.code`（如 `router`）|
| 3 | 节点数量 | 数字 | `node_groups.node_count` |
| 4 | 命名模板 | 字符串 | 如 `{group}-{i:05d}` |
| 5 | 已展开 | 是/否 | `node_groups.materialized_at IS NOT NULL`（导出用；**导入时忽略**——导入组永远虚拟态） |
| 6 | 画布 X | 数字 | `node_groups.canvas_x` |
| 7 | 画布 Y | 数字 | `node_groups.canvas_y` |
| 8 | 属性策略 | 多行单元格 | 每策略一行：`字段名\|策略类型\|参数` |
| 9 | 边策略 | 多行单元格 | 每策略一行：`目标组名\|边类型代码\|模式\|K` |

### 属性策略格式

每行：`字段名|策略类型|参数`，参数用 `;` 分隔 key=value：

```
vlan_id|range|min=100;max=200
role|fixed|fixedValue=core-router
mgmt_ip|increment|base=10.0.0.1;step=1
region|random|pool=北京;上海;广州
```

**策略类型：** `fixed / random / increment / range`（对齐 `AttrStrategyItem`）
**参数键：** `fixedValue / pool / base / step / min / max`（对齐 pydantic 字段）

### 边策略格式

每行：`目标组名|边类型代码|模式|K`

```
接入交换机组|link|modulo|K=4
核心路由器组|link|all_to_all|
```

**模式：** `modulo / one_to_n / all_to_all / dense`
**K：** 仅 modulo / one_to_n 用，其它模式留空

---

## `节点告警` Sheet

| # | 列 | 类型 | 说明 |
|---|---|---|---|
| 1 | 节点类型代码 | 字符串 | 定位 nodeType（跨 nodeType 混一起） |
| 2 | 节点名称 | 字符串 | 目标物理节点 `name` |
| 3 | 告警序号 | 数字 | `node_alarms.alarm_index`（同一节点内的序号） |
| 4+ | `<告警字段名>` × N | 按 alarm_schema_fields 展开 | 一字段一列；`mapping_target` 字段列**不导出**（运行时从节点派生） |

**表头 comment：** mapping_target 字段说明"字段值由节点属性派生，不出现在告警 Sheet 里"。

---

## `节点组告警` Sheet

| # | 列 | 类型 | 说明 |
|---|---|---|---|
| 1 | 组名 | 字符串 | `node_groups.group_name`（同 topology 内唯一） |
| 2 | 告警序号 | 数字 | `node_group_alarms.alarm_index` |
| 3+ | `<告警字段名>` × N | 同上 | 从 alarm_schema 展开；mapping_target 字段列不导出 |

---

## 拓扑未绑 alarm_schema

`节点告警` + `节点组告警` Sheet **不生成**（跟现有 CTE `alarms` 视图行为一致）。导入时如果元信息里绑了 schema 但 workbook 没这两个 Sheet：视为 "0 条告警"，不算错。

---

## 导入行为

### 流程

1. 验文件：非 `.xlsx` → 400 + 40410
2. 读 `拓扑元信息` Sheet 拿新拓扑的 name / description / 网管 / alarm_schema code
3. 名字冲突：追加 `" (导入)"` / `" (导入 2)"`...
4. 解析 `alarm_schema code`：查 `alarm_schemas.code`；找不到 → 400 + 40430 "告警模板不存在"（**不自动创建**）
5. 解析`所属网管`：查 `domains.name`；找不到 → **自动创建**（跟接口 Excel 一致）
6. 遍历 nodeType Sheets（按 A1 comment `__NODE_TYPE_CODE__` 定位 `node_types.code`）：找不到 → 400 + 40431 "节点类型代码不存在"，附列表
7. 单事务里：`INSERT topology` → 所有 nodes + node_attrs + canvas_nodes → 所有 edges + edge_attrs → node_groups → node_alarms + attrs → node_group_alarms + attrs
8. 边的 (源节点/目标节点) name 在 workbook 所有 nodeType Sheets 里查节点：命中的存 `node.id` 作为 FK；未命中 → 行级错误
9. 同 (nodeTypeCode, name) 在 workbook 里出现多次 → 400 + 40432 "节点名重复不唯一"
10. 事务失败：整份回滚，无残留

### 错误分级

| 级别 | 处理 |
|---|---|
| **致命** | 非 .xlsx / openpyxl 打不开 / 元信息 Sheet 缺失 / alarm_schema 找不到 / nodeType/edgeType code 找不到 / 节点名重复 |
| **行级错误** | 边引用未知节点 name / 数字列填非数字 / 变长单元格值含 `\|` / 必填字段空 |
| **警告** | 自动创建的 `domain`；alarm_schema 与拓扑绑定信息不匹配（比如元信息里说绑 v1，但导入前发现 v1 字段已变） |

### 响应

```json
{
  "code": 0,
  "data": {
    "topologyId": "topo_xxx",
    "topologyName": "机房拓扑 (导入)",
    "counts": {"nodes": 42, "edges": 30, "groups": 5, "nodeAlarms": 60, "groupAlarms": 8},
    "errors": ["Sheet '连接' 第 5 行：源节点 'router-99' 未找到"],
    "warnings": ["自动创建了网管 '新环境'"]
  },
  "message": "ok"
}
```

---

## API 端点

**新增：**

- `GET /admin/api/topologies/{id}/export-excel` → xlsx 二进制流（`application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`）
- `POST /admin/api/topologies/import-excel` → 收 multipart `.xlsx`，返回上述响应体

**保留：**

- `GET /admin/api/topologies/{id}/export` (JSON) — 工程/程序化调用继续可用
- `POST /admin/api/topologies/import` (JSON) — 同上

**前端：**

- CanvasView "导出" 按钮切到 excel 端点（`downloadBlob`）
- CanvasView "导入" 按钮 accept 改 `.xlsx`；简化确认弹窗（不做客户端预览）

---

## 后端 / 前端 改动

**新增：**
- `backend/app/admin/_topology_excel.py` — workbook 编解码 + 校验（仿 `_api_excel.py`）
- `backend/tests/test_topologies_excel.py` — 端到端测试
- `backend/tests/test_topologies_excel_helpers.py` — 单元测试（策略编解码）

**修改：**
- `backend/app/admin/topology.py` — 加 export-excel / import-excel 两端点
- `frontend/src/views/CanvasView.vue` — "导出"/"导入" 按钮切到 Excel 流程
- `frontend/src/api/topology.ts` — 加 `exportExcel(id)` / `importExcel(file)`

**不改：**
- DB schema / 迁移
- 现有 JSON 端点（`export_topology` / `import_topology`）
- CTE / instance_app / mock 路由
- `_api_excel.py` / `node_alarm.py` / `node_group.py` 等已有模块

---

## 测试计划

### 单元测试（`test_topologies_excel_helpers.py`）

1. `format_attr_strategies` / `parse_attr_strategies` 循环一致性——4 种策略（fixed / random / increment / range）
2. `format_edge_strategies` / `parse_edge_strategies` 循环一致性——4 种模式
3. Sheet 名清洗 + dedupe 后缀
4. A1 comment 存/取 `__NODE_TYPE_CODE__` / `__EDGE_TYPE_CODE__` / `__NODE_GROUP__` 等
5. `_总表` 生成：根据 workbook 现存 Sheet 动态生成条目
6. 拓扑无 alarm_schema：告警 Sheet 不生成 + 总表里也不出现

### 端到端测试（`test_topologies_excel.py`）

7. **导出往返：** 造 topology + 2 nodeType + 各 5 节点 + 3 edge + 2 group + 若干告警 → export → openpyxl 读回 → Sheet 数量 / 内容对齐
8. **导入新建：** 从零 xlsx → 导入 → DB 里新 topology 出现 + 所有关联数据齐
9. **名字冲突：** "机房" 已存在 → 导入后名为 "机房 (导入)"
10. **边引用未知节点：** `连接` Sheet 里源节点 'router-99' 不存在 → 该行 errors 收集，其它照插
11. **节点名重复：** workbook 里两条 `router-01` → 400 + 40432
12. **alarm_schema code 不存在：** → 400 + 40430
13. **domain 自动创建：** → warnings 里记录，DB 里出现
14. **组的 attr_strategies 4 种类型都能 round-trip**
15. **`mapping_target` 字段列不出现在导出的告警 Sheet 里**
16. **`_总表` hyperlink 指向的目标 Sheet 存在**（openpyxl 读 hyperlink 属性验证）
17. **materialize 组的物理节点：** 一组材化后有 3 物理节点，导出时物理节点走 nodes Sheet + 组定义走 节点组 Sheet + 关联通过 `所属组` 列

### 前端手工验证

- 画布上一个复杂拓扑 → "导出" → xlsx 打开检查 `_使用说明` / `_总表`（含所有 5 类）/ 元信息 / 各 nodeType/edgeType Sheet / 节点组 / 告警
- Excel 里改一个节点属性 → 重新导入 → 新拓扑出现，值已更
- 非 .xlsx 上传拒收
- 名字冲突自动加后缀

---

## 上线切换

- **迁移：** 无 DB schema 变更，无需迁移
- **UI 切换：** 直接切到 Excel 流程；用户想用 JSON 可 curl 后端旧端点
- **回滚：** 代码回退即可（无数据格式改变）
