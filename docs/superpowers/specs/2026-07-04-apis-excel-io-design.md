# 接口导出/导入改为 Excel 设计

**日期：** 2026-07-04
**状态：** 已批准，待写实施计划

---

## 目标

将现有的 JSON 接口导入/导出改为 Excel（.xlsx），让用户在 Excel 里能直接看到、修改接口配置（含 headers/query/参数映射/SQL/响应模板），无需理解 JSON 结构。

---

## 设计原则

- **一个网管/设备一个 Sheet**：符合"打开文件按业务分区看"的直觉
- **一行一个接口**：接口的所有信息集中在这一行，不跨 Sheet 找
- **变长嵌套字段用"单元格内多行 + 固定列 + `|` 分隔"** 表达；字段值含 `|` 时导入报错，不做自动转义
- **完全替换 JSON**：删除现有 JSON 导入/导出端点，不做双格式共存
- **不动数据库 schema、mock 路由注册、请求流水线**

---

## 架构

### 后端（`backend/app/admin/api_config.py`）

- **删除** 现有 `POST /apis/export`（JSON 导出）
- **新增** `POST /apis/export`（复用同一路径，签名不变：`{ ids?, domainId? }`），返回 xlsx 二进制流：`Response(content=..., media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")`，不走 `{code, data}` 包装
- **重写** `POST /apis/import`：只接受 `.xlsx`（其他扩展名 → 400 + 40410 "仅支持 .xlsx 文件"）；删除 JSON 解析分支

### 后端新增模块（`backend/app/admin/_api_excel.py`）

模块内部函数（不对外暴露）：
- `build_workbook(rows, domains, topologies) -> openpyxl.Workbook`
- `parse_workbook(wb, existing_domains, existing_topologies) -> ParseResult`
- `format_cell_list(records: list[dict], columns: list[str]) -> str`
- `parse_cell_list(cell_text: str, columns: list[str], row_hint: str) -> list[dict]`
- `sanitize_sheet_name(name: str, used: set[str]) -> str`

数据类：`ParseResult(created_rows, updated_rows, errors, warnings, auto_created_domains, new_routes)`

依赖：项目里已有 `openpyxl`，无新增。

### 前端

- `frontend/src/api/api_config.ts`
  - `export(params)`：改为 `http.post('/apis/export', params, { responseType: 'blob' })`，返回 `Promise<Blob>`
  - `import(file)`：`FormData` 上传 `.xlsx`（.json 不再受理，前端也拦截）
- `frontend/src/components/apis/ApiConfigTable.vue`
  - "导出"按钮：拿 `Blob` → `downloadBlob(blob, timestampExcelFilename('apis-export'))`，**删除**当前 `.replace('.xlsx', '.json')` 那行
  - "导入"按钮：文件选择 `accept=".xlsx"`；导入确认框文案改为 "仅支持 Excel (.xlsx) 文件"

### 不变

- 数据库 schema、mock 路由注册逻辑、请求流水线
- `apiConfigApi.export(...)` 的调用方点、下载工具函数

---

## Workbook 结构

### Sheet 划分

| Sheet | 内容 |
|---|---|
| `<域名>` (每域 1 个) | 该域下所有接口，一行一个 |
| `未归类` | `domain_id IS NULL` 的接口 |
| `_使用说明` | 首个 Sheet，纯说明文档；导入时被跳过 |

导入时：Sheet 名 `_` 开头一律跳过；其余按"A1 单元格 comment 里的原始域名 → Sheet 名"顺序匹配已有域；找不到 → 自动创建域（延续现有逻辑）。

### 每个域 Sheet 的列（顺序即导入解析顺序）

| # | 列 | 类型 | 说明 |
|---|---|---|---|
| 1 | 方法 | 枚举 | GET/POST/PUT/PATCH/DELETE，大写；空 → 跳过该行 |
| 2 | 路径 | 字符串 | 如 `/rest/plat/xxx`；空 → 跳过该行 |
| 3 | 接口名 | 字符串 | 必填 |
| 4 | 启用 | 是/否 | 空视为"是" |
| 5 | 分类 | 字符串 | 域内子目录，可空 |
| 6 | 分组 | 字符串 | groupName，可空 |
| 7 | 数据源 | 枚举 | `sql` / `static` |
| 8 | 拓扑 | 字符串 | 拓扑**名**（不是 ID）；可空 |
| 9 | 鉴权类型 | 枚举 | `none` / `xtoken` / `basic`，空视为 `none` |
| 10 | 鉴权头名 | 字符串 | 仅 `xtoken` 用，如 `X-Token` |
| 11 | 请求头 | 多行单元格 | 每行 `名称\|必填\|期望值\|样例\|说明` |
| 12 | Query 参数 | 多行单元格 | 每行 `名称\|类型\|必填\|样例\|说明` |
| 13 | 请求体 | 单行单元格 | `Content-Type\|必填\|样例\|说明`（空 = 无 body 约束） |
| 14 | SQL 语句 | 长文本 | 仅 sql 数据源；列宽 80 + 自动换行 |
| 15 | 响应模板 | 长文本 | 仅 sql 数据源；同上 |
| 16 | 参数映射 | 多行单元格 | 仅 sql 数据源；每行 `参数名\|位置\|类型\|必填\|SQL绑定名` |
| 17 | 静态响应体 | 长文本 | 仅 static 数据源 |
| 18 | 故障-延迟毫秒 | 数字 | 空 = 不注入 |
| 19 | 故障-错误率 | 数字 | 0~1，空 = 不注入 |
| 20 | 故障-错误状态码 | 数字 | 空 = 用默认 500 |

**表头行样式：** 第 1 行冻结、加粗、浅灰背景；每个表头单元格附 `cell.comment` 说明分隔符和必填规则。

**变长列表列约定：**
- 记录之间用换行（openpyxl 写 `\n`；Excel 显示为软换行）
- 字段之间用 `|`
- 字段值中的"必填"列统一写 `是` / `否`（跟"启用"列一致）
- 单元格空 → 该字段空数组 `[]`
- 值含 `|` → 导入报错（不做转义）

### 未在列里显式建模的 config 键

`config` 里可能存在未在表格里显式建模的键（未来新增字段）。策略：
- **导出**：只写上表 20 列显式建模的键
- **导入**：对已存在接口做 UPDATE 时，**保留原 config 里未被表格覆盖的键**，只覆盖同名键；新建接口 config 只包含表格里的键

好处：用户在 Excel 里改鉴权时，不会误删未来可能新增的其他 config 字段。

---

## 导入合并与匹配

### 主键匹配：`(method, path)` 全局唯一

DB 里 `api_configs.UNIQUE(method, path)`，全局唯一。所以：

- **命中 → UPDATE**：用行里的字段覆盖，包括 `domain_id`（由 Sheet 名决定）。**副作用：跨 Sheet 移动接口 = 换域**（把 `/api/foo` 从 "网管A" Sheet 剪到 "网管B" Sheet，导入后其 `domain_id` 就换到 B）
- **未命中 → INSERT**：`domain_id` 用 Sheet 名匹配的域；Sheet 名找不到已有域 → 自动创建新域

### 未在 Excel 中出现的 DB 接口

**保留不删。** 导入 = 增量 upsert，不做同步删除。

用户想删接口 → 用 UI 里的删除按钮，或 `启用=否` 软下线；靠"从 Excel 里删行"来删接口是危险语义，坚决不做。这一点写进 `_使用说明` Sheet。

### 拓扑名 → topology_id 解析

按 `topologies.name` 查表：
- 唯一命中 → 用其 `id`
- 多命中 → 用第一个（按 `created_at ASC`），进 `warnings`
- 未命中 → `topology_id = NULL`，进 `warnings`
- 单元格为空 → `topology_id = NULL`（合法，不算警告）

### 校验错误分类

| 级别 | 处理 |
|---|---|
| **致命**（阻断整次导入） | 文件非 `.xlsx` / openpyxl 打不开 / 无任何数据 Sheet |
| **行级错误**（跳过该行） | method 不在枚举里 / 数据源不在枚举里 / 单元格值含 `\|` / 变长列表字段数超上限 / 数字列填了非数字 |
| **警告**（写入但记录） | 拓扑名找不到 / 拓扑名多匹配 / 自动创建了域 |

### 响应体

```json
{
  "code": 0,
  "data": {
    "created": 5,
    "updated": 12,
    "errors": ["Sheet '网管A' 第 3 行：method 'FOO' 不合法"],
    "warnings": ["Sheet '网管A' 第 5 行：拓扑名 'topo_x' 未找到"],
    "autoCreatedDomains": ["新网管"]
  }
}
```

前端在导入完成 toast 里分别显示 errors 和 warnings 两类。

### 事务边界

整份 xlsx 在**单个** `transaction()` 里处理。任何"致命"错抛出 → 整个事务回滚。行级错误只跳过该行，事务继续；最终一次性提交。

事务提交成功后再做 `mock_registry.register(...)`（跟当前 JSON 导入相同的两阶段模式，避免回滚留下幽灵路由）。

---

## 边角与约定

### Sheet 名 Excel 限制

Excel 硬性规则：Sheet 名 ≤ 31 字符、不能含 `: \ / ? * [ ]`。

**处理：**
- 导出：`sheet_name = sanitize(domain.name)`，把非法字符替换成 `_`，超 31 字符截断；清洗后重名 → 追加 `~2`、`~3` 后缀
- 导入：**不依赖清洗后的 sheet 名反查域**——导出时把原始域名写在 Sheet A1 单元格的 `cell.comment` 里，导入时先看 comment，comment 为空再用 Sheet 名匹配
- 好处：用户重命名 Sheet 后仍能正确对齐；重命名域走"自动创建/匹配"逻辑

### 域名唯一性

DB 里 `domains.name` 无 UNIQUE 约束。存在同名域时：用 `created_at ASC LIMIT 1`，进 `warnings`。

### 变长单元格边角

- 单元格空 → 空数组 `[]`
- 单元格里连续两个换行 → 跳过空行
- 某行字段数 < 期望 → 缺的按空处理（如请求头一行只写 `Authorization|是`，剩下 3 个字段空）
- 某行字段数 > 期望 → 行级错误
- 值含 `|` → 行级错误

### 空文件 / 只有 `_使用说明`

致命错误：`"Excel 中未找到任何数据 Sheet"`，事务未开启即回退。

---

## 测试计划

测试文件：`backend/tests/admin/test_apis_excel.py`（若无 tests 目录，实施时新建）。

### 单元测试（`_api_excel.py`）

1. `format_cell_list` 空数组 → 空字符串
2. `format_cell_list` / `parse_cell_list` 循环一致性：`[{name:"A", required:True, expectValue:"X"}]` → format → parse → 结构相同
3. `parse_cell_list` 值含 `|` → 抛 `ExcelValidationError`
4. `parse_cell_list` 字段数超限 → 抛错
5. `parse_cell_list` 字段数不足 → 自动补空
6. `sanitize_sheet_name`：`网管/华为 iMaster NCE ...` → 合法 sheet 名 + 长度 ≤ 31；重名追加 `~2`

### 端到端测试（`fastapi.testclient.TestClient`）

7. **导出往返**：造 3 个域 + 5 个接口（覆盖 sql/static / 有无 headers / 有无参数映射）→ `POST /apis/export` → openpyxl 读回 → 校验 Sheet 数、行数、单元格内容
8. **导入新建**：从零 xlsx，包含 2 个新接口 → 导入 → DB 出现 + `mock_registry` 路由已挂
9. **导入更新**：改一个已有接口的 name + headers → 导入 → DB 已更新，路由未变
10. **跨 Sheet 移动**：接口行从 Sheet "A" 移到 "B" → 导入后 `domain_id` 变 B，接口仅一份
11. **拓扑名解析**：唯一/多命中/未命中 3 case → warnings 数量正确
12. **值含 `|` 报错**：header `expectValue` 写 `foo|bar` → errors 里有该行提示，其他行照常导入
13. **Sheet 名清洗**：域名 `A/B` 和 `A_B` 并存 → 两个 Sheet 名分别为 `A_B` 和 `A_B~2`；导入后正确回填两个域
14. **保留未建模 config 键**：造一个接口 `config = {..., customFuture: "x"}`，导入更新其鉴权 → `customFuture` 仍在 DB 里
15. **非 .xlsx 文件**：上传 `.json` → 400 + 40410；上传 `.xlsx` 但内容损坏 → 致命错误

### 前端手工验证

- 全量导出 → 打开 xlsx → 每个域一个 Sheet + `_使用说明` 存在，表头 comment 显示分隔符说明
- 修改一个接口 name → 导入 → UI 刷新后名字更新
- accept 收窄到 `.xlsx`：选 `.json` 时前端拦下报错

---

## 上线切换

- 无数据迁移
- 无 UI 灰度：直接切换按钮行为
- 用户老 JSON 文件 → **不再兼容**；生产上目前仅本人使用，可接受
