import { apiPatch } from './http'

export interface TopologyStats {
  nodeCount: number
  edgeCount: number
}

export interface TopologyListItem {
  id: string
  name: string
  description: string | null
  domainId: string | null
  domainName: string | null
  version: number
  createdAt: string
  updatedAt: string
}

export interface TopologyDetail extends TopologyListItem {
  stats: TopologyStats
  alarmSchemaId?: string | null
  nodeAlarmCount?: number
}

export interface TopologyCreate {
  name: string
  description?: string | null
  domainId?: string | null
}

export interface TopologyUpdate {
  name?: string
  description?: string | null
  domainId?: string | null
}

export interface PageResult<T> {
  items: T[]
  total: number
  page: number
  pageSize: number
}

export interface DeleteResult {
  deletedCount?: number
  // LEGACY-07: 删除拓扑时自动解绑 api_configs，回显被解绑接口数
  unboundApiCount?: number
}

// LEGACY-07: 删除拓扑前的预扫描结果（受影响的 api_configs）
export interface AffectedApi {
  id: string
  name: string
  method: string
  path: string
}

export interface TopologyDeleteImpact {
  topologyId: string
  topologyName: string
  affectedApiCount: number
  affectedApis: AffectedApi[]
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

// --- Import/Export (M4-02) ---
export interface TopologyExportNodeIo {
  id: string
  nodeTypeCode: string
  name: string
  dn: string | null
  status: string
  attrs: Record<string, unknown>
  canvas: { x: number; y: number } | null
}

export interface TopologyExportEdgeIo {
  id: string
  edgeTypeCode: string
  sourceId: string
  targetId: string
  status: string
  attrs: Record<string, unknown>
}

export interface TopologyExportMetaIo {
  name: string
  description: string | null
  version: number
}

export interface TopologyExportDoc {
  schemaVersion: string
  exportedAt: string
  topology: TopologyExportMetaIo
  nodes: TopologyExportNodeIo[]
  edges: TopologyExportEdgeIo[]
}

export interface TopologyImportResult {
  topologyId: string
  name: string
  nodeCount: number
  edgeCount: number
  canvasCount: number
}

// --- Alarm Schema Binding ---
export const topologyApi = {
  bindAlarmSchema: (
    id: string,
    alarmSchemaId: string | null,
    clearExisting = false,
  ): Promise<{ alarmSchemaId: string | null }> =>
    apiPatch(`/topologies/${id}/alarm-schema`, { alarmSchemaId, clearExisting }),
}
