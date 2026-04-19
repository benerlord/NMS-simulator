import { apiGet, apiPost, apiPut, apiDelete } from './http'

export interface EdgeCreate {
  topologyId: string
  edgeTypeId: string
  sourceId: string
  targetId: string
  status?: string
}

export interface EdgeUpdate {
  status?: string | null
}

export interface EdgeDetail {
  id: string
  topologyId: string
  edgeTypeId: string
  sourceId: string
  targetId: string
  status: string
  createdAt: string
  updatedAt: string
  attrs?: Record<string, string | null>
}

export interface EdgeItem {
  id: string
  topologyId: string
  edgeTypeId: string
  sourceId: string
  targetId: string
  status: string
  createdAt: string
  updatedAt: string
}

export interface EdgeListResponse {
  items: EdgeItem[]
  total: number
  page: number
  pageSize: number
}

export const edgeApi = {
  list: (topologyId: string, params?: { edgeTypeId?: string; sourceId?: string; targetId?: string; page?: number; pageSize?: number }): Promise<EdgeListResponse> =>
    apiGet(`/topologies/${topologyId}/edges`, params),

  get: (id: string): Promise<EdgeDetail> =>
    apiGet(`/edges/${id}`),

  create: (topologyId: string, data: EdgeCreate): Promise<{ id: string }> =>
    apiPost(`/topologies/${topologyId}/edges`, data),

  update: (id: string, data: EdgeUpdate): Promise<{ id: string }> =>
    apiPut(`/edges/${id}`, data),

  delete: (id: string): Promise<{ id: string }> =>
    apiDelete(`/edges/${id}`),

  setAttrs: (id: string, attrs: Record<string, string | null>): Promise<{ id: string }> => {
    const attrsList = Object.entries(attrs).map(([field_key, value]) => ({ field_key, value }))
    return apiPut(`/edges/${id}/attrs`, attrsList)
  },
}
