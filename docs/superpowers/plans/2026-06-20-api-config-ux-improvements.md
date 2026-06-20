# 接口配置页 UX 改进 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修接口配置页 5 项 UX 痛点：折叠状态保留 + 请求规格 Tab 化 + Query 白名单去重 + 响应模板/参数映射 tooltip。

**Architecture:** 纯前端 4 文件改动，后端零修改、DB 零迁移。每 Task 单一职责，可独立 commit / 独立 review。

**Tech Stack:** Vue 3.5 `<script setup>` + Ant Design Vue 4（`Tabs` + `Tooltip` + `Form.Item :tooltip` + `Switch`）+ TypeScript。

**Spec：** `docs/superpowers/specs/2026-06-20-api-config-ux-improvements-design.md`

---

## File Structure

| 文件 | Task | 责任 |
|------|------|------|
| `frontend/src/components/apis/ApiConfigTable.vue` | T1 | 折叠状态保留（拆 watch + `seenKeys`） |
| `frontend/src/components/apis/ApiConfigModal.vue` | T2/T3/T4 | 删外层 Query Switch + 派生 strict + Tabs 化 + 响应模板 tooltip + 删原 hint |
| `frontend/src/components/apis/QuerySpecTable.vue` | T2 | 始终可见 + 文案更新 |
| `frontend/src/components/apis/ParamMappingTable.vue` | T4 | 参数映射 tooltip |

---

## 工作环境约定

- 主仓直接工作：`C:/Users/benerlord/Desktop/InterfaceTest`（不开 worktree）
- 分支：`main`
- 每 Task 完成跑 `cd /c/Users/benerlord/Desktop/InterfaceTest/frontend && npx tsc --noEmit`，必须 exit 0
- 前端无单测体系，验证靠 tsc + Task 5 手动 smoke
- Task 顺序有依赖：T2 删除外层 Query Switch + 始终可见 → T3 Tab 化 → T4 tooltip 各自独立但都在 ApiConfigModal

---

## Task 1: 折叠状态保留

**Files:**
- Modify: `frontend/src/components/apis/ApiConfigTable.vue`

**目标：** 用户手动展开的目录在列表刷新后保留展开状态，仅新出现的目录默认折叠。

- [ ] **Step 1：定位现有 watch**

读 `frontend/src/components/apis/ApiConfigTable.vue` 第 50-130 行，确认当前结构：
- 第 50 行：`const collapsedGroups = ref(new Set<string>())`
- 第 63-130 行：`watch([items, domains, searchKeyword], ...)` 单一 watch 处理两件事

- [ ] **Step 2：新增 seenKeys ref**

在第 50 行 `collapsedGroups` 之后新增：

```ts
// 已被处理过的目录 key（用于区分"新出现"vs"已存在"）
const seenKeys = ref(new Set<string>())
```

- [ ] **Step 3：替换 watch（拆成两条）**

删除现有第 63-130 行整段 watch（含其上 `// Auto-collapse all groups by default whenever items or domains change` 注释和 `// When searching, expand groups that contain matching results` 注释），替换为：

```ts
// 计算当前快照下所有目录 key（domain names + sub-categories + '__none__'）
function computeAllGroupKeys(): Set<string> {
  const keys = new Set<string>()
  const domainKeys = new Set(props.domains.map(d => d.name))
  for (const dk of domainKeys) keys.add(dk)

  const subGroupKeysByDomain = new Map<string, Set<string>>()
  for (const d of props.domains) subGroupKeysByDomain.set(d.id, new Set())

  for (const api of props.items) {
    const dId = api.domainId || null
    const cat = api.category
    if (dId && cat && cat !== props.domains.find(d => d.id === dId)?.name) {
      subGroupKeysByDomain.get(dId)?.add(cat)
    }
  }
  for (const set of subGroupKeysByDomain.values()) {
    for (const sg of set) keys.add(sg)
  }
  keys.add('__none__')
  return keys
}

// Watch A：仅 items / domains 变化 → 增量补默认折叠 + 清理已消失的 key
watch(
  [() => props.items, () => props.domains],
  () => {
    const newKeys = computeAllGroupKeys()
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
  },
  { immediate: true },
)

// Watch B：仅搜索词变化 → 匹配的展开，未匹配的折叠（不影响 seenKeys）
watch(searchKeyword, () => {
  const kw = searchKeyword.value.trim().toLowerCase()
  const domainKeys = new Set(props.domains.map(d => d.name))
  const subGroupKeysByDomain = new Map<string, Set<string>>()
  for (const d of props.domains) {
    subGroupKeysByDomain.set(d.id, new Set())
  }
  for (const api of props.items) {
    const dId = api.domainId || null
    const cat = api.category
    if (dId && cat && cat !== props.domains.find(d => d.id === dId)?.name) {
      subGroupKeysByDomain.get(dId)?.add(cat)
    }
  }

  if (!kw) return // 清空搜索词时不重置（保留用户折叠状态）

  const hasDomainMatch = new Map<string, boolean>()
  const hasSubGroupMatch = new Map<string, boolean>()
  for (const dk of domainKeys) hasDomainMatch.set(dk, false)

  for (const api of props.items) {
    if (!api.name.toLowerCase().includes(kw) && !api.path.toLowerCase().includes(kw)) continue
    const dk = api.domainName || null
    const cat = api.category
    if (dk && domainKeys.has(dk)) {
      if (!cat || cat === dk) {
        hasDomainMatch.set(dk, true)
      } else {
        hasSubGroupMatch.set(`${dk}::${cat}`, true)
      }
    }
  }

  for (const dk of domainKeys) {
    const subKeys = subGroupKeysByDomain.get(props.domains.find(d => d.name === dk)?.id || '') || new Set()
    const anySubMatch = [...subKeys].some(sg => hasSubGroupMatch.get(`${dk}::${sg}`))
    if (hasDomainMatch.get(dk) || anySubMatch) {
      collapsedGroups.value.delete(dk)
    } else {
      collapsedGroups.value.add(dk)
    }
    for (const sg of subKeys) {
      if (hasSubGroupMatch.get(`${dk}::${sg}`)) {
        collapsedGroups.value.delete(sg)
      } else {
        collapsedGroups.value.add(sg)
      }
    }
  }
})
```

注意：保留 Watch B 的"清空搜索词不重置"语义（`if (!kw) return`），与旧逻辑相比这是一个**小行为变化**：清空搜索词后用户原来手动展开/折叠的状态会保留，而旧逻辑会全部重置为折叠（旧逻辑这部分本质也是 bug 的一部分，符合 spec 整体意图）。

- [ ] **Step 4：类型检查**

```bash
cd /c/Users/benerlord/Desktop/InterfaceTest/frontend && npx tsc --noEmit
```

Expected: exit 0

- [ ] **Step 5：提交**

```bash
cd /c/Users/benerlord/Desktop/InterfaceTest && git add frontend/src/components/apis/ApiConfigTable.vue && git commit -m "$(cat <<'EOF'
fix(apis): 接口列表目录折叠状态在刷新后保留

拆 watch：items/domains 变化时仅为新出现的目录补默认折叠 + 清理
消失的 key；搜索词变化走独立逻辑（清空搜索不重置）。修复新建/
编辑接口后整列表自动全折叠的 bug。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: 删除外层 Query 白名单 Switch + QuerySpec 始终可见 + 派生 strict

**Files:**
- Modify: `frontend/src/components/apis/ApiConfigModal.vue`
- Modify: `frontend/src/components/apis/QuerySpecTable.vue`

**目标：** 去除"启用 Query 严格白名单"外层 Switch，改为"表里有任何一行 = 自动启用严格"。后端契约不变，提交时派生 `requestQueryStrict` 字段值。

- [ ] **Step 1：删除外层 Query Switch（模板）**

读 `frontend/src/components/apis/ApiConfigModal.vue` 第 819-841 行（请求规格 Collapse 内）。当前结构：

```vue
<HeaderSpecTable v-model="formState.requestHeaders" />

<div class="query-strict-row">
  <span class="query-strict-label">启用 Query 严格白名单</span>
  <Switch
    v-model:checked="formState.requestQueryStrict"
    checked-children="启用"
    un-checked-children="未启用"
  />
  <span class="hint hint-inline">
    {{
      formState.requestQueryStrict
        ? '启用后未声明的 query 字段会被 400 + 40025 拒绝（即使本表为空）'
        : '未启用：调用方可传任意 query；启用后转为白名单语义'
    }}
  </span>
</div>
<QuerySpecTable
  v-if="formState.requestQueryStrict"
  v-model="formState.requestQuery"
/>

<BodySpecPanel v-model="formState.requestBody" />
```

替换为：

```vue
<HeaderSpecTable v-model="formState.requestHeaders" />

<QuerySpecTable v-model="formState.requestQuery" />

<BodySpecPanel v-model="formState.requestBody" />
```

即：删除整段 `<div class="query-strict-row">` Switch + 去除 QuerySpecTable 上的 `v-if`。

- [ ] **Step 2：修改提交派生（buildConfig 函数）**

定位 `ApiConfigModal.vue` 第 433-436 行：

```ts
  if (formState.value.requestQueryStrict) {
    // 即使 query 数组为空也写入：[] 表示"严格模式 + 零 query 允许"
    request.query = formState.value.requestQuery
  }
```

替换为：

```ts
  if (formState.value.requestQuery.length > 0) {
    request.query = formState.value.requestQuery
  }
```

- [ ] **Step 3：修改面板 header 文案**

定位 `ApiConfigModal.vue` 第 475-477 行（`requestPanelHeader` computed 内）：

```ts
  if (formState.value.requestQueryStrict) {
    parts.push(`query 严格 ${formState.value.requestQuery.length}`)
  }
```

替换为：

```ts
  if (formState.value.requestQuery.length > 0) {
    parts.push(`query 严格 ${formState.value.requestQuery.length}`)
  }
```

- [ ] **Step 4：删除已废弃的 query-strict-row CSS**

定位 `ApiConfigModal.vue` 的 `<style scoped>` 段中名为 `.query-strict-row`、`.query-strict-label`、`.hint-inline`（仅本场景使用）的样式块。如果 `.hint-inline` 在其它地方被引用则保留，否则删除。

操作步骤：
1. 在文件搜索 `.query-strict-row` → 删除该 class 及其所有 CSS 规则
2. 搜索 `.query-strict-label` → 删除
3. 搜索 `.hint-inline` → 如果只出现在 `<style>` 段（不在 template 其它地方），删除；如有其它使用则保留

- [ ] **Step 5：更新 QuerySpecTable tooltip 文案**

定位 `frontend/src/components/apis/QuerySpecTable.vue` 第 63 行：

```vue
        <Tooltip title="严格白名单：只要本表存在（哪怕空），调用方传入未声明字段就会被 400 拒绝（错误码 40025）。如要允许任意 query，移除整段声明。">
```

替换为：

```vue
        <Tooltip title="白名单：表中存在任意一行时，所有未声明的 query 字段会被 400 (40025) 拒绝；表空则不限制。">
```

- [ ] **Step 6：更新 QuerySpecTable 空状态文案**

定位 `QuerySpecTable.vue` 第 135-139 行：

```vue
      <template #emptyText>
        <span style="color: #999; font-size: 12px">
          暂无声明 query 参数，点击右上"新增 Query 参数"
        </span>
      </template>
```

替换为：

```vue
      <template #emptyText>
        <span style="color: #999; font-size: 12px">
          暂无声明 → 当前不启用白名单。添加第一行后即启用严格模式
        </span>
      </template>
```

- [ ] **Step 7：类型检查**

```bash
cd /c/Users/benerlord/Desktop/InterfaceTest/frontend && npx tsc --noEmit
```

Expected: exit 0

- [ ] **Step 8：提交**

```bash
cd /c/Users/benerlord/Desktop/InterfaceTest && git add frontend/src/components/apis/ApiConfigModal.vue frontend/src/components/apis/QuerySpecTable.vue && git commit -m "$(cat <<'EOF'
feat(apis): 去除外层 Query 严格白名单 Switch

QuerySpecTable 始终可见，提交时按 requestQuery.length>0 派生
requestQueryStrict 字段，后端契约不变。表内 tooltip / 空状态文
案同步更新。

⚠️ 行为变化：历史"严格=true & 0 行声明"组合（拒绝任何 query
字段）保存后会被静默降级为"不限制"。该用例在当前 DB 中未发现
实际使用，符合 YAGNI。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: 请求规格 Tab 化

**Files:**
- Modify: `frontend/src/components/apis/ApiConfigModal.vue`

**目标：** 把请求规格 Collapse 内三段（Header / Query / Body）从纵向铺开改成 Tabs 切换，每 Tab 标题带数量徽章。

- [ ] **Step 1：新增 Tab 状态 ref + computed**

读 `ApiConfigModal.vue` 第 1-20 行的 import 区。当前已 import `Tabs` 是否需要确认 —— 实际项目大概率从 `ant-design-vue` 用过 Tabs，但本文件若未引入需补充。

定位现有 import 区，检查是否包含 `Tabs`：
```bash
grep -n "Tabs\b" /c/Users/benerlord/Desktop/InterfaceTest/frontend/src/components/apis/ApiConfigModal.vue
```

如未引入，在 `import { ... } from 'ant-design-vue'` 内补 `Tabs` 和 `TabPane`。Antd Vue 4 可用 `<a-tabs>` / `<a-tab-pane>` 直接 kebab-case 标签（自动注册），所以**通常无需 import**——保持现状即可，如 tsc 报错再补。

定位 `requestPanelHeader` computed（约第 470 行）所在的脚本区，在其前后新增：

```ts
const requestSpecActiveTab = ref<'header' | 'query' | 'body'>('header')

const headerCount = computed(() => formState.value.requestHeaders.length)
const queryCount = computed(() => formState.value.requestQuery.length)
const bodyTabLabel = computed(() =>
  formState.value.requestBody ? '请求体 ✓' : '请求体',
)
```

注意：`ref` 已在文件顶部 import，无需新增；`computed` 已 import。如未 import 需补：检查文件顶部 `import { ref, computed, watch } from 'vue'` 应已包含。

- [ ] **Step 2：替换请求规格 Collapse 内部布局**

Task 2 完成后，第 819-841 行附近的请求规格内部应是：

```vue
        <Collapse :bordered="false" class="fault-collapse">
          <CollapsePanel key="request" :header="requestPanelHeader">
            <div class="request-spec-stack">
              <HeaderSpecTable v-model="formState.requestHeaders" />
              <QuerySpecTable v-model="formState.requestQuery" />
              <BodySpecPanel v-model="formState.requestBody" />
            </div>
          </CollapsePanel>
```

把 `<div class="request-spec-stack">` 及其内部三个组件，替换为 Tabs：

```vue
        <Collapse :bordered="false" class="fault-collapse">
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

- [ ] **Step 3：编辑模式下设置默认 Tab**

定位 `ApiConfigModal.vue` 的 `watch(() => props.apiId, ...)` 编辑加载逻辑（搜索 `props.apiId` 找到对应的 watch；该 watch 把 cfg 反向映射到 `formState`，例如第 240-280 行附近）。在该 watch 内、`formState.value` 赋值**完成之后**追加：

```ts
    // Tab 默认选中：第一个有数据的；都没有则 header
    if (formState.value.requestHeaders.length > 0) {
      requestSpecActiveTab.value = 'header'
    } else if (formState.value.requestQuery.length > 0) {
      requestSpecActiveTab.value = 'query'
    } else if (formState.value.requestBody) {
      requestSpecActiveTab.value = 'body'
    } else {
      requestSpecActiveTab.value = 'header'
    }
```

新建模式（无 props.apiId）由于初始化时 `requestSpecActiveTab` 已是 `'header'`，无需额外处理。

- [ ] **Step 4：清理已废弃的 request-spec-stack CSS**

定位 `<style scoped>` 段中 `.request-spec-stack` 样式块，删除（替换为 Tabs 后此 class 已不存在于 template）。

- [ ] **Step 5：类型检查**

```bash
cd /c/Users/benerlord/Desktop/InterfaceTest/frontend && npx tsc --noEmit
```

Expected: exit 0

如出现 `Tabs` / `TabPane` 类型错误，在 import 区补：

```ts
import { Tabs } from 'ant-design-vue'
// TabPane 通过 Tabs.TabPane 访问，或直接用 kebab-case 模板自动注册
```

- [ ] **Step 6：提交**

```bash
cd /c/Users/benerlord/Desktop/InterfaceTest && git add frontend/src/components/apis/ApiConfigModal.vue && git commit -m "$(cat <<'EOF'
feat(apis): 请求规格内 Header/Query/Body 改 Tabs 切换

外层 Collapse 保留（与 fault 风格一致），内层 3 段从纵向铺开改
为 Tabs（type=card），Tab 标题带数量徽章/状态标记。编辑模式自
动定位到第一个有数据的 Tab。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: 响应模板 + 参数映射两个 tooltip

**Files:**
- Modify: `frontend/src/components/apis/ApiConfigModal.vue`
- Modify: `frontend/src/components/apis/ParamMappingTable.vue`

**目标：** 给两个字段加 hover 帮助卡片。响应模板用 Form.Item 内置 `:tooltip` prop；参数映射用 `<InfoCircleOutlined>` + `<Tooltip>` 组合（与 QuerySpecTable 一致）。

- [ ] **Step 1：ApiConfigModal 顶部 import h**

定位 `ApiConfigModal.vue` 的 `import { ... } from 'vue'`，确保 `h` 已 import。若未引入则添加：

```ts
import { ref, computed, watch, h } from 'vue'
```

注意：实际现有的 import 可能不含 `h`，需要按当前内容补充而非替换全部。

- [ ] **Step 2：新增 responseTemplateTooltip 渲染函数**

在 `ApiConfigModal.vue` script 区适当位置（建议靠近 `templateParseError` computed 附近，约第 459 行后）新增：

```ts
const responseTemplateTooltip = () => h('div', { style: 'font-size:12px;line-height:1.6' }, [
  h('div', { style: 'font-weight:500;margin-bottom:4px' }, '内置占位符'),
  h('div', null, [
    h('code', null, '{{items}}'), ' 当前页行数组 / ',
    h('code', null, '{{total}}'), ' 总数 / ',
    h('code', null, '{{count}}'), ' 本页行数',
  ]),
  h('div', null, [
    h('code', null, '{{page}}'), ' = ',
    h('code', null, '{{pageNo}}'), ' / ',
    h('code', null, '{{pageSize}}'), ' / ',
    h('code', null, '{{offset}}'),
  ]),
  h('div', null, [
    h('code', null, '{{totalPageNo}}'), ' = ',
    h('code', null, '{{totalPages}}'), ' / ',
    h('code', null, '{{hasNext}}'), ' / ',
    h('code', null, '{{hasPrev}}'),
  ]),
  h('div', null, [
    h('code', null, '{{uuid}}'), ' / ',
    h('code', null, '{{now}}'), '（ISO-8601 UTC）',
  ]),
  h('div', { style: 'margin-top:6px;font-weight:500' }, '表达式（{{ }} 内可写算术）'),
  h('div', null, '+ - * / %，函数：ceil/floor/round/abs/min/max/int'),
  h('div', null, [h('code', null, '"total": "{{total + 1}}"')]),
  h('div', { style: 'margin-top:6px;font-weight:500' }, '注入规则'),
  h('div', null, [h('code', null, '"data": "{{items}}"'), ' 整串匹配 → 注入原数组（不加引号）']),
  h('div', null, [h('code', null, '"msg": "共{{total}}条"'), ' 子串 → 文本替换']),
])
```

- [ ] **Step 3：在响应模板 Form.Item 加 tooltip**

定位 `ApiConfigModal.vue` 第 759-763 行：

```vue
        <Form.Item
          v-if="formState.dataSource === 'sql'"
          label="响应模板"
          name="responseTemplate"
        >
```

替换为：

```vue
        <Form.Item
          v-if="formState.dataSource === 'sql'"
          label="响应模板"
          name="responseTemplate"
          :tooltip="{ title: responseTemplateTooltip, overlayStyle: { maxWidth: '420px' } }"
        >
```

- [ ] **Step 4：删除原底部 hint 占位符行**

定位 `ApiConfigModal.vue` 第 774-777 行：

```vue
          <div v-else class="hint" v-pre>
            占位符：{{items}} / {{total}} / {{page}} 或 {{pageNo}} / {{pageSize}} / {{uuid}} / {{now}}。
            整串匹配（如 "data": "{{items}}"）注入原值保持数组/对象类型；子串匹配做文本替换。留空走默认模板。
          </div>
```

**整段删除**（4 行）。

**保留**第 771-773 行 `<div v-if="templateParseError" class="hint hint-error">` 和第 778-780 行 `<div v-if="sqlColumnNames.length > 0" class="hint hint-columns">`——这两个是动态状态提示，与 tooltip 不重叠。

删除后该 Form.Item 内部应只剩：
```vue
          <Input.TextArea ... />
          <div v-if="templateParseError" class="hint hint-error">
            JSON 解析失败：{{ templateParseError }}
          </div>
          <div v-if="sqlColumnNames.length > 0" class="hint hint-columns">
            查询列名（snake_case）：{{ columnNamesHint }}
          </div>
```

- [ ] **Step 5：ParamMappingTable 加 tooltip**

读 `frontend/src/components/apis/ParamMappingTable.vue`。当前 import 区（第 1-4 行）：

```ts
import { Table, Input, AutoComplete, Select, Switch, Button, Space } from 'ant-design-vue'
import { PlusOutlined, DeleteOutlined } from '@ant-design/icons-vue'
import { computed } from 'vue'
```

替换为（加 `Tooltip` + `InfoCircleOutlined` + `h`）：

```ts
import { Table, Input, AutoComplete, Select, Switch, Button, Space, Tooltip } from 'ant-design-vue'
import { PlusOutlined, DeleteOutlined, InfoCircleOutlined } from '@ant-design/icons-vue'
import { computed, h } from 'vue'
```

- [ ] **Step 6：定义 paramMappingTooltip 渲染函数**

在 `ParamMappingTable.vue` 的 `defineProps`/`defineEmits` 块之后（约第 30 行附近），新增：

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

- [ ] **Step 7：模板加图标 + Tooltip**

定位 `ParamMappingTable.vue` 第 80 行：

```vue
      <span class="title">参数映射</span>
```

替换为：

```vue
      <span class="title">
        参数映射
        <Tooltip :title="paramMappingTooltip" :overlay-style="{ maxWidth: '420px' }">
          <InfoCircleOutlined class="info-icon" />
        </Tooltip>
      </span>
```

- [ ] **Step 8：补充 info-icon CSS**

定位 `ParamMappingTable.vue` 的 `<style scoped>` 段（约第 161 行后），在 `.title { ... }` 规则之后新增（参考 QuerySpecTable.vue:167-171 同款）：

```css
.title {
  font-weight: 500;
  color: #595959;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.info-icon {
  color: #8c8c8c;
  font-size: 13px;
  cursor: help;
}
```

注意：原 `.title` 没有 `display: inline-flex`，需更新整个 `.title` 规则（保留原 `font-weight`/`color`，新增 `display`/`align-items`/`gap`），不要只 append `.info-icon`。

- [ ] **Step 9：类型检查**

```bash
cd /c/Users/benerlord/Desktop/InterfaceTest/frontend && npx tsc --noEmit
```

Expected: exit 0

- [ ] **Step 10：提交**

```bash
cd /c/Users/benerlord/Desktop/InterfaceTest && git add frontend/src/components/apis/ApiConfigModal.vue frontend/src/components/apis/ParamMappingTable.vue && git commit -m "$(cat <<'EOF'
feat(apis): 响应模板/参数映射加帮助 tooltip

响应模板用 Form.Item :tooltip prop（自带问号图标），内容含占位
符 + 表达式语法 + 函数白名单 + 注入规则示例；同时删除底部已重
复的"占位符"hint 行。参数映射用 InfoCircleOutlined + Tooltip
组合（与 QuerySpecTable 一致），内容含字段含义 + 错误码 + SQL
示例。两个 tooltip 内容用 h() 渲染函数支持 <code> 高亮。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: 完整 smoke 验收

**Files:** 无代码改动，仅手动测试。

任一步骤失败 → 回到对应 Task 修复后重做本 Task。

- [ ] **Step 1：启动后端 + 前端**

```bash
cd /c/Users/benerlord/Desktop/InterfaceTest/backend && python -m app.main &
cd /c/Users/benerlord/Desktop/InterfaceTest/frontend && npm run dev
```

浏览器开 http://localhost:5173 → 接口管理。

- [ ] **Step 2：折叠保留 — 编辑后保留展开**

手动展开某个域 A → 编辑域 A 中任一接口（如改个 description）→ 保存。预期：域 A 仍展开（不被自动折叠）。

- [ ] **Step 3：折叠保留 — 新建接口落入展开目录**

展开域 A → 在 A 下新建一个接口（设 `domainId` 选 A）→ 保存。预期：域 A 仍展开，新接口可见。

- [ ] **Step 4：折叠保留 — 新分类默认折叠**

新建一个接口设 `category='SmokeTest'`（一个全新的分类名，不在已有任何域下用过）→ 保存。预期：原本展开的目录保持展开，但 `SmokeTest` 分类默认折叠（需用户主动点开）。

- [ ] **Step 5：折叠保留 — 搜索后清空不重置**

随便手动展开 1-2 个目录 → 在搜索框输入"xxx"过滤一下 → 清空搜索框。预期：之前手动展开的目录仍为展开状态（旧 bug 会全收起）。

- [ ] **Step 6：请求规格 Tab — 数量徽章正确**

编辑一个已有 headers/query/body 配置的接口（例如已有 3 个 headers）。预期：请求规格 Collapse 展开后 3 个 Tab 标题分别显示 `请求头 (3)` / `请求 Query (N)` / `请求体 ✓` 或 `请求体`（取决于配置）。

- [ ] **Step 7：请求规格 Tab — 切换不丢数据**

在 Query Tab 加一行声明（不点保存）→ 切到 Header Tab → 改个 header → 切回 Query Tab。预期：刚才加的 query 行还在；header 改动也还在。

- [ ] **Step 8：请求规格 Tab — 编辑模式自动定位**

打开一个只配置了 body 的接口（headers=0, queries=0, body 非空）。预期：Collapse 展开后默认停在 `请求体` Tab。

- [ ] **Step 9：Query 去重 — 表内有行 → 严格生效**

新建接口 → 加一行 query 声明（如 name=`pageNo`, type=int, required=false）→ 保存。然后调用该 mock 接口传一个未声明的 query（如 `?unknownField=x`）：

```bash
curl -i "http://127.0.0.1:8080/<mock_path>?pageNo=1&unknownField=x"
```

预期：400 + `{"code": 40025, ...}`。

- [ ] **Step 10：Query 去重 — 表空 → 不限制**

编辑刚才的接口 → 删完所有 query 行 → 保存。再次 curl 传任意 query：

```bash
curl -i "http://127.0.0.1:8080/<mock_path>?anything=ok"
```

预期：通过，不返回 40025。

- [ ] **Step 11：Query 去重 — 旧数据兼容**

如果有历史接口配置了 `strict=true & query=[]`（"严格 + 零声明"），编辑该接口 → 不改任何内容直接保存。预期：DB 中该接口的 `requestQueryStrict` 字段被回写为 `false`（行为降级），后续调用任意 query 都放行。

API 校验：
```bash
curl -s "http://127.0.0.1:8080/admin/api/api-configs/<id>" | python -c "import sys,json; d=json.load(sys.stdin)['data']; print(json.dumps(d.get('config',{}).get('request',{}), indent=2))"
```
预期：响应中 `request` 段不含 `query` 字段（因为派生 strict=false 时 buildConfig 跳过写入）。

- [ ] **Step 12：响应模板 tooltip — 内容正确**

编辑一个 dataSource='sql' 的接口 → 响应模板 label 旁有 Antd 自带问号图标 → hover → 卡片宽度 ≤ 420px，含 4 段：内置占位符 / 表达式 / 注入规则 / 示例，含 `<code>` 灰底高亮（如 `{{items}}`）。

- [ ] **Step 13：响应模板 — 原底部 hint 已删但动态提示保留**

仍在同一接口编辑界面，响应模板 textarea 下方：
- ❌ 不再有 `占位符：{{items}} / {{total}} ...` 那段文字
- ✅ 如果 textarea 内是非法 JSON，仍有 `JSON 解析失败：...`
- ✅ 如果之前在 SqlRunner 跑过 SQL 提取了列名，仍有 `查询列名（snake_case）：...`

- [ ] **Step 14：参数映射 tooltip — 内容正确**

同一接口，参数映射区域标题 "参数映射" 旁 hover `<InfoCircleOutlined>` 图标 → 卡片宽度 ≤ 420px，含：用途 + 字段含义 + 错误码 + SQL 示例（`WHERE topology_id = :topology_id` + `映射: 参数名=topologyId, 位置=query, SQL 绑定名=topology_id`）。

- [ ] **Step 15：清理 smoke 数据**

删除 Step 3 / Step 4 / Step 9 创建的测试接口。后端 + 前端进程关闭释放端口：

```bash
# 关前端 Ctrl+C
# 关后端
netstat -ano | grep ":8080.*LISTENING" | awk '{print $5}' | xargs -I {} taskkill //F //PID {}
```

- [ ] **Step 16：本任务无需 commit**

如所有手动步骤通过则计划完成。

---

## 完成条件

- Task 1-4 全部 commit 完成（main 分支，4 个 commit）
- Task 5 全部 14 个验证步骤通过（Step 1/15 为环境准备/清理，Step 16 为收尾）
- `npx tsc --noEmit` exit 0
- 接口管理页折叠状态持久、请求规格 Tab 化、Query 双开关合一、两个字段有 tooltip
