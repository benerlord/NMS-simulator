<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import { Modal, Form, Input, InputNumber, Select, Button, Tag, message } from 'ant-design-vue'
import { nodeGroupApi } from '@/api/nodeGroup'
import { nodeTypeApi, edgeTypeApi } from '@/api/types'
import type { NodeTypeDetail, NodeTypeFieldItem, EdgeTypeItem } from '@/api/types'
import type { NodeGroupItem } from '@/api/nodeGroup'

interface Props {
  visible: boolean
  topologyId: string
  editGroupId?: string | null
}

const props = withDefaults(defineProps<Props>(), { editGroupId: null })
const emit = defineEmits<{
  close: []
  created: []
  updated: []
}>()

const isEdit = computed(() => !!props.editGroupId)
const currentStep = ref(0)
const submitting = ref(false)
const loadingEdit = ref(false)

// Shared data
const nodeTypes = ref<NodeTypeDetail[]>([])
const edgeTypes = ref<EdgeTypeItem[]>([])
const existingGroups = ref<NodeGroupItem[]>([])

// Step 1 — Basic info
const step1 = ref({
  nodeTypeId: '',
  groupName: '',
  nodeCount: 100,
  nameTemplate: 'SW-{i:05d}',
  nameWidth: 5,
})

// Step 2 — Attr strategies
interface StrategyRow {
  fieldKey: string
  fieldLabel: string
  fieldType: string
  required: boolean
  strategy: 'fixed' | 'random' | 'increment' | 'range'
  fixedValue: string
  pool: string[]
  base: string
  step: string
  min: number
  max: number
  // For tag add
  poolInput: string
}
const strategyRows = ref<StrategyRow[]>([])
const step2FieldErrors = ref<Record<string, string>>({})
const step2ContentRef = ref<HTMLElement>()
const step2Fields = ref<NodeTypeFieldItem[]>([])

// Step 3 — Edge strategies
interface EdgeRule {
  targetGroupId: string
  edgeTypeCode: string
  mode: string
  ratioK: number | undefined
}
const edgeRules = ref<EdgeRule[]>([])

// Computed
const step1Valid = computed(() =>
  step1.value.nodeTypeId.trim() !== '' &&
  step1.value.groupName.trim() !== '' &&
  step1.value.nodeCount >= 1 &&
  step1.value.nodeCount <= 1_000_000,
)

const step2Valid = computed(() => true) // Always valid (all strategies have defaults)

const namePreview = computed(() => {
  const tpl = step1.value.nameTemplate
  const name = step1.value.groupName || 'Group'
  const count = step1.value.nodeCount
  const previews: string[] = []
  const limit = Math.min(count, 5)
  for (let i = 1; i <= limit; i++) {
    let rendered = tpl.replace('{group}', name)
    const w = step1.value.nameWidth
    rendered = rendered.replace(`{i:0${w}d}`, String(i).padStart(w, '0'))
    previews.push(rendered)
  }
  return { previews, overflow: count > 5, remainder: count - 5 }
})

// Selected node type fields (for step 2)
const selectedNodeTypeId = computed(() => step1.value.nodeTypeId)

// Edge count estimate
const edgeEstimates = computed(() => {
  return edgeRules.value.map((rule) => {
    const srcCount = step1.value.nodeCount
    const tgtGroup = existingGroups.value.find((g) => g.id === rule.targetGroupId)
    const tgtCount = tgtGroup?.nodeCount ?? 0
    let estimate = 0
    switch (rule.mode) {
      case 'all_to_all': estimate = srcCount * tgtCount; break
      case 'dense': estimate = Math.min(srcCount, tgtCount); break
      case 'modulo': estimate = srcCount; break
      case 'one_to_n': estimate = srcCount * (rule.ratioK ?? 0); break
    }
    return estimate
  })
})

// Initialize
watch(
  () => props.visible,
  async (v) => {
    if (!v) return
    currentStep.value = 0
    submitting.value = false

    // Fetch node types, edge types, and existing groups in parallel
    try {
      const [ntRes, etRes, groupsRes] = await Promise.all([
        nodeTypeApi.list(),
        edgeTypeApi.list(),
        nodeGroupApi.list(props.topologyId),
      ])
      nodeTypes.value = ntRes.items as unknown as NodeTypeDetail[]
      edgeTypes.value = etRes.items as unknown as EdgeTypeItem[]
      existingGroups.value = groupsRes.items
    } catch {
      // ignore
    }

    // Edit mode: load existing data
    if (props.editGroupId) {
      loadingEdit.value = true
      try {
        const grp = await nodeGroupApi.get(props.editGroupId)
        step1.value = {
          nodeTypeId: grp.nodeTypeId,
          groupName: grp.groupName,
          nodeCount: grp.nodeCount,
          nameTemplate: grp.nameTemplate,
          nameWidth: _extractWidth(grp.nameTemplate),
        }
        if (grp.edgeStrategies) {
          edgeRules.value = grp.edgeStrategies.map((es) => ({
            targetGroupId: es.targetGroupId,
            edgeTypeCode: es.edgeTypeCode,
            mode: es.mode,
            ratioK: es.ratioK ?? undefined,
          }))
        } else {
          edgeRules.value = []
        }
        // Load fields for step 2
        await loadFieldsForType(grp.nodeTypeId)
        // Pre-fill strategies
        for (const row of strategyRows.value) {
          const existing = grp.attrStrategies.find((s) => s.fieldKey === row.fieldKey)
          if (existing) {
            row.strategy = existing.strategy
            row.fixedValue = existing.fixedValue ?? ''
            row.pool = existing.pool ?? []
            row.base = existing.base ?? ''
            row.step = existing.step ?? ''
            row.min = existing.min ?? 1
            row.max = existing.max ?? 100
          }
        }
      } catch {
        message.error('加载节点组详情失败')
      } finally {
        loadingEdit.value = false
      }
    } else {
      // Reset for create mode
      step1.value = { nodeTypeId: '', groupName: '', nodeCount: 100, nameTemplate: '{group}-{i:05d}', nameWidth: 5 }
      strategyRows.value = []
      edgeRules.value = []
    }
  },
)

// When node type changes, auto-fill name template and load fields
watch(selectedNodeTypeId, async (ntId) => {
  if (!ntId) {
    step1.value.nameTemplate = 'SW-{i:05d}'
    strategyRows.value = []
    step2FieldErrors.value = {}
    return
  }
  const nt = nodeTypes.value.find((t) => t.id === ntId)
  if (nt) {
    step1.value.groupName = nt.name
    step1.value.nameTemplate = `{group}-{i:0${step1.value.nameWidth}d}`
  }
  await loadFieldsForType(ntId)
})

watch(
  () => step1.value.nameWidth,
  (w) => {
    const tpl = step1.value.nameTemplate
    step1.value.nameTemplate = tpl.replace(/\{i:0\d+d\}/, `{i:0${w}d}`)
  },
)

function _extractWidth(tpl: string): number {
  const m = tpl.match(/\{i:0(\d+)d\}/)
  return m ? Number(m[1]) : 5
}

async function loadFieldsForType(nodeTypeId: string) {
  try {
    const detail = await nodeTypeApi.get(nodeTypeId)
    step2Fields.value = detail.fields || []
    strategyRows.value = detail.fields.map((f) => ({
      fieldKey: f.fieldKey,
      fieldLabel: f.fieldLabel,
      fieldType: f.fieldType,
      required: f.required,
      strategy: 'fixed' as const,
      fixedValue: f.defaultValue ?? '',
      pool: [],
      base: '',
      step: '1',
      min: 1,
      max: 100,
      poolInput: '',
    }))
  } catch {
    strategyRows.value = []
  }
}

// Step 2 helpers
function onStrategyChange(row: StrategyRow, val: string) {
  row.strategy = val as StrategyRow['strategy']
  clearStep2Error(row.fieldKey)
}

function addPoolValue(row: StrategyRow) {
  const v = row.poolInput.trim()
  if (!v) return
  if (!row.pool.includes(v)) {
    row.pool = [...row.pool, v]
  }
  row.poolInput = ''
}

function removePoolValue(row: StrategyRow, idx: number) {
  row.pool = row.pool.filter((_, i) => i !== idx)
}

function incrementPreview(row: StrategyRow): string {
  if (!row.base || !row.step) return ''
  const previews: string[] = []
  for (let i = 0; i < 3; i++) {
    const b = parseInt(row.base, 10)
    const s = parseInt(row.step, 10)
    if (!isNaN(b) && !isNaN(s)) {
      previews.push(String(b + i * s))
    } else {
      previews.push(`${row.base}+${i}*${row.step}`)
    }
  }
  return previews.join(', ')
}

// Step 3 helpers
function addEdgeRule() {
  if (edgeRules.value.length >= 10) return
  edgeRules.value.push({
    targetGroupId: '',
    edgeTypeCode: '',
    mode: 'all_to_all',
    ratioK: undefined,
  })
}

function removeEdgeRule(idx: number) {
  edgeRules.value = edgeRules.value.filter((_, i) => i !== idx)
}

function onEdgeModeChange(rule: EdgeRule, mode: string) {
  rule.mode = mode
  if (mode === 'modulo' || mode === 'one_to_n') {
    rule.ratioK = rule.ratioK ?? 2
  } else {
    rule.ratioK = undefined
  }
}

// Navigation
function step2ValidateAndScroll(): boolean {
  const newErrors: Record<string, string> = {}
  for (const row of strategyRows.value) {
    if (!row.required) continue
    let hasError = false
    let errMsg = ''
    if (row.strategy === 'fixed' && !row.fixedValue.trim()) {
      hasError = true
      errMsg = '固定值不能为空'
    } else if (row.strategy === 'random' && row.pool.length === 0) {
      hasError = true
      errMsg = '随机选取至少需要一个值'
    } else if (row.strategy === 'increment' && (!row.base.trim() || !row.step.trim())) {
      hasError = true
      errMsg = '起始值和步长不能为空'
    }
    if (hasError) {
      newErrors[row.fieldKey] = errMsg
    }
  }

  if (Object.keys(newErrors).length > 0) {
    step2FieldErrors.value = newErrors
    nextTick(() => {
      const el = step2ContentRef.value?.querySelector('.step2-field-error') as HTMLElement
      el?.scrollIntoView({ behavior: 'smooth', block: 'center' })
      el?.focus()
    })
    return false
  }

  step2FieldErrors.value = {}
  return true
}

function clearStep2Error(fieldKey: string) {
  if (step2FieldErrors.value[fieldKey]) {
    delete step2FieldErrors.value[fieldKey]
  }
}

function nextStep() {
  if (currentStep.value === 1) {
    if (!step2ValidateAndScroll()) return
  }
  if (currentStep.value < 2) currentStep.value++
}

function prevStep() {
  if (currentStep.value > 0) currentStep.value--
}

// Submit
async function handleSubmit() {
  submitting.value = true
  try {
    const payload = {
      nodeTypeId: step1.value.nodeTypeId,
      groupName: step1.value.groupName.trim(),
      nodeCount: step1.value.nodeCount,
      nameTemplate: step1.value.nameTemplate,
      attrStrategies: strategyRows.value
        .filter((r) => {
          if (r.strategy === 'fixed') return !!r.fixedValue.trim()
          if (r.strategy === 'random') return r.pool.length > 0
          if (r.strategy === 'increment') return !!r.base.trim() && !!r.step.trim()
          return true // range always has valid defaults
        })
        .map((r) => ({
        fieldKey: r.fieldKey,
        strategy: r.strategy,
        fixedValue: r.strategy === 'fixed' ? r.fixedValue : null,
        pool: r.strategy === 'random' && r.pool.length > 0 ? r.pool : null,
        base: r.strategy === 'increment' ? r.base : null,
        step: r.strategy === 'increment' ? r.step : null,
        min: r.strategy === 'range' ? r.min : null,
        max: r.strategy === 'range' ? r.max : null,
      })),
      edgeStrategies: edgeRules.value.length > 0
        ? edgeRules.value.map((r) => ({
            targetGroupId: r.targetGroupId,
            edgeTypeCode: r.edgeTypeCode,
            mode: r.mode,
            ratioK: r.ratioK ?? null,
          }))
        : null,
    }

    if (isEdit.value) {
      await nodeGroupApi.update(props.editGroupId!, {
        groupName: payload.groupName,
        nodeCount: payload.nodeCount,
        nameTemplate: payload.nameTemplate,
        attrStrategies: payload.attrStrategies,
        edgeStrategies: payload.edgeStrategies,
      })
      message.success('节点组已更新')
      emit('updated')
    } else {
      await nodeGroupApi.create(props.topologyId, payload)
      message.success('节点组已创建')
      emit('created')
    }
    emit('close')
  } catch (err: any) {
    message.error(`提交失败: ${err.message ?? '未知错误'}`)
  } finally {
    submitting.value = false
  }
}

function handleCancel() {
  emit('close')
}
</script>

<template>
  <Modal
    :open="visible"
    :title="isEdit ? '编辑节点组' : '创建节点组'"
    :width="620"
    :confirm-loading="submitting"
    :confirm-disabled="submitting"
    @cancel="handleCancel"
    @ok="handleSubmit"
    ok-text="完成"
    cancel-text="取消"
  >
    <a-spin v-if="loadingEdit" tip="加载中..." />

    <template v-else>
      <!-- Steps indicator -->
      <div class="steps-bar">
        <div
          v-for="(label, idx) in ['基础信息', '属性策略', '连接规则']"
          :key="idx"
          class="step-dot"
          :class="{
            active: currentStep === idx,
            done: currentStep > idx,
          }"
        >
          <span class="step-num">{{ idx + 1 }}</span>
          <span class="step-label">{{ label }}</span>
        </div>
      </div>

      <!-- Step 1 — Basic info -->
      <div v-show="currentStep === 0" class="step-content">
        <Form layout="vertical">
          <Form.Item label="节点类型" required>
            <Select
              v-model:value="step1.nodeTypeId"
              placeholder="选择节点类型"
              :disabled="isEdit"
              show-search
              option-filter-prop="label"
            >
              <Select.Option
                v-for="nt in nodeTypes"
                :key="nt.id"
                :value="nt.id"
                :label="nt.name"
              >
                <span class="type-option">
                  <span>{{ nt.name }}</span>
                  <span class="type-code">{{ nt.code }}</span>
                </span>
              </Select.Option>
            </Select>
          </Form.Item>

          <Form.Item label="组名称" required>
            <Input v-model:value="step1.groupName" placeholder="输入节点组名称" />
          </Form.Item>

          <Form.Item label="节点数量" required>
            <InputNumber
              v-model:value="step1.nodeCount"
              :min="1"
              :max="1000000"
              style="width: 100%"
              placeholder="1 ~ 1,000,000"
            />
            <span class="field-hint">范围: 1 ~ 1,000,000</span>
          </Form.Item>

          <Form.Item label="编号格式">
            <Select v-model:value="step1.nameWidth" style="width: 100%">
              <Select.Option :value="3">3 位（001-999）</Select.Option>
              <Select.Option :value="4">4 位（0001-9999）</Select.Option>
              <Select.Option :value="5">5 位（00001-99999）</Select.Option>
              <Select.Option :value="6">6 位（000001-999999）</Select.Option>
            </Select>
          </Form.Item>

          <!-- Name preview -->
          <div class="name-preview">
            <div class="preview-title">命名预览</div>
            <div class="preview-list">
              <span v-for="name in namePreview.previews" :key="name" class="preview-name">{{ name }}</span>
              <span v-if="namePreview.overflow" class="preview-more">
                ...（共 {{ namePreview.remainder }} 个）
              </span>
            </div>
          </div>
        </Form>
      </div>

      <!-- Step 2 — Attr strategies -->
      <div v-show="currentStep === 1" ref="step2ContentRef" class="step-content">
        <div v-if="strategyRows.length === 0" class="step-empty">
          该节点类型无自定义字段，可跳过此步骤。
        </div>
        <div v-else class="strategy-list">
          <div
            v-for="row in strategyRows"
            :key="row.fieldKey"
            class="strategy-row"
            :class="{ 'step2-field-error': step2FieldErrors[row.fieldKey] }"
          >
            <div class="strategy-header">
              <span class="strategy-field-label">{{ row.fieldLabel }}</span>
              <span v-if="row.required" class="field-required-mark">*</span>
              <span class="strategy-field-key">({{ row.fieldKey }})</span>
            </div>

            <div class="strategy-controls">
              <Select
                :value="row.strategy"
                @change="(v: string) => { onStrategyChange(row, v); clearStep2Error(row.fieldKey) }"
                style="width: 130px"
              >
                <Select.Option value="fixed">固定值</Select.Option>
                <Select.Option value="random">随机选取</Select.Option>
                <Select.Option value="increment">递增</Select.Option>
                <Select.Option value="range">范围随机</Select.Option>
              </Select>

              <div class="strategy-params">
                <!-- fixed -->
                <Input
                  v-if="row.strategy === 'fixed'"
                  v-model:value="row.fixedValue"
                  @input="clearStep2Error(row.fieldKey)"
                  placeholder="固定值"
                  style="width: 160px"
                />

                <!-- random -->
                <div v-if="row.strategy === 'random'" class="pool-editor">
                  <div class="pool-tags">
                    <Tag
                      v-for="(item, idx) in row.pool"
                      :key="item"
                      closable
                      @close="() => removePoolValue(row, idx)"
                    >
                      {{ item }}
                    </Tag>
                    <Input
                      v-model:value="row.poolInput"
                      placeholder="输入后回车添加"
                      style="width: 120px"
                      size="small"
                      @press-enter="addPoolValue(row); clearStep2Error(row.fieldKey)"
                    />
                  </div>
                </div>

                <!-- increment -->
                <div v-if="row.strategy === 'increment'" class="increment-params">
                  <Input
                    v-model:value="row.base"
                    @input="clearStep2Error(row.fieldKey)"
                    placeholder="起始值"
                    style="width: 100px"
                  />
                  <span class="params-sep">+</span>
                  <Input
                    v-model:value="row.step"
                    @input="clearStep2Error(row.fieldKey)"
                    placeholder="步长"
                    style="width: 80px"
                  />
                  <span class="increment-preview">
                    预览: {{ incrementPreview(row) }}
                  </span>
                </div>

                <!-- range -->
                <div v-if="row.strategy === 'range'" class="range-params">
                  <InputNumber
                    v-model:value="row.min"
                    placeholder="最小值"
                    style="width: 90px"
                  />
                  <span class="params-sep">~</span>
                  <InputNumber
                    v-model:value="row.max"
                    placeholder="最大值"
                    style="width: 90px"
                  />
                </div>
              </div>
            </div>
            <div
              v-if="step2FieldErrors[row.fieldKey]"
              class="strategy-error-msg"
            >
              {{ step2FieldErrors[row.fieldKey] }}
            </div>
          </div>
        </div>
      </div>

      <!-- Step 3 — Edge strategies -->
      <div v-show="currentStep === 2" class="step-content">
        <div class="edge-header">
          <span class="step-hint">连接规则为可选项，无规则也可提交</span>
          <Button
            v-if="edgeRules.length < 10"
            type="dashed"
            size="small"
            @click="addEdgeRule"
          >
            + 添加规则
          </Button>
        </div>

        <div v-if="edgeRules.length === 0" class="step-empty">
          暂未添加连接规则。
        </div>

        <div v-else class="edge-list">
          <div v-for="(rule, idx) in edgeRules" :key="idx" class="edge-rule">
            <div class="edge-rule-row">
              <Select
                v-model:value="rule.targetGroupId"
                placeholder="目标组"
                style="flex: 1"
              >
                <Select.Option
                  v-for="grp in existingGroups.filter(g => g.id !== props.editGroupId)"
                  :key="grp.id"
                  :value="grp.id"
                >
                  {{ grp.groupName }}
                </Select.Option>
              </Select>

              <Select
                v-model:value="rule.edgeTypeCode"
                placeholder="边类型"
                style="flex: 1"
              >
                <Select.Option
                  v-for="et in edgeTypes"
                  :key="et.id"
                  :value="et.code"
                >
                  {{ et.name }} ({{ et.code }})
                </Select.Option>
              </Select>

              <Select
                :value="rule.mode"
                @change="(v: string) => onEdgeModeChange(rule, v)"
                style="width: 110px"
              >
                <Select.Option value="all_to_all">全连接</Select.Option>
                <Select.Option value="dense">一对一</Select.Option>
                <Select.Option value="modulo">取模分配</Select.Option>
                <Select.Option value="one_to_n">一对多</Select.Option>
              </Select>
            </div>

            <div class="edge-rule-extra">
              <template v-if="rule.mode === 'modulo' || rule.mode === 'one_to_n'">
                <span class="ratio-label">K =</span>
                <InputNumber
                  v-model:value="rule.ratioK"
                  :min="1"
                  style="width: 70px"
                />
              </template>

              <span class="edge-estimate" v-if="edgeEstimates[idx] > 0">
                预期边数: {{ edgeEstimates[idx].toLocaleString() }} 条
              </span>

              <span
                v-if="rule.mode === 'all_to_all' && edgeEstimates[idx] > 1_000_000"
                class="edge-warn"
              >
                ⚠ 超过 1,000,000 上限
              </span>

              <Button type="link" danger size="small" @click="removeEdgeRule(idx)">
                删除
              </Button>
            </div>
          </div>
        </div>
      </div>

      <!-- Footer nav -->
      <div class="steps-nav">
        <Button v-if="currentStep > 0" @click="prevStep">上一步</Button>
        <div class="nav-spacer" />
        <Button
          v-if="currentStep < 2"
          type="primary"
          :disabled="currentStep === 0 ? !step1Valid : !step2Valid"
          @click="nextStep"
        >
          下一步
        </Button>
      </div>
    </template>
  </Modal>
</template>

<style scoped>
.steps-bar {
  display: flex;
  justify-content: center;
  gap: 24px;
  margin-bottom: 20px;
  padding-bottom: 12px;
  border-bottom: 1px solid #f0f0f0;
}

.step-dot {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: rgba(0, 0, 0, 0.25);
}

.step-dot .step-num {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: #f0f0f0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 500;
}

.step-dot.active {
  color: #1890ff;
}

.step-dot.active .step-num {
  background: #1890ff;
  color: #fff;
}

.step-dot.done {
  color: #52c41a;
}

.step-dot.done .step-num {
  background: #52c41a;
  color: #fff;
}

.step-label {
  font-size: 13px;
}

.step-content {
  min-height: 200px;
  max-height: 400px;
  overflow-y: auto;
  padding: 4px 0;
}

.step-empty {
  color: rgba(0, 0, 0, 0.35);
  text-align: center;
  padding: 32px 0;
  font-size: 13px;
}

.step-hint {
  color: rgba(0, 0, 0, 0.35);
  font-size: 12px;
}

.field-hint {
  display: block;
  font-size: 11px;
  color: rgba(0, 0, 0, 0.35);
  margin-top: 4px;
}

.type-option {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.type-code {
  font-size: 11px;
  color: rgba(0, 0, 0, 0.35);
}

/* Name preview */
.name-preview {
  margin-top: 12px;
  padding: 12px;
  background: #fafafa;
  border-radius: 4px;
  border: 1px solid #f0f0f0;
}

.preview-title {
  font-size: 12px;
  color: rgba(0, 0, 0, 0.45);
  margin-bottom: 8px;
}

.preview-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.preview-name {
  font-size: 12px;
  background: #e6f7ff;
  color: #1890ff;
  padding: 2px 8px;
  border-radius: 3px;
  font-family: monospace;
}

.preview-more {
  font-size: 11px;
  color: rgba(0, 0, 0, 0.35);
  align-self: center;
}

/* Strategy rows */
.strategy-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.strategy-row {
  padding: 10px 12px;
  border: 1px solid #f0f0f0;
  border-radius: 4px;
}

.strategy-row.step2-field-error {
  border-color: #ff4d4f;
  background: #fff2f0;
}

.field-required-mark {
  color: #ff4d4f;
  font-weight: bold;
  margin-right: 2px;
}

.strategy-error-msg {
  margin-top: 6px;
  font-size: 12px;
  color: #ff4d4f;
}

.strategy-header {
  display: flex;
  align-items: baseline;
  gap: 4px;
  margin-bottom: 8px;
}

.strategy-field-label {
  font-size: 13px;
  font-weight: 500;
}

.strategy-field-key {
  font-size: 11px;
  color: rgba(0, 0, 0, 0.35);
}

.strategy-controls {
  display: flex;
  align-items: center;
  gap: 8px;
}

.strategy-params {
  flex: 1;
}

.params-sep {
  margin: 0 4px;
  color: rgba(0, 0, 0, 0.45);
}

.pool-editor {
  min-width: 160px;
}

.pool-tags {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
}

.increment-params {
  display: flex;
  align-items: center;
  gap: 4px;
}

.increment-preview {
  font-size: 11px;
  color: rgba(0, 0, 0, 0.35);
  margin-left: 8px;
}

.range-params {
  display: flex;
  align-items: center;
  gap: 4px;
}

/* Edge rules */
.edge-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.edge-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.edge-rule {
  padding: 10px 12px;
  border: 1px solid #f0f0f0;
  border-radius: 4px;
}

.edge-rule-row {
  display: flex;
  gap: 8px;
}

.edge-rule-extra {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed #f0f0f0;
}

.ratio-label {
  font-size: 12px;
  color: rgba(0, 0, 0, 0.45);
}

.edge-estimate {
  font-size: 12px;
  color: #1890ff;
  margin-left: auto;
}

.edge-warn {
  font-size: 11px;
  color: #ff4d4f;
}

/* Nav footer */
.steps-nav {
  display: flex;
  justify-content: space-between;
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid #f0f0f0;
}

.nav-spacer {
  flex: 1;
}
</style>
