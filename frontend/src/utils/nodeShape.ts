import { Graph } from '@antv/x6'
import { getNodeIconByCode } from './nodeIcons'

export const INFRA_NODE_SHAPE = 'infra-node'
export const INFRA_NODE_WIDTH = 80
export const INFRA_NODE_HEIGHT = 90
const ICON_SIZE = 56

let registered = false

export function registerInfraNodeShape() {
  if (registered) return
  registered = true
  Graph.registerNode(INFRA_NODE_SHAPE, {
    width: INFRA_NODE_WIDTH,
    height: INFRA_NODE_HEIGHT,
    markup: [
      { tagName: 'image', selector: 'icon' },
      { tagName: 'text', selector: 'label' },
    ],
    attrs: {
      icon: {
        width: ICON_SIZE,
        height: ICON_SIZE,
        x: (INFRA_NODE_WIDTH - ICON_SIZE) / 2,
        y: 0,
        'xlink:href': '',
      },
      label: {
        refX: INFRA_NODE_WIDTH / 2,
        refY: ICON_SIZE + 4,
        textAnchor: 'middle',
        textVerticalAnchor: 'top',
        fontSize: 12,
        fill: '#262626',
      },
    },
  })
}

export function buildInfraNodeAttrs(code: string | null | undefined, label: string) {
  return {
    icon: { 'xlink:href': getNodeIconByCode(code) },
    label: { text: label },
  }
}

// ============ Macro Node Shape ============

export const MACRO_NODE_SHAPE = 'macro-node'
export const MACRO_NODE_WIDTH = 200
export const MACRO_NODE_HEIGHT = 88

export function registerMacroNodeShape() {
  try {
    Graph.registerNode(MACRO_NODE_SHAPE, {
      width: MACRO_NODE_WIDTH,
      height: MACRO_NODE_HEIGHT,
      markup: [
        { tagName: 'rect', selector: 'body' },
        { tagName: 'rect', selector: 'innerBorder' },
        { tagName: 'text', selector: 'groupName' },
        { tagName: 'text', selector: 'nodeCount' },
        { tagName: 'rect', selector: 'statusBarBg' },
        { tagName: 'rect', selector: 'statusFill' },
        { tagName: 'text', selector: 'statusText' },
      ],
      attrs: {
        body: {
          width: MACRO_NODE_WIDTH,
          height: MACRO_NODE_HEIGHT,
          fill: '#fff',
          stroke: '#1890ff',
          strokeWidth: 2,
          rx: 6,
          ry: 6,
        },
        innerBorder: {
          x: 3,
          y: 3,
          width: MACRO_NODE_WIDTH - 6,
          height: MACRO_NODE_HEIGHT - 6,
          fill: 'none',
          stroke: '#1890ff',
          strokeWidth: 1,
          rx: 3,
          ry: 3,
        },
        groupName: {
          x: MACRO_NODE_WIDTH / 2,
          y: 22,
          textAnchor: 'middle',
          textVerticalAnchor: 'middle',
          fontSize: 15,
          fontWeight: 'bold',
          fill: '#262626',
          text: '',
        },
        nodeCount: {
          x: MACRO_NODE_WIDTH / 2,
          y: 44,
          textAnchor: 'middle',
          textVerticalAnchor: 'middle',
          fontSize: 13,
          fill: '#8c8c8c',
          text: '',
        },
        statusBarBg: {
          x: 8,
          y: 58,
          width: MACRO_NODE_WIDTH - 16,
          height: 6,
          rx: 3,
          ry: 3,
          fill: '#f0f0f0',
        },
        statusFill: {
          x: 8,
          y: 58,
          width: 0,
          height: 6,
          rx: 3,
          ry: 3,
          fill: '#52c41a',
        },
        statusText: {
          x: MACRO_NODE_WIDTH / 2,
          y: 74,
          textAnchor: 'middle',
          textVerticalAnchor: 'middle',
          fontSize: 10,
          fill: '#8c8c8c',
          text: '',
        },
      },
    })
  } catch {
    // Already registered (HMR / SPA re-entry)
  }
}

export function buildMacroNodeAttrs(params: {
  groupName: string
  nodeCount: number
  onlineRatio?: number
  statusLabel?: string
}) {
  const { groupName, nodeCount, onlineRatio = 1, statusLabel } = params
  const fillWidth = Math.round((MACRO_NODE_WIDTH - 16) * Math.max(0, Math.min(1, onlineRatio)))
  return {
    groupName: { text: groupName },
    nodeCount: { text: `× ${nodeCount.toLocaleString()}` },
    statusFill: { width: fillWidth, fill: onlineRatio > 0 ? '#52c41a' : '#d9d9d9' },
    statusText: { text: statusLabel ?? '' },
  }
}
