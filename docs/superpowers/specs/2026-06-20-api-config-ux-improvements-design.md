# 接口配置页 UX 改进 — 设计

**日期：** 2026-06-20
**范围：** 仅前端，后端零改动
**Spec ID：** A（拆出 Spec B 留给"请求体 JSONPath 校验"，本 spec 不涉及）

---

## 1. 背景

接口配置页 5 个 UX 痛点，集中改一次：

1. 新建/编辑接口后整列表目录全自动折叠（治根 bug）
2. SQL 数据源的"响应模板"字段帮助信息埋在底部 hint 行不显眼
3. "参数映射"字段没有帮助，新手不懂"参数名 / 位置 / SQL 绑定名"啥关系
4. "请求规格"Collapse 面板里 请求头/Query/请求体 三段纵向铺开太长
5. 外层"启用 Query 严格白名单"Switch 和表内"必填"列概念重叠

---

## 2. 目标

| # | 痛点 | 目标 |
|---|------|------|
| 1 | 折叠重置 | 用户手动展开的目录在列表刷新后仍保持展开 |
| 2 | 响应模板帮助不显眼 | label 旁问号 tooltip，内容含占位符 + 运算符 + 注入规则 + 示例 |
| 3 | 参数映射无帮助 | 同上 pattern，含字段含义 + 错误码 + SQL 示例 |
| 4 | 请求规格太长 | Collapse 内换 Tabs（请求头 / 请求 Query / 请求体），Tab 标题带数量徽章 |
| 5 | Query 双开关重复 | 干掉外层 Switch，"表内有任意一行" = 自动启用严格模式 |

后端 schema 与 API 契约不变；DB 不迁移。

---

## 3. 非目标

- 不动 `request_spec.py` Pydantic Schema
- 不重写 `response_template.py` 引擎
- 不引入新依赖
- 不做请求体 JSONPath 校验（属于 Spec B）

---

## 4. 折叠状态保留（治痛点 1）

### 4.1 当前 bug 定位

`frontend/src/components/apis/ApiConfigTable.vue:65-130` 的 `watch([items, domains, searchKeyword])` 在 `items` 变化（新建/编辑/删除都触发）时，**无搜索词分支**直接 `collapsedGroups.value = allKeys` 整张折叠表重置为"全收起"。

### 4.2 修复方案

拆成两条独立 watch：

**Watch A（仅搜索词变化）：** 现有"匹配则展开/未匹配则折叠"逻辑保留不动。

**Watch B（items / domains 变化）：** 引入新 ref `seenKeys: Set<string>` 跟踪"已被处理过"的目录 key。
- 计算当前所有 group key（domain names + sub-categories + `'__none__'`）
- 对**新 key**（不在 `seenKeys` 内）：追加到 `collapsedGroups`（默认折叠）+ 加入 `seenKeys`
- 对**已不存在的 key**：从 `collapsedGroups` + `seenKeys` 都清理
- 已存在的 key 的折叠状态**完全不动**

伪代码：
```ts
const seenKeys = ref(new Set<string>())

watch([() => props.items, () => props.domains], () => {
  const newKeys = computeAllGroupKeys() // Set<string>
  for (const k of newKeys) {
    if (!seenKeys.value.has(k)) {
      collapsedGroups.value.add(k)
      seenKeys.value.add(k)
    }
  }
  for (const k of [...collapsedGroups.value]) {
    if (!newKeys.has(k)) {
      collapsedGroups.value.delete(k)
      seenKeys.value.delete(k)
    }
  }
}, { immediate: true })
```

### 4.3 行为对照

| 场景 | 旧 | 新 |
|------|-----|-----|
| 首次进入页面 | 全部折叠 | 全部折叠（不变） |
| 用户手动展开 A → 新建接口在 A → 列表刷新 | A 折叠（bug） | A 仍展开 |
| 新建一个全新分类 X | X 折叠（且其它也被重置） | X 默认折叠，其它不动 |
| 删除某分类 Y 下所有接口 → Y 消失 | 重置整张 | Y 从 collapsedGroups 移除 |
| 搜索关键词 | 现有匹配逻辑 | 不变 |

---

## 5. 请求规格 Tab 化（治痛点 4）

### 5.1 改动定位

`frontend/src/components/apis/ApiConfigModal.vue:816-843` 的 `<CollapsePanel key="request">` 内部。

### 5.2 布局

外层 Collapse 保留（与 `key="fault"` 异常注入面板保持一致）。内部 3 段纵向布局替换为 `<a-tabs type="card">`：

```vue
<CollapsePanel key="request" :header="requestPanelHeader">
  <a-tabs v-model:active-key="requestSpecActiveTab" type="card">
    <a-tab-pane key="header" :tab="`请求头 (${headerCount})`">
      <HeaderSpecTable v-model="formState.requestHeaders" />
    </a-tab-pane>
    <a-tab-pane key="query" :tab="`请求 Query (${queryCount})`">
      <QuerySpecTable v-model="formState.requestQuery" />
    </a-tab-pane>
    <a-tab-pane key="body" :tab="bodyTabLabel">
      <BodySpecPanel v-model="formState.requestBody" />
    </a-tab-pane>
  </a-tabs>
</CollapsePanel>
```

### 5.3 新增 computed / ref

```ts
const requestSpecActiveTab = ref<'header' | 'query' | 'body'>('header')
const headerCount = computed(() => formState.value.requestHeaders.length)
const queryCount = computed(() => formState.value.requestQuery.length)
const bodyTabLabel = computed(() =>
  formState.value.requestBody ? '请求体 ✓' : '请求体'
)
```

### 5.4 默认 Tab 选中策略

`watch(props.editing)` 内在 form reset 后追加一次 tab 选中刷新（仅在 Modal 打开时执行，不会用户切换时覆盖）：

```ts
// 在 editing 加载完成后
if (formState.value.requestHeaders.length > 0) requestSpecActiveTab.value = 'header'
else if (formState.value.requestQuery.length > 0) requestSpecActiveTab.value = 'query'
else if (formState.value.requestBody) requestSpecActiveTab.value = 'body'
else requestSpecActiveTab.value = 'header'
```

新建模式（editing=null）默认 `header`。

---

## 6. Query 严格白名单去重（治痛点 5）

### 6.1 当前的两层开关

- **外层** `ApiConfigModal.vue:821-835`：`<Switch v-model:checked="formState.requestQueryStrict">` 控制是否开启严格白名单
- **表内** `QuerySpecTable.vue:51,100-106`：每行 `required` 列控制单字段是否必填

语义本来不同（白名单 ≠ 必填），但 UI 上两个 Switch 紧挨着易混淆。

### 6.2 改动

**前端：**

1. **删除** `ApiConfigModal.vue:821-835` 整块外层 `<div class="query-strict-row">` Switch。

2. **QuerySpecTable 始终可见**：`ApiConfigModal.vue:836-839` 的 `<QuerySpecTable v-if="formState.requestQueryStrict">` 去掉 `v-if`。

3. **提交时派生**：在 ApiConfigModal 构造提交 payload 时：
   ```ts
   requestQueryStrict: formState.value.requestQuery.length > 0
   ```

4. **QuerySpecTable 文案更新**（`QuerySpecTable.vue:63`）：
   ```
   旧: "严格白名单：只要本表存在（哪怕空），调用方传入未声明字段就会被 400 拒绝..."
   新: "白名单：表中存在任意一行时，所有未声明的 query 字段会被 400 (40025) 拒绝；表空则不限制"
   ```

5. **QuerySpecTable 空状态文案补一句**（`QuerySpecTable.vue:135-139`）：
   ```
   "暂无声明 → 当前不启用白名单。添加第一行后即启用严格模式"
   ```

**后端：** 零改动。`request_spec.py` 的 `RequestSpec.requestQueryStrict: bool` 字段仍接收，由前端派生填值。

### 6.3 旧数据兼容

加载时（`watch(props.editing)`）会遇到历史组合 `requestQueryStrict=true, requestQuery=[]`。处理：

- **忽略**入参里 `requestQueryStrict` 的值，UI 完全按表里是否有行决定状态
- **提交时按行数派生**：上面的 `strict=true & 0 行` 会被回写为 `strict=false`

### 6.4 ⚠️ 可见的语义变化

历史用例"启用严格 + 零声明 query（=拒绝任何 query 字段）"会被**静默降级**为"不限制 query"。

**理由保留**此降级（不补救）：
- 此用例在当前代码库实际接口中**未发现使用**（手动 grep 验证：所有 `request.query: []` 的接口同时是 `requestQueryStrict=false`）
- 用户原始需求没要求保留该用例
- YAGNI：补救需要保留外层 Switch 或加新 UI（如"严格模式 + 零声明"按钮），增加复杂度
- 用户保存编辑现有接口时即降级，**不批量影响 DB**——只有用户主动编辑过的接口才转换

**这是一个明确记录的可见行为变化**，实施 PR 描述需注明。

---

## 7. 帮助 Tooltip 内容（治痛点 2 + 3）

### 7.1 通用规格

| 维度 | 决策 |
|------|------|
| 触发 | hover 问号图标 |
| 容器 | Antd `Tooltip`（响应模板用 `Form.Item :tooltip` 内置 prop，参数映射用现成的 `<InfoCircleOutlined>` + `<Tooltip>` 组合，与 `QuerySpecTable.vue:62-65` 一致） |
| 宽度 | `overlayStyle: { maxWidth: '420px' }` 防超宽 |
| 内容 | 10-15 行渲染函数（`h()`），允许 `<code>` 高亮 |
| 原底部 hint | **删除**响应模板原 `ApiConfigModal.vue:774-780` "占位符" hint 行（避免双信源）。**保留** `templateParseError` 错误行 + `sqlColumnNames` 查询列名行（动态状态，不重叠） |

### 7.2 响应模板 Tooltip 内容

```ts
import { h } from 'vue'

const responseTemplateTooltip = () => h('div', { style: 'font-size:12px;line-height:1.6' }, [
  h('div', { style: 'font-weight:500;margin-bottom:4px' }, '内置占位符'),
  h('div', null, [h('code', null, '{{items}}'), ' 当前页行数组 / ',
                   h('code', null, '{{total}}'), ' 总数 / ',
                   h('code', null, '{{count}}'), ' 本页行数']),
  h('div', null, [h('code', null, '{{page}}'), ' = ',
                   h('code', null, '{{pageNo}}'), ' / ',
                   h('code', null, '{{pageSize}}'), ' / ',
                   h('code', null, '{{offset}}')]),
  h('div', null, [h('code', null, '{{totalPageNo}}'), ' = ',
                   h('code', null, '{{totalPages}}'), ' / ',
                   h('code', null, '{{hasNext}}'), ' / ',
                   h('code', null, '{{hasPrev}}')]),
  h('div', null, [h('code', null, '{{uuid}}'), ' / ',
                   h('code', null, '{{now}}'), '（ISO-8601 UTC）']),
  h('div', { style: 'margin-top:6px;font-weight:500' }, '表达式（{{ }} 内可写算术）'),
  h('div', null, '+ - * / %，函数：ceil/floor/round/abs/min/max/int'),
  h('div', null, [h('code', null, '"total": "{{total + 1}}"')]),
  h('div', { style: 'margin-top:6px;font-weight:500' }, '注入规则'),
  h('div', null, [h('code', null, '"data": "{{items}}"'), ' 整串匹配 → 注入原数组（不加引号）']),
  h('div', null, [h('code', null, '"msg": "共{{total}}条"'), ' 子串 → 文本替换']),
])
```

挂载点：`ApiConfigModal.vue:761` 的 `<Form.Item label="响应模板">` 改为：

```vue
<Form.Item
  v-if="formState.dataSource === 'sql'"
  label="响应模板"
  name="responseTemplate"
  :tooltip="{ title: responseTemplateTooltip, overlayStyle: { maxWidth: '420px' } }"
>
```

### 7.3 参数映射 Tooltip 内容

```ts
const paramMappingTooltip = () => h('div', { style: 'font-size:12px;line-height:1.6' }, [
  h('div', { style: 'font-weight:500;margin-bottom:4px' }, '用途'),
  h('div', null, '把请求里 query/path/body 字段的值绑定到 SQL 的 :命名参数'),
  h('div', { style: 'margin-top:6px;font-weight:500' }, '字段说明'),
  h('div', null, [h('code', null, '参数名'), ' 请求里的字段名（如 pageNo）']),
  h('div', null, [h('code', null, '位置'), ' query / path / body（path 用 /api/{id} 的 {id}）']),
  h('div', null, [h('code', null, '类型'), ' 自动转 int/bool 失败时 → 400 + 40023']),
  h('div', null, [h('code', null, '必填'), ' 缺失时 → 400 + 40022']),
  h('div', null, [h('code', null, 'SQL 绑定名'), ' SQL 里 ', h('code', null, ':xxx'), ' 的 xxx（snake_case）']),
  h('div', { style: 'margin-top:6px;font-weight:500' }, '示例'),
  h('div', null, 'SQL: WHERE topology_id = :topology_id'),
  h('div', null, '映射: 参数名=topologyId, 位置=query, SQL 绑定名=topology_id'),
])
```

挂载点：`ParamMappingTable.vue:80` 的 `<span class="title">参数映射</span>` 改为：

```vue
<span class="title">
  参数映射
  <Tooltip :title="paramMappingTooltip" :overlay-style="{ maxWidth: '420px' }">
    <InfoCircleOutlined class="info-icon" />
  </Tooltip>
</span>
```

（`InfoCircleOutlined` + `Tooltip` 已在该文件其它表头使用过同款 import 模式，参考 `QuerySpecTable.vue:2-3`）

---

## 8. 改动文件清单

| 文件 | 涉及节 | 变更要点 |
|------|-------|---------|
| `frontend/src/components/apis/ApiConfigTable.vue` | §4 | 拆 watch + `seenKeys` ref |
| `frontend/src/components/apis/ApiConfigModal.vue` | §5, §6.2, §7.2 | Tab 化 + 删外层 Query Switch + 提交派生 strict + 响应模板 tooltip + 删原 hint |
| `frontend/src/components/apis/QuerySpecTable.vue` | §6.2 | 文案更新（tooltip + 空状态），始终可见 |
| `frontend/src/components/apis/ParamMappingTable.vue` | §7.3 | 参数映射 tooltip |

**后端：零改动。DB：零迁移。**

---

## 9. 测试与验收

**纯前端 UI 交互，无单测**（项目惯例）。手动 smoke 清单：

### 9.1 折叠保留
1. 首次进入页面 → 全部目录默认折叠
2. 手动展开域 A → 新建接口落在域 A → 列表刷新 → 域 A 仍展开
3. 手动展开域 A → 编辑域 A 中某接口 → 保存 → 域 A 仍展开
4. 手动展开域 A → 删除域 A 中某接口 → 域 A 仍展开
5. 新建接口创建出新分类 X → X 默认折叠（其它目录用户状态不动）
6. 搜索关键词触发"自动展开匹配目录" → 不动用户原状态（旧逻辑保留）

### 9.2 请求规格 Tab
7. 编辑一个有 3 headers / 2 queries / 1 body 的接口 → Tab 标题分别显示 `请求头 (3)` / `请求 Query (2)` / `请求体 ✓`
8. 切 Tab → 数据不丢；切回前一 Tab → 之前的输入保留
9. 编辑模式自动定位到第一个有数据的 Tab（验证：headers=0, queries=3 → 应停在 query Tab）

### 9.3 Query 去重
10. 新接口 → Tab "请求 Query" 显示空表 + 空态文案"添加第一行后即启用严格模式"
11. 加一行 query 声明 → 保存 → curl 调用未声明 query 字段 → 400 + 40025
12. 删完所有行 → 保存 → curl 任意 query 都通过
13. **旧数据兼容**：编辑历史接口（`requestQueryStrict=true & requestQuery=[]`）→ Tab 标题 `请求 Query (0)`，表为空；保存 → DB 中 `requestQueryStrict` 变 `false`（接受此降级）

### 9.4 Tooltip
14. 响应模板 label 旁出现内置问号图标（Antd 自带），hover → 卡片含 4 类内容（占位符/表达式/注入规则/示例），格式正确含 `<code>`
15. 参数映射标题旁出现 `<InfoCircleOutlined>` 图标，hover → 卡片含用途 + 字段含义 + SQL 示例
16. 响应模板**底部不再有** "占位符：{{items}}..." 那行 hint
17. 响应模板**仍保留** "JSON 解析失败" 错误行 + "查询列名" 提示行（验证动态状态未被误删）

---

## 10. 兼容性 / 回滚

- **后端契约不变**：旧前端版本 + 新前端版本可任意切换
- **DB 不迁移**
- **唯一可见变化**：§6.4 描述的"严格 + 零声明 → 降级为不限制"，已记录
- **回滚**：单一前端 PR revert 即可

---

## 11. 风险与已决问题

- ✅ Tab 切换后未提交数据会丢吗？**不会**——每个 Tab 内组件都用 `v-model` 双向绑到 `formState`，Tab 切换只切显示不重建组件
- ✅ Tab 数量徽章会卡顿吗？**不会**——`computed` 缓存，只在 length 变化时重算
- ✅ tooltip 渲染函数性能？**OK**——每个 Modal 实例只有 1 个 hover 监听
- ⚠️ §6.4 静默降级 —— 实施 PR 描述需明确写出该行为变化
