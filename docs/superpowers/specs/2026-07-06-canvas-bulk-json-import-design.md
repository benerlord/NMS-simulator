# 画布批量 JSON 导入节点 — 设计方案

**日期：** 2026-07-06
**范围：** 画布页面新增"从 JSON 数组批量导入同类型实体节点"能力
**关联既有能力：**
- `frontend/src/utils/jsonFieldMatch.ts` — 单节点 JSON→字段值 / 生成字段的匹配语义（复用）
- `NodeAttrsModal` 单节点创建（保留、并行入口）
- 节点组（Node Group）— 参数化生成宏节点（与本功能互补，不重叠）

---

## 1. 目标与非目标

### 目标
- 用户可以贴一份 JSON 数组，一次性在画布上创建多个**同一类型**的实体节点
- 复用现有 JSON key 松匹配 + 值兼容转换语义（`jsonFieldMatch`），保持与其他 5 处 JSON 入口一致的体验
- 行级隔离预览（四分组呈现），部分失败不影响其他行
- 后端单事务、集中做行级 skip 处理，前端只负责 UI 编排

### 非目标
- 不支持"跨类型"导入（同一次导入所有节点必须同一 `nodeTypeId`）
- 不支持导入节点组 / 宏节点 / 边（仅实体节点 + 其 attrs）
- 不支持"更新已有节点属性"（冲突严格跳过，不覆盖）
- 不支持文件上传（仅粘贴 textarea）
- 不支持 JSONL / NDJSON（仅标准 JSON 数组）
- 不支持批量创建时同时选择"哪些字段忽略" —— 由类型定义 + 值兼容规则决定

---

## 2. 用户流程

```
TypePalette 类型卡片 hover
       ↓
[批量导入] 小按钮（ImportOutlined）
       ↓
BulkImportNodesModal 打开（类型锁定 = 该类型）
       ↓
Step 1: 粘贴 JSON 数组 + 配置
    - 大 textarea
    - "名称来源" 下拉（__auto__ / <某个 key>）
    - "起始坐标 X/Y" InputNumber（默认视口中心）
    - "每行列数" InputNumber（默认 6）
    - [解析预览] 按钮
       ↓
Step 2: 预览四分组
    - ✅ 将导入 N 条（可展开看每行字段值 + 计算出的 x/y）
    - ⏭️ 将跳过 M 条（每条附理由）
    - ❓ 未匹配 JSON key（全局提示）
    - ⚠️ 批次内 name 重复（第一次保留、其余跳过）
    - [返回编辑] / [确认导入 N 条]
       ↓
POST /admin/api/topologies/{id}/nodes/bulk
       ↓
后端事务：N 条 nodes + attrs 一并写入
       ↓
响应 { created: [...], skipped: [...] }
       ↓
前端刷新画布（fetchGraph）+ 提示"成功 N，跳过 M"
```

**入口不变量：**
- 拖拽单节点入口（NodeAttrsModal）完全保留、不受影响
- 批量导入是 TypePalette 类型卡片的 hover 副操作，不干扰主拖拽

---

## 3. 7 个关键决策（brainstorm 结论）

| # | 决策 | 结论 |
|---|------|------|
| 1 | 入口 | TypePalette 上"批量导入"按钮，类型自动锁定 |
| 2 | Name 来源 | 用户在 Modal 里选"哪个 JSON key 作为 name" + 兜底"自动生成 `<typeName>_<idx>`" |
| 3 | 布局 | 默认 6 列网格，起点=视口中心，格距 220×140，用户可调 |
| 4 | 预览 | 行级隔离 + 四分组（将导入 / 将跳过 / 未匹配 key / 批次内重名） |
| 5 | 输入 | 单一粘贴 textarea（标准 JSON 数组） |
| 6 | 冲突 | 严格跳过（画布已有同名 / 批次内重名均跳过，不覆盖） |
| 7 | 后端 | 新增 `POST /nodes/bulk` 端点，一个事务，服务端做行级隔离 |

---

## 4. 组件与文件结构

### 前端新增（4 个文件）

**`frontend/src/utils/jsonBulkNodes.ts`** — 纯函数库
```ts
export interface BulkPreviewValid {
  index: number
  name: string
  attrs: Record<string, string>
  x: number
  y: number
  warnings: string[]  // 字段值不兼容的字段列表
}
export interface BulkPreviewSkipped {
  index: number
  name: string | null
  reason: string
  raw: Record<string, unknown>
}
export interface BulkPreview {
  valid: BulkPreviewValid[]
  skipped: BulkPreviewSkipped[]
  duplicatesInBatch: Array<{ index: number; name: string }>
  unmatchedKeys: string[]
}
export interface LayoutOptions {
  startX: number
  startY: number
  cols: number
  dx?: number   // 默认 220
  dy?: number   // 默认 140
}
export function parseBulkJson(text: string):
  | { ok: true; items: Record<string, unknown>[] }
  | { ok: false; error: string }
export function buildBulkPreview(
  items: Record<string, unknown>[],
  fields: FieldLike[],
  nameKey: string,      // '__auto__' 或 具体 JSON key
  typeName: string,     // 用于 __auto__ 生成
  existingNames: Set<string>,
  layout: LayoutOptions,
): BulkPreview
```

**`frontend/src/components/canvas/BulkImportNodesModal.vue`** — 两步式 Modal（Step 1 输入 / Step 2 预览）

**`frontend/src/components/canvas/BulkImportPreview.vue`** — 预览子组件（分组 Collapse + Table）

**`frontend/src/api/node.ts`** — 追加 `bulkCreate` 方法

### 前端修改（2 个文件）

**`frontend/src/components/canvas/TypePalette.vue`**
- 类型卡片 hover 显示"批量导入"图标按钮（`ImportOutlined`）
- emit `bulk-import` 事件，携带 `NodeTypeDetail`

**`frontend/src/views/CanvasView.vue`**
- 监听 TypePalette 的 `bulk-import` 事件
- 传入当前视口中心（`graph.value.pageToLocal(...)`）作为默认 startX/startY
- 成功后调用 `fetchGraph()` + `graph.centerContent()` 到导入区域

### 后端修改（2 个文件）

**`backend/app/admin/schemas/node.py`** — 追加 3 个 Pydantic 类：
```python
class BulkNodeItem(CamelModel):
    name: str
    x: float
    y: float
    attrs: dict[str, Optional[str]] = Field(default_factory=dict)

class BulkNodesCreateRequest(CamelModel):
    node_type_id: str
    items: list[BulkNodeItem]

class BulkCreatedItem(CamelModel):
    index: int
    id: str
    name: str

class BulkSkippedItem(CamelModel):
    index: int
    name: Optional[str]
    reason: str

class BulkNodesCreateResponse(CamelModel):
    created: list[BulkCreatedItem]
    skipped: list[BulkSkippedItem]
```

**`backend/app/admin/node.py`** — 追加 1 个端点 `POST /topologies/{topology_id}/nodes/bulk`

### 测试新增

- `frontend/src/utils/__tests__/jsonBulkNodes.test.ts`（若项目未接 vitest，则改为在 backend 集成测试里覆盖同等语义）
- `backend/tests/test_node_bulk.py`（≥12 用例）

---

## 5. 后端端点契约

### 请求
```
POST /admin/api/topologies/{topology_id}/nodes/bulk
Content-Type: application/json

{
  "nodeTypeId": "ntype_abc123",
  "items": [
    {
      "name": "core-sw-01",
      "x": 400.0,
      "y": 300.0,
      "attrs": { "ip": "10.0.0.1", "vendor": "Cisco" }
    },
    { "name": "core-sw-02", "x": 620.0, "y": 300.0, "attrs": { "ip": "10.0.0.2" } }
  ]
}
```

### 响应
```json
{
  "code": 0,
  "data": {
    "created": [
      { "index": 0, "id": "node_xxx", "name": "core-sw-01" },
      { "index": 1, "id": "node_yyy", "name": "core-sw-02" }
    ],
    "skipped": [
      { "index": 2, "name": "core-sw-01", "reason": "批次内名称重复" }
    ]
  },
  "message": "ok"
}
```

### 前置错误（整批 4xx，不进入行级处理）
- 拓扑不存在 → 404
- 节点类型不存在 → 404
- 请求体校验失败（Pydantic 层） → 422

### 行级 skip 理由文案（用户可见）
- `"name 为空"`
- `"画布已有同名节点"`
- `"批次内名称重复"`
- `"必填字段 <fieldLabel> 缺失"`
- `"字段 <fieldLabel> 值超过最大长度 <max_length>"`

### 后端执行逻辑（沿用现有 `transaction()` context manager 模式）
```python
with transaction() as conn:
    # 1. 前置检查
    if not conn.execute("SELECT id FROM topologies WHERE id=?", (topology_id,)).fetchone():
        raise HTTPException(status_code=404,
            detail={"code": 40402, "message": "拓扑不存在"})
    if not conn.execute("SELECT id FROM node_types WHERE id=?", (req.node_type_id,)).fetchone():
        raise HTTPException(status_code=404,
            detail={"code": 40403, "message": "节点类型不存在"})

    # 2. 加载字段元数据
    field_rows = conn.execute(
        "SELECT field_key, field_label, field_type, max_length, required "
        "FROM node_type_fields WHERE node_type_id=?",
        (req.node_type_id,)
    ).fetchall()
    field_map = { r["field_key"]: r for r in field_rows }

    # 3. 预取已存在 name（同一拓扑内）
    existing_names = {
        r["name"] for r in conn.execute(
            "SELECT name FROM nodes WHERE topology_id=?", (topology_id,)
        ).fetchall()
    }

    created: list[dict] = []
    skipped: list[dict] = []
    seen_in_batch: set[str] = set()

    for idx, item in enumerate(req.items):
        name = (item.name or "").strip()
        if not name:
            skipped.append({"index": idx, "name": item.name, "reason": "name 为空"})
            continue
        if name in existing_names:
            skipped.append({"index": idx, "name": name, "reason": "画布已有同名节点"})
            continue
        if name in seen_in_batch:
            skipped.append({"index": idx, "name": name, "reason": "批次内名称重复"})
            continue

        err = _validate_attrs_for_bulk(field_map, item.attrs)
        if err:
            skipped.append({"index": idx, "name": name, "reason": err})
            continue

        node_id = _new_id()  # backend/app/admin/node.py 现有 helper
        conn.execute(
            "INSERT INTO nodes (id, topology_id, node_type_id, name, status) "
            "VALUES (?, ?, ?, ?, 'online')",
            (node_id, topology_id, req.node_type_id, name),
        )
        # 位置存 canvas_nodes 表（nodes 表无 x/y 列）
        conn.execute(
            "INSERT OR REPLACE INTO canvas_nodes (node_id, topology_id, x, y) "
            "VALUES (?, ?, ?, ?)",
            (node_id, topology_id, item.x, item.y),
        )
        for field_key, value in item.attrs.items():
            if value is None or field_key not in field_map:
                continue  # 未定义的 key 静默忽略
            conn.execute(
                "INSERT INTO node_attrs (node_id, field_key, value) VALUES (?, ?, ?)",
                (node_id, field_key, value),
            )
        created.append({"index": idx, "id": node_id, "name": name})
        seen_in_batch.add(name)

return {"code": 0, "data": {"created": created, "skipped": skipped}, "message": "ok"}
```

### `_validate_attrs_for_bulk` 语义（复用 `set_node_attrs` 规则）
```python
def _validate_attrs_for_bulk(
    field_map: dict[str, sqlite3.Row],
    attrs: dict[str, Optional[str]],
) -> Optional[str]:
    # 必填字段
    for field_key, field in field_map.items():
        if field["required"] and not attrs.get(field_key):
            return f"必填字段 {field['field_label']} 缺失"
    # text 长度
    for field_key, value in attrs.items():
        field = field_map.get(field_key)
        if not field or value is None:
            continue
        if field["field_type"] == "text":
            max_length = field["max_length"] or 255
            if len(value) > max_length:
                return f"字段 {field['field_label']} 值超过最大长度 {max_length}"
    return None
```

---

## 6. 前端数据流 & JSON 匹配语义

### `parseBulkJson(text)`
1. `JSON.parse(text)` — 语法失败 → `{ ok: false, error: '<parser msg>' }`
2. 顶层必须是数组 — 否则 → `{ ok: false, error: 'JSON 顶层必须是数组，收到 <type>' }`
3. 每项必须是 object（非 null / 非 array） — 否则 → `{ ok: false, error: '第 X, Y 项不是 object' }`
4. 通过 → `{ ok: true, items }`

### `buildBulkPreview(items, fields, nameKey, typeName, existingNames, layout)`
对每个 item 顺序处理：

**a. 抽取 name**
- `nameKey === '__auto__'` → `${typeName}_${idx+1}`
- 否则 → 用 `keyMatch(nameKey, k)` 遍历 item keys 找匹配值，转字符串
- 空/缺失 → skipped, `reason='name 为空'`

**b. 冲突检测**
- `existingNames` 已含 → skipped, `reason='画布已有同名节点'`
- `seenInBatch` 已含 → `duplicatesInBatch`

**c. 字段值匹配（复用 `jsonFieldMatch`）**
- 遍历 item 的每个 (jsonKey, jsonValue)：
  - 用 `keyMatch` 找 field
  - 找不到 field → `unmatchedKeys` 集合（去重、全局提示）
  - 找到 field → `coerceValue`
    - 失败 → `warnings.push(fieldLabel)`，该字段不填
    - 成功 → `attrs[fieldKey] = coerced.value`

**d. 必填字段兜底（前端做，后端不看 defaultValue）**
- 遍历 `fields`：
  - 若 `attrs[fieldKey]` 已有值 → 不动
  - 若无值但 `field.defaultValue` 存在 → `attrs[fieldKey] = field.defaultValue`
  - 若 `required && !attrs[fieldKey]`（默认也没值）→ skipped, `reason='必填字段 <fieldLabel> 缺失'`
- 后端 `_validate_attrs_for_bulk` 仅看提交上来的 `attrs` 字典，不再回退默认值 —— 单一职责边界

**e. 计算 x/y**
- `validIdx` = 通过校验的行在 valid 数组的序号
- `x = layout.startX + (validIdx % cols) * dx`
- `y = layout.startY + Math.floor(validIdx / cols) * dy`
- `dx = layout.dx ?? 220`，`dy = layout.dy ?? 140`

### HTTP 提交（前 → 后）
```ts
await nodeApi.bulkCreate(topologyId, {
  nodeTypeId,
  items: preview.valid.map(v => ({
    name: v.name,
    x: v.x,
    y: v.y,
    attrs: v.attrs,
  })),
})
```

---

## 7. 错误分类矩阵

| 错误类型 | 归属分组 |
|---------|---------|
| JSON 语法错误 | Modal 顶部红色 Alert（阻塞） |
| 顶层不是数组 | Modal 顶部红色 Alert |
| 数组元素不是 object | Modal 顶部红色 Alert（附索引） |
| 空数组 | Modal 顶部黄色 Alert，允许继续 |
| name 为空/缺失 | ⏭️ 将跳过 |
| 画布已有同名 | ⏭️ 将跳过 |
| 批次内重名 | ⚠️ 批次内重名（单独分组） |
| 必填字段缺失 | ⏭️ 将跳过 |
| 字段值类型不兼容 | ✅ 将导入 + 行 warning |
| 未匹配 JSON key | ❓ 全局提示 Alert |
| 后端 skipped（竞态） | 导入完成后 `Modal.info` 提示 |

---

## 8. UI 呈现

### Step 1 输入
```
┌── Modal: 批量导入 <typeName> ───────────────────┐
│                                                 │
│  名称来源 [Select ▼]  起始X [InputNumber]        │
│                        起始Y [InputNumber]        │
│  __auto__ 自动生成      每行列数 [InputNumber]    │
│  name                                            │
│  deviceName                                      │
│  ... (JSON 首条 keys)                            │
│                                                 │
│  ┌ textarea (rows=12, monospace) ─────────┐    │
│  │  [{"name":"...", "ip":"..."}, ...]     │    │
│  └─────────────────────────────────────────┘    │
│                                                 │
│                    [取消]  [解析预览] (primary)  │
└─────────────────────────────────────────────────┘
```

**动态行为：**
- 用户在 textarea 停打后 `debounce(400ms)` → `parseBulkJson` → 名称来源下拉的 options 更新为"__auto__ + 首条 keys"（若解析失败，下拉禁用）

### Step 2 预览
```
┌── Modal: 批量导入 <typeName> - 预览 ────────────┐
│                                                 │
│  ❓ JSON 中以下 key 未在字段定义里，将忽略：      │
│      region, tag, custom_note                    │
│                                                 │
│  ┌── ✅ 将导入 (12)              [▼ 展开] ──┐   │
│  │  # | Name | X | Y | attrs 摘要         │   │
│  │  0 | core-01 | 400 | 300 | ip=10.0.0.1 │   │
│  │  ...                                    │   │
│  └─────────────────────────────────────────┘   │
│  ┌── ⏭️ 将跳过 (3)               [▼ 展开] ──┐   │
│  │  # | Name | 理由                        │   │
│  │  5 | -    | name 为空                   │   │
│  └─────────────────────────────────────────┘   │
│  ┌── ⚠️ 批次内重名 (1)            [▼ 展开] ──┐   │
│  │  # | Name                                │   │
│  │  8 | core-01                             │   │
│  └─────────────────────────────────────────┘   │
│                                                 │
│         [返回编辑]         [确认导入 12 条]      │
│                            ↑ N=0 时 disabled     │
└─────────────────────────────────────────────────┘
```

### 导入完成后
- `message.success('成功导入 12 个节点')`（若 M > 0 用 warning：`成功 12，跳过 3`）
- 后端 `skipped` 非空 → `Modal.info` 展示详情
- Modal 关闭 + `fetchGraph()` → 画布刷新
- 自动 `graph.centerCell(newNodes[0])` 把视口对准第一个新节点

---

## 9. 布局默认值与边界

**网格参数：**
- `cols = 6` 默认
- `dx = 220` = `INFRA_NODE_WIDTH(200) + 20 gap`
- `dy = 140` = `INFRA_NODE_HEIGHT(120) + 20 gap`

**默认起点计算**（打开 Modal 时，此时 N 未知）：
```ts
const viewCenter = graph.pageToLocal(clientWidth/2, clientHeight/2)
const startX = Math.round(viewCenter.x - (cols * dx) / 2)
const startY = Math.round(viewCenter.y - dy)   // 固定上移 1 行，避免依赖 N
```
用户可在 Modal 里调整；解析预览后不再自动重算 —— 保持用户输入为准。

**性能守护：**
- 数组超过 500 项 → Modal 顶部 warning，允许继续但提示"性能考虑，建议分批"
- 前端预览不做分页（500 以内 Collapse+Table 足够快）

---

## 10. 测试策略

### 前端单元测试（`jsonBulkNodes.test.ts`，Vitest）
若项目未接 vitest，改为通过后端集成测试覆盖同等语义（该文件仍写，作为可选未来接入）。

- `parseBulkJson` 正常数组
- `parseBulkJson` JSON 语法错误 → error
- `parseBulkJson` 顶层是 object → error
- `parseBulkJson` 元素含 null / string → error 并附索引
- `parseBulkJson` 空数组 → `ok, items: []`
- `buildBulkPreview` 全部有效 → valid.length === N
- `buildBulkPreview` name 缺失 → 归 skipped
- `buildBulkPreview` name 与 existingNames 冲突 → 归 skipped
- `buildBulkPreview` 批次内重名 → 第一进 valid、其余进 duplicatesInBatch
- `buildBulkPreview` 必填字段缺失 → 归 skipped
- `buildBulkPreview` 字段值不兼容 → 进 valid + row warning
- `buildBulkPreview` 未匹配 key 汇总去重
- `buildBulkPreview` nameKey='__auto__' 生成 `<typeName>_1..N`
- `buildBulkPreview` nameKey='deviceName' 从 item['deviceName'] 抽取（含 keyMatch 松匹配）
- `buildBulkPreview` 网格布局坐标计算正确（第 7 项应换行）

### 后端集成测试（`backend/tests/test_node_bulk.py`，pytest + FastAPI TestClient）
- 单条正常创建 → created=1, skipped=0，DB 中有 1 行 nodes + K 行 node_attrs
- 多条正常创建 → 事务一次提交，x/y 正确写入
- 拓扑不存在 → 404
- 节点类型不存在 → 404
- 必填字段缺失 → 该行 skipped，其他行成功
- text 字段超 max_length → 该行 skipped，理由含 fieldLabel + max_length
- text 字段无 max_length → 后端 fallback 255
- 画布已有同名 → 该行 skipped
- 批次内重名 → 第一个 created，后续 skipped
- 空 items → created=0, skipped=0, HTTP 200
- items 中包含未定义的 field_key → 静默忽略、不进 node_attrs、不算错
- name 前后有空格 → 后端 `.strip()`

### 手动 E2E 清单（写入 plan，不自动化）
- TypePalette 类型卡片 hover 显示"批量导入"图标按钮
- 点击 → BulkImportNodesModal 打开，标题含类型名
- 粘贴合法 JSON → 名称来源下拉自动填充"__auto__ + 首条 keys"
- 点[解析预览] → Step 2 四分组渲染正确
- 点[确认导入] → 后端 200 → Modal 关闭 → 画布刷新出现新节点
- 新节点按 6 列网格排布、位置在视口中心附近
- 点击新节点 → NodeAttrsPanel 显示 attrs 已正确填入
- 竞态模拟：两个 tab 几乎同时导入同名节点，第二个 tab 响应含 skipped

### 回归清单
- 拖拽单节点入口 NodeAttrsModal 仍工作
- NodeAttrsModal 里"从 JSON 填充" 仍工作（复用的 `jsonFieldMatch` 未变）
- 节点组的宏节点创建仍工作
- 类型管理页 Excel 导入导出仍工作

---

## 11. 非目标 & 未来演进

**明确不做：**
- 跨类型导入（一次导入含多个 nodeTypeId）
- 文件上传 / JSONL
- 冲突时"覆盖已有节点属性"
- 从 CSV / Excel 导入（Excel 是"类型定义"通道，不是"实例数据"通道）
- 批量创建同时创建边（边靠后续在画布上手动连或用节点组的边策略）

**未来可选增强（新独立需求）：**
- 批量导入完成后自动进入"框选/组合"模式，方便一次性移动新节点
- 支持"预览时就地修改某行 name / attrs"再导入
- 导入完成后弹二级 Modal：是否为这批节点批量创建边到某个中心节点
