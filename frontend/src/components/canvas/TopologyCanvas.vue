<script setup lang="ts">
import { onMounted, onBeforeUnmount, shallowRef, ref, watch } from 'vue'
import { Graph, History } from '@antv/x6'
import type { TopologyGraph } from '@/api/topology'
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
} from '@/utils/nodeShape'

registerInfraNodeShape()

interface Props {
  graphData: TopologyGraph | null
  graph?: unknown
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'init', graph: unknown): void
  (e: 'nodeMoved', nodeId: string, x: number, y: number): void
  (e: 'nodeClick', nodeId: string): void
  (e: 'edgeClick', edgeId: string): void
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

    graph.resetCells(cells)
    history.enable()
  }

  graph.on('node:moved', (args: { node: Node; x: number; y: number }) => {
    emit('nodeMoved', args.node.id, args.x, args.y)
  })

  graph.on('node:click', (args: { node: Node }) => {
    hideTooltip()
    emit('nodeClick', args.node.id)
  })

  graph.on('edge:click', (args: { edge: Cell }) => {
    hideTooltip()
    emit('edgeClick', args.edge.id)
  })

  graph.on('node:mouseenter', ({ node, e }: { node: Node; e: MouseEvent }) => {
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
  () => props.graphData,
  (data) => {
    hideTooltip()
    initGraph(data)
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
