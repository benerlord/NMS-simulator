<script setup lang="ts">
import { onMounted, onBeforeUnmount, shallowRef, ref, watch } from 'vue'
import { Graph, History } from '@antv/x6'
import type { TopologyGraph } from '@/api/topology'
import type { GroupGraphData } from '@/api/nodeGroup'
import { nodeGroupApi } from '@/api/nodeGroup'
import type { Cell, Node } from '@antv/x6'
import { useNodeTypes } from '@/composables/useTypes'
import { nodeApi } from '@/api/node'
import type { NodeTypeDetail } from '@/api/types'
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
  registerMacroNodeShape,
} from '@/utils/nodeShape'

registerInfraNodeShape()
registerMacroNodeShape()

interface Props {
  graphData: TopologyGraph | null
  groupGraph?: GroupGraphData | null
  topologyId: string
  connectingMode?: boolean
  graph?: unknown
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'init', graph: unknown): void
  (e: 'nodeMoved', nodeId: string, x: number, y: number): void
  (e: 'nodeSelect', nodeId: string, isMacro: boolean): void
  (e: 'edgeSelect', edgeId: string, isMacro: boolean, isHybrid: boolean, edgeData: Record<string, unknown> | null): void
  (e: 'selectionClear'): void
  (e: 'nodeDblClick', nodeId: string): void
  (e: 'edgeDblClick', edgeId: string): void
  (e: 'macroEdgeDblClick', edgeId: string, edgeData: Record<string, unknown>): void
}>()

const containerRef = shallowRef<HTMLDivElement | null>(null)
let graphInstance: Graph | null = null

const { nodeTypes, fetchNodeTypes } = useNodeTypes()

interface TooltipAttr {
  label: string
  value: string
}

interface TooltipData {
  name: string
  typeName: string
  dn: string | null
  status: string
  attrs: TooltipAttr[]
}

const tooltipVisible = ref(false)
const tooltipData = ref<TooltipData | null>(null)
const tooltipX = ref(0)
const tooltipY = ref(0)

let hoverTimer: ReturnType<typeof setTimeout> | null = null
let hoverSeq = 0
const HOVER_DELAY = 250

function getNodeType(nodeTypeId: string): NodeTypeDetail | null {
  return nodeTypes.value.find((t) => t.id === nodeTypeId) ?? null
}

function getNodeTypeCode(nodeTypeId: string): string | null {
  return getNodeType(nodeTypeId)?.code ?? null
}

function clearHoverTimer() {
  if (hoverTimer) {
    clearTimeout(hoverTimer)
    hoverTimer = null
  }
}

function hideTooltip() {
  clearHoverTimer()
  hoverSeq += 1
  tooltipVisible.value = false
  tooltipData.value = null
}

async function scheduleTooltip(node: Node, clientX: number, clientY: number) {
  clearHoverTimer()
  const seq = ++hoverSeq
  const nodeId = node.id
  const data = node.getData() as { nodeTypeId?: string; name?: string } | undefined
  const nodeTypeId = data?.nodeTypeId

  hoverTimer = setTimeout(async () => {
    if (seq !== hoverSeq) return

    let detail
    try {
      detail = await nodeApi.get(nodeId)
    } catch {
      return
    }
    if (seq !== hoverSeq) return

    const nt = nodeTypeId ? getNodeType(nodeTypeId) : null
    const attrs: TooltipAttr[] = []
    if (nt?.fields && detail.attrs) {
      const sorted = [...nt.fields].sort((a, b) => a.sortOrder - b.sortOrder)
      for (const field of sorted) {
        const raw = detail.attrs[field.fieldKey]
        if (raw === null || raw === undefined || raw === '') continue
        attrs.push({ label: field.fieldLabel, value: String(raw) })
      }
    }

    if (containerRef.value) {
      const bbox = containerRef.value.getBoundingClientRect()
      tooltipX.value = clientX - bbox.left + 12
      tooltipY.value = clientY - bbox.top + 12
    }

    tooltipData.value = {
      name: detail.name,
      typeName: nt?.name ?? '',
      dn: detail.dn,
      status: detail.status,
      attrs,
    }
    tooltipVisible.value = true
  }, HOVER_DELAY)
}

function updateTooltipPosition(clientX: number, clientY: number) {
  if (!containerRef.value) return
  const bbox = containerRef.value.getBoundingClientRect()
  tooltipX.value = clientX - bbox.left + 12
  tooltipY.value = clientY - bbox.top + 12
}

function initGraph(data: TopologyGraph | null) {
  if (!containerRef.value) return

  const w = containerRef.value.clientWidth
  const h = containerRef.value.clientHeight
  if (w === 0 || h === 0) return

  if (graphInstance) {
    graphInstance.dispose()
    graphInstance = null
  }

  const graph = new Graph({
    container: containerRef.value,
    width: w,
    height: h,
    grid: true,
    mousewheel: true,
    autoResize: true,
  })

  const history = new History({ enabled: false })
  graph.use(history)

  if (data) {
    const cells: Cell[] = []

    const nodeMap: Record<string, { x: number; y: number }> = {}
    for (const cn of data.canvasNodes) {
      nodeMap[cn.nodeId] = { x: cn.x, y: cn.y }
    }

    for (const node of data.nodes) {
      const pos = nodeMap[node.id] ?? { x: Math.random() * 600, y: Math.random() * 400 }
      const code = getNodeTypeCode(node.nodeTypeId)
      cells.push(
        graph.createNode({
          id: node.id,
          shape: INFRA_NODE_SHAPE,
          x: pos.x,
          y: pos.y,
          width: INFRA_NODE_WIDTH,
          height: INFRA_NODE_HEIGHT,
          attrs: buildInfraNodeAttrs(code, node.name),
          data: { ...node },
        }),
      )
    }

    for (const edge of data.edges) {
      cells.push(
        graph.createEdge({
          id: edge.id,
          source: edge.sourceId,
          target: edge.targetId,
          data: { ...edge },
        }),
      )
    }

    // Macro nodes
    const gg = props.groupGraph
    // Build set of all node IDs on canvas (normal + macro) for edge endpoint resolution
    const allNodeIds = new Set<string>(data.nodes.map((n) => n.id))
    if (gg) {
      const macroIds = new Set(gg.macroNodes.map((mn) => mn.id))
      for (const mn of gg.macroNodes) {
        allNodeIds.add(mn.id)
        const x = mn.x ?? Math.random() * 600
        const y = mn.y ?? Math.random() * 400
        const onlineRatio = mn.nodeCount > 0 ? mn.statusBreakdown.online / mn.nodeCount : 0
        const statusLabel = mn.isMaterialized
          ? `${mn.statusBreakdown.online}/${mn.nodeCount} online`
          : ''
        cells.push(
          graph.createNode({
            id: mn.id,
            shape: MACRO_NODE_SHAPE,
            x,
            y,
            width: MACRO_NODE_WIDTH,
            height: MACRO_NODE_HEIGHT,
            attrs: buildMacroNodeAttrs({
              groupName: mn.groupName,
              nodeCount: mn.nodeCount,
              onlineRatio,
              statusLabel,
            }),
            data: {
              macroNodeId: mn.id,
              topologyId: mn.topologyId,
              nodeTypeId: mn.nodeTypeId,
              groupName: mn.groupName,
              nodeCount: mn.nodeCount,
              isMaterialized: mn.isMaterialized,
            },
          }),
        )
      }

      for (const me of gg.macroEdges) {
        // Render if both endpoints exist on canvas (can be macro↔macro or macro↔normal)
        if (allNodeIds.has(me.sourceGroupId) && allNodeIds.has(me.targetGroupId)) {
          const tgtIsMacro = macroIds.has(me.targetGroupId)
          const isHybrid = !tgtIsMacro

          // Hybrid edges: respect visual direction (user's source→target order)
          const visualSource = isHybrid
            ? (me.visualSourceIsMacro ? me.sourceGroupId : me.targetGroupId)
            : me.sourceGroupId
          const visualTarget = isHybrid
            ? (me.visualSourceIsMacro ? me.targetGroupId : me.sourceGroupId)
            : me.targetGroupId

          const modeLabel = me.ratioK ? ` K=${me.ratioK}` : ''
          const label = isHybrid
            ? `${me.edgeTypeCode} 混合连接 ×${me.totalEdgeCount}`
            : `${me.edgeTypeCode} (${me.mode}${modeLabel}) ×${me.totalEdgeCount}`

          cells.push(
            graph.createEdge({
              id: `macro-${me.sourceGroupId}-${me.targetGroupId}`,
              source: visualSource,
              target: visualTarget,
              attrs: {
                line: isHybrid
                  ? {
                      stroke: '#1890ff',
                      strokeWidth: 2,
                      strokeDasharray: '8 4 2 4',
                      targetMarker: { name: 'block', width: 8, height: 6, fill: '#1890ff' },
                    }
                  : {
                      stroke: '#faad14',
                      strokeWidth: 2,
                      strokeDasharray: '6 4',
                      targetMarker: { name: 'block', width: 8, height: 6, fill: '#faad14' },
                    },
              },
              labels: [
                {
                  attrs: {
                    text: { text: label },
                    rect: { fill: '#fff', fillOpacity: 0.9, rx: 2 },
                  },
                  position: { distance: 0.5 },
                },
              ],
              data: {
                sourceGroupId: me.sourceGroupId,
                targetGroupId: me.targetGroupId,
                edgeTypeCode: me.edgeTypeCode,
                mode: me.mode,
                ratioK: me.ratioK,
                totalEdgeCount: me.totalEdgeCount,
                isHybrid,
              },
            }),
          )
        }
      }
    }

    graph.resetCells(cells)
    history.enable()
  }

  graph.on('node:moved', (args: { node: Node; x: number; y: number }) => {
    const data = args.node.getData()
    if (data?.macroNodeId) {
      nodeGroupApi.updatePosition(data.macroNodeId, { x: args.x, y: args.y }).catch(() => {})
    }
    emit('nodeMoved', args.node.id, args.x, args.y)
  })

  graph.on('node:click', (args: { node: Node }) => {
    if (props.connectingMode) {
      hideTooltip()
      emit('nodeDblClick', args.node.id)
      return
    }
    // Select on single click (not in connecting mode)
    const data = args.node.getData()
    emit('nodeSelect', args.node.id, !!data?.macroNodeId)
  })

  graph.on('node:dblclick', (args: { node: Node }) => {
    hideTooltip()
    emit('nodeDblClick', args.node.id)
  })

  graph.on('edge:click', (args: { edge: Cell }) => {
    const edgeData = args.edge.getData()
    const isMacro = !!edgeData?.sourceGroupId
    const isHybrid = !!edgeData?.isHybrid
    emit('edgeSelect', args.edge.id, isMacro, isHybrid, edgeData)
  })

  graph.on('edge:dblclick', (args: { edge: Cell }) => {
    hideTooltip()
    const edgeData = args.edge.getData()
    if (edgeData?.sourceGroupId) {
      emit('macroEdgeDblClick', args.edge.id, edgeData)
    } else {
      emit('edgeDblClick', args.edge.id)
    }
  })

  graph.on('blank:click', () => {
    emit('selectionClear')
  })

  graph.on('node:mouseenter', ({ node, e }: { node: Node; e: MouseEvent }) => {
    const data = node.getData()
    // Skip tooltip for macro nodes
    if (data?.macroNodeId) return
    scheduleTooltip(node, e.clientX, e.clientY)
  })

  graph.on('node:mousemove', ({ e }: { e: MouseEvent }) => {
    if (tooltipVisible.value) {
      updateTooltipPosition(e.clientX, e.clientY)
    }
  })

  graph.on('node:mouseleave', () => {
    hideTooltip()
  })

  graph.on('blank:mousedown', () => {
    hideTooltip()
  })

  graphInstance = graph
  emit('init', graph)
}

onMounted(async () => {
  await fetchNodeTypes()
  initGraph(props.graphData)
})

onBeforeUnmount(() => {
  clearHoverTimer()
  if (graphInstance) {
    graphInstance.dispose()
    graphInstance = null
  }
})

watch(
  () => [props.graphData, props.groupGraph],
  () => {
    hideTooltip()
    initGraph(props.graphData)
  },
)
</script>

<template>
  <div class="topology-canvas-wrapper">
    <div ref="containerRef" class="topology-canvas" />
    <div
      v-if="tooltipVisible && tooltipData"
      class="node-tooltip"
      :style="{ left: tooltipX + 'px', top: tooltipY + 'px' }"
    >
      <div class="tooltip-header">
        <span class="tooltip-name">{{ tooltipData.name }}</span>
        <span class="tooltip-type">{{ tooltipData.typeName }}</span>
      </div>
      <div class="tooltip-row">
        <span class="tooltip-label">状态</span>
        <span class="tooltip-value" :class="`status-${tooltipData.status}`">{{ tooltipData.status }}</span>
      </div>
      <div v-if="tooltipData.dn" class="tooltip-row">
        <span class="tooltip-label">DN</span>
        <span class="tooltip-value">{{ tooltipData.dn }}</span>
      </div>
      <div v-if="tooltipData.attrs.length" class="tooltip-divider" />
      <div
        v-for="attr in tooltipData.attrs"
        :key="attr.label"
        class="tooltip-row"
      >
        <span class="tooltip-label">{{ attr.label }}</span>
        <span class="tooltip-value">{{ attr.value }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.topology-canvas-wrapper {
  position: relative;
  width: 100%;
  height: 100%;
}

.topology-canvas {
  width: 100%;
  height: 100%;
  background: #fafafa;
  border: 1px solid #e8e8e8;
  border-radius: 4px;
}

.node-tooltip {
  position: absolute;
  min-width: 200px;
  max-width: 320px;
  background: rgba(0, 0, 0, 0.85);
  color: #fff;
  padding: 10px 12px;
  border-radius: 6px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
  pointer-events: none;
  z-index: 1000;
  font-size: 12px;
  line-height: 1.6;
}

.tooltip-header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 6px;
  padding-bottom: 6px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.15);
}

.tooltip-name {
  font-weight: 600;
  font-size: 13px;
  word-break: break-all;
}

.tooltip-type {
  color: rgba(255, 255, 255, 0.6);
  font-size: 11px;
  flex-shrink: 0;
}

.tooltip-row {
  display: flex;
  gap: 8px;
  align-items: flex-start;
}

.tooltip-label {
  color: rgba(255, 255, 255, 0.65);
  min-width: 56px;
  flex-shrink: 0;
}

.tooltip-value {
  color: #fff;
  word-break: break-all;
  flex: 1;
}

.tooltip-value.status-online {
  color: #52c41a;
}

.tooltip-value.status-offline {
  color: #f5222d;
}

.tooltip-value.status-warning {
  color: #faad14;
}

.tooltip-divider {
  height: 1px;
  background: rgba(255, 255, 255, 0.15);
  margin: 6px 0;
}
</style>
