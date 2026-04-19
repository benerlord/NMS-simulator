<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRoute } from 'vue-router'
import { message } from 'ant-design-vue'
import { Modal } from 'ant-design-vue'
import { Graph } from '@antv/x6'
import CanvasToolbar from '@/components/canvas/CanvasToolbar.vue'
import TopologyCanvas from '@/components/canvas/TopologyCanvas.vue'
import TypePalette from '@/components/canvas/TypePalette.vue'
import NodeAttrsPanel from '@/components/canvas/NodeAttrsPanel.vue'
import NodeAttrsModal from '@/components/canvas/NodeAttrsModal.vue'
import EdgeAttrsPanel from '@/components/canvas/EdgeAttrsPanel.vue'
import { useCanvas } from '@/composables/useCanvas'
import { useEdgeTypes } from '@/composables/useTypes'
import { nodeApi } from '@/api/node'
import { edgeApi } from '@/api/edge'
import { getWsClient } from '@/ws/client'
import type { NodeTypeDetail } from '@/api/types'
import {
  INFRA_NODE_SHAPE,
  INFRA_NODE_WIDTH,
  INFRA_NODE_HEIGHT,
  buildInfraNodeAttrs,
  registerInfraNodeShape,
} from '@/utils/nodeShape'

registerInfraNodeShape()

const route = useRoute()
const topologyId = route.params.id as string

const { graph, graphData, loading, saving, dirty, saveError, lastSavedAt, fetchGraph, savePositions, markDirty } = useCanvas(topologyId)
const { edgeTypes, fetchEdgeTypes } = useEdgeTypes()

const canUndo = ref(false)
const canRedo = ref(false)
const isDragOver = ref(false)

// Node attrs panel state
const attrsPanelVisible = ref(false)
const selectedNodeId = ref<string | null>(null)
const selectedNodeTypeId = ref<string | null>(null)
const selectedNodeName = ref('')
const selectedNodeAttrs = ref<Record<string, string | null>>({})

// Edge attrs panel state
const edgeAttrsPanelVisible = ref(false)
const selectedEdgeId = ref<string | null>(null)
const selectedEdgeTypeId = ref<string | null>(null)
const selectedEdgeAttrs = ref<Record<string, string | null>>({})

// Node creation modal state
const createModalVisible = ref(false)
const pendingDropNodeType = ref<NodeTypeDetail | null>(null)
const pendingDropPosition = ref({ x: 0, y: 0 })

// Connecting mode state
const connectingMode = ref(false)
const connectingSourceId = ref<string | null>(null)
const connectingStep = ref<'select-target' | 'select-type'>('select-target')
const pendingEdgeTargetId = ref<string | null>(null)

// Edge type selector state
const edgeTypeSelectorVisible = ref(false)
const connectingEdgeTypeId = ref<string | null>(null)

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
      .filter((c) => c.isNode())
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
  if (selectedNodeId.value) {
    e.preventDefault()
    confirmDeleteNode(selectedNodeId.value, selectedNodeName.value)
  } else if (selectedEdgeId.value) {
    e.preventDefault()
    confirmDeleteEdge(selectedEdgeId.value)
  }
}

onMounted(async () => {
  await fetchGraph()
  await fetchEdgeTypes()
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
      .filter((c) => c.isNode())
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
    try {
      await nodeApi.updatePosition(nodeId, { x, y })
    } catch (err: any) {
      message.error(`保存节点位置失败: ${err.message ?? '未知错误'}`)
    }
  }, POSITION_SAVE_DELAY)
}

async function handleNodeClick(nodeId: string) {
  // In connecting mode, handle differently
  if (connectingMode.value) {
    await handleNodeClickInConnectMode(nodeId)
    return
  }

  const g = graph.value as Graph
  const cell = g.getCellById(nodeId)
  if (!cell || !cell.isNode()) return

  const nodeData = cell.getData()
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

async function handleEdgeClick(edgeId: string) {
  const g = graph.value as Graph
  const cell = g.getCellById(edgeId)
  if (!cell || !cell.isEdge()) return

  const edgeData = cell.getData()
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
  markDirty()
  resetAutoSaveTimer()
  message.success('连线已删除')
}

function handleToggleConnectMode() {
  connectingMode.value = !connectingMode.value
  if (connectingMode.value) {
    connectingSourceId.value = null
    connectingStep.value = 'select-target'
    attrsPanelVisible.value = false
    edgeAttrsPanelVisible.value = false
    message.info('点击源节点开始连线')
  }
}

async function handleNodeClickInConnectMode(nodeId: string) {
  if (connectingStep.value === 'select-target') {
    // First node click - set source and show edge type selector
    connectingSourceId.value = nodeId
    connectingStep.value = 'select-type'
    edgeTypeSelectorVisible.value = true
  } else if (connectingStep.value === 'select-type') {
    // Second node click - this is the target
    pendingEdgeTargetId.value = nodeId
    if (!connectingEdgeTypeId.value) {
      message.warning('请先选择边类型')
      return
    }
    await createEdge(connectingEdgeTypeId.value)
  }
}

function handleSelectEdgeType(edgeTypeId: string) {
  connectingEdgeTypeId.value = edgeTypeId
  edgeTypeSelectorVisible.value = false
  message.info('现在点击目标节点')
}

function handleEdgeTypeSelectorClose() {
  edgeTypeSelectorVisible.value = false
  // Reset connecting state
  connectingMode.value = false
  connectingSourceId.value = null
  connectingStep.value = 'select-target'
  connectingEdgeTypeId.value = null
}

async function createEdge(edgeTypeId: string) {
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

    // Add edge to graph
    const g = graph.value as Graph
    g.addEdge({
      id: result.id,
      source: sourceId,
      target: targetId,
      data: {
        id: result.id,
        topologyId,
        edgeTypeId,
        sourceId,
        targetId,
        status: 'up',
      },
    })

    message.success('连线已创建')
  } catch (err: any) {
    message.error(`创建连线失败: ${err.message ?? '未知错误'}`)
  } finally {
    connectingMode.value = false
    connectingSourceId.value = null
    pendingEdgeTargetId.value = null
    connectingStep.value = 'select-target'
  }
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

  const data = e.dataTransfer.getData('application/node-type')
  if (!data) return

  let nodeType: NodeTypeDetail
  try {
    nodeType = JSON.parse(data)
  } catch {
    message.error('无效的节点类型数据')
    return
  }

  const g = graph.value as Graph
  if (!g) {
    message.error('画布未初始化')
    return
  }

  const container = g.container
  const bbox = container.getBoundingClientRect()
  const x = e.clientX - bbox.left
  const y = e.clientY - bbox.top

  // Store pending drop info and show modal
  pendingDropNodeType.value = nodeType
  pendingDropPosition.value = { x, y }
  createModalVisible.value = true
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
      <TypePalette />

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
            :graph="graph"
            @init="handleInit"
            @node-moved="handleNodeMoved"
            @node-click="handleNodeClick"
            @edge-click="handleEdgeClick"
          />
        </template>
        <a-empty v-else description="暂无拓扑数据" />

        <!-- Node attrs panel -->
        <NodeAttrsPanel
          :visible="attrsPanelVisible"
          :node-id="selectedNodeId"
          :node-type-id="selectedNodeTypeId"
          :node-name="selectedNodeName"
          :attrs="selectedNodeAttrs"
          @close="handleAttrsPanelClose"
          @update="handleAttrsUpdate"
          @delete="confirmDeleteNode"
        />

        <!-- Edge attrs panel -->
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

      <!-- Node creation modal -->
      <NodeAttrsModal
        v-if="pendingNodeTypeForModal"
        :visible="createModalVisible"
        :topology-id="topologyId"
        :node-type-id="pendingNodeTypeForModal.id"
        :node-type-name="pendingNodeTypeForModal.name"
        @close="handleCreateModalClose"
        @created="handleNodeCreated"
      />

      <!-- Edge type selector modal -->
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
