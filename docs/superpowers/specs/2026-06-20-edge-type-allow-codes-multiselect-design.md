# 边类型"允许源/目标类型"多选下拉化 — 设计

**日期：** 2026-06-20
**作者：** brainstorming 会话
**范围：** 仅前端，无后端变更，无数据库迁移

---

## 1. 背景与动机

类型管理 →「新建/编辑边类型」Modal 中，"允许源类型"和"允许目标类型"两个字段当前是纯文本输入框，placeholder 为 `逗号分隔，如: switch,router`。用户需要手敲节点类型的 `code`。

**实际痛点（2026-06-20 真实事故）：** 用户配置边类型 `M_VMAttachedToVolume`，目标白名单填了 `CLOUD_VM`，但实际节点类型 code 是 `CLOUD_VM_NOVA`。肉眼难分辨大小写下划线差异，画布连线时直接踩 40109 校验失败。

此外，原 `edge.py:214` 用 `json.loads()` 解析这两个字段触发 500 JSONDecodeError —— 已在前置 bugfix 修复（`split(",")` 解析），本设计在此基础上把"易选错"的根因也消除。

---

## 2. 目标

- 用户在 Modal 里通过**多选下拉 + 搜索**直接选节点类型，而非手敲 code
- 选项同时展示**中文名 + code**，搜索可匹配两者
- 编辑模式下旧数据如含"幽灵 code"（DB 里存在但当前已无对应 node_type），**显著标红提醒**，且不悄悄丢数据
- 留空 = 不限制的语义**保持不变**（向后兼容）
- **后端零改动**、**DB 不迁移**、**回滚成本为零**

## 3. 非目标

- 不动 `edge_types` 表结构
- 不动 `EdgeTypeCreate` / `EdgeTypeUpdate` Pydantic Schema（仍 `Optional[str]`）
- 不对存量数据做批量清洗/迁移（用户在编辑时手动决定是否清理 stale code）
- 不动其它使用 `node_type.code` 的功能（如导入导出 Excel）

---

## 4. 数据流

```
[EdgeTypeTable.vue]
  onMounted → nodeTypeApi.list() → nodeTypes: NodeTypeItem[]
        │
        │ :node-types
        ▼
[EdgeTypeModal.vue]
  props.nodeTypes
        │
        ├─ computed groupedNodeTypeOptions (按 category 分组 + 名称排序)
        ├─ computed validCodes (Set<string>)
        └─ <a-select mode="multiple" :options>
            v-model:value="form.allowSourceTypeCodes"  // 内部为 string[]

  加载（编辑模式）:
    form.allow*TypeCodes = (props.editing.allow*TypeCodes ?? '')
        .split(',').map(s => s.trim()).filter(Boolean)
    去重: [...new Set(parsed)]

  提交（create / update）:
    allow*TypeCodes: form.allow*TypeCodes.length
      ? form.allow*TypeCodes.join(',')
      : null
```

**存储格式不变**：DB 列仍为 `VARCHAR(500)` 逗号分隔字符串。后端 `edge.py:212-234` 已是 `split(",")` 解析，零改动。

---

## 5. UI 规格

### 5.1 选项标签格式（A 方案）

`{name} ({code})` 单行，例如 `弹性云服务器 (CLOUD_VM_NOVA)`。

### 5.2 下拉分组（B 方案）

使用 Antd `Select` 的 `options` 嵌套结构（`{ label: '<category>', options: [...] }`），渲染为 `OptGroup`：

- 组间按 `category` 字典序排
- 组内按 `name` 中文排序 (`localeCompare(b.name, 'zh-CN')`)
- 组标题就是 category 字符串（如 `cloud` / `physical` / `logical`）

### 5.3 失效 code 处理（B 方案）

`isStaleCode(code) = !validCodes.value.has(code)`。

通过 `<template #tagRender>` 自定义 tag：
- **非 stale**：默认色 tag，文本为完整 label（`{name} ({code})`）
- **stale**：`color="error"` 红色 tag，文本为 code 本身，包 `<a-tooltip title="该节点类型已不存在">`
- 两种 tag 都 `closable`，用户可主动删除

### 5.4 搜索行为

```ts
:filter-option="(input, option) =>
  String(option.label).toLowerCase().includes(input.toLowerCase())"
```

option.label 形如 `弹性云服务器 (CLOUD_VM_NOVA)`，单次匹配同时覆盖中文名和 code。

### 5.5 其它 Select 属性

| 属性 | 值 | 用途 |
|------|-----|------|
| `mode` | `"multiple"` | 多选 |
| `placeholder` | `"留空 = 不限制"` | 明确语义 |
| `:max-tag-count` | `3` | 防 Modal 撑爆 |
| `:max-tag-text-length` | `12` | 长 code 截断 |
| `allow-clear` | true | 一键清空 |
| `show-search` | true | 启用搜索 |
| `option-label-prop` | `"label"` | tag 显示完整 label |

### 5.6 留空语义（A 方案保持）

`form.allow*TypeCodes` 为空数组 → 提交 `null` → 后端 `if edge_type["allow_source_type_codes"]:` 跳过校验，任意类型可连。

---

## 6. 实现文件清单

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `frontend/src/components/types/EdgeTypeTable.vue` | 修改 | 新增 `nodeTypes` ref + `onMounted` 拉 `nodeTypeApi.list()`，通过 `:node-types` 传给 Modal |
| `frontend/src/components/types/EdgeTypeModal.vue` | 修改 | 替换两个 `<a-input>` 为 `<a-select mode="multiple">` + 新增 prop `nodeTypes` + CSV↔array 转换逻辑 + 4 个 computed/方法（`groupedNodeTypeOptions` / `validCodes` / `filterByNameOrCode` / `isStaleCode`） |

**后端、数据库、其它组件：无变更。**

---

## 7. 边界情况

| 输入 | 行为 |
|------|------|
| `null` / `""` / `",,,"` 全分隔符 | 解析为 `[]`，提交回写 `null` |
| 含重复 code（如 `"A,A,B"`） | `[...new Set(...)]` 去重 |
| 含 stale code（如 `"CLOUD_VM"`） | 保留在数组里 + 红色 tag + tooltip，用户决定是否删 |
| 新建模式（无 `props.editing`） | 初始化为 `[]`，无 stale 概念 |
| `nodeTypeApi.list()` 失败 | `nodeTypes` 为 `[]`，所有已选 code 判 stale 红色显示——明显提示但不阻塞编辑 |
| 用户手动删除 stale tag 后保存 | CSV 中不再含该 code |
| 用户未做任何改动直接保存 | CSV 原样回写（含 stale）—— 默认不主动清理 |

---

## 8. 不引入的复杂度

- ❌ 不做"一键清理所有 stale code"按钮（YAGNI，按需逐个删即可）
- ❌ 不弹"检测到 N 个失效 code"全局提示（红 tag 已足够可见）
- ❌ 不做 source 选了某类型后自动过滤 target 选项（边类型本无此约束）
- ❌ 不引入 `Select` 虚拟滚动（11 ~ 几十个类型量级 Antd 原生 OK）
- ❌ 不做 Vue Composition API 抽取公共 hook（仅两处用法、组件内 computed 足够）

---

## 9. 测试与验收

**纯前端 UI 交互，项目当前无 frontend 单测体系**，按现有惯例靠手动 smoke：

1. 新建边类型，两下拉留空 → 保存 → DB 字段 `NULL` → 画布连任意节点类型 200
2. 新建边类型，源选`云硬盘(CLOUD_VOLUME)`，目标选`弹性云服务器(CLOUD_VM_NOVA)` → 保存 → DB 存 `"CLOUD_VOLUME"` / `"CLOUD_VM_NOVA"` → 画布连线匹配方向 200，反向 400/40109
3. 搜索"弹" → 下拉仅出弹性云服务器；搜索"VOL" → 仅出云硬盘
4. 编辑 `M_VMAttachedToVolume`：目标字段里 `CLOUD_VM` 显示红 tag + hover 提示；下拉打开能正常选 `CLOUD_VM_NOVA`；点 stale tag 的 × 可删除
5. 编辑→直接保存（无改动）→ CSV 原样回写（含 stale）；编辑→删 stale → 保存 → CSV 不再含
6. 下拉里节点类型按 `category` 分组，组标题显示分类名
7. 选超过 3 个时显示 `+N 更多`

---

## 10. 兼容性 & 回滚

- **向前兼容**：旧 CSV 格式直接 `split(",")` 还原；新 UI 写出的也是同格式 CSV
- **零迁移**：DB 列不改、Schema 不改、API 契约不改
- **回滚**：单一前端 commit revert 即可，DB 数据完全不受影响
