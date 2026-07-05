# 告警模板 Excel 导入导出 设计方案

**日期**：2026-07-05
**背景**：告警模板（`alarm_schemas`）目前有完整的 CRUD API 和 UI，但**缺少导入导出能力**。用户在多环境间迁移模板、批量维护字段、备份定义时都必须逐个手工新建，效率低且易出错。节点类型近期已完成 Excel 多 Sheet 导入导出，用户对该交互模式已经熟悉；本次为告警模板补齐相同能力。

## 术语

- **告警模板**：`alarm_schemas` 表定义的告警字段模板，被 `topologies.alarm_schema_id` 反向引用；一个模板可被多个拓扑复用
- **字段**：`alarm_schema_fields` 表中的模板字段定义，含类型、默认值、必填、映射目标等
- **展示字段**：`alarm_schemas.display_field_key`，指向 fields 中某个 `field_key`，前端展示告警列表时用作行标题
- **映射节点属性**（`mapping_target`）：字段值可映射到对应节点属性，触发告警时联动更新节点属性

## 现状分析

### 数据模型

```sql
alarm_schemas:
  id, code (UNIQUE), name, description, display_field_key, created_at, updated_at

alarm_schema_fields:
  id, alarm_schema_id (FK), field_key, field_label, field_type, max_length,
  default_value, options, required, sort_order, mapping_target
```

- `alarm_schemas.code` UNIQUE — 用作导入时的匹配键
- 字段 diff 逻辑：现有 `PUT /alarm-schemas/{id}` 里已经是"整批 DELETE + INSERT"覆盖式，导入沿用相同策略
- 无级联删除：告警模板被拓扑引用时删除会 409（无关本次任务）

### API 现状

`backend/app/admin/alarm_schema.py` 已有 CRUD：
- `GET /alarm-schemas` — list
- `GET /alarm-schemas/{id}` — detail
- `POST /alarm-schemas` — create
- `PUT /alarm-schemas/{id}` — update
- `DELETE /alarm-schemas/{id}` — delete

**缺失**：export、import/preview、import 三个端点

### 前端现状

`AlarmSchemaTable.vue`（97 行）目前只有"新建告警模板"按钮 + 表格 + 编辑/删除。无导入导出入口，无行选择。

### 节点类型的参照实现

`backend/app/admin/node_type.py`：
- `_build_node_types_excel(items)` — 生成多 Sheet workbook
- `_safe_sheet_name(code)` — Sheet 名清理（去非法字符 + 截长）
- `_build_header_map(ws)` / `_col(headers, name, row)` — 按表头名读取列（列顺序无关）
- `POST /node-types/export` — 返回 xlsx blob
- `POST /node-types/import/preview` — 返回 `{toCreate, toUpdate, errors}`
- `POST /node-types/import` — 返回 `{created, updated, totalFields, errors}`

`NodeTypeTable.vue` 顶部工具栏：批量导出 Dropdown + 导入按钮 + 隐藏 `<input type="file">` + `Modal.confirm` 内联渲染预览 VNode。

## 目标

- 后端新增导出 / 导入 preview / 导入 三个端点，Excel 多 Sheet 结构复刻节点类型模式，字段列适配告警模板差异（去 category/domain，保留 display_field_key + mapping_target）
- 前端 `AlarmSchemaTable` 增加"批量导出 / 导出选中 / 导入"三个入口，导入流程与节点类型一致（preview → 弹窗确认 → 正式导入）
- 遵循节点类型侧的最小校验策略：只做基本类型合法性检查，`display_field_key` 和 `mapping_target` 的引用完整性交给运行时兜底
- 老导出/新导入不涉及兼容（首个版本，无历史格式）

## 架构

改动集中在**告警模板**子系统。不涉及告警映射引擎、拓扑绑定、node_alarms/node_group_alarms 数据表。

**保持不动**：`alarm_schemas` / `alarm_schema_fields` 表结构；现有 CRUD 端点；`AlarmSchemaModal` / `AlarmSchemaFieldEditor` 组件。

**改动分层**：

| 层 | 文件 | 改动摘要 |
|----|------|---------|
| Schema | `backend/app/admin/schemas/alarm.py` | 新增 `AlarmSchemaExportRequest`、`AlarmSchemaImportPreviewItem`、`AlarmSchemaImportPreview`、`AlarmSchemaImportResult` |
| Route | `backend/app/admin/alarm_schema.py` | 新增 `_build_alarm_schemas_excel` / `_safe_sheet_name` / `_build_header_map` / `_col` / `_load_import_workbook`；新增 3 个端点 |
| API 类型 | `frontend/src/api/alarmSchema.ts` | 新增 `AlarmSchemaImportPreviewItem` / `AlarmSchemaImportPreview` / `AlarmSchemaImportResult` interfaces；`alarmSchemaApi` 新增 `export/importPreview/import` 三方法 |
| 组件 | `frontend/src/components/alarmSchemas/AlarmSchemaTable.vue` | 顶部工具栏加"批量导出" Dropdown + "导入"按钮 + `<input type="file">`；表格加 `rowSelection`；`handleImport` / `handleExport` 处理函数 |

**辅助函数落位选择**：`_col` / `_build_header_map` / `_safe_sheet_name` 内联到 `alarm_schema.py`（不抽公共 utils —— 只有两处使用，抽公共模块是过度设计，将来第三处再用时再抽）。

**DB migration**：无。

## Excel 结构规范

### Sheet 1：模板汇总

必填列：`Code`、`名称`
可选列：`描述`、`展示字段Key`、`字段数`、`创建时间`、`更新时间`

导出时全部输出；导入时仅按表头名读取（列顺序无关，缺列忽略，`字段数/时间`列导入时不使用）。

### Sheet 2..N：`<code>`（每模板一个）

必填列：`字段标识`、`显示名称`、`字段类型`
可选列：`最大长度`、`默认值`、`选项`、`必填`、`排序`、`映射节点属性`

`必填` 列值为 `"是"` / `"否"`。`映射节点属性` 空值表示不映射。

**Sheet 名清理**：调用 `_safe_sheet_name(code)` —— 去掉 Excel 非法字符 `\ * / [ ] ? :`，超过 31 字符则截断到 28 + `"..."`。

## 组件与数据流

### 导出路径

```
用户点"批量导出"（全部）或"导出选中"（勾选后）
  ↓
[前端] alarmSchemaApi.export(ids?: string[])
  ↓ POST /admin/api/alarm-schemas/export  body: { ids?: [...] }
  ↓ responseType: 'blob'
[后端] connect() 查 alarm_schemas 行（按 ids 或全部，ORDER BY created_at DESC）
  for each row:
    fields = _get_fields(conn, id)
    构造 item dict（含 display_field_key + fields）
  ↓
[后端] _build_alarm_schemas_excel(items):
  Sheet 1 "模板汇总": 
    header = ["Code", "名称", "描述", "展示字段Key", "字段数", "创建时间", "更新时间"]
    每模板 1 行
  Sheet 2..N "<code>":
    header = ["字段标识", "显示名称", "字段类型", "最大长度",
              "默认值", "选项", "必填", "排序", "映射节点属性"]
    该模板字段
  ↓ StreamingResponse
[前端] downloadBlob + timestampExcelFilename('alarm-schemas')
```

### 导入 preview 路径

```
[前端] 选文件后 alarmSchemaApi.importPreview(file)
  ↓ POST /admin/api/alarm-schemas/import/preview  multipart/form-data
[后端] _load_import_workbook(contents) → 校验 "模板汇总" Sheet 存在，缺则 400
  遍历"模板汇总"每行:
    if 空行: break
    code = _col(headers, "Code", row)
    name = _col(headers, "名称", row)
    if 缺 code or name: errors.append("Code=... 缺必填字段，跳过"); continue
    SELECT id, name FROM alarm_schemas WHERE code = ?
      找到 → toUpdate.append({code, name, oldName: existing.name})
      未找到 → toCreate.append({code, name})
  ↓ 返回 { toCreate, toUpdate, errors }
[前端] Modal.confirm 内联渲染 VNode:
  - "将新建（N 个）：" + 列表 [code（name）]
  - "将覆盖（字段将被替换）（M 个）：" + 列表 [code（oldName → newName）]
  - "解析错误（K 个）：" + errors 展示（如有）
  用户点"确认" → 走正式导入
  用户点"取消" → 终止
```

### 正式导入路径

```
[前端] alarmSchemaApi.import(file)
  ↓ POST /admin/api/alarm-schemas/import  multipart/form-data
[后端] transaction:
  _load_import_workbook(contents)
  ws = wb["模板汇总"]
  headers = _build_header_map(ws)
  result = AlarmSchemaImportResult(created=0, updated=0, totalFields=0, errors=[])
  
  for row in ws.iter_rows(min_row=2, values_only=True):
    if 全空行: break
    code = _col(headers, "Code", row)
    name = _col(headers, "名称", row)
    description = _col(headers, "描述", row)
    display_field_key = _col(headers, "展示字段Key", row)
    if 缺 code or name: errors 记录，continue
    
    existing = SELECT id FROM alarm_schemas WHERE code = ?
    if existing:
      schema_id = existing["id"]
      UPDATE alarm_schemas SET name=?, description=?, display_field_key=?, updated_at=now WHERE id=?
      result.updated += 1
    else:
      schema_id = _new_id()
      INSERT INTO alarm_schemas (id, code, name, description, display_field_key)
      result.created += 1
    
    sheet_name = _safe_sheet_name(code)
    if sheet_name in wb.sheetnames:
      DELETE FROM alarm_schema_fields WHERE alarm_schema_id = ?
      fheaders = _build_header_map(wb[sheet_name])
      seen_fields = set()
      for frow in wb[sheet_name] rows (min_row=2):
        if 全空行: break
        fkey / flabel / ftype = _col(...) (必填三项，缺则跳过)
        if fkey 非合法标识符 (_IDENT_RE): errors 记录跳过
        if fkey in _FIXED_COLS: errors 记录跳过（与固定列冲突）
        if fkey in seen_fields: errors 记录跳过（重复）
        ftype 白名单校验（text/number/select/boolean/array）→ 非法跳过
        text 类型 max_length 空/非整数/<1 → 兜底 255
        非 text 类型 max_length 空 → None，非整数 → None
        array 类型 default_value 非合法 JSON array → 跳过
        mapping_target 非空且非合法标识符 → 跳过
        INSERT INTO alarm_schema_fields (...)
        result.total_fields += 1
        seen_fields.add(fkey)
  ↓ 返回 result
[前端] 
  message.success(`已导入：新建 ${created} 个 / 覆盖 ${updated} 个 / 字段 ${totalFields} 个`)
  if errors: message.warning(errors.slice(0, 3).join('；') + (errors.length > 3 ? '…' : ''))
  refresh() 刷新表格
```

## 前端组件详细

### AlarmSchemaTable.vue 顶部工具栏

```
┌──────────────────────────────────────────┐
│ [新建告警模板] [批量导出 ▼] [导入]         │
│                                          │
│  批量导出 Dropdown Menu:                  │
│    ├ 全部导出                             │
│    └ 导出选中（N 项）  (disabled 若 N=0) │
└──────────────────────────────────────────┘
```

- `selectedRowKeys: Ref<string[]>` — 表格 `rowSelection` 绑定
- `<input ref="fileInputRef" type="file" accept=".xlsx" style="display:none" @change="handleFileChosen">`
- 导入按钮 → `fileInputRef.value?.click()` 触发文件选择

### 关键工具复用

- `downloadBlob(blob, filename)` — 已存在于 `frontend/src/utils/download.ts`
- `timestampExcelFilename(prefix)` — 已存在，返回 `{prefix}-{yyyyMMdd-HHmmss}.xlsx`

## 测试要点

### 后端测试（新建 `backend/tests/test_alarm_schema_excel.py`）

- **导出**：
  - `test_export_all_returns_xlsx_with_summary_sheet` — 导出全部 → 有"模板汇总" Sheet + 每模板独立 Sheet
  - `test_export_ids_only_returns_selected` — 只导出指定 ids
  - `test_export_sheet_contains_mapping_target_column` — 字段 Sheet 含"映射节点属性"列
  - `test_export_summary_contains_display_field_key_column` — 汇总 Sheet 含"展示字段Key"列
- **导入 preview**：
  - `test_import_preview_categorizes_create_and_update` — 一部分 code 存在一部分不存在时正确分类
  - `test_import_preview_records_old_name_on_update` — 覆盖项 oldName 与新 name 不同时正确记录
  - `test_import_preview_missing_summary_sheet_returns_400` — 缺"模板汇总" Sheet 返回 400
- **导入**：
  - `test_import_creates_new_schema_with_fields` — 新模板 + 字段一起导入
  - `test_import_overwrites_existing_schema` — 已存在 code → name/描述/display_field_key 覆盖；字段全部替换
  - `test_import_text_field_missing_maxlen_defaults_to_255` — text 类型 max_length 空 → 落库 255
  - `test_import_invalid_field_type_records_error` — field_type='invalid' → errors 记录跳过
  - `test_import_field_key_conflict_with_fixed_col_records_error` — field_key='id' → errors 记录跳过
  - `test_import_invalid_mapping_target_records_error` — mapping_target='123abc'（非合法标识符）→ errors 记录跳过
  - `test_import_partial_failure_isolated_per_row` — 某模板字段解析失败（如非法 field_type）不影响其他模板导入成功；errors 里体现该行问题

### 前端手动回归

- 空库建 3 个模板 → 全部导出 → xlsx 打开验证结构（3 个 code Sheet + 1 个汇总）
- 改名后再导入原 xlsx → preview 显示"将覆盖 3 个"其中改名的那个 oldName 不同 → 确认后模板复原
- 建 5 个模板勾选 2 个 → 导出选中 → xlsx 只含 2 个
- 手动编辑 xlsx 加新 code 一行 → 导入 → preview 显示"将新建 1 个 / 将覆盖 N 个"
- 导入含 field_type='invalid' 的 xlsx → 结果显示 errors 提示

## 非目标

- 不涉及**拓扑到告警模板的绑定关系**导入导出（拓扑 → 模板 是反向引用，逻辑上不属于模板定义）
- 不为 `mapping_target` 做"引用节点属性存在性"校验（运行时兜底 —— 沿用现有告警映射引擎的行为）
- 不为 `display_field_key` 做"引用字段存在性"校验（运行时兜底）
- 不新增独立的 `AlarmSchemaImportPreviewModal.vue` 组件（用 Modal.confirm 内联渲染 VNode，与节点类型侧一致）
- 不迁移现有节点类型的 `_col` / `_build_header_map` / `_safe_sheet_name` 到公共 utils 模块（YAGNI —— 只有两处调用，将来第三处再用时再抽）
- 不导出 `node_alarms` / `node_group_alarms` 实例数据（这是告警实例数据，不属于"模板"定义）

## 风险

- **字段全量覆盖导致 node_alarms attrs 里孤儿字段**：导入覆盖字段列表时会 DELETE 老字段 + INSERT 新字段，若某个 field_key 在覆盖后消失，已有的 `node_alarms.attrs` 里对该 key 的取值就变成孤儿。这是**现有 update 端点的既有行为**，本次导入沿用；预览弹窗里"将覆盖"文案已经提示"字段将被替换"，用户可以感知。
- **Sheet 名 code 冲突**：两个模板 code 经 `_safe_sheet_name` 清理后可能碰撞（如 `abc/def` 和 `abc_def`）—— `_safe_sheet_name` 只清理非法字符，不做去重。此风险与节点类型侧完全一致，评审时统一处理或都不处理。本次沿用节点类型的做法：不去重，Excel 层自动追加 `1` 后缀（openpyxl 默认行为），导入时用户可能看不到某模板的字段 Sheet 而被跳过导入字段，errors 里会体现。
- **大文件性能**：openpyxl 一次性加载 xlsx；预计几十到几百个模板量级不成问题。若未来需要千级支持，再考虑流式解析。

## 交付物

- 后端：`schemas/alarm.py`（+30 行）+ `admin/alarm_schema.py`（+200 行）+ `tests/test_alarm_schema_excel.py`（新增，约 200 行）
- 前端：`api/alarmSchema.ts`（+40 行）+ `components/alarmSchemas/AlarmSchemaTable.vue`（97 → 约 200 行）
- 无 DB migration
- 估算工时：3-5 小时
