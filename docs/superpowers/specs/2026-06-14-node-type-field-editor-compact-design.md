# 节点/边类型字段编辑器紧凑化改造 — 设计文档

- **日期**：2026-06-14
- **范围**：
  1. 类型管理页（`TypesView.vue`）的节点类型 / 边类型 Tab — 字段定义编辑器（§1-§10）
  2. 画布上的节点/边属性编辑 — 字段值编辑器（§11）
- **不在范围**：告警模板（V2 已紧凑）；字段编辑器抽公共组件

## 1. 背景与动机

类型管理页当前对"节点类型字段"和"边类型字段"的编辑流程：

1. 进入类型列表 → 点行尾的展开图标 → 展开行渲染 `NodeTypeFieldEditor` / `EdgeTypeFieldEditor`
2. 点"添加字段"或"编辑字段"按钮 → **弹出 Modal** → 8 个表单项竖排 → 提交 → 调单字段 API（POST/PUT/DELETE `/node-types/{id}/fields/...`）→ refresh

问题：
- 每次添加/编辑字段都要弹 Modal，操作慢且打断流
- Modal 里 8 个表单项竖排，纵向占空间大
- 排序通过数字输入框（双源数据：数组顺序 vs sortOrder 列）容易混乱
- 与同页"告警模板"Tab 的字段编辑器（V2 已重写为紧凑表格 + 行内编辑）风格不一致

**目标**：将节点类型 / 边类型字段编辑改造为与告警模板一致的紧凑模式（Modal 内嵌行内可编辑表格 + 整批同步），统一类型管理页的交互语言。

## 2. 设计决策（已确认）

| # | 决策 | 选择 |
|---|------|------|
| Q1 | 字段编辑入口 | **A** — 搬进节点类型 Modal（与告警模板对齐） |
| Q2 | 节点类型列表的展开行 | **A** — 直接删除展开行 |
| Q3 | 删字段时已有 `node_attrs` 的处理 | **C** — 弹窗确认 + 影响数预扫描 |
| Q4 | 范围 | **A** — 节点类型 + 边类型同步整改，不抽公共组件 |
| Q5 | 画布字段值编辑紧凑化策略 | **B** — Modal 双列网格 + 抽屉水平 label |
| Q6 | 编辑节点抽屉宽度 | **B** — 320 → 380px |

## 3. 后端 API 变更

### 3.1 节点类型端点

| 端点 | 改动 |
|------|------|
| `POST /admin/api/node-types` | body 新增可选 `fields: NodeTypeFieldInput[]`。事务内：INSERT node_types → 批量 INSERT node_type_fields |
| `PUT /admin/api/node-types/{id}` | body 新增可选 `fields: NodeTypeFieldInput[]`。如提供 → 走 §3.3 diff 同步 |
| **新增** `POST /admin/api/node-types/{id}/fields/delete-impact` | body `{ fieldKeys: string[] }` → 返回 `[{fieldKey, affectedNodeCount}]` |
| **删除** `POST /admin/api/node-types/{id}/fields` | 单字段端点，整批同步取代 |
| **删除** `PUT /admin/api/node-types/{id}/fields/{field_id}` | 同上 |
| **删除** `DELETE /admin/api/node-types/{id}/fields/{field_id}` | 同上 |

### 3.2 边类型端点（对称）

- `POST /admin/api/edge-types` / `PUT /admin/api/edge-types/{id}` 加 `fields: EdgeTypeFieldInput[]?`
- 新增 `POST /admin/api/edge-types/{id}/fields/delete-impact`（统计 `edge_attrs`）
- 删除 3 个单字段端点（POST/PUT/DELETE）

### 3.3 整批同步 diff 算法

`field_key` 在现行实现中事实上不可变（单字段 update 端点禁止改 key），继续作为 diff 主键。

```
existing = SELECT field_key, id FROM node_type_fields WHERE node_type_id = ?
incoming = data.fields  # 来自 body，由前端提交

to_insert = [f for f in incoming if f.field_key not in {k for k in existing}]
to_update = [f for f in incoming if f.field_key in {k for k in existing}]
to_delete = [k for k in existing if k not in {f.field_key for f in incoming}]

# 事务内顺序：
#   for k in to_delete:
#       DELETE FROM node_type_fields WHERE node_type_id = ? AND field_key = k
#       DELETE FROM node_attrs WHERE field_key = k AND node_id IN (
#           SELECT id FROM nodes WHERE node_type_id = ?    -- 仅清理同类型节点的孤儿
#       )
#   for f in to_update:
#       UPDATE node_type_fields SET label/type/max_length/default_value/options/required/sort_order = ?
#       WHERE node_type_id = ? AND field_key = ?
#   for f in to_insert:
#       INSERT INTO node_type_fields (...) VALUES (...)
```

**约束/校验：**

- incoming 里 `field_key` 重复 → 400
- `field_key` 仍不可变：rename 需"删旧+加新"两步操作
- `sort_order`：服务端按数组下标重写（防止前端不传或乱传）

### 3.4 delete-impact 端点

```python
@router.post("/node-types/{type_id}/fields/delete-impact")
def get_delete_impact(type_id: str, payload: FieldDeleteImpactRequest) -> dict:
    with connect() as conn:
        items = []
        for k in payload.field_keys:
            count = conn.execute(
                """SELECT COUNT(*) FROM node_attrs a
                   JOIN nodes n ON a.node_id = n.id
                   WHERE n.node_type_id = ? AND a.field_key = ?""",
                (type_id, k),
            ).fetchone()[0]
            items.append({"field_key": k, "affected_node_count": count})
    return {"code": 0, "data": {"items": items}, "message": "ok"}
```

边类型对称：JOIN `edges` 表统计 `edge_attrs`。

### 3.5 Pydantic schema 改动

```python
# backend/app/admin/schemas/node_type.py
class NodeTypeFieldInput(CamelModel):
    """整批同步用，无 id；field_key 是稳定主键"""
    field_key: str
    field_label: str
    field_type: Literal["text", "number", "select", "boolean"]
    max_length: Optional[int] = None
    default_value: Optional[str] = None
    options: Optional[str] = None
    required: bool = False
    sort_order: int = 0

class NodeTypeCreate(CamelModel):
    # ... 现有字段不变
    fields: Optional[list[NodeTypeFieldInput]] = None

class NodeTypeUpdate(CamelModel):
    # ... 现有字段不变
    fields: Optional[list[NodeTypeFieldInput]] = None

class FieldDeleteImpactRequest(CamelModel):
    field_keys: list[str]

class FieldDeleteImpactItem(CamelModel):
    field_key: str
    affected_node_count: int
```

EdgeType 对称。

## 4. 前端组件结构

### 4.1 组件树（节点类型，边类型对称）

```
TypesView.vue（不变）
  └─ NodeTypeTable.vue（删除展开行相关代码）
      ├─ a-table（无 expandedRowRender / expandedRowKeys）
      └─ NodeTypeModal.vue（重写）
          ├─ 基础信息区（保留：code/name/category/icon/color/shape/renderMode/dnTemplate/description）
          ├─ <a-divider />
          └─ NodeTypeFieldEditor.vue（完全重写为受控紧凑表格）
              ├─ Affix 顶部工具栏（"+ 新增字段" + "X 个字段"计数）
              ├─ a-table（行内编辑控件）
              └─ 底部工具栏（"+ 新增字段"）
```

### 4.2 受控数据流

- `NodeTypeFieldEditor` 接受 `fields: NodeTypeFieldInput[]` prop + `emit('update:fields', next)`
- `NodeTypeModal` 内部 `form.fields` ref：
  - 打开（编辑）：`form.fields = deepClone(editing.fields)`
  - 打开（新建）：`form.fields = []`
  - 提交时一并放入 POST/PUT body
- 不再有"每个字段独立 API"调用
- 不再有 `useTypes.ts` 的 `createNodeTypeField/updateNodeTypeField/deleteNodeTypeField`

### 4.3 紧凑表格列定义

| 列 | 控件 | 宽度 | 说明 |
|---|------|------|------|
| Key | Input | 120 | 编辑模式下 disabled（仅新行可编辑），照搬现有 field_key 不可变约束 |
| Label | Input | 140 | |
| Type | Select | 100 | text / number / select / boolean |
| MaxLen | InputNumber | 80 | 仅 type=text 时启用 |
| Default | Input | 100 | |
| Options | Input | 120 | 仅 type=select 时启用，逗号分隔 |
| Required | Switch | 70 | |
| 操作 | ↑↓ + 删除按钮 | 100 | 排序按数组下标 |

`sort_order` 字段：前端不展示控件，提交时按数组下标统一写为 idx；后端再次重写防止前端传错。

### 4.4 删除字段的影响预扫描流程

`NodeTypeModal` 的提交流程：

```ts
async function submit() {
  const original = props.editing?.fields ?? []
  const originalKeys = new Set(original.map(f => f.fieldKey))
  const currentKeys = new Set(form.fields.map(f => f.fieldKey))
  const deletedKeys = [...originalKeys].filter(k => !currentKeys.has(k))

  if (deletedKeys.length > 0 && props.editing) {
    const impact = await nodeTypeApi.getFieldDeleteImpact(props.editing.id, deletedKeys)
    const nonEmpty = impact.items.filter(it => it.affectedNodeCount > 0)
    if (nonEmpty.length > 0) {
      const confirmed = await modalConfirm(buildImpactMessage(nonEmpty))
      if (!confirmed) return
    }
  }

  if (props.editing) {
    await nodeTypeApi.update(props.editing.id, { ...basicFields, fields: form.fields })
  } else {
    await nodeTypeApi.create({ ...basicFields, fields: form.fields })
  }
  emit('saved')
}
```

**新建节点类型时**：originalKeys 为空 → 跳过预扫描，直接 POST。

### 4.5 边类型对称改造

- `EdgeTypeModal.vue` + `EdgeTypeFieldEditor.vue` 镜像节点类型
- `EdgeTypeTable.vue` 同步删除展开行
- `useTypes.ts` 删除 `createEdgeTypeField/updateEdgeTypeField/deleteEdgeTypeField`

### 4.6 不改的部分

- `NodeTypeTable.vue` 的搜索 / 分类筛选 / 批量操作 Dropdown / Excel 导入导出 / 网管设备关联
- 节点类型字段在画布属性面板的渲染（`NodeAttrsPanel.vue`）— K-V attrs 结构不变
- 后端 Excel 导入/导出代码路径（仍直接 INSERT 到 `node_type_fields`）

## 5. 文件清单

### 后端
- `backend/app/admin/schemas/node_type.py` — 加 `fields` 到 Create/Update；新增 `NodeTypeFieldInput` / `EdgeTypeFieldInput` / `FieldDeleteImpactRequest` / `FieldDeleteImpactItem`
- `backend/app/admin/node_type.py` — 改写 `create_node_type` / `update_node_type` / `create_edge_type` / `update_edge_type`；新增私有 `_sync_node_type_fields()` / `_sync_edge_type_fields()` helper；新增 2 个 delete-impact 端点；删除 6 个单字段端点
- `backend/tests/test_node_type_field_sync.py`（新）
- `backend/tests/test_edge_type_field_sync.py`（新）

### 前端
- `frontend/src/api/types.ts` — `NodeTypeCreate/Update/EdgeTypeCreate/Update` 加 `fields?: ...[]`；新增 `getFieldDeleteImpact()` 方法；删除 `createField/updateField/deleteField`
- `frontend/src/composables/useTypes.ts` — 删除 6 个字段级方法
- `frontend/src/components/types/NodeTypeFieldEditor.vue` — 完全重写（参考 `AlarmSchemaFieldEditor.vue` 结构，去 Mapping 列）
- `frontend/src/components/types/EdgeTypeFieldEditor.vue` — 同上
- `frontend/src/components/types/NodeTypeModal.vue` — 内嵌 FieldEditor；加 `form.fields`；submit 流程加 delete-impact 预扫描；Modal 宽度 560 → 880px
- `frontend/src/components/types/EdgeTypeModal.vue` — 对称改造
- `frontend/src/components/types/NodeTypeTable.vue` — 删除 expandedRow 相关代码
- `frontend/src/components/types/EdgeTypeTable.vue` — 同上

## 6. 测试策略

### 6.1 后端 pytest（`test_node_type_field_sync.py`）

| 用例 | 覆盖点 |
|---|---|
| `test_create_node_type_with_fields` | POST 一次性带 fields → 类型 + 字段都落库 |
| `test_update_sync_fields_insert_only` | PUT 仅新增 → 旧字段不动 |
| `test_update_sync_fields_update_only` | PUT 改字段 label/type → field_key 不变，UPDATE 生效 |
| `test_update_sync_fields_delete_cleans_orphan_attrs` | PUT 删字段 + 该字段在 node_attrs 有数据 → 同时清理 node_attrs 中同类型节点的孤儿行 |
| `test_update_sync_fields_delete_keeps_other_type_attrs` | 同名 field_key 在其他 node_type 的节点 attrs 不被波及 |
| `test_update_sync_fields_duplicate_field_key_rejected` | incoming 重复 field_key → 400 |
| `test_update_omit_fields_preserves_existing` | PUT body 不含 `fields` → 字段不变 |
| `test_delete_impact_returns_affected_counts` | POST delete-impact → 每个 field_key 受影响节点数正确 |
| `test_delete_impact_empty_for_unused_field` | 未引用字段 → affectedNodeCount=0 |
| `test_legacy_single_field_endpoints_removed` | 旧 3 个端点 → 404 |

边类型对称：`test_edge_type_field_sync.py`（`node_attrs` → `edge_attrs`、`nodes` → `edges`）。

### 6.2 前端 smoke 测试（实施时人工执行）

1. 节点类型列表无展开图标；"字段数"列依然显示数量
2. 点编辑 → Modal 内字段表格预填，行内改 label 立即可见
3. 新增字段 → 行追加在表底；改 type=select → Options 列启用；改 type=text → MaxLen 列启用
4. ↑↓ 按钮排序生效；保存后刷新列表，顺序持久化
5. 删一个**未被引用**的字段 → 直接保存成功，无弹窗
6. 删一个**有节点引用**的字段 → 弹"X 个节点会清除该字段"确认 → 确认后该字段在 node_attrs 中的数据全部清除
7. 取消弹窗 → Modal 留在原态，字段未提交
8. 同名 field_key 在不同 node_type → 删 A 类型的字段不影响 B 类型节点的 attrs
9. 边类型 Tab 重复步骤 1-7
10. 告警模板 Tab 不受影响

## 7. 风险与缓解

| 风险 | 缓解 |
|---|---|
| Modal 内字段超 ~15 个时表格滚动体验差 | Modal body 设 max-height（参考 `NodeAttrsModal`），字段区独立纵向滚动；Affix 工具栏粘顶仍可点 |
| 用户改完字段忘点保存切走 → 全部丢失 | Antd Modal 默认 maskClosable=false；与告警模板一致 |
| `DELETE FROM node_attrs WHERE field_key = ?` 跨多节点性能 | 已有 `idx_node_attrs_key` 索引；万级节点无问题 |
| Excel 导入路径仍 INSERT 字段表，可能与 sync 路径并发 | 项目单进程 + WAL，事务隔离已足够 |
| 删除 3+3 个旧端点是破坏性 API 改动 | 项目内唯一消费者是前端；同 PR 改完即可（按 CLAUDE.md"不留 backwards-compat shim"） |
| delete-impact 的 field_key 列表过大 | 实际很难超过 20 个；不做特殊优化 |

## 8. 兼容性

- **数据库 schema 不变**：复用现有 `node_type_fields`、`edge_type_fields`、`node_attrs`、`edge_attrs`、`nodes`、`edges` 表
- **field_key 仍不可变**：与旧行为一致
- **Excel 导入/导出格式不变**
- **画布属性面板渲染不变**

## 9. 决策日志

| 决策 | 选项 | 选 | 理由 |
|------|------|------|------|
| 字段编辑入口 | A 搬进 Modal / B 展开行内联 / C 草稿模式 | A | 与告警模板对齐；最紧凑；不再有"双视图" |
| 列表展开行 | A 删除 / B 保留只读 | A | 信息密度高；操作路径清晰；与告警模板一致 |
| 删字段时孤儿数据 | A 直接清 / B 保留 / C 弹窗确认 | C | 与 LEGACY-07 delete-impact 风格一致；保护数据 |
| 范围 | A 节点+边同步 / B 仅节点 / C 抽公共组件 | A | 体验一致；不引入抽象债 |

## 10. 不在范围内

- 告警模板字段编辑器（V2 已紧凑，不动）
- 三套字段编辑器抽公共组件（明确放弃，避免 prop 大杂烩反模式）
- 字段拖拽排序（用 ↑↓ 即可）
- 节点字段增加 mapping_target / display_field_key（告警特有概念）
- `NodeAlarmsTab` 内的告警卡片 Collapse 布局（V1/V2 已合理）
- 拖拽调整抽屉宽度（与本次紧凑化主线无关）
- 后端 API（§11 是纯前端 UI 改造）

## 11. 画布节点字段编辑紧凑化（新增范围）

### 11.1 背景

画布上有两处节点字段值编辑：

1. **`NodeAttrsModal.vue`**（创建节点弹窗）—— 默认 Modal 宽度 520px，Form `layout="vertical"`，每字段两行（label 在上、input 在下）。字段一多就要纵向滚动。
2. **`NodeAttrsPanel.vue`**（编辑节点右侧抽屉）—— 固定 320px 宽，同样 `vertical` layout，痛点相同。

注意：本节与 §3-§10 的"字段定义编辑器"是**不同场景**：
- 类型管理编辑"字段定义"（key/label/type/maxLen/options/required/sort，多列结构）→ 适合行内表格
- 画布编辑"字段值"（label : value，一对一关系）→ 适合 Form 紧凑布局

不能复用同一组件结构。

### 11.2 NodeAttrsModal（创建节点）

- **Modal 宽度**：520 → 720px
- **Form layout**：`vertical` 改为**双列网格**（Antd Row + Col）
  - 默认：`<a-col :span="12">`，每行两个字段
  - 字段顺序：按 `node_type_fields.sort_order` 升序填充
  - 节点名称行不参与双列（保持单行宽度，因为名称是关键字段）
  - boolean 字段、超短字段也用 `span="12"`（避免特殊判断带来视觉跳动）
- **Form.Item 间距**：默认 `margin-bottom: 24px` → 紧凑 `16px`
- **响应式**：Modal 在小屏（< 720px）上 Antd 自动收缩 → 双列降级为单列（`<a-col :xs="24" :md="12">`）
- **校验/必填星号**：保持 Antd Form.Item 现有方案不变
- **节点名称必填校验 + 自动滚动**：保留现有逻辑

### 11.3 NodeAttrsPanel（编辑节点抽屉）

- **面板宽度**：320 → 380px
- **Form layout**：`vertical` 改为 **`horizontal`** + `label-col={ flex: '100px' }` + `wrapper-col={ flex: 'auto' }`
- **Form.Item 间距**：默认 `margin-bottom: 24px` → `12px`
- **节点名称行**：保持当前的"label 上、input 下"独立块（突出关键信息）
- **长 label 截断**：CSS `text-overflow: ellipsis; white-space: nowrap;` + 鼠标悬停显示完整 label（Antd Tooltip）
- **告警 Tab**：完全不动（V1/V2 已是 Collapse 列表）
- **底部按钮（删除/保存）**：保持现有 flex 固定底部

### 11.4 EdgeAttrsPanel（编辑边属性，对称改造）

- 与 `NodeAttrsPanel` 同步：320 → 380px，水平 label，紧凑间距
- 不动其他功能（语义/方向等元数据展示）

### 11.5 文件清单（追加）

**前端：**
- `frontend/src/components/canvas/NodeAttrsModal.vue` — Modal 宽度 720，字段区改双列网格 + 紧凑间距
- `frontend/src/components/canvas/NodeAttrsPanel.vue` — 面板宽度 380，Form 水平 layout + 紧凑间距 + label 截断 tooltip
- `frontend/src/components/canvas/EdgeAttrsPanel.vue` — 同 NodeAttrsPanel 改造

**无后端文件改动。**

### 11.6 测试（追加 smoke 步骤）

11. 创建节点弹窗宽度 720px，字段两列摆放（窗口窄时降级单列）
12. 字段顺序按 sort_order 填充（左到右、上到下）
13. 必填校验仍生效，scroll-to-error 功能正常
14. 编辑节点抽屉宽度 380px，字段 label 在左、input 在右
15. 长 label 截断 + 悬停 tooltip 显示完整
16. 抽屉切到告警 Tab 显示不变
17. 边属性面板与节点同款紧凑布局

### 11.7 风险（追加）

| 风险 | 缓解 |
|---|---|
| 双列网格在某些字段（如长 select 选项）拥挤 | Antd Select 默认会撑满 Col 宽度，选项面板（dropdown）独立浮层不受影响 |
| 抽屉加宽 60px 影响小屏笔记本（1366×768）的画布操作 | 380px 占 1366 屏的 27.8%，仍有 986px 画布；可接受 |
| 现有"必填字段未填 → scroll + focus"在双列网格下定位是否准确 | `querySelector('.ant-form-item-has-error')` 仍能找到 DOM 元素，无影响 |
