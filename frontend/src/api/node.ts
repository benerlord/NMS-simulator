import { apiGet, apiPost, apiPut, apiPatch, apiDelete } from './http'

export interface NodeCreate {
  nodeTypeId: string
  name: string
  dn?: string | null
  status?: string
}

export interface NodeUpdate {
  name?: string | null
  dn?: string | null
  status?: string | null
}

export interface NodePositionUpdate {
  x: number
  y: number
}

export interface NodeDetail {
  id: string
  topologyId: string
  nodeTypeId: string
  name: string
  dn: string | null
  status: string
  createdAt: string
  updatedAt: string
  x: number | null
  y: number | null
  attrs?: Record<string, string | null>
}

export interface NodeItem {
  id: string
  topologyId: string
  nodeTypeId: string
  name: string
  dn: string | null
  status: string
  createdAt: string
  updatedAt: string
  x: number | null
  y: number | null
}

export interface NodeListResponse {
  items: NodeItem[]
  total: number
  page: number
  pageSize: number
}

export interface BulkNodeItem {
  name: string
  x: number
  y: number
  attrs: Record<string, string | null>
}

export interface BulkNodesCreateRequest {
  nodeTypeId: string
  items: BulkNodeItem[]
}

export interface BulkCreatedItem {
  index: number
  id: string
  name: string
}

export interface BulkSkippedItem {
  index: number
  name: string | null
  reason: string
}

export interface BulkNodesCreateResponse {
  created: BulkCreatedItem[]
  skipped: BulkSkippedItem[]
}

export const nodeApi = {
  list: (topologyId: string, params?: { nodeTypeId?: string; status?: string; page?: number; pageSize?: number }): Promise<NodeListResponse> =>
    apiGet(`/topologies/${topologyId}/nodes`, params),

  get: (id: string): Promise<NodeDetail> =>
    apiGet(`/nodes/${id}`),

  create: (topologyId: string, data: NodeCreate): Promise<{ id: string }> =>
    apiPost(`/topologies/${topologyId}/nodes`, data),

  update: (id: string, data: NodeUpdate): Promise<{ id: string }> =>
    apiPut(`/nodes/${id}`, data),

  delete: (id: string): Promise<{ id: string }> =>
    apiDelete(`/nodes/${id}`),

  updatePosition: (id: string, data: NodePositionUpdate): Promise<{ id: string }> =>
    apiPatch(`/nodes/${id}/position`, data),

  setAttrs: (id: string, attrs: Record<string, string | null>): Promise<{ id: string }> => {
    const attrsList = Object.entries(attrs).map(([field_key, value]) => ({ field_key, value }))
    return apiPut(`/nodes/${id}/attrs`, attrsList)
  },

  bulkCreate: (
    topologyId: string,
    data: BulkNodesCreateRequest,
  ): Promise<BulkNodesCreateResponse> =>
    apiPost(`/topologies/${topologyId}/nodes/bulk`, data),
}
