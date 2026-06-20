# 边类型"允许源/目标类型"多选下拉化 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `EdgeTypeModal` 中"允许源类型/目标类型"两个 CSV 文本框改成 Antd 多选下拉框（按 category 分组、支持名字+code 搜索、显著标红失效 code）。

**Architecture:** 纯前端改动。`EdgeTypeTable` 通过 `useNodeTypes` composable 拉一次 node_types，作为 prop 传给 `EdgeTypeModal`；Modal 内部把 DB 的 CSV 字符串 ↔ `string[]` 互转，UI 用 `<a-select mode="multiple">` 渲染。后端零改动，DB 不迁移。

**Tech Stack:** Vue 3.5 `<script setup>` + Ant Design Vue 4（`Select` + `tagRender` slot + `OptGroup`）+ TypeScript。

**Spec:** `docs/superpowers/specs/2026-06-20-edge-type-allow-codes-multiselect-design.md`

**前置条件：** 假设后端 `edge.py:212-234` 已是 `split(",")` 解析（2026-06-20 已修复的 commit）。如未修复，先 revert 本计划改动会导致 500，但本计划不依赖未修复路径。

---

## File Structure

| 文件 | 责任 |
|------|------|
| `frontend/src/components/types/EdgeTypeTable.vue` | 拉取 nodeTypes + 通过 prop 注入 Modal |
| `frontend/src/components/types/EdgeTypeModal.vue` | 表单状态从 `string` 改 `string[]` + 渲染多选下拉 + CSV↔array 转换 + 自定义 tag 渲染 |

---

## 工作环境约定

- 在主仓 `C:/Users/benerlord/Desktop/InterfaceTest` 直接工作（**不开 worktree**）—— 改动小（2 文件）、纯前端、回滚成本为零
- 每个 Task 完成后跑 `npx tsc --noEmit` 类型检查，必须 exit 0
- 项目无 frontend 单测体系，验证靠 TypeScript 类型检查 + Task 4 手动 smoke
- 工作目录约定：所有命令默认 `cd /c/Users/benerlord/Desktop/InterfaceTest`

---

## Task 1: EdgeTypeTable 拉取 nodeTypes 并下传

**Files:**
- Modify: `frontend/src/components/types/EdgeTypeTable.vue`
- Modify: `frontend/src/components/types/EdgeTypeModal.vue`（仅加 prop 接口，不消费）

**目标：** 加数据通道，Modal 接收 prop 但暂不消费——独立可提交、不破坏现有功能。

- [ ] **Step 1：EdgeTypeTable 引入 useNodeTypes**

修改 `frontend/src/components/types/EdgeTypeTable.vue:6` 行：

```ts
import { useEdgeTypes, useNodeTypes } from '@/composables/useTypes'
```

并在 `useEdgeTypes()` 调用之后（第 19 行后），加：

```ts
const { nodeTypes, fetchNodeTypes } = useNodeTypes()
```

并在文件末尾 `fetchEdgeTypes()` 调用（第 102 行）后加：

```ts
fetchNodeTypes()
```

- [ ] **Step 2：EdgeTypeTable 通过 prop 传给 Modal**

修改 `frontend/src/components/types/EdgeTypeTable.vue` 第 206-212 行的 `<EdgeTypeModal>` 标签，添加 `:node-types="nodeTypes"`：

```vue
<EdgeTypeModal
  v-model:open="modalOpen"
  :editing="modalEditing"
  :loading="modalLoading"
  :node-types="nodeTypes"
  @create="handleCreate"
  @update="handleUpdate"
/>
```

- [ ] **Step 3：EdgeTypeModal 声明 prop**

修改 `frontend/src/components/types/EdgeTypeModal.vue` 顶部 import 区（约第 6-8 行），把 `NodeTypeDetail` 加入 import：

```ts
import type {
  EdgeTypeCreate, EdgeTypeUpdate, EdgeTypeDetail, EdgeTypeFieldInput,
  NodeTypeDetail,
} from '@/api/types'
```

把 `defineProps` 块（第 35-39 行）改为：

```ts
const props = defineProps<{
  open: boolean
  editing?: EdgeTypeDetail | null
  loading?: boolean
  nodeTypes: NodeTypeDetail[]
}>()
```

注意：`nodeTypes` 设为必填（不带 `?`），强制调用方传值。

- [ ] **Step 4：类型检查**

```bash
cd /c/Users/benerlord/Desktop/InterfaceTest/frontend && npx tsc --noEmit
```

Expected: exit 0（无报错）

- [ ] **Step 5：手动启动前端确认无 console 报错**

```bash
cd /c/Users/benerlord/Desktop/InterfaceTest/frontend && npm run dev
```

后端需先启动（`cd /c/Users/benerlord/Desktop/InterfaceTest/backend && python -m app.main`）。

浏览器开 http://localhost:5173 → 进类型管理页 → 打开/关闭"新建边类型" Modal 几次。预期：开发者控制台无红色错误。完成验证后 Ctrl+C 关闭前端、`taskkill //F //PID <backend_pid>` 关后端。

- [ ] **Step 6：提交**

```bash
cd /c/Users/benerlord/Desktop/InterfaceTest && git add frontend/src/components/types/EdgeTypeTable.vue frontend/src/components/types/EdgeTypeModal.vue && git commit -m "$(cat <<'EOF'
feat(types): EdgeTypeTable 拉 nodeTypes 下传 Modal

为后续把允许源/目标类型改成多选下拉做数据准备。
Modal 接收 prop 但暂未消费，保持现有 UI 不变。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: EdgeTypeModal 替换 2 个文本框为多选下拉

**Files:**
- Modify: `frontend/src/components/types/EdgeTypeModal.vue`

**目标：** 把两个 `<a-input>` 换成 `<a-select mode="multiple">`，分组渲染 + 名字/code 双向搜索 + CSV↔array 双向转换。本 Task 完成后基础功能已可用（stale code 用默认 tag 渲染，颜色与正常 tag 相同——下个 Task 才标红）。

- [ ] **Step 1：修改 EdgeTypeForm 类型**

修改 `frontend/src/components/types/EdgeTypeModal.vue` 第 21-33 行 `interface EdgeTypeForm`，把两个字段类型从 `string` 改为 `string[]`：

```ts
interface EdgeTypeForm {
  code: string
  name: string
  semantic: string
  directed: boolean
  exclusiveTarget: boolean
  allowSourceTypeCodes: string[]
  allowTargetTypeCodes: string[]
  lineStyle: string
  color: string
  description: string
  fields: EdgeTypeFieldInput[]
}
```

- [ ] **Step 2：修改 defaultForm() 初始值**

修改第 49-61 行 `defaultForm`，两个字段初始为空数组：

```ts
const defaultForm = (): EdgeTypeForm => ({
  code: '',
  name: '',
  semantic: 'connect',
  directed: true,
  exclusiveTarget: false,
  allowSourceTypeCodes: [],
  allowTargetTypeCodes: [],
  lineStyle: '',
  color: '',
  description: '',
  fields: [],
})
```

- [ ] **Step 3：加 CSV → array 解析工具函数**

在 `defaultForm` 函数定义之后（第 62 行附近）加一个文件级工具函数：

```ts
function parseCsvCodes(csv: string | null | undefined): string[] {
  if (!csv) return []
  const parts = csv.split(',').map(s => s.trim()).filter(Boolean)
  return [...new Set(parts)]
}
```

- [ ] **Step 4：修改 watch 中编辑模式的加载逻辑**

修改第 66-96 行 `watch(() => props.open, (open) => { ... })` 内部 `if (props.editing)` 分支的第 75-76 行：

```ts
allowSourceTypeCodes: parseCsvCodes(props.editing.allowSourceTypeCodes),
allowTargetTypeCodes: parseCsvCodes(props.editing.allowTargetTypeCodes),
```

- [ ] **Step 5：修改 submit() 提交逻辑**

修改第 141-173 行 `submit` 函数中两处 `allowSourceTypeCodes: form.value.allowSourceTypeCodes || null` 和 `allowTargetTypeCodes: form.value.allowTargetTypeCodes || null`（共 4 行：151/152/165/166），改为：

```ts
// emit update payload 中
allowSourceTypeCodes: form.value.allowSourceTypeCodes.length ? form.value.allowSourceTypeCodes.join(',') : null,
allowTargetTypeCodes: form.value.allowTargetTypeCodes.length ? form.value.allowTargetTypeCodes.join(',') : null,
```

create 分支同样替换。两处共 4 处替换。

- [ ] **Step 6：加 computed groupedNodeTypeOptions**

在 `<script setup>` 顶部 import 区把 `computed` 改为已有，无需修改 import（第 2 行已 import `computed`）。

在 `isEdit` computed（第 47 行）之后新增：

```ts
const groupedNodeTypeOptions = computed(() => {
  const byCategory = new Map<string, { label: string; value: string }[]>()
  for (const nt of props.nodeTypes) {
    const list = byCategory.get(nt.category) ?? []
    list.push({
      label: `${nt.name} (${nt.code})`,
      value: nt.code,
    })
    byCategory.set(nt.category, list)
  }
  const sortedCategories = [...byCategory.keys()].sort()
  return sortedCategories.map(category => ({
    label: category,
    options: byCategory.get(category)!.sort((a, b) =>
      a.label.localeCompare(b.label, 'zh-CN')
    ),
  }))
})
```

- [ ] **Step 7：加 filterOption 方法**

紧接其后加：

```ts
function filterByNameOrCode(input: string, option: { label?: string }): boolean {
  if (!input) return true
  return String(option.label ?? '').toLowerCase().includes(input.toLowerCase())
}
```

- [ ] **Step 8：替换"允许源类型"输入框**

修改 `frontend/src/components/types/EdgeTypeModal.vue` 第 233-237 行（"允许源类型" `<a-form-item>` 内部），整个 `<a-input>` 替换为：

```vue
<a-form-item label="允许源类型">
  <a-select
    v-model:value="form.allowSourceTypeCodes"
    mode="multiple"
    placeholder="留空 = 不限制"
    :max-tag-count="3"
    :max-tag-text-length="12"
    allow-clear
    show-search
    :filter-option="filterByNameOrCode"
    :options="groupedNodeTypeOptions"
    option-label-prop="label"
  />
</a-form-item>
```

- [ ] **Step 9：替换"允许目标类型"输入框**

同样修改第 241-245 行（"允许目标类型" `<a-form-item>` 内部），整个 `<a-input>` 替换为：

```vue
<a-form-item label="允许目标类型">
  <a-select
    v-model:value="form.allowTargetTypeCodes"
    mode="multiple"
    placeholder="留空 = 不限制"
    :max-tag-count="3"
    :max-tag-text-length="12"
    allow-clear
    show-search
    :filter-option="filterByNameOrCode"
    :options="groupedNodeTypeOptions"
    option-label-prop="label"
  />
</a-form-item>
```

- [ ] **Step 10：类型检查**

```bash
cd /c/Users/benerlord/Desktop/InterfaceTest/frontend && npx tsc --noEmit
```

Expected: exit 0

- [ ] **Step 11：手动 smoke 检查基础功能**

启动前后端：

```bash
cd /c/Users/benerlord/Desktop/InterfaceTest/backend && python -m app.main &
cd /c/Users/benerlord/Desktop/InterfaceTest/frontend && npm run dev
```

浏览器进入类型管理 → 新建边类型 → 两下拉打开应能看到分组列表（cloud / physical / logical 等组）→ 选 2 个类型 → 在搜索框输入"弹"应过滤 → 保存。然后立即编辑该边类型，预期已选 tag 正确显示（中文名+code 格式）。完成后关闭前后端进程。

- [ ] **Step 12：提交**

```bash
cd /c/Users/benerlord/Desktop/InterfaceTest && git add frontend/src/components/types/EdgeTypeModal.vue && git commit -m "$(cat <<'EOF'
feat(types): 边类型允许源/目标类型改为多选下拉

替换两个 CSV 文本框为 Antd Select mode=multiple，按 category 分组、
显示"中文名 (code)"、支持名字/code 搜索。CSV ↔ array 双向转换在
Modal 内部完成，存储格式不变（DB 字段仍为逗号分隔字符串）。
本 commit 后失效 code 仍用默认色 tag 显示（下一 commit 标红）。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: 失效 code 标红 + tooltip

**Files:**
- Modify: `frontend/src/components/types/EdgeTypeModal.vue`

**目标：** 添加 `validCodes` 计算属性 + 自定义 `#tagRender` 把已选但 node_types 表中不存在的 code 渲染成红色 tag + hover 提示。

- [ ] **Step 1：加 validCodes computed**

在 Task 2 Step 7 加的 `filterByNameOrCode` 函数之后，新增：

```ts
const validCodes = computed<Set<string>>(() => {
  return new Set(props.nodeTypes.map(nt => nt.code))
})

function isStaleCode(code: string): boolean {
  return !validCodes.value.has(code)
}
```

- [ ] **Step 2：给"允许源类型"Select 加 tagRender slot**

修改"允许源类型"的 `<a-select>`（Task 2 Step 8 引入的），把自闭标签改为带 slot 的形式：

```vue
<a-form-item label="允许源类型">
  <a-select
    v-model:value="form.allowSourceTypeCodes"
    mode="multiple"
    placeholder="留空 = 不限制"
    :max-tag-count="3"
    :max-tag-text-length="12"
    allow-clear
    show-search
    :filter-option="filterByNameOrCode"
    :options="groupedNodeTypeOptions"
    option-label-prop="label"
  >
    <template #tagRender="{ value, label, closable, onClose }">
      <a-tooltip v-if="isStaleCode(value)" title="该节点类型已不存在">
        <a-tag color="error" :closable="closable" @close="onClose" style="margin-right: 3px;">
          {{ value }}
        </a-tag>
      </a-tooltip>
      <a-tag v-else :closable="closable" @close="onClose" style="margin-right: 3px;">
        {{ label }}
      </a-tag>
    </template>
  </a-select>
</a-form-item>
```

- [ ] **Step 3：给"允许目标类型"Select 加同样的 tagRender slot**

修改"允许目标类型"的 `<a-select>`，同样改为带 slot 形式：

```vue
<a-form-item label="允许目标类型">
  <a-select
    v-model:value="form.allowTargetTypeCodes"
    mode="multiple"
    placeholder="留空 = 不限制"
    :max-tag-count="3"
    :max-tag-text-length="12"
    allow-clear
    show-search
    :filter-option="filterByNameOrCode"
    :options="groupedNodeTypeOptions"
    option-label-prop="label"
  >
    <template #tagRender="{ value, label, closable, onClose }">
      <a-tooltip v-if="isStaleCode(value)" title="该节点类型已不存在">
        <a-tag color="error" :closable="closable" @close="onClose" style="margin-right: 3px;">
          {{ value }}
        </a-tag>
      </a-tooltip>
      <a-tag v-else :closable="closable" @close="onClose" style="margin-right: 3px;">
        {{ label }}
      </a-tag>
    </template>
  </a-select>
</a-form-item>
```

- [ ] **Step 4：类型检查**

```bash
cd /c/Users/benerlord/Desktop/InterfaceTest/frontend && npx tsc --noEmit
```

Expected: exit 0

- [ ] **Step 5：手动 smoke 检查失效 code 可视化**

启动前后端，进入"类型管理"→点击编辑 `M_VMAttachedToVolume` 边类型（其目标类型字段含失效 code `CLOUD_VM`）。预期：
- 目标类型字段中 `CLOUD_VM` 显示为**红色 tag**，hover 提示"该节点类型已不存在"
- 下拉打开可看到正常的 `CLOUD_VM_NOVA (弹性云服务器)` 选项
- 点 stale tag 的 `×` 可移除
- 保存后再次打开，确认 stale tag（如未删除）仍保留

完成后关闭前后端进程。

- [ ] **Step 6：提交**

```bash
cd /c/Users/benerlord/Desktop/InterfaceTest && git add frontend/src/components/types/EdgeTypeModal.vue && git commit -m "$(cat <<'EOF'
feat(types): 边类型失效 code 红色 tag 警示

在多选下拉的 tagRender slot 中，对存储有但当前 node_types 表中
已不存在的 code（如旧数据残留的 CLOUD_VM 写错）显示 color=error
红色 tag + hover tooltip"该节点类型已不存在"，用户可手动删除。
默认不主动清理，保留数据完整性。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: 完整 smoke 验收

**目标：** 按 spec §9 的 7 步清单完整跑一遍，确认无回归。

无代码改动，仅手动测试。任一步骤失败 → 回到对应 Task 修复。

- [ ] **Step 1：启动后端 + 前端**

```bash
cd /c/Users/benerlord/Desktop/InterfaceTest/backend && python -m app.main &
cd /c/Users/benerlord/Desktop/InterfaceTest/frontend && npm run dev
```

浏览器开 http://localhost:5173 → 类型管理。

- [ ] **Step 2：新建边类型，两下拉留空，验证不限制**

新建边类型 → code: `smoke_open`，name: `Smoke Open` → 两个下拉都不选 → 保存。

API 验证：
```bash
curl -s "http://127.0.0.1:8080/admin/api/edge-types" | python -c "import sys,json; d=json.load(sys.stdin)['data']; e=[x for x in (d if isinstance(d,list) else d['items']) if x['code']=='smoke_open'][0]; print('source:', repr(e['allowSourceTypeCodes']), 'target:', repr(e['allowTargetTypeCodes']))"
```
Expected: `source: None target: None`

- [ ] **Step 3：编辑同边类型，分别选源/目标**

编辑刚才的 `smoke_open` → 源选`云硬盘 (CLOUD_VOLUME)`，目标选`弹性云服务器 (CLOUD_VM_NOVA)` → 保存。

API 验证：
```bash
curl -s "http://127.0.0.1:8080/admin/api/edge-types" | python -c "import sys,json; d=json.load(sys.stdin)['data']; e=[x for x in (d if isinstance(d,list) else d['items']) if x['code']=='smoke_open'][0]; print('source:', repr(e['allowSourceTypeCodes']), 'target:', repr(e['allowTargetTypeCodes']))"
```
Expected: `source: 'CLOUD_VOLUME' target: 'CLOUD_VM_NOVA'`

- [ ] **Step 4：搜索过滤**

新建/编辑边类型 → 在任一下拉里点开 → 搜索"弹" → 预期只剩弹性云服务器一项；搜索"VOL" → 预期只剩云硬盘一项；搜索"xyz不存在" → 预期空列表。

- [ ] **Step 5：失效 code 警示**

编辑 `M_VMAttachedToVolume`（在 "ManageOne云资源查询" 拓扑场景下） → 目标类型字段应显示**红色** `CLOUD_VM` tag + hover 提示"该节点类型已不存在"。

- [ ] **Step 6：保留失效 code（默认行为）**

接 Step 5，直接点保存（不删 stale tag）→ API 查询确认 `allowTargetTypeCodes` 仍含 `CLOUD_VM`。

- [ ] **Step 7：删除失效 code 后保存**

再次编辑 `M_VMAttachedToVolume` → 点 stale tag 的 `×` 删除 `CLOUD_VM` → 加 `CLOUD_VM_NOVA` 替代 → 保存。验证：
```bash
curl -s "http://127.0.0.1:8080/admin/api/edge-types" | python -c "import sys,json; d=json.load(sys.stdin)['data']; e=[x for x in (d if isinstance(d,list) else d['items']) if x['code']=='M_VMAttachedToVolume'][0]; print('target:', repr(e['allowTargetTypeCodes']))"
```
Expected: `target: 'CLOUD_VM_NOVA'`（不再含 `CLOUD_VM`）

然后画布上选 "ManageOne云资源查询" → 把一个云硬盘节点连到一个弹性云服务器节点（边类型选 `M_VMAttachedToVolume`） → 预期成功创建边（200，不再 40109）。

- [ ] **Step 8：分组显示**

新建边类型 → 任一下拉打开 → 预期：选项按 category 分组显示（如 `cloud` / `physical` 等 OptGroup 标题），同组内按中文名排序。

- [ ] **Step 9：超过 3 个折叠**

新建边类型 → 在源/目标任一下拉选超过 3 个节点类型 → 预期显示 `+N` 收纳标签。

- [ ] **Step 10：清理 smoke 数据**

删除测试用 `smoke_open` 边类型。关闭前端 Ctrl+C、后端 `taskkill //F //PID <pid>`。

- [ ] **Step 11：本任务无需 commit**

如所有手动步骤通过则计划完成；如失败则定位到具体 Task（1/2/3）修复后重做本 Task。

---

## 完成条件

- Task 1-3 全部 commit 完成（main 分支）
- Task 4 全部 11 步通过
- `npx tsc --noEmit` exit 0
- 类型管理页"新建边类型"Modal 两字段为多选下拉
- 编辑 `M_VMAttachedToVolume` 显示红色 stale tag
- 后端日志无 JSONDecodeError / 500
