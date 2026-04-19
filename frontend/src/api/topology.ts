export interface TopologyStats {
  nodeCount: number
  edgeCount: number
}

export interface TopologyListItem {
  id: string
  name: string
  description: string | null
  version: number
  createdAt: string
  updatedAt: string
}

export interface TopologyDetail extends TopologyListItem {
  stats: TopologyStats
}

export interface TopologyCreate {
  name: string
  description?: string | null
}

export interface TopologyUpdate {
  name?: string
  description?: string | null
}

export interface PageResult<T> {
  items: T[]
  total: number
  page: number
  pageSize: number
}

export interface DeleteResult {
  deletedCount?: number
}

// --- Graph types ---
export interface TopologyCanvasNode {
  nodeId: string
  x: number
  y: number
}

export interface TopologyNode {
  id: string
  topologyId: string
  nodeTypeId: string
  name: string
  dn: string | null
  status: string
  createdAt: string
  updatedAt: string
}

export interface TopologyEdge {
  id: string
  topologyId: string
  edgeTypeId: string
  sourceId: string
  targetId: string
  status: string
  createdAt: string
  updatedAt: string
}

export interface TopologyGraph {
  id: string
  name: string
  description: string | null
  version: number
  nodes: TopologyNode[]
  edges: TopologyEdge[]
  canvasNodes: TopologyCanvasNode[]
}
