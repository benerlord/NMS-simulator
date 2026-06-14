import http from './http'
import { apiGet, apiPost, apiPut, apiDelete } from './http'

// ============ 整批同步用字段输入（无 id） ============

export interface NodeTypeFieldInput {
  fieldKey: string
  fieldLabel: string
  fieldType: 'text' | 'number' | 'select' | 'boolean'
  maxLength?: number | null
  defaultValue?: string | null
  options?: string | null
  required?: boolean
  sortOrder?: number
}

export interface EdgeTypeFieldInput {
  fieldKey: string
  fieldLabel: string
  fieldType: 'text' | 'number' | 'select' | 'boolean'
  maxLength?: number | null
  defaultValue?: string | null
  options?: string | null
  required?: boolean
  sortOrder?: number
}

export interface FieldDeleteImpactItem {
  fieldKey: string
  affectedNodeCount: number  // 节点类型/边类型共用，边类型语义为"受影响的边数"
}

export interface FieldDeleteImpactResponse {
  items: FieldDeleteImpactItem[]
}

// ============ Node Types ============

export interface NodeTypeFieldItem {
  id: number
  nodeTypeId: string
  fieldKey: string
  fieldLabel: string
  fieldType: 'text' | 'number' | 'select' | 'boolean'
  maxLength: number | null
  defaultValue: string | null
  options: string | null
  required: boolean
  sortOrder: number
}

export interface NodeTypeItem {
  id: string
  code: string
  name: string
  category: string
  icon: string | null
  color: string | null
  shape: string | null
  renderMode: string
  dnTemplate: string | null
  description: string | null
  domainIds: string[]
  domainNames: string[]
  createdAt: string
  updatedAt: string
}

export interface NodeTypeDetail extends NodeTypeItem {
  fields: NodeTypeFieldItem[]
}

export interface NodeTypeCreate {
  code: string
  name: string
  category: string
  icon?: string | null
  color?: string | null
  shape?: string | null
  renderMode?: string
  dnTemplate?: string | null
  description?: string | null
  fields?: NodeTypeFieldInput[] | null
}

export interface NodeTypeUpdate {
  name?: string | null
  icon?: string | null
  color?: string | null
  shape?: string | null
  renderMode?: string | null
  dnTemplate?: string | null
  description?: string | null
  fields?: NodeTypeFieldInput[] | null
}

// ============ Edge Types ============

export interface EdgeTypeFieldItem {
  id: number
  edgeTypeId: string
  fieldKey: string
  fieldLabel: string
  fieldType: 'text' | 'number' | 'select' | 'boolean'
  maxLength: number | null
  defaultValue: string | null
  options: string | null
  required: boolean
  sortOrder: number
}

export interface EdgeTypeItem {
  id: string
  code: string
  name: string
  semantic: string
  directed: boolean
  exclusiveTarget: boolean
  allowSourceTypeCodes: string | null
  allowTargetTypeCodes: string | null
  lineStyle: string | null
  color: string | null
  description: string | null
  createdAt: string
  updatedAt: string
}

export interface EdgeTypeDetail extends EdgeTypeItem {
  fields: EdgeTypeFieldItem[]
}

export interface EdgeTypeCreate {
  code: string
  name: string
  semantic?: string
  directed?: boolean
  exclusiveTarget?: boolean
  allowSourceTypeCodes?: string | null
  allowTargetTypeCodes?: string | null
  lineStyle?: string | null
  color?: string | null
  description?: string | null
  fields?: EdgeTypeFieldInput[] | null
}

export interface EdgeTypeUpdate {
  name?: string | null
  semantic?: string | null
  directed?: boolean | null
  exclusiveTarget?: boolean | null
  allowSourceTypeCodes?: string | null
  allowTargetTypeCodes?: string | null
  lineStyle?: string | null
  color?: string | null
  description?: string | null
  fields?: EdgeTypeFieldInput[] | null
}

export interface TypeImportPreviewItem {
  code: string
  name: string
  oldName?: string | null
}

export interface TypeImportPreview {
  toCreate: TypeImportPreviewItem[]
  toUpdate: TypeImportPreviewItem[]
  errors: string[]
}

export interface TypeImportResult {
  created: number
  updated: number
  totalFields: number
  errors: string[]
}

export interface BatchDeleteResult {
  deletedCount: number
  skipped: { id: string; reason: string }[]
}

// ============ API Functions ============

export const nodeTypeApi = {
  list: (params?: { domainId?: string }): Promise<{ items: NodeTypeDetail[]; total: number }> =>
    apiGet('/node-types', params as Record<string, unknown>),

  importPreview: (file: File): Promise<TypeImportPreview> => {
    const form = new FormData()
    form.append('file', file)
    return http.post('/node-types/import/preview', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then(r => r.data.data)
  },

  import: (file: File): Promise<TypeImportResult> => {
    const form = new FormData()
    form.append('file', file)
    return http.post('/node-types/import', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then(r => r.data.data)
  },

  get: (id: string): Promise<NodeTypeDetail> =>
    apiGet(`/node-types/${id}`),

  create: (data: NodeTypeCreate): Promise<{ id: string }> =>
    apiPost('/node-types', data),

  update: (id: string, data: NodeTypeUpdate): Promise<{ id: string }> =>
    apiPut(`/node-types/${id}`, data),

  delete: (id: string): Promise<{ id: string }> =>
    apiDelete(`/node-types/${id}`),

  getFieldDeleteImpact: (typeId: string, fieldKeys: string[]): Promise<FieldDeleteImpactResponse> =>
    apiPost(`/node-types/${typeId}/fields/delete-impact`, { fieldKeys }),

  batchDelete: (ids: string[]): Promise<BatchDeleteResult> =>
    apiPost('/node-types/batch-delete', { ids }),

  updateDomains: (typeId: string, domainIds: string[]): Promise<{ id: string }> =>
    apiPut(`/node-types/${typeId}/domains`, { domainIds }),

  batchUpdateDomains: (nodeTypeIds: string[], domainIds: string[]): Promise<{ nodeTypeIds: string[]; domainIds: string[] }> =>
    apiPut('/node-types/domains', { nodeTypeIds, domainIds }),

  export: (ids?: string[]): Promise<Blob> =>
    http.post('/node-types/export', { ids }, { responseType: 'blob' }).then(r => r.data),
}

export const edgeTypeApi = {
  list: (): Promise<{ items: EdgeTypeDetail[]; total: number }> =>
    apiGet('/edge-types'),

  get: (id: string): Promise<EdgeTypeDetail> =>
    apiGet(`/edge-types/${id}`),

  create: (data: EdgeTypeCreate): Promise<{ id: string }> =>
    apiPost('/edge-types', data),

  update: (id: string, data: EdgeTypeUpdate): Promise<{ id: string }> =>
    apiPut(`/edge-types/${id}`, data),

  delete: (id: string): Promise<{ id: string }> =>
    apiDelete(`/edge-types/${id}`),

  getFieldDeleteImpact: (typeId: string, fieldKeys: string[]): Promise<FieldDeleteImpactResponse> =>
    apiPost(`/edge-types/${typeId}/fields/delete-impact`, { fieldKeys }),

  batchDelete: (ids: string[]): Promise<BatchDeleteResult> =>
    apiPost('/edge-types/batch-delete', { ids }),

  export: (ids?: string[]): Promise<{ items: EdgeTypeDetail[] }> =>
    apiPost('/edge-types/export', { ids }),
}
