# 边类型 Excel 导入导出 设计方案

**日期**：2026-07-05
**背景**：边类型（`edge_types`）目前有 CRUD API，但导出**返回 JSON**（`{items: [...]}`）不是 Excel，且**完全没有导入能力**（无 preview 端点，无 import 端点，前端无入口）。节点类型和告警模板刚完成 Excel 多 Sheet 导入导出，用户对该交互模式已熟悉。本次补齐边类型，同时把现有 JSON 导出直接改造成 Excel。

## 术语

- **边类型**：`edge_types` 表定义的边模板，含语义（connect/contain）、方向、允许的源/目标节点类型、视觉样式
- **字段**：`edge_type_fields` 表中的边类型字段定义，结构同节点类型字段（无告警模板的 `mapping_target`）
- **允许源/目标类型**（`allow_source_type_codes` / `allow_target_type_codes`）：逗号分隔的 `node_types.code` 白名单字符串；空表示不限制

## 现状分析

### 数据模型

```sql
edge_types:
  id, code (UNIQUE), name, semantic, directed, exclusive_target,
  allow_source_type_codes, allow_target_type_codes, line_style, color,
  description, created_at, updated_at

edge_type_fields:
  id, edge_type_id (FK), field_key, field_label, field_type, max_length,
  default_value, options, required, sort_order
```

- `edge_types.code` UNIQUE — 用作导入时的匹配键
- 字段 diff 逻辑：现有 `PUT /edge-types/{id}` 已经是"整批 DELETE + INSERT"覆盖式，导入沿用相同策略
- 边类型字段**无固定列冲突约束**（不像告警模板要避开 `id/node_id/alarm_index/created_at/updated_at`）
- 边类型 CRUD 全部代码位于 `backend/app/admin/node_type.py` 内（历史遗留，与节点类型共文件）

### API 现状

`backend/app/admin/node_type.py` 已有：
- `GET /edge-types` — list
- `GET /edge-types/{id}` — detail
- `POST /edge-types` — create
- `PUT /edge-types/{id}` — update
- `DELETE /edge-types/{id}` — delete
- `POST /edge-types/batch-delete` — 批量删
- **`POST /edge-types/export`** — **当前返回 JSON**，非 xlsx

**缺失**：xlsx 版 export、import/preview、import 三个端点

### 前端现状

`EdgeTypeTable.vue`（250 行）目前只有"批量导出"按钮 → 调 `edgeTypeApi.export(ids)` → `downloadJson(result.items, ...)` → 下载 `.json` 文件。无导入按钮、无行选择用于导出的 Dropdown。

### 节点类型 / 告警模板的参照实现

已有工具函数（复用）：
- `backend/app/admin/node_type.py:_safe_sheet_name` — Sheet 名清理（复用）
- `backend/app/admin/node_type.py:_build_header_map` / `_col` — 按表头名读取列（复用）
- `backend/app/admin/node_type.py:_load_import_workbook` — 硬编码检查 `"类型汇总"` Sheet（**需要参数化**）

## 目标

- 后端把 `POST /edge-types/export` 改造成返回 xlsx blob；新增 `POST /edge-types/import/preview` 和 `POST /edge-types/import` 端点
- 前端 `EdgeTypeTable` 顶部改成"批量导出 Dropdown（全部/选中）+ 导入按钮"，导入流程与节点类型/告警模板一致（preview → Modal.confirm → 正式导入）
- 边类型特有字段（semantic/directed/exclusive_target/allow_codes/line_style/color）在 Excel 中的表示明确、可回读
- 遵循节点类型的最小校验策略：`allow_source/target_type_codes` 引用不存在的 `node_types.code` 记 warning 但字符串仍保存（运行时兜底）
- 无向后兼容：JSON 格式导出直接删除，用户诉求就是切换到 Excel

## 架构

改动集中在**类型管理**子系统的边类型侧。不涉及节点类型的功能变更（仅参数化 `_load_import_workbook`），不涉及告警模板、拓扑、Mock 流水线。

**保持不动**：
- `edge_types` / `edge_type_fields` 表结构
- 现有边类型 CRUD 端点行为
- 节点类型 Excel 导入导出行为（仅 `_load_import_workbook` 签名变，行为不变）
- 告警模板 Excel 导入导出（独立于此模块）
- `EdgeTypeModal` / `EdgeTypeFieldEditor` 组件

**改动分层**：

| 层 | 文件 | 改动摘要 |
|----|------|---------|
| Schema | `backend/app/admin/schemas/node_type.py` | 新增 `EdgeTypeImportPreviewItem`、`EdgeTypeImportPreview`、`EdgeTypeImportResult`（结构对齐 `NodeType*` 三个类） |
| Schema | `backend/app/admin/schemas/__init__.py` | 导出上述 3 个新类 |
| Route | `backend/app/admin/node_type.py` | `_load_import_workbook` 加 `expected_sheet` 参数（默认 `"类型汇总"`）；新增 `_build_edge_types_excel`；改造 `export_edge_types` 返回 xlsx blob；新增 preview/import 两个端点 |
| API 类型 | `frontend/src/api/types.ts` | `EdgeTypeItem` 不变；新增 `EdgeTypeImportPreviewItem`/`Preview`/`Result` 3 interface；`edgeTypeApi.export` 签名改为 `Promise<Blob>`；新增 `edgeTypeApi.importPreview/import` 方法 |
| 组件 | `frontend/src/components/types/EdgeTypeTable.vue` | 工具栏"批量导出"改成 Dropdown + 加"导入"按钮 + 隐藏 file input；`handleFileChosen`/`doImport` 处理函数 |

**DB migration**：无。

**辅助工具落位**：`_safe_sheet_name` / `_build_header_map` / `_col` / `_load_import_workbook` 都在 `node_type.py` 里，直接复用；不抽公共 utils（YAGNI —— 现在只有节点类型和边类型两处使用，均在同文件；告警模板另有一套内联工具，跨文件抽公共模块暂无收益）。

## Excel 结构规范

### Sheet 1：边类型汇总

必填列：`Code`、`名称`
可选列：`语义`、`有向`、`唯一目标`、`允许源类型`、`允许目标类型`、`线条样式`、`颜色`、`描述`、`字段数`、`创建时间`、`更新时间`

- `语义` 值：`connect` / `contain`（空 → 兜底 `connect`，与 DB 默认值一致；**非空但非白名单值** → 记 errors 跳过整行）
- `有向` / `唯一目标` 值：`是` / `否`（其他值兜底 `否`）
- `允许源类型` / `允许目标类型` 值：逗号分隔的 node_type code 列表（如 `switch,router`），空表示不限制
- `线条样式` 值：`solid` / `dashed` / `dotted` 等，不做值校验
- `颜色` 值：任意字符串（如 `#1890ff`），不做值校验
- `字段数` / `创建时间` / `更新时间`：仅导出输出，导入时忽略

### Sheet 2..N：`<code>`（每边类型一个）

必填列：`字段标识`、`显示名称`、`字段类型`
可选列：`最大长度`、`默认值`、`选项`、`必填`、`排序`

- `字段类型` 白名单：`text` / `number` / `select` / `boolean` / `array`
- `必填` 值：`是` / `否`
- `字段标识` 需为合法标识符（字母/数字/下划线，字母或下划线开头）
- text 类型 `最大长度` 空/非法 → 兜底 255

**Sheet 名清理**：调用 `_safe_sheet_name(code)` —— 去掉 Excel 非法字符 `\ * / [ ] ? :`，超过 31 字符则截断到 28 + `"..."`。

## 组件与数据流

### 复用工具的改造

`_load_import_workbook` 从硬编码 `"类型汇总"` 改为参数化：

```python
def _load_import_workbook(contents: bytes, expected_sheet: str = "类型汇总") -> Workbook:
    try:
        wb = load_workbook(filename=BytesIO(contents))
    except Exception:
        raise HTTPException(status_code=400, detail={"code": 40211, "message": "文件无法解析，请确认是有效的 xlsx 文件"})
    if expected_sheet not in wb.sheetnames:
        raise HTTPException(status_code=400, detail={"code": 40212, "message": f"缺少「{expected_sheet}」Sheet"})
    return wb
```

- 节点类型侧原调用 `_load_import_workbook(contents)` → 默认参数生效，行为不变
- 边类型侧调用 `_load_import_workbook(contents, "边类型汇总")`

### 导出路径（改造现有端点）

```
用户点"批量导出"（全部或"导出选中"）
  ↓
[前端] edgeTypeApi.export(ids?: string[])
  ↓ POST /admin/api/edge-types/export  body: { ids?: [...] }
  ↓ responseType: 'blob'
[后端] connect() 查 edge_types 行（按 ids 或全部，ORDER BY name）
  for each row:
    fields = _get_edge_type_fields(conn, id)
    构造 EdgeTypeDetail 并 model_dump(mode="json", by_alias=True) → camelCase dict
  ↓
[后端] _build_edge_types_excel(items):
  Sheet 1 "边类型汇总":
    header = ["Code", "名称", "语义", "有向", "唯一目标",
              "允许源类型", "允许目标类型", "线条样式", "颜色",
              "描述", "字段数", "创建时间", "更新时间"]
    每边类型 1 行；directed/exclusiveTarget → "是"/"否"；
    allowSourceTypeCodes/allowTargetTypeCodes 原样输出（None → 空）
  Sheet 2..N "<code>":
    header = ["字段标识", "显示名称", "字段类型", "最大长度",
              "默认值", "选项", "必填", "排序"]
    每字段 1 行；required → "是"/"否"
  ↓ StreamingResponse xlsx blob
[前端] downloadBlob + timestampExcelFilename('edge-types-export')
```

### 导入 preview 路径

```
[前端] 选文件 → edgeTypeApi.importPreview(file)
  ↓ POST /admin/api/edge-types/import/preview  multipart/form-data
[后端] _load_import_workbook(contents, "边类型汇总")
  遍历"边类型汇总"每行:
    if 空行: break
    code = _col(headers, "Code", row)
    name = _col(headers, "名称", row)
    if 缺 code or name: errors.append(...); continue
    SELECT id, name FROM edge_types WHERE code = ?
      找到 → toUpdate: {code, name, oldName: existing.name}
      未找到 → toCreate: {code, name}
  ↓ 返回 { toCreate, toUpdate, errors }
[前端] Modal.confirm 内联 VNode（跟节点类型 handleFileChosen 完全一致）:
  - 将新建（N 个）
  - 将覆盖（M 个，字段将被替换）
  - 解析错误（K 个）
  用户点"确认" → doImport(file)
```

### 正式导入路径

```
[前端] edgeTypeApi.import(file)
  ↓ POST /admin/api/edge-types/import  multipart/form-data
[后端] transaction:
  wb = _load_import_workbook(contents, "边类型汇总")
  ws = wb["边类型汇总"]
  headers = _build_header_map(ws)
  result = EdgeTypeImportResult()
  # 预取所有 node_type.code 集合，用于 allow_codes 引用校验
  known_node_codes = { r["code"] for r in conn.execute("SELECT code FROM node_types") }
  
  for row in ws.iter_rows(min_row=2, values_only=True):
    if 空行: break
    code = _col(headers, "Code", row)
    name = _col(headers, "名称", row)
    if not code or not name: errors 记录跳过; continue
    
    semantic_raw = _col(headers, "语义", row) or "connect"
    semantic = semantic_raw.strip().lower()
    if semantic not in ("connect", "contain"):
      result.errors.append(f"[{code}] 语义 '{semantic_raw}' 非法（仅支持 connect/contain），跳过整行")
      continue
    
    directed = 1 if _col(headers, "有向", row) == "是" else 0
    exclusive_target = 1 if _col(headers, "唯一目标", row) == "是" else 0
    allow_source_raw = _col(headers, "允许源类型", row)  # "switch,router" or None
    allow_target_raw = _col(headers, "允许目标类型", row)
    line_style = _col(headers, "线条样式", row)
    color = _col(headers, "颜色", row)
    description = _col(headers, "描述", row)
    
    # allow_codes 引用校验（warning-only）
    for kind, raw in [("源", allow_source_raw), ("目标", allow_target_raw)]:
      if raw:
        for c in [x.strip() for x in raw.split(",") if x.strip()]:
          if c not in known_node_codes:
            result.errors.append(f"[{code}] 允许{kind}类型 '{c}' 不存在的节点类型 code，字符串仍保存")
    
    existing = SELECT id FROM edge_types WHERE code = ?
    if existing:
      type_id = existing["id"]
      UPDATE edge_types SET name=?, semantic=?, directed=?, exclusive_target=?,
        allow_source_type_codes=?, allow_target_type_codes=?, line_style=?,
        color=?, description=?, updated_at=datetime('now') WHERE id=?
      result.updated += 1
    else:
      type_id = _new_edge_id()
      INSERT INTO edge_types (id, code, name, semantic, directed, exclusive_target,
        allow_source_type_codes, allow_target_type_codes, line_style, color, description)
      result.created += 1
    
    sheet_name = _safe_sheet_name(code)
    if sheet_name in wb.sheetnames:
      DELETE FROM edge_type_fields WHERE edge_type_id = ?
      fheaders = _build_header_map(wb[sheet_name])
      seen_fields = set()
      for frow in wb[sheet_name] rows (min_row=2):
        if 空行: break
        fkey / flabel / ftype_raw = _col(...)（必填三项，缺则跳过）
        if fkey 非合法标识符（简单正则 [A-Za-z_][A-Za-z0-9_]*）: errors 记录跳过
        if fkey in seen_fields: errors 记录跳过（重复）
        ftype 白名单校验 → 非法跳过
        text 类型 max_length 空/非整数/<1 → 255；非 text 空 → None
        array default_value JSON 语法 + list 类型校验
        INSERT INTO edge_type_fields (edge_type_id, field_key, ...)
        result.total_fields += 1
  ↓ 返回 result { created, updated, totalFields, errors }
[前端]
  message.success(`新建 ${created} 个 / 覆盖 ${updated} 个 / 字段 ${totalFields} 个`)
  if errors: message.warning(errors.slice(0, 3).join('；') + (errors.length > 3 ? '…' : ''))
  fetchEdgeTypes() 刷新表格
```

## 前端组件详细

### EdgeTypeTable.vue 顶部工具栏

```
┌──────────────────────────────────────────────────────────┐
│ 边类型 [搜索] [批量删除] [批量导出 ▼] [导入] [新建边类型] │
│                        ├ 全部导出                        │
│                        └ 导出选中（N 项）                │
└──────────────────────────────────────────────────────────┘
```

- `selectedRowKeys: Ref<string[]>` — 已存在，复用
- `<input ref="fileInputRef" type="file" accept=".xlsx" style="display:none" @change="handleFileChosen">`
- 导出按钮改成 `Dropdown` + `Menu`（跟 AlarmSchemaTable 一致）
- 导入按钮 → `fileInputRef.value?.click()` 触发文件选择
- 导入弹窗 `Modal.confirm({ content: h(...) })` 内联渲染，跟节点类型/告警模板一致

### 工具函数复用

- `downloadBlob(blob, filename)` — 已存在于 `frontend/src/utils/download.ts`
- `timestampExcelFilename(prefix)` — 已存在
- 删除现有 `import { downloadJson, timestampFilename } from '@/utils/download'`

## 测试要点

### 后端测试（新建 `backend/tests/test_edge_type_excel.py`）

- **导出**：
  - `test_export_all_returns_xlsx_with_summary_sheet` — 有"边类型汇总" Sheet + 每 code 独立 Sheet
  - `test_export_summary_contains_semantic_and_directed_columns` — 汇总表头正确（13 列）
  - `test_export_directed_and_exclusive_serialized_as_yes_no` — bool → "是"/"否"
  - `test_export_allow_codes_kept_as_comma_separated_string` — 逗号分隔原样
  - `test_export_ids_only_returns_selected` — 按 ids 过滤
- **preview**：
  - `test_import_preview_categorizes_create_and_update` — toCreate/toUpdate 分类
  - `test_import_preview_records_old_name_on_update` — oldName 正确
  - `test_import_preview_missing_summary_sheet_returns_400` — 缺"边类型汇总" → 400
- **正式导入**：
  - `test_import_creates_new_edge_type_with_fields` — 新建 + 字段
  - `test_import_overwrites_existing_edge_type` — 覆盖式（字段替换）
  - `test_import_directed_column_yes_maps_to_true` — "是" → True，"否" → False
  - `test_import_invalid_semantic_records_error_and_skips_row` — 非法 semantic 跳过整行
  - `test_import_text_field_missing_maxlen_defaults_to_255` — 兜底
  - `test_import_allow_codes_unknown_node_code_records_warning` — 引用不存在记 warning，字符串仍保存
  - `test_import_partial_failure_isolated_per_row` — 行级隔离

### 前端手动回归

- 建 3 边类型 → 批量导出全部 → xlsx 打开验证结构（1 汇总 Sheet + 3 code Sheet）
- 编辑一个改名 → 导入原 xlsx → preview 显示"将覆盖 3 个"其中 1 个 oldName 不同 → 确认后模板复原
- 建 5 边类型勾选 2 个 → 导出选中 → xlsx 只含 2 个
- 手动改 xlsx 加新 code → 导入 → preview 显示"将新建 1 个 / 将覆盖 N 个"
- 手动改 xlsx "语义" 列为 `invalid` → 导入 → 结果 warning 提示

## 非目标

- 不迁移边类型 CRUD 代码到独立 `edge_type.py` 文件（历史遗留，本次不做无关重构）
- 不做 `allow_source/target_type_codes` 的引用完整性**强校验**（宽松策略：记 warning 但存原字符串，跟告警模板 `mapping_target` 一致）
- 不为 `line_style` / `color` 做值校验（运行时兜底）
- 不做 backward compat 兼容旧的 JSON 导出格式（直接切换，用户诉求即是"改成 Excel"）
- 不为节点类型侧的 `_load_import_workbook` 调用点添加显式参数（默认值 `"类型汇总"` 已保证行为不变）
- 不做 `EdgeTypeCreate/Update` Pydantic 的破坏性改动（不加 `_new_edge_id` 之外的东西）

## 风险

- **JSON → xlsx 硬切换**：老 `.json` 导出文件无法导入到新版本。用户诉求即是切换，非风险。
- **`_load_import_workbook` 参数化影响面**：grep 已确认 `node_type.py:582` 定义一处 + `node_type.py:607, 660` 调用两处 + `alarm_schema.py` 有独立同名函数（不受影响）。默认参数 `"类型汇总"` 保证节点类型侧调用点行为不变。
- **allow_codes 存在空格**：老 DB 数据里可能有 `"switch, router"`（含空格）。导出到 Excel 原样输出后，导入时 split 后 `.strip()` 保证正确解析，字段值最终会被规范化为 `"switch,router"`（无空格）。这是一次隐性规范化，副作用可接受。
- **多值列使用逗号分隔与告警模板 `|` 不一致**：本项目内两个多值列的约定不同（`allow_codes` 用 `,`，"所属网管/设备" 用 `|`）。这是因为 `allow_codes` 存 DB 就是逗号，跟数据源保持一致最省逻辑；用户查看 xlsx 时能一致识别（两种分隔符都是常见惯例）。

## 交付物

- 后端：`schemas/node_type.py`（+30 行）+ `admin/node_type.py`（+200 行改造/新增）+ `tests/test_edge_type_excel.py`（新建，约 250 行）
- 前端：`api/types.ts`（+40 行）+ `components/types/EdgeTypeTable.vue`（250 → 约 320 行）
- 无 DB migration
- 估算工时：3-5 小时
