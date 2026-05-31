import http, { apiGet, apiPost, apiPut, apiPatch, apiDelete } from './http'

export type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
export type DataSource = 'sql' | 'static'

// ---------- M5: 请求契约 / 鉴权 ----------
// 落到 api_configs.config.{request, auth}；后端 schema 见 backend/app/admin/schemas/request_spec.py。

export type QueryParamType = 'string' | 'int' | 'bool'
export type BodyContentType =
  | 'application/json'
  | 'application/x-www-form-urlencoded'
  | 'text/plain'
export type AuthType = 'none' | 'xtoken' | 'basic'

export interface HeaderSpec {
  name: string
  required: boolean
  expectValue?: string | null
  example?: string | null
  description?: string | null
}

export interface QuerySpec {
  name: string
  type: QueryParamType
  required: boolean
  example?: string | null
  description?: string | null
}

export interface BodySpec {
  contentType: BodyContentType
  required: boolean
  example?: string | null
  description?: string | null
}

export interface RequestSpec {
  headers?: HeaderSpec[]
  query?: QuerySpec[]
  body?: BodySpec | null
}

export interface AuthConfig {
  type: AuthType
  headerName?: string | null
}

export interface ApiConfigItem {
  id: string
  name: string
  method: HttpMethod
  path: string
  enabled: boolean
  groupName: string | null
  domainId: string | null
  domainName: string | null
  category: string | null
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
  domainId?: string | null
  category?: string | null
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
  domainId?: string | null
  category?: string | null
  dataSource?: DataSource
  sqlText?: string | null
  config?: Record<string, unknown>
}

export interface ApiConfigListParams {
  groupName?: string | null
  domainId?: string | null
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

// LEGACY-06: 切换拓扑前的预扫描结果
export interface TopologySwitchPreview {
  missingViews: string[]
  availableViews: string[]
  currentSqlReferences: string[]
  warning: string | null
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

  // LEGACY-06: 切换前调用此端点，把 missingViews 列表呈现在二次确认弹窗里
  fetchTopologySwitchPreview: (
    id: string,
    targetTopologyId: string,
  ): Promise<TopologySwitchPreview> =>
    apiGet(`/apis/${id}/topology-switch-preview`, { targetTopologyId }),

  delete: (id: string): Promise<{ id: string }> =>
    apiDelete(`/apis/${id}`),

  export: (params?: { domainId?: string; ids?: string[] }): Promise<{ schemaVersion: string; exportedAt: string; apis: ApiConfigDetail[] }> =>
    apiPost('/apis/export', params || {}),

  import: (file: File): Promise<{ created: number; updated: number; errors: string[] }> => {
    const form = new FormData()
    form.append('file', file)
    return http.post('/apis/import', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then(r => r.data.data)
  },
}
