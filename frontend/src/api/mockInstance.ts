import { apiGet, apiPost, apiPut, apiPatch, apiDelete } from './http'

export interface MockInstanceItem {
  id: string
  name: string
  topologyId: string
  topologyName: string
  port: number
  description: string | null
  enabled: boolean
  apiCount: number
  createdAt: string
  updatedAt: string
}

export interface MockInstanceCreate {
  name: string
  topologyId: string
  port: number
  description?: string | null
  enabled?: boolean
}

export interface MockInstanceUpdate {
  name?: string | null
  topologyId?: string | null
  port?: number
  description?: string | null
  enabled?: boolean
}

export const mockInstanceApi = {
  list: (): Promise<{ items: MockInstanceItem[]; total: number }> =>
    apiGet('/mock-instances'),

  create: (data: MockInstanceCreate): Promise<{ id: string }> =>
    apiPost('/mock-instances', data),

  update: (id: string, data: MockInstanceUpdate): Promise<{ id: string }> =>
    apiPut(`/mock-instances/${id}`, data),

  delete: (id: string): Promise<{ id: string }> =>
    apiDelete(`/mock-instances/${id}`),

  patchEnabled: (id: string, enabled: boolean): Promise<{ id: string }> =>
    apiPatch(`/mock-instances/${id}/enabled`, { enabled }),
}
