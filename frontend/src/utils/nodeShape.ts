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
