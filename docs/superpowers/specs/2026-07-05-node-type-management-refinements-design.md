# 节点类型管理体验优化 设计方案

**日期**：2026-07-05
**背景**：用户在使用节点类型 / 边类型 / 告警模板 Modal 时反馈三处摩擦：

1. **文本字段 MaxLen 强制填写**：新建 / 编辑节点类型或边类型时，`text` 文本字段必须手动设置 `max_length`，忘填就报错；Excel 导入侧则完全不校验，text 类型 `max_length` 为空也能导入成功 —— 前后端行为不一致
2. **字段配置区表头 / 新增按钮不 sticky**：字段配置区往下翻滚时，Table 表头和"新增字段"按钮都会滚出视野，用户被迫滚回顶部才能加字段
3. **无法在 Modal 里设置所属网管/设备**：节点类型的"所属网管/设备"关联需要跳到列表页 Dropdown 单独操作；同时 Modal 里的 icon / color / shape / 渲染模式 / DN 模板 5 个字段用户不知道是什么（"这些字段有什么用"）

## 术语

- **网管/设备**：本项目 domain 概念的中文表达，对应 DB 中 `domains` 表；`domains.name` 是 `UNIQUE`
- **死字段**：数据库里存了、UI 有输入、但代码中从未被任何消费方读取的字段
- **字段配置区**：Modal 底部 Divider 分隔的字段编辑器（node/edge/alarm 三处）

## 现状分析

### 死字段全仓 grep 结论

| 字段 | 消费方 | 结论 |
|------|--------|------|
| `category` 分类 | `TypePalette` / `NodeTypeTable` 分组过滤 | **有用** |
| `icon` 图标 | 无（画布走 `getNodeIconByCode(code)` 静态映射） | **死字段** |
| `color` 颜色 | 无 | **死字段** |
| `shape` 形状 | 无 | **死字段** |
| `render_mode` 渲染模式 | 表格展示了这一列，但画布 renderer 从不 switch 分支 | **死字段** |
| `dn_template` DN 模板 | 无（节点名走别的逻辑） | **死字段** |

用户列出的 5 个字段（分类之外）在整个 codebase 里没有任何 renderer / handler 消费，属于历史遗留。

### 网管关联链路现状

- 后端已提供 `PUT /node-types/{id}/domains` 和批量 `PUT /node-types/domains`
- 前端 `NodeTypeTable` 里 Dropdown 有"关联网管/设备"入口
- 但 `NodeTypeModal` 里没有网管选择器 → 新建/编辑不能一站式设置

### 3 个字段编辑器结构一致

| 编辑器 | 位置 | 顶部结构 | Table 原 scroll |
|--------|------|---------|----------------|
| `NodeTypeFieldEditor` | `components/types/` | `Affix` + `toolbar-top` | `{ x: 900 }` |
| `EdgeTypeFieldEditor` | `components/types/` | `Affix` + `toolbar-top` | `{ x: 900 }` |
| `AlarmSchemaFieldEditor` | `components/alarmSchemas/` | `Affix` + `toolbar-top` | `{ x: 1000 }` |

三者结构近乎克隆：`<Affix>` 包裹顶部 toolbar；Table 只有横向滚动；底部还有一个冗余的"新增字段"按钮 `.toolbar-bottom`。因 Modal body 自身也是滚动容器，`Affix` 在 Modal 内滚动时并不生效。

### text max_length 校验分歧

- Schema 层（`NodeTypeFieldInput` / `EdgeTypeFieldInput` / `AlarmSchemaFieldCreate`）都用 `@model_validator(mode='after')` 强制 text 必须传 `max_length`，`None` 就 raise `ValueError`
- Excel 导入侧（`import_node_types`）直接把 `max_length` 列读进去存 DB，text 类型没有校验
- 结论：**同一份数据经不同入口进入 DB，规则完全不同**

## 目标

- 5 个死字段从**读写路径**剥离，DB 列保留以避免 ALTER 风险
- text 类型 `max_length` 在**所有入口**（Modal / Excel / 直接 API）留空时兜底为 **255**，不再报错
- 3 个字段编辑器统一改成**独立滚动**：容器固定 360px 高，Table `scroll.y = 300` 表头 sticky；`Affix` 移除、底部冗余按钮删除
- `NodeTypeModal` 新增"所属网管/设备"多选，Create/Update API 一次事务完成类型 + 字段 + 网管关联
- Excel 导入/导出同步"所属网管/设备"列，按 `domains.name`（UNIQUE）匹配；老文件（无该列或有死字段列）向前向后兼容

## 架构

改动集中在**类型管理**子系统的 Modal / 编辑器 / Schema 三层。不涉及画布、Mock 流水线、Instance 管理等其它子系统。

**保持不动**：`domain_node_types` 表结构；`nodes` 表；画布渲染路径（`nodeShape.ts`，本来就不读死字段）。

**改动分层**：

| 层 | 文件 | 改动摘要 |
|----|------|---------|
| DB | `migrations.py`、`seed.py` | 无（DB 列全部保留，seed 里 `render_mode` 沿用） |
| Schema | `schemas/node_type.py` | `NodeTypeCreate/Update/Item/Detail` 删 5 死字段；加 `domain_ids: Optional[list[str]]`；`NodeTypeFieldInput.max_length` 校验改成"None → 255"；`EdgeTypeFieldInput.max_length` 同步 |
| Schema | `schemas/alarm.py` | `AlarmSchemaFieldCreate.max_length` 校验同步（None → 255）|
| Route | `admin/node_type.py` | `_row_to_node_type_item` / `list` / `get` / `create` / `update` / `_build_node_types_excel` / `import_node_types` / `preview_node_types_import` 剥离 5 死字段；创建/更新事务内一并 replace `domain_node_types`；Excel 汇总表增加"所属网管/设备"列，导入按 name 反查 |
| API 类型 | `frontend/src/api/types.ts` | `NodeType*` 接口删 5 字段，`NodeTypeCreate/Update` 加 `domainIds?: string[]` |
| 组件 | `components/types/NodeTypeModal.vue` | 表单只留 code / name / category / description / **所属网管/设备**；`styles.body` 的 `maxHeight` / `overflowY` 移除；打开时并行 fetch domains；提交路径构造 `domainIds` |
| 组件 | `components/types/NodeTypeFieldEditor.vue` | 删 `Affix` 包裹、删 `.toolbar-bottom`、外层容器 `height: 360px + flex column`；Table `:scroll="{ x: 900, y: 300 }"`；MaxLen `InputNumber` 加 `placeholder="默认 255"` |
| 组件 | `components/types/EdgeTypeFieldEditor.vue` | 同上（`x: 900, y: 300`） |
| 组件 | `components/alarmSchemas/AlarmSchemaFieldEditor.vue` | 同上（`x: 1000, y: 300`） |
| 组件 | `components/types/NodeTypeTable.vue` | 删"渲染模式"列 |

## 组件与数据流

### Modal 布局（改后）

```
┌─ 节点类型 Modal (width: 880px, body 自然高度) ───────────┐
│ [表单区 — 高度自适应，不滚动]                              │
│   类型代码* | 类型名称*                                    │
│   分类     | 所属网管/设备（多选，可搜）                     │
│   描述                                                   │
│ ─── Divider: 字段配置 ─────                              │
│ [字段编辑区 — height: 360px, overflow: hidden]           │
│  ┌ toolbar (flex 常驻顶部，不参与滚动) ─────────────────┐  │
│  │ [+新增字段] [从JSON生成] N 个字段                    │  │
│  ├─ Table (:scroll={ x: 900, y: 300 }, 表头 sticky) ──┤  │
│  │  Key  Label  Type  MaxLen  Default  Options  Req    │  │
│  │  ...  ...    ...   ...     ...      ...      ...    │  │
│  │  ↕ 300px 独立滚动区                                  │  │
│  └────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────┘
```

关键：
- Modal body 移除 `maxHeight` / `overflowY` —— 表单区不再滚动
- 字段编辑区自己独立滚动，通过 Table `scroll.y` 触发表头 sticky
- toolbar 用 flex 定位在容器顶部，天然固定，不再需要 `Affix`
- 底部冗余的"新增字段"按钮删除（顶部已常驻可见）

### 保存路径（创建 / 编辑）

```
用户点确定
  ↓
[前端] confirmDeleteImpactIfAny() 保持不变
  ↓
[前端] 组装 payload:
  { code, name, category, description, domainIds, fields }
  ↓
POST /admin/api/node-types  (or PUT /{id})
  ↓
[后端] transaction 内:
  1. INSERT/UPDATE node_types
     (仅写 code, name, category, description；不再写 5 死字段)
  2. _sync_node_type_fields(conn, id, fields)
     (text max_length 缺失时 default 255 已由 Schema 层兜底)
  3. if payload has domainIds (含空数组):
       DELETE FROM domain_node_types WHERE node_type_id = ?
       for did in domainIds:
         INSERT OR IGNORE INTO domain_node_types (?, ?)
  ↓
返回 {id}
```

要点：
- `domain_ids` 用 `Optional[list[str]]`：`None` 表示不改动关联，`[]` 表示清空所有关联
- 事务保证类型、字段、网管三段一起成功或一起回滚
- 前端网管选择器空数组和"未修改"通过 `undefined` vs `[]` 区分

### Excel 导入路径

```
上传 xlsx
  ↓
"类型汇总" Sheet 遍历行:
  code / name / category [必填，缺一跳过]
  所属网管/设备 [可选，值形如 "网管A|网管B"]
  ↓
  for each row:
    INSERT/UPDATE node_types (仅写非死字段)
    domains_cell = _col(headers, "所属网管/设备", row)
    if domains_cell:
      for dname in domains_cell.split('|'):
        row = SELECT id FROM domains WHERE name = ?
        if row: to_link[type_id].add(row["id"])
        else: errors.append(f"[{code}] 网管 '{dname}' 不存在，关联跳过")
  ↓
  遍历类型专属 Sheet 同步字段:
    if fieldType == 'text' and (maxlen 为空/非数字/<1):
      maxlen = 255
    else:
      maxlen = int(maxlen)
  ↓
  一次性 DELETE + INSERT domain_node_types (仅当行提供了该列)
  ↓
返回 result（含 errors + created/updated/total_fields + linked/unlinked 计数）
```

### 兼容性策略

- **老 Excel 文件（有 icon/color/shape/renderMode/dnTemplate 列，无所属网管列）**：`_build_header_map` 按表头名读取，找不到就返回 None，正常导入类型定义，死字段列被忽略
- **新 Excel 文件（有所属网管列）导入到未升级版本**：旧版本 `_build_header_map` 找不到"所属网管/设备"就跳过，仅忽略关联，类型定义正常写入
- **前端旧接口调用（不传 domainIds）**：后端把 `domain_ids` 设为 `Optional`，`None` 时不动关联表，纯类型编辑不受影响

## 测试要点

### 后端单测（`backend/tests/`）

- `test_node_type_schema.py`（新建，若不存在）
  - `text` 类型 `max_length` 为 None → normalized 到 255（不 raise）
  - `text` 类型 `max_length=100` → 保留 100
  - `text` 类型 `max_length=0` → 仍 raise（ge=1 保留）
  - `NodeTypeCreate` 带 `domain_ids: []`、`None`、`["dom_xxx"]` 三种形态都能正常解析
- `test_edge_type_schema.py`（同上，覆盖 EdgeTypeFieldInput）
- `test_alarm_schema.py`（同上，覆盖 AlarmSchemaFieldCreate）

### 后端 e2e（`backend/tests/`）

- `POST /node-types` 带 `domainIds=["dom_a"]` → 类型创建，`domain_node_types` 有一条 `(dom_a, ntype_xxx)`
- `PUT /node-types/{id}` 带 `domainIds=[]` → `domain_node_types` 里该类型的关联全部清空
- `PUT /node-types/{id}` 不带 `domainIds` 只改 name → 关联不动
- 导出的 xlsx 里"类型汇总" Sheet 表头包含"所属网管/设备"，不再包含 icon/颜色/形状/渲染模式/DN模板
- 导入 xlsx（新格式）"所属网管/设备"列填 "网管A|不存在的网管" → 类型创建成功，`errors` 里有"网管 '不存在的网管' 不存在，关联跳过"，`domain_node_types` 里只有网管A 的关联
- 导入 xlsx（老格式，含 icon/颜色 等列，无所属网管列）→ 类型创建成功，死字段列被忽略

### 手动 UI 回归

- 打开 NodeTypeModal：网管多选可搜可选，编辑模式回填正确
- 字段配置区：Table 内滚动 20+ 字段时，表头保持可见；"新增字段"按钮始终可见；底部没有第二个"新增字段"按钮
- EdgeTypeModal、AlarmSchemaModal 字段编辑区行为一致
- 新建 text 字段留 MaxLen 空 → 保存不报错，编辑回显 MaxLen=255
- 编辑历史节点类型（有 icon/color/... 值）→ Modal 不显示这些字段，保存后 DB 里旧值原封不动

## 非目标

- 不 DROP 数据库 5 个死列（避免 SQLite ALTER 风险；用户如后续想彻底清理可另开一个 migration 任务）
- 不为 icon/color/shape 真正接入画布 renderer（YAGNI，用户已确认删除方向）
- 不改造 `EdgeTypeModal` 的表单顶部（本次改动只涉及 EdgeTypeFieldEditor 的字段编辑区）
- 不为告警模板增加 Excel 导入导出功能（告警模板本身没有该功能，只跟随 Schema 层同步 max_length 兜底）
- 不涉及节点组（node_groups）的字段编辑器改造 —— 节点组配置节点属性策略走的是 `AttrStrategyEditor`，与本次三个字段编辑器结构不同

## 风险

- **网管选择器 fetch 时机**：Modal 打开时并行 fetch domains 列表，若接口慢会导致选择器初始为空但短暂可见；`useDomains` 应已有缓存，风险低
- **老 Excel 文件字段完整性**：`import_node_types` 老代码用 `_col(headers, "图标", row)` 等读死字段，改后这些 `_col` 调用整体删除；如果外部脚本 hardcode 依赖导出 xlsx 里有"图标"列，会破坏兼容 —— 但项目内没有此类脚本
- **`domain_ids` 语义**：`None` 表示"不动关联"，`[]` 表示"清空关联"；前端需要在 `NodeTypeUpdate` 里显式区分。若忘记传就等于不动，安全侧倾向明确保留

## 交付物

- 后端：Schema / 路由 / 测试 5-7 个文件
- 前端：Modal / FieldEditor / Table / api 类型 6-8 个文件
- 测试：单测 + e2e 共 8-10 个新测试
- 无 DB migration
