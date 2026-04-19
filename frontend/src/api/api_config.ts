import { apiGet, apiPost, apiPut, apiPatch, apiDelete } from './http'

export type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
export type DataSource = 'sql' | 'static'

export interface ApiConfigItem {
  id: string
  name: string
  method: HttpMethod
  path: string
  enabled: boolean
  groupName: string | null
  dataSource: DataSource
  topologyId: string | null
  createdAt: string
  updatedAt: string
}

export interface ApiConfigDetail extends ApiConfigItem {
  sqlText: string | null
  config: Record<string, unknown>
}

export interface ApiConfigCreate {
  name: string
  method: HttpMethod
  path: string
  enabled?: boolean
  groupName?: string | null
  dataSource: DataSource
  topologyId?: string | null
  sqlText?: string | null
  config?: Record<string, unknown>
}

export interface ApiConfigUpdate {
  name?: string
  method?: HttpMethod
  path?: string
  groupName?: string | null
  dataSource?: DataSource
  sqlText?: string | null
  config?: Record<string, unknown>
}

export interface ApiConfigListParams {
  groupName?: string | null
  enabled?: boolean | null
  topologyId?: string | null
  method?: HttpMethod | null
  path?: string | null
  page?: number
  pageSize?: number
}

export interface ApiConfigListResult {
  items: ApiConfigItem[]
  total: number
  page: number
  pageSize: number
}

export const apiConfigApi = {
  list: (params?: ApiConfigListParams): Promise<ApiConfigListResult> =>
    apiGet('/apis', params as Record<string, unknown> | undefined),

  get: (id: string): Promise<ApiConfigDetail> =>
    apiGet(`/apis/${id}`),

  create: (data: ApiConfigCreate): Promise<ApiConfigDetail> =>
    apiPost('/apis', data),

  update: (id: string, data: ApiConfigUpdate): Promise<ApiConfigDetail> =>
    apiPut(`/apis/${id}`, data),

  patchEnabled: (id: string, enabled: boolean): Promise<ApiConfigDetail> =>
    apiPatch(`/apis/${id}/enabled`, { enabled }),

  patchTopology: (id: string, topologyId: string | null): Promise<ApiConfigDetail> =>
    apiPatch(`/apis/${id}/topology`, { topologyId }),

  delete: (id: string): Promise<{ id: string }> =>
    apiDelete(`/apis/${id}`),
}
