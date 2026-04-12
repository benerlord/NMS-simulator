/**
 * X6 Graph initialization and custom node/edge registration.
 */
import { Graph, Shape } from '@antv/x6';

const DEVICE_ICONS: Record<string, string> = {
  router: 'M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z',
  switch: 'M20 13H4c-.55 0-1 .45-1 1v6c0 .55.45 1 1 1h16c.55 0 1-.45 1-1v-6c0-.55-.45-1-1-1zM7 19c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2zM20 3H4c-.55 0-1 .45-1 1v6c0 .55.45 1 1 1h16c.55 0 1-.45 1-1V4c0-.55-.45-1-1-1zM7 9c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2z',
  firewall: 'M12 1L3 5v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V5l-9-4zm0 10.99h7c-.53 4.12-3.28 7.79-7 8.94V12H5V6.3l7-3.11v8.8z',
  server: 'M4 1h16c1.1 0 2 .9 2 2v4c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V3c0-1.1.9-2 2-2zm0 8h16c1.1 0 2 .9 2 2v4c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2v-4c0-1.1.9-2 2-2zm0 8h16c1.1 0 2 .9 2 2v4c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2v-4c0-1.1.9-2 2-2z',
  host: 'M21 2H3c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h7l-2 3v1h8v-1l-2-3h7c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 12H3V4h18v10z',
};

const STATUS_COLORS: Record<string, string> = {
  online: '#52c41a',
  offline: '#ff4d4f',
  maintenance: '#faad14',
};

export function registerCustomNode() {
  Graph.registerNode('device-node', {
    inherit: 'rect',
    width: 160,
    height: 64,
    attrs: {
      body: {
        strokeWidth: 2,
        stroke: '#d9d9d9',
        fill: '#fff',
        rx: 8,
        ry: 8,
      },
      icon: {
        refX: 12,
        refY: 16,
        width: 24,
        height: 24,
        fill: '#1890ff',
      },
      label: {
        refX: 44,
        refY: 16,
        textAnchor: 'start',
        textVerticalAnchor: 'top',
        fontSize: 13,
        fontWeight: 600,
        fill: '#262626',
      },
      dn: {
        refX: 44,
        refY: 34,
        textAnchor: 'start',
        textVerticalAnchor: 'top',
        fontSize: 10,
        fill: '#8c8c8c',
      },
      portCount: {
        refX: 44,
        refY: 48,
        textAnchor: 'start',
        textVerticalAnchor: 'top',
        fontSize: 10,
        fill: '#8c8c8c',
      },
      statusDot: {
        refX: 142,
        refY: 8,
        r: 5,
        fill: '#52c41a',
      },
    },
    markup: [
      { tagName: 'rect', selector: 'body' },
      { tagName: 'path', selector: 'icon', groupSelector: 'iconGroup' },
      { tagName: 'text', selector: 'label' },
      { tagName: 'text', selector: 'dn' },
      { tagName: 'text', selector: 'portCount' },
      { tagName: 'circle', selector: 'statusDot' },
    ],
    ports: {
      groups: {
        link: {
          position: { name: 'absolute' },
          attrs: {
            circle: {
              r: 6,
              magnet: true,
              stroke: '#1890ff',
              strokeWidth: 2,
              fill: '#fff',
              style: { visibility: 'hidden' },
            },
          },
        },
      },
      items: [
        { group: 'link', id: 'top', args: { x: '50%', y: 0 } },
        { group: 'link', id: 'bottom', args: { x: '50%', y: '100%' } },
        { group: 'link', id: 'left', args: { x: 0, y: '50%' } },
        { group: 'link', id: 'right', args: { x: '100%', y: '50%' } },
      ],
    },
  }, true);

  Graph.registerEdge('topology-edge', {
    inherit: 'edge',
    attrs: {
      line: {
        stroke: '#a2b1c3',
        strokeWidth: 2,
        targetMarker: null,
      },
    },
    labels: [{
      attrs: {
        label: {
          fontSize: 10,
          fill: '#8c8c8c',
        },
      },
      position: { distance: 0.5 },
    }],
    router: { name: 'manhattan' },
    connector: { name: 'rounded' },
  }, true);
}

export function createGraph(container: HTMLElement): Graph {
  registerCustomNode();

  const graph = new Graph({
    container,
    autoResize: true,
    background: { color: '#f5f5f5' },
    grid: {
      visible: true,
      type: 'doubleMesh',
      args: [
        { color: '#eee', thickness: 1 },
        { color: '#ddd', thickness: 1, factor: 4 },
      ],
    },
    mousewheel: { enabled: true, zoomAtMousePosition: true, modifiers: [], minScale: 0.2, maxScale: 3 },
    panning: { enabled: true, modifiers: [] },
    selecting: { enabled: true, rubberband: true, multiple: true, modifiers: ['ctrl'] },
    connecting: {
      snap: true,
      allowBlank: false,
      allowMulti: true,
      allowLoop: false,
      highlight: true,
      createEdge() {
        return new Shape.Edge({
          shape: 'topology-edge',
          attrs: { line: { stroke: '#a2b1c3', strokeWidth: 2, targetMarker: null } },
          router: { name: 'manhattan' },
          connector: { name: 'rounded' },
        });
      },
      validateConnection({ sourceCell, targetCell }) {
        return sourceCell?.id !== targetCell?.id;
      },
    },
    highlighting: {
      magnetAvailable: {
        name: 'stroke',
        args: { attrs: { fill: '#fff', stroke: '#1890ff' } },
      },
    },
  });

  // Show ports on hover
  graph.on('node:mouseenter', ({ node }) => {
    const ports = node.getPorts();
    ports.forEach(port => {
      node.portProp(port.id!, 'attrs/circle/style/visibility', 'visible');
    });
  });
  graph.on('node:mouseleave', ({ node }) => {
    const ports = node.getPorts();
    ports.forEach(port => {
      node.portProp(port.id!, 'attrs/circle/style/visibility', 'hidden');
    });
  });

  return graph;
}

export function deviceToNode(dev: Device) {
  const iconPath = DEVICE_ICONS[dev.type] || DEVICE_ICONS['host'];
  const statusColor = STATUS_COLORS[dev.status] || '#d9d9d9';
  return {
    id: dev.id,
    shape: 'device-node',
    x: dev.x || 100,
    y: dev.y || 100,
    attrs: {
      icon: { d: iconPath },
      label: { text: dev.name },
      dn: { text: dev.dn || '' },
      statusDot: { fill: statusColor },
    },
    data: { device: dev },
  };
}

export function linkToEdge(link: Link, devices: Device[]) {
  const srcDev = devices.find(d => d.id === link.sourceDeviceId);
  const tgtDev = devices.find(d => d.id === link.targetDeviceId);
  if (!srcDev || !tgtDev) return null;

  const typeColors: Record<string, string> = {
    physical: '#a2b1c3',
    logical: '#722ed1',
    aggregate: '#fa8c16',
  };

  return {
    id: link.id,
    shape: 'topology-edge',
    source: { cell: link.sourceDeviceId },
    target: { cell: link.targetDeviceId },
    attrs: {
      line: {
        stroke: typeColors[link.type] || '#a2b1c3',
        strokeDasharray: link.type === 'logical' ? '5 5' : undefined,
      },
    },
    labels: link.bandwidth ? [{
      attrs: { label: { text: link.bandwidth } },
      position: { distance: 0.5 },
    }] : [],
    data: { link },
  };
}

// Import types locally to avoid circular deps
interface Device {
  id: string;
  name: string;
  type: string;
  dn: string;
  status: string;
  x?: number;
  y?: number;
}

interface Link {
  id: string;
  sourceDeviceId: string;
  sourcePortId: string;
  targetDeviceId: string;
  targetPortId: string;
  type: string;
  bandwidth?: string;
  status: string;
}
