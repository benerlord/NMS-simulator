<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRoute } from 'vue-router'
import { message } from 'ant-design-vue'
import { Modal, Form, InputNumber, Select } from 'ant-design-vue'
import { Graph } from '@antv/x6'
import CanvasToolbar from '@/components/canvas/CanvasToolbar.vue'
import TopologyCanvas from '@/components/canvas/TopologyCanvas.vue'
import TypePalette from '@/components/canvas/TypePalette.vue'
import GroupPalette from '@/components/canvas/GroupPalette.vue'
import GroupCreateModal from '@/components/canvas/GroupCreateModal.vue'
import NodeAttrsPanel from '@/components/canvas/NodeAttrsPanel.vue'
import NodeAttrsModal from '@/components/canvas/NodeAttrsModal.vue'
import EdgeAttrsPanel from '@/components/canvas/EdgeAttrsPanel.vue'
import { useCanvas } from '@/composables/useCanvas'
import { useNodeGroups } from '@/composables/useNodeGroups'
import { useEdgeTypes } from '@/composables/useTypes'
import { nodeApi } from '@/api/node'
import { edgeApi } from '@/api/edge'
import { nodeGroupApi } from '@/api/nodeGroup'
import { getWsClient } from '@/ws/client'
import type { NodeTypeDetail } from '@/api/types'
import type { NodeGroupItem } from '@/api/nodeGroup'
import {
  INFRA_NODE_SHAPE,
  INFRA_NODE_WIDTH,
  INFRA_NODE_HEIGHT,
  buildInfraNodeAttrs,
  registerInfraNodeShape,
  MACRO_NODE_SHAPE,
  MACRO_NODE_WIDTH,
  MACRO_NODE_HEIGHT,
  buildMacroNodeAttrs,
} from '@/utils/nodeShape'

registerInfraNodeShape()

const route = useRoute()
const topologyId = route.params.id as string

const { graph, graphData, loading, saving, dirty, saveError, lastSavedAt, fetchGraph, savePositions, markDirty } = useCanvas(topologyId)
const { edgeTypes, fetchEdgeTypes } = useEdgeTypes()
const { groups, groupGraph, materializing, fetchGroups, fetchGroupGraph, createGroup, updateGroup, deleteGroup, materializeGroup } = useNodeGroups(topologyId, fetchGraph)

const canUndo = ref(false)
const canRedo = ref(false)
const isDragOver = ref(false)

// Node attrs panel state
const attrsPanelVisible = ref(false)
const selectedNodeId = ref<string | null>(null)
const selectedNodeTypeId = ref<string | null>(null)
const selectedNodeName = ref('')
const selectedNodeAttrs = ref<Record<string, string | null>>({})

// Selection state (for keyboard delete of any canvas element)
const selectedElement = ref<{
  type: 'node' | 'macroNode' | 'edge' | 'macroEdge' | 'hybridEdge'
  id: string
  name?: string
  edgeData?: Record<string, unknown> | null
} | null>(null)

// Edge attrs panel state
const edgeAttrsPanelVisible = ref(false)
const selectedEdgeId = ref<string | null>(null)
const selectedEdgeTypeId = ref<string | null>(null)
const selectedEdgeAttrs = ref<Record<string, string | null>>({})

// Node creation modal state
const createModalVisible = ref(false)
const pendingDropNodeType = ref<NodeTypeDetail | null>(null)
const pendingDropPosition = ref({ x: 0, y: 0 })

// Group create modal state
const groupCreateModalVisible = ref(false)
const editGroupId = ref<string | null>(null)

// Connecting mode state
const connectingMode = ref(false)
const connectingSourceId = ref<string | null>(null)
const connectingSourceIsMacro = ref(false)
const connectingStep = ref<'select-target' | 'select-type' | 'select-mode'>('select-target')
const pendingEdgeTargetId = ref<string | null>(null)
const pendingEdgeTargetIsMacro = ref(false)

// Edge type / mode selector state
const edgeTypeSelectorVisible = ref(false)
const connectingEdgeTypeId = ref<string | null>(null)
const connectingEdgeMode = ref<string>('all_to_all')
const connectingRatioK = ref<number>(2)
const edgeModeSelectorVisible = ref(false)

// Computed for template type narrowing workaround
const pendingNodeTypeForModal = computed(() => pendingDropNodeType.value)

// Debounce timer for node position save
let positionSaveTimer: ReturnType<typeof setTimeout> | null = null
const POSITION_SAVE_DELAY = 500 // ms

// Auto-save timer
let autoSaveTimer: ReturnType<typeof setTimeout> | null = null
const AUTO_SAVE_DELAY = 60000 // 60 seconds

function resetAutoSaveTimer() {
  if (autoSaveTimer) {
    clearTimeout(autoSaveTimer)
  }
  autoSaveTimer = setTimeout(() => {
    if (dirty.value) {
      performAutoSave()
    }
  }, AUTO_SAVE_DELAY)
}

async function performAutoSave() {
  try {
    const positions = (graph.value as Graph)
      .getCells()
      .filter((c) => c.isNode() && !c.id.startsWith('grp_'))
      .map((c) => {
        const pos = c.getPosition()
        return { nodeId: c.id, x: pos.x, y: pos.y }
      })
    await savePositions(positions)
  } catch {
    // Auto-save failed, will retry on next timer
  }
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key !== 'Delete' && e.key !== 'Backspace') return
  if (connectingMode.value) return
  const target = e.target as HTMLElement | null
  if (target) {
    const tag = target.tagName
    if (tag === 'INPUT' || tag === 'TEXTAREA' || target.isContentEditable) return
  }
  // Priority: new selection system (single-click), fallback to old panel-based selection
  if (selectedElement.value) {
    e.preventDefault()
    const el = selectedElement.value
    switch (el.type) {
      case 'node':
        confirmDeleteNode(el.id, el.name || '')
        break
      case 'macroNode':
        confirmDeleteMacroNode(el.id, el.name || '')
        break
      case 'edge':
        confirmDeleteEdge(el.id)
        break
      case 'macroEdge':
      case 'hybridEdge':
        confirmDeleteMacroEdge(el.id, el.edgeData || null)
        break
    }
  } else if (selectedNodeId.value) {
    e.preventDefault()
    confirmDeleteNode(selectedNodeId.value, selectedNodeName.value)
  } else if (selectedEdgeId.value) {
    e.preventDefault()
    confirmDeleteEdge(selectedEdgeId.value)
  }
}

function handleNodeSelect(nodeId: string, isMacro: boolean) {
  const g = graph.value as Graph | null
  const cell = g?.getCellById(nodeId)
  if (isMacro) {
    const data = cell?.getData?.() || {}
    selectedElement.value = {
      type: 'macroNode',
      id: nodeId,
      name: data.groupName || nodeId,
    }
  } else {
    const data = cell?.getData?.() || {}
    selectedElement.value = {
      type: 'node',
      id: nodeId,
      name: data.name || nodeId,
    }
  }
  highlightSelection(cell)
}

function handleEdgeSelect(edgeId: string, isMacro: boolean, isHybrid: boolean, edgeData: Record<string, unknown> | null) {
  const g = graph.value as Graph | null
  const cell = g?.getCellById(edgeId)
  if (isHybrid) {
    selectedElement.value = { type: 'hybridEdge', id: edgeId, edgeData }
  } else if (isMacro) {
    selectedElement.value = { type: 'macroEdge', id: edgeId, edgeData }
  } else {
    selectedElement.value = { type: 'edge', id: edgeId }
  }
  highlightSelection(cell)
}

function handleSelectionClear() {
  clearSelectionHighlight()
  selectedElement.value = null
}

function highlightSelection(cell: unknown) {
  clearSelectionHighlight()
  if (!cell) return
  const c = cell as any
  try {
    // Store original stroke for restore later
    const origAttrs = c.getAttrs?.()
    if (!c._origAttrs && origAttrs) {
      c._origAttrs = JSON.parse(JSON.stringify(origAttrs))
    }
    if (c.isNode?.()) {
      c.attr?.('body/stroke', '#1890ff')
      c.attr?.('body/strokeWidth', 3)
    } else if (c.isEdge?.()) {
      c.attr?.('line/stroke', '#1890ff')
      c.attr?.('line/strokeWidth', 3)
    }
    c._selected = true
  } catch {
    // ignore
  }
}

function clearSelectionHighlight() {
  const g = graph.value as Graph | null
  if (!g) return
  const cells = g.getCells()
  for (const cell of cells) {
    const c = cell as any
    if (c._selected) {
      try {
        if (c._origAttrs) {
          c.setAttrs?.(c._origAttrs)
          c._origAttrs = null
        }
        c._selected = false
      } catch {
        // ignore
      }
    }
  }
}

function confirmDeleteMacroNode(groupId: string, groupName: string) {
  Modal.confirm({
    title: '删除节点组',
    content: `确认删除节点组"${groupName || groupId}"？其包含的全部节点和边将一并删除，此操作不可撤销。`,
    okText: '删除',
    okType: 'danger',
    cancelText: '取消',
    onOk: () => performDeleteMacroNode(groupId),
  })
}

async function performDeleteMacroNode(groupId: string) {
  try {
    await deleteGroup(groupId)
  } catch (err: any) {
    message.error(`删除节点组失败: ${err.message ?? '未知错误'}`)
    return
  }
  const g = graph.value as Graph
  const cell = g.getCellById(groupId)
  if (cell) {
    // Remove connected macro edges from canvas
    const connectedEdges = g.getConnectedEdges(cell)
    for (const edge of connectedEdges) {
      g.removeCell(edge)
    }
    g.removeCell(cell)
  }
  selectedElement.value = null
  await fetchGroups()
  await fetchGroupGraph()
  message.success('节点组已删除')
}

function confirmDeleteMacroEdge(edgeId: string, edgeData: Record<string, unknown> | null) {
  const srcGrpId = (edgeData?.sourceGroupId as string) || ''
  const tgtGrpId = (edgeData?.targetGroupId as string) || ''
  const isHybrid = edgeData?.isHybrid as boolean

  Modal.confirm({
    title: isHybrid ? '删除混合连接' : '删除宏边',
    content: isHybrid
      ? `确认删除此混合连接策略？画布连线将移除。`
      : `确认删除宏边"${srcGrpId.slice(0, 12)}... → ${tgtGrpId.slice(0, 12)}..."？该连接策略将从源组中清除。`,
    okText: '删除',
    okType: 'danger',
    cancelText: '取消',
    onOk: () => performDeleteMacroEdge(edgeId, edgeData),
  })
}

async function performDeleteMacroEdge(edgeId: string, edgeData: Record<string, unknown> | null) {
  if (!edgeData) return
  const srcGroupId = edgeData.sourceGroupId as string
  const tgtGroupId = edgeData.targetGroupId as string

  try {
    // Fetch current group to get existing strategies
    const sourceGroup = groups.value.find((g) => g.id === srcGroupId)
    if (!sourceGroup) throw new Error('源组不存在')

    const existingStrategies = sourceGroup.edgeStrategies || []
    const filtered = existingStrategies.filter(
      (es) => !(es.targetGroupId === tgtGroupId),
    )

    await nodeGroupApi.update(srcGroupId, { edgeStrategies: filtered.length > 0 ? filtered : null })
  } catch (err: any) {
    message.error(`删除宏边失败: ${err.message ?? '未知错误'}`)
    return
  }

  const g = graph.value as Graph
  const cell = g.getCellById(edgeId)
  if (cell) {
    g.removeCell(cell)
  }
  selectedElement.value = null
  await fetchGroupGraph()
  message.success('宏边已删除')
}

onMounted(async () => {
  await Promise.all([fetchGraph(), fetchGroupGraph(), fetchEdgeTypes()])
  resetAutoSaveTimer()

  window.addEventListener('keydown', handleKeydown)

  // Subscribe to topology.saved event
  const ws = getWsClient()
  ws.on('topology.saved', (event) => {
    const payload = event.payload as { topologyId: string }
    if (payload.topologyId === topologyId) {
      // Another client saved this topology
    }
  })
})

function handleInit(x6Graph: unknown) {
  const g = x6Graph as Graph
  graph.value = x6Graph

  g.on('history:change', () => {
    canUndo.value = g.canUndo()
    canRedo.value = g.canRedo()
    markDirty()
    resetAutoSaveTimer()
  })
}

async function handleSave() {
  try {
    const positions = (graph.value as Graph)
      .getCells()
      .filter((c) => c.isNode() && !c.id.startsWith('grp_'))
      .map((c) => {
        const pos = c.getPosition()
        return { nodeId: c.id, x: pos.x, y: pos.y }
      })
    await savePositions(positions)
    message.success('保存成功')
    resetAutoSaveTimer()
  } catch {
    message.error('保存失败')
  }
}

function handleUndo() {
  ;(graph.value as Graph).undo()
  markDirty()
  resetAutoSaveTimer()
}

function handleRedo() {
  ;(graph.value as Graph).redo()
  markDirty()
  resetAutoSaveTimer()
}

function handleZoomIn() {
  ;(graph.value as Graph).zoom(0.1)
  resetAutoSaveTimer()
}

function handleZoomOut() {
  ;(graph.value as Graph).zoom(-0.1)
  resetAutoSaveTimer()
}

function handleFit() {
  ;(graph.value as Graph).fitToContent()
  resetAutoSaveTimer()
}

function handleNodeMoved(nodeId: string, x: number, y: number) {
  markDirty()
  resetAutoSaveTimer()
  // Debounce: save position within 500ms after drag ends
  if (positionSaveTimer) {
    clearTimeout(positionSaveTimer)
  }
  positionSaveTimer = setTimeout(async () => {
    // Macro node positions are saved in TopologyCanvas via nodeGroupApi
    if (nodeId.startsWith('grp_')) return
    try {
      await nodeApi.updatePosition(nodeId, { x, y })
    } catch (err: any) {
      message.error(`保存节点位置失败: ${err.message ?? '未知错误'}`)
    }
  }, POSITION_SAVE_DELAY)
}

async function handleNodeDblClick(nodeId: string) {
  // In connecting mode, handle differently
  if (connectingMode.value) {
    await handleNodeClickInConnectMode(nodeId)
    return
  }

  const g = graph.value as Graph
  const cell = g.getCellById(nodeId)
  if (!cell || !cell.isNode()) return

  const nodeData = cell.getData()
  // Macro node: no operation on double-click
  if (nodeData?.macroNodeId) return

  selectedElement.value = { type: 'node', id: nodeId, name: nodeData?.name || '' }
  selectedNodeId.value = nodeId
  selectedNodeTypeId.value = nodeData?.nodeTypeId || null
  selectedNodeName.value = nodeData?.name || ''

  // Fetch full node data including attrs
  try {
    const nodeDetail = await nodeApi.get(nodeId)
    selectedNodeAttrs.value = nodeDetail.attrs || {}
  } catch {
    selectedNodeAttrs.value = {}
  }

  attrsPanelVisible.value = true
}

function handleAttrsPanelClose() {
  attrsPanelVisible.value = false
  selectedNodeId.value = null
  selectedNodeTypeId.value = null
  selectedNodeName.value = ''
  selectedNodeAttrs.value = {}
  selectedElement.value = null
}

function handleAttrsUpdate(nodeId: string, attrs: Record<string, string | null>) {
  selectedNodeAttrs.value = attrs
  // Update the node in graph data
  const g = graph.value as Graph
  const cell = g.getCellById(nodeId)
  if (cell && cell.isNode()) {
    const data = cell.getData()
    cell.setData({ ...data, attrs })
  }
}

function handleNodeRename(nodeId: string, newName: string) {
  selectedNodeName.value = newName
  const g = graph.value as Graph
  const cell = g.getCellById(nodeId)
  if (cell && cell.isNode()) {
    cell.attr('label/text', newName)
    cell.setData({ ...cell.getData(), name: newName })
  }
}

async function handleEdgeDblClick(edgeId: string) {
  const g = graph.value as Graph
  const cell = g.getCellById(edgeId)
  if (!cell || !cell.isEdge()) return

  const edgeData = cell.getData()
  selectedElement.value = { type: 'edge', id: edgeId }
  selectedEdgeId.value = edgeId
  selectedEdgeTypeId.value = edgeData?.edgeTypeId || null

  // Fetch full edge data including attrs
  try {
    const edgeDetail = await edgeApi.get(edgeId)
    selectedEdgeAttrs.value = edgeDetail.attrs || {}
  } catch {
    selectedEdgeAttrs.value = {}
  }

  edgeAttrsPanelVisible.value = true
}

function handleEdgeAttrsPanelClose() {
  edgeAttrsPanelVisible.value = false
  selectedEdgeId.value = null
  selectedEdgeTypeId.value = null
  selectedEdgeAttrs.value = {}
  selectedElement.value = null
}

function handleMacroEdgeDblClick(_edgeId: string, edgeData: Record<string, unknown>) {
  const src = (edgeData.sourceGroupId as string) ?? ''
  const tgt = (edgeData.targetGroupId as string) ?? ''
  const mode = (edgeData.mode as string) ?? '?'
  const code = (edgeData.edgeTypeCode as string) ?? '?'
  const ratioK = edgeData.ratioK ?? '-'
  const total = (edgeData.totalEdgeCount as number) ?? 0
  const isHybrid = edgeData.isHybrid as boolean

  Modal.info({
    title: isHybrid ? '混合连接策略' : '宏边策略',
    content: isHybrid
      ? `类型: 混合连接 (${code})\n模式: all_to_all\n源组: ${(src as string).slice(0, 12)}...\n目标节点: ${(tgt as string).slice(0, 12)}...\n已生成边数: ${total.toLocaleString()}`
      : `连接规则: ${code} / ${mode}${ratioK !== undefined && ratioK !== null ? ` (K=${ratioK})` : ''}\n源组: ${(src as string).slice(0, 12)}...\n目标组: ${(tgt as string).slice(0, 12)}...\n已生成边数: ${total.toLocaleString()}`,
    okText: '关闭',
  })
}

function handleEdgeAttrsUpdate(edgeId: string, attrs: Record<string, string | null>) {
  selectedEdgeAttrs.value = attrs
  // Update the edge in graph data
  const g = graph.value as Graph
  const cell = g.getCellById(edgeId)
  if (cell && cell.isEdge()) {
    const data = cell.getData()
    cell.setData({ ...data, attrs })
  }
}

function confirmDeleteNode(nodeId: string, nodeName: string) {
  Modal.confirm({
    title: '删除节点',
    content: `确认删除节点"${nodeName || nodeId}"？其所有相连边将一并删除，此操作不可撤销。`,
    okText: '删除',
    okType: 'danger',
    cancelText: '取消',
    onOk: () => performDeleteNode(nodeId),
  })
}

async function performDeleteNode(nodeId: string) {
  try {
    await nodeApi.delete(nodeId)
  } catch (err: any) {
    message.error(`删除节点失败: ${err.message ?? '未知错误'}`)
    return
  }
  const g = graph.value as Graph
  const cell = g.getCellById(nodeId)
  if (cell) {
    const connectedEdges = g.getConnectedEdges(cell)
    for (const edge of connectedEdges) {
      g.removeCell(edge)
    }
    g.removeCell(cell)
  }
  if (selectedNodeId.value === nodeId) {
    handleAttrsPanelClose()
  }
  selectedElement.value = null
  markDirty()
  resetAutoSaveTimer()
  message.success('节点已删除')
}

function confirmDeleteEdge(edgeId: string) {
  const g = graph.value as Graph
  const cell = g.getCellById(edgeId)
  let descriptor = edgeId
  if (cell && cell.isEdge()) {
    const src = cell.getSourceCellId()
    const tgt = cell.getTargetCellId()
    const srcNode = src ? g.getCellById(src) : null
    const tgtNode = tgt ? g.getCellById(tgt) : null
    const srcName = srcNode?.getData()?.name || src || '?'
    const tgtName = tgtNode?.getData()?.name || tgt || '?'
    descriptor = `${srcName} → ${tgtName}`
  }
  Modal.confirm({
    title: '删除连线',
    content: `确认删除连线"${descriptor}"？此操作不可撤销。`,
    okText: '删除',
    okType: 'danger',
    cancelText: '取消',
    onOk: () => performDeleteEdge(edgeId),
  })
}

async function performDeleteEdge(edgeId: string) {
  try {
    await edgeApi.delete(edgeId)
  } catch (err: any) {
    message.error(`删除连线失败: ${err.message ?? '未知错误'}`)
    return
  }
  const g = graph.value as Graph
  const cell = g.getCellById(edgeId)
  if (cell) {
    g.removeCell(cell)
  }
  if (selectedEdgeId.value === edgeId) {
    handleEdgeAttrsPanelClose()
  }
  selectedElement.value = null
  markDirty()
  resetAutoSaveTimer()
  message.success('连线已删除')
}

function _getNodeType(nodeId: string): 'normal' | 'macro' {
  const g = graph.value as Graph | null
  if (!g) return 'normal'
  const cell = g.getCellById(nodeId)
  if (!cell || !cell.isNode()) return 'normal'
  return cell.getData()?.macroNodeId ? 'macro' : 'normal'
}

function handleToggleConnectMode() {
  connectingMode.value = !connectingMode.value
  if (connectingMode.value) {
    connectingSourceId.value = null
    connectingSourceIsMacro.value = false
    connectingStep.value = 'select-target'
    attrsPanelVisible.value = false
    edgeAttrsPanelVisible.value = false
    connectingEdgeTypeId.value = null
    connectingEdgeMode.value = 'all_to_all'
    connectingRatioK.value = 2
    message.info('点击源节点开始连线')
  }
}

async function handleNodeClickInConnectMode(nodeId: string) {
  const nodeType = _getNodeType(nodeId)

  if (connectingStep.value === 'select-target') {
    connectingSourceId.value = nodeId
    connectingSourceIsMacro.value = nodeType === 'macro'
    connectingStep.value = 'select-type'
    edgeTypeSelectorVisible.value = true
  } else if (connectingStep.value === 'select-type') {
    pendingEdgeTargetId.value = nodeId
    pendingEdgeTargetIsMacro.value = nodeType === 'macro'

    const srcMacro = connectingSourceIsMacro.value
    const tgtMacro = nodeType === 'macro'

    // Macro→Macro: after edge type selection, need mode selector too
    if (srcMacro && tgtMacro) {
      if (!connectingEdgeTypeId.value) {
        message.warning('请先选择边类型')
        return
      }
      connectingStep.value = 'select-mode'
      edgeModeSelectorVisible.value = true
      return
    }

    // Normal→Normal: create physical edge
    if (!srcMacro && !tgtMacro) {
      if (!connectingEdgeTypeId.value) {
        message.warning('请先选择边类型')
        return
      }
      await createNormalEdge(connectingEdgeTypeId.value)
      return
    }

    // Hybrid: Normal↔Macro → all_to_all strategy
    await createHybridConnection()
  }
}

function handleSelectEdgeType(edgeTypeId: string) {
  connectingEdgeTypeId.value = edgeTypeId
  edgeTypeSelectorVisible.value = false
  const srcMacro = connectingSourceIsMacro.value
  if (!srcMacro) {
    message.info('现在点击目标节点')
  } else {
    message.info('现在点击目标宏节点')
  }
}

function handleEdgeTypeSelectorClose() {
  edgeTypeSelectorVisible.value = false
  connectingMode.value = false
  connectingSourceId.value = null
  connectingSourceIsMacro.value = false
  connectingStep.value = 'select-target'
  connectingEdgeTypeId.value = null
}

function handleSelectEdgeMode(mode: string) {
  connectingEdgeMode.value = mode
}

async function handleEdgeModeConfirm() {
  edgeModeSelectorVisible.value = false
  await createMacroToMacroConnection(
    connectingEdgeTypeId.value!,
    connectingEdgeMode.value,
    connectingEdgeMode.value === 'modulo' || connectingEdgeMode.value === 'one_to_n'
      ? connectingRatioK.value
      : undefined,
  )
}

function handleEdgeModeSelectorClose() {
  edgeModeSelectorVisible.value = false
  connectingMode.value = false
  connectingSourceId.value = null
  connectingSourceIsMacro.value = false
  connectingStep.value = 'select-target'
  connectingEdgeTypeId.value = null
}

async function createNormalEdge(edgeTypeId: string) {
  if (!connectingSourceId.value || !pendingEdgeTargetId.value) return
  const sourceId = connectingSourceId.value
  const targetId = pendingEdgeTargetId.value
  try {
    const result = await edgeApi.create(topologyId, {
      topologyId,
      edgeTypeId,
      sourceId,
      targetId,
      status: 'up',
    })
    const g = graph.value as Graph
    g.addEdge({
      id: result.id,
      source: sourceId,
      target: targetId,
      data: { id: result.id, topologyId, edgeTypeId, sourceId, targetId, status: 'up' },
    })
    message.success('连线已创建')
  } catch (err: any) {
    message.error(`创建连线失败: ${err.message ?? '未知错误'}`)
  } finally {
    connectingMode.value = false
    connectingSourceId.value = null
    connectingSourceIsMacro.value = false
    pendingEdgeTargetId.value = null
    connectingStep.value = 'select-target'
  }
}

async function createHybridConnection() {
  const srcId = connectingSourceId.value!
  const tgtId = pendingEdgeTargetId.value!
  const srcMacro = connectingSourceIsMacro.value
  const tgtMacro = pendingEdgeTargetIsMacro.value

  const macroGroupId = srcMacro ? srcId : tgtId

  const edgeType = edgeTypes.value.find((et) => et.id === connectingEdgeTypeId.value)
  if (!edgeType) {
    message.error('边类型不存在')
    resetConnectState()
    return
  }

  // The non-macro endpoint (normal node ID) is the "other" side
  const otherId = srcMacro ? tgtId : srcId

  try {
    const existingGroup = groups.value.find((g) => g.id === macroGroupId)
    if (!existingGroup) {
      message.error('宏节点组不存在')
      resetConnectState()
      return
    }

    const existingStrategies = existingGroup.edgeStrategies || []
    const newStrategy = {
      targetGroupId: otherId,
      edgeTypeCode: edgeType.code,
      mode: 'all_to_all' as const,
      ratioK: null as number | null,
      visualSourceIsMacro: srcMacro,
    }

    await nodeGroupApi.update(macroGroupId, {
      edgeStrategies: [...existingStrategies, newStrategy],
    })
    await fetchGroupGraph()
    message.success('混合连接策略已创建')

    // Re-render by re-initializing graph through watch
  } catch (err: any) {
    message.error(`创建混合连接失败: ${err.message ?? '未知错误'}`)
  } finally {
    resetConnectState()
  }
}

async function createMacroToMacroConnection(
  edgeTypeId: string,
  mode: string,
  ratioK: number | undefined,
) {
  const srcId = connectingSourceId.value!
  const tgtId = pendingEdgeTargetId.value!

  const edgeType = edgeTypes.value.find((et) => et.id === edgeTypeId)
  if (!edgeType) {
    message.error('边类型不存在')
    resetConnectState()
    return
  }

  const sourceGroup = groups.value.find((g) => g.id === srcId)
  if (!sourceGroup) {
    message.error('源节点组不存在')
    resetConnectState()
    return
  }

  try {
    const existingStrategies = sourceGroup.edgeStrategies || []
    const newStrategy = {
      targetGroupId: tgtId,
      edgeTypeCode: edgeType.code,
      mode,
      ratioK: ratioK ?? null,
    }

    await nodeGroupApi.update(srcId, {
      edgeStrategies: [...existingStrategies, newStrategy as any],
    })
    await fetchGroupGraph()
    message.success('宏边策略已创建')
  } catch (err: any) {
    message.error(`创建宏边策略失败: ${err.message ?? '未知错误'}`)
  } finally {
    resetConnectState()
  }
}

function resetConnectState() {
  connectingMode.value = false
  connectingSourceId.value = null
  connectingSourceIsMacro.value = false
  pendingEdgeTargetId.value = null
  pendingEdgeTargetIsMacro.value = false
  connectingStep.value = 'select-target'
  connectingEdgeTypeId.value = null
  connectingEdgeMode.value = 'all_to_all'
  connectingRatioK.value = 2
}

function handleDragOver(e: DragEvent) {
  e.preventDefault()
  if (e.dataTransfer) {
    e.dataTransfer.dropEffect = 'copy'
  }
  isDragOver.value = true
  resetAutoSaveTimer()
}

function handleDragLeave() {
  isDragOver.value = false
}

function handleDrop(e: DragEvent) {
  e.preventDefault()
  isDragOver.value = false
  resetAutoSaveTimer()

  if (!e.dataTransfer) return

  const g = graph.value as Graph
  if (!g) {
    message.error('画布未初始化')
    return
  }

  const container = g.container
  const bbox = container.getBoundingClientRect()
  const x = e.clientX - bbox.left
  const y = e.clientY - bbox.top

  // Dispatch by MIME type
  const nodeTypeData = e.dataTransfer.getData('application/node-type')
  if (nodeTypeData) {
    let nodeType: NodeTypeDetail
    try {
      nodeType = JSON.parse(nodeTypeData)
    } catch {
      message.error('无效的节点类型数据')
      return
    }
    pendingDropNodeType.value = nodeType
    pendingDropPosition.value = { x, y }
    createModalVisible.value = true
    return
  }

  const groupData = e.dataTransfer.getData('application/node-group')
  if (groupData) {
    let grp: { id: string; groupName: string; nodeCount: number }
    try {
      grp = JSON.parse(groupData)
    } catch {
      message.error('无效的节点组数据')
      return
    }
    // Update macro node position via API
    nodeGroupApi.updatePosition(grp.id, { x, y }).then(() => {
      fetchGroupGraph()
    }).catch(() => {})
    markDirty()
    message.success(`已定位节点组: ${grp.groupName}`)
    return
  }
}

function handleGroupCreate() {
  editGroupId.value = null
  groupCreateModalVisible.value = true
}

async function handleGroupCreated() {
  groupCreateModalVisible.value = false
  await fetchGraph()        // Refresh graphData first so initGraph has fresh data
  fetchGroups()             // Background: refresh palette list
  await fetchGroupGraph()   // Triggers initGraph re-render with fresh graphData
}

async function handleGroupUpdated() {
  groupCreateModalVisible.value = false
  await fetchGraph()
  fetchGroups()
  await fetchGroupGraph()
}

function handleGroupCreateModalClose() {
  groupCreateModalVisible.value = false
  editGroupId.value = null
}

function handleZoomToGroup(groupId: string) {
  const g = graph.value as Graph | null
  if (!g) return
  const cell = g.getCellById(groupId)
  if (cell) {
    const pos = cell.getBBox()
    g.centerPoint(pos.center.x, pos.center.y)
    g.zoomToFit({ padding: 40 })
  }
}

async function handleNodeCreated(nodeId: string, name: string) {
  createModalVisible.value = false

  const g = graph.value as Graph
  const pos = pendingDropPosition.value
  const nodeType = pendingDropNodeType.value

  pendingDropNodeType.value = null

  if (!nodeType) return

  g.addNode({
    id: nodeId,
    shape: INFRA_NODE_SHAPE,
    x: pos.x,
    y: pos.y,
    width: INFRA_NODE_WIDTH,
    height: INFRA_NODE_HEIGHT,
    attrs: buildInfraNodeAttrs(nodeType.code, name),
    data: {
      id: nodeId,
      topologyId,
      nodeTypeId: nodeType.id,
      name,
      status: 'online',
    },
  })

  markDirty()
  message.success(`已创建节点: ${name}`)
}

function handleCreateModalClose() {
  createModalVisible.value = false
  pendingDropNodeType.value = null
}

onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleKeydown)
  if (positionSaveTimer) {
    clearTimeout(positionSaveTimer)
  }
  if (autoSaveTimer) {
    clearTimeout(autoSaveTimer)
  }
})
</script>

<template>
  <div class="canvas-view">
    <CanvasToolbar
      :saving="saving"
      :dirty="dirty"
      :can-undo="canUndo"
      :can-redo="canRedo"
      :save-error="saveError"
      :last-saved-at="lastSavedAt"
      :connecting-mode="connectingMode"
      @save="handleSave"
      @undo="handleUndo"
      @redo="handleRedo"
      @zoom-in="handleZoomIn"
      @zoom-out="handleZoomOut"
      @fit="handleFit"
      @toggle-connect="handleToggleConnectMode"
    />

    <div class="canvas-content">
      <div class="left-panels">
        <TypePalette :topology-id="topologyId" />
        <GroupPalette
          :topology-id="topologyId"
          @create="handleGroupCreate"
          @edit="(grpId: string) => { editGroupId = grpId; groupCreateModalVisible = true }"
          @zoom-to-group="handleZoomToGroup"
        />
      </div>

      <div
        class="canvas-area"
        :class="{ 'drag-over': isDragOver }"
        @dragover="handleDragOver"
        @dragleave="handleDragLeave"
        @drop="handleDrop"
      >
        <a-spin v-if="loading" tip="加载拓扑数据..." />
        <template v-else-if="graphData">
          <TopologyCanvas
            :graph-data="graphData"
            :group-graph="groupGraph"
            :topology-id="topologyId"
            :connecting-mode="connectingMode"
            :graph="graph"
            @init="handleInit"
            @node-moved="handleNodeMoved"
            @node-select="handleNodeSelect"
            @edge-select="handleEdgeSelect"
            @selection-clear="handleSelectionClear"
            @node-dbl-click="handleNodeDblClick"
            @edge-dbl-click="handleEdgeDblClick"
            @macro-edge-dbl-click="handleMacroEdgeDblClick"
          />
        </template>
        <a-empty v-else description="暂无拓扑数据" />

        <NodeAttrsPanel
          :visible="attrsPanelVisible"
          :node-id="selectedNodeId"
          :node-type-id="selectedNodeTypeId"
          :node-name="selectedNodeName"
          :attrs="selectedNodeAttrs"
          @close="handleAttrsPanelClose"
          @update="handleAttrsUpdate"
          @delete="confirmDeleteNode"
          @rename="handleNodeRename"
        />

        <EdgeAttrsPanel
          :visible="edgeAttrsPanelVisible"
          :edge-id="selectedEdgeId"
          :edge-type-id="selectedEdgeTypeId"
          :attrs="selectedEdgeAttrs"
          @close="handleEdgeAttrsPanelClose"
          @update="handleEdgeAttrsUpdate"
          @delete="confirmDeleteEdge"
        />
      </div>

      <NodeAttrsModal
        v-if="pendingNodeTypeForModal"
        :visible="createModalVisible"
        :topology-id="topologyId"
        :node-type-id="pendingNodeTypeForModal.id"
        :node-type-name="pendingNodeTypeForModal.name"
        @close="handleCreateModalClose"
        @created="handleNodeCreated"
      />

      <GroupCreateModal
        :visible="groupCreateModalVisible"
        :topology-id="topologyId"
        :edit-group-id="editGroupId"
        @close="handleGroupCreateModalClose"
        @created="handleGroupCreated"
        @updated="handleGroupUpdated"
      />

      <!-- Edge type selector -->
      <Modal
        v-model:open="edgeTypeSelectorVisible"
        title="选择边类型"
        :footer="null"
        :width="400"
        @cancel="handleEdgeTypeSelectorClose"
      >
        <div class="edge-type-list">
          <div
            v-for="edgeType in edgeTypes"
            :key="edgeType.id"
            class="edge-type-item"
            @click="handleSelectEdgeType(edgeType.id)"
          >
            <div class="edge-type-name">{{ edgeType.name }}</div>
            <div class="edge-type-semantic">{{ edgeType.semantic || '无描述' }}</div>
          </div>
        </div>
      </Modal>

      <!-- Edge mode selector (macro→macro) -->
      <Modal
        v-model:open="edgeModeSelectorVisible"
        title="选择连接模式"
        :width="400"
        @ok="handleEdgeModeConfirm"
        @cancel="handleEdgeModeSelectorClose"
        ok-text="确认创建"
      >
        <Form layout="vertical">
          <Form.Item label="连接模式">
            <Select v-model:value="connectingEdgeMode" style="width: 100%">
              <Select.Option value="all_to_all">全连接</Select.Option>
              <Select.Option value="dense">一对一</Select.Option>
              <Select.Option value="modulo">取模分配</Select.Option>
              <Select.Option value="one_to_n">一对多</Select.Option>
            </Select>
          </Form.Item>
          <Form.Item
            v-if="connectingEdgeMode === 'modulo' || connectingEdgeMode === 'one_to_n'"
            label="K 值"
          >
            <InputNumber v-model:value="connectingRatioK" :min="1" style="width: 100%" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  </div>
</template>

<style scoped>
.canvas-view {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.canvas-content {
  flex: 1;
  display: flex;
  overflow: hidden;
}

.left-panels {
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  overflow: hidden;
}

.canvas-area {
  flex: 1;
  padding: 16px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  transition: background-color 0.2s;
  position: relative;
}

.canvas-area.drag-over {
  background-color: #e6f7ff;
}

.edge-type-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.edge-type-item {
  padding: 12px;
  border: 1px solid #e8e8e8;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.2s;
}

.edge-type-item:hover {
  border-color: #1890ff;
  background-color: #f0f9ff;
}

.edge-type-name {
  font-weight: 500;
  font-size: 14px;
  margin-bottom: 4px;
}

.edge-type-semantic {
  font-size: 12px;
  color: #999;
}
</style>
