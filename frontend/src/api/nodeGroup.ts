import { apiGet, apiPost, apiPut, apiPatch, apiDelete } from './http'

// ============ Attr Strategy ============

export interface AttrStrategyItem {
  fieldKey: string
  strategy: 'fixed' | 'random' | 'increment' | 'range'
  fixedValue?: string | null
  pool?: string[] | null
  base?: string | null
  step?: string | null
  min?: number | null
  max?: number | null
}

// ============ Edge Strategy ============

export interface EdgeStrategyItem {
  targetGroupId: string
  edgeTypeCode: string
  mode: 'modulo' | 'one_to_n' | 'all_to_all' | 'dense'
  ratioK?: number | null
}

// ============ NodeGroup CRUD ============

export interface NodeGroupCreate {
  nodeTypeId: string
  groupName: string
  nodeCount: number
  nameTemplate?: string
  attrStrategies?: AttrStrategyItem[]
  edgeStrategies?: EdgeStrategyItem[] | null
}

export interface NodeGroupUpdate {
  groupName?: string | null
  nodeCount?: number | null
  nameTemplate?: string | null
  attrStrategies?: AttrStrategyItem[] | null
  edgeStrategies?: EdgeStrategyItem[] | null
}

export interface NodeGroupItem {
  id: string
  topologyId: string
  nodeTypeId: string
  groupName: string
  nodeCount: number
  nameTemplate: string
  attrStrategies: AttrStrategyItem[]
  edgeStrategies: EdgeStrategyItem[] | null
  isMaterialized: boolean
  createdAt: string
  updatedAt: string
}

// ============ Materialize ============

export interface MaterializeProgress {
  phase: 'nodes' | 'edges' | 'done'
  current: number
  total: number
  pct: number
  elapsedMs: number
}

export interface MaterializeResult {
  materializedNodes: number
  materializedEdges: number
  elapsedMs: number
}

// ============ Group Graph ============

export interface MacroNodeStatus {
  online: number
  offline: number
}

export interface MacroNode {
  id: string
  topologyId: string
  nodeTypeId: string
  groupName: string
  nodeCount: number
  isMaterialized: boolean
  statusBreakdown: MacroNodeStatus
  x: number | null
  y: number | null
}

export interface MacroEdge {
  sourceGroupId: string
  targetGroupId: string
  edgeTypeCode: string
  mode: string
  ratioK: number | null
  totalEdgeCount: number
  visualSourceIsMacro: boolean | null
}

export interface GroupGraphData {
  macroNodes: MacroNode[]
  macroEdges: MacroEdge[]
}

// ============ Node Group Alarms ============

export interface NodeGroupAlarmItem {
  id: string
  nodeGroupId: string
  alarmIndex: number
  attrs: Record<string, string | null>
  createdAt: string
  updatedAt: string
}

export interface NodeGroupAlarmCreate {
  attrs?: Record<string, string | null>
}

export interface NodeGroupAlarmAttrSet {
  attrs: Record<string, string | null>
}

// ============ API Functions ============

export const nodeGroupApi = {
  list: (topologyId: string): Promise<{ items: NodeGroupItem[] }> =>
    apiGet(`/topologies/${topologyId}/node-groups`),

  get: (id: string): Promise<NodeGroupItem> =>
    apiGet(`/node-groups/${id}`),

  create: (topologyId: string, data: NodeGroupCreate): Promise<{ id: string }> =>
    apiPost(`/topologies/${topologyId}/node-groups`, data),

  update: (id: string, data: NodeGroupUpdate): Promise<{ id: string }> =>
    apiPut(`/node-groups/${id}`, data),

  delete: (id: string): Promise<{ id: string }> =>
    apiDelete(`/node-groups/${id}`),

  materialize: (id: string): Promise<MaterializeResult> =>
    apiPost(`/node-groups/${id}/materialize`),

  getGroupGraph: (topologyId: string): Promise<GroupGraphData> =>
    apiGet(`/topologies/${topologyId}/group-graph`),

  updatePosition: (id: string, data: { x: number; y: number }): Promise<{ id: string; x: number; y: number }> =>
    apiPatch(`/node-groups/${id}/position`, data),

  listAlarms: (groupId: string): Promise<NodeGroupAlarmItem[]> =>
    apiGet(`/node-groups/${groupId}/alarms`),

  createAlarm: (groupId: string, data: NodeGroupAlarmCreate = {}): Promise<NodeGroupAlarmItem> =>
    apiPost(`/node-groups/${groupId}/alarms`, data),

  updateAlarmAttrs: (alarmId: string, data: NodeGroupAlarmAttrSet): Promise<NodeGroupAlarmItem> =>
    apiPut(`/node-group-alarms/${alarmId}/attrs`, data),

  deleteAlarm: (alarmId: string): Promise<null> =>
    apiDelete(`/node-group-alarms/${alarmId}`),
}
