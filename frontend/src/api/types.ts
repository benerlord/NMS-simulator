import { apiGet, apiPost, apiPut, apiDelete } from './http'

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
}

export interface NodeTypeUpdate {
  name?: string | null
  icon?: string | null
  color?: string | null
  shape?: string | null
  renderMode?: string | null
  dnTemplate?: string | null
  description?: string | null
}

export interface NodeTypeFieldCreate {
  fieldKey: string
  fieldLabel: string
  fieldType: 'text' | 'number' | 'select' | 'boolean'
  maxLength?: number | null
  defaultValue?: string | null
  options?: string | null
  required?: boolean
  sortOrder?: number
}

export interface NodeTypeFieldUpdate {
  fieldLabel?: string | null
  fieldType?: 'text' | 'number' | 'select' | 'boolean' | null
  maxLength?: number | null
  defaultValue?: string | null
  options?: string | null
  required?: boolean | null
  sortOrder?: number | null
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
}

export interface EdgeTypeFieldCreate {
  fieldKey: string
  fieldLabel: string
  fieldType: 'text' | 'number' | 'select' | 'boolean'
  maxLength?: number | null
  defaultValue?: string | null
  options?: string | null
  required?: boolean
  sortOrder?: number
}

export interface EdgeTypeFieldUpdate {
  fieldLabel?: string | null
  fieldType?: 'text' | 'number' | 'select' | 'boolean' | null
  maxLength?: number | null
  defaultValue?: string | null
  options?: string | null
  required?: boolean | null
  sortOrder?: number | null
}

export interface BatchDeleteResult {
  deletedCount: number
  skipped: { id: string; reason: string }[]
}

// ============ API Functions ============

export const nodeTypeApi = {
  list: (): Promise<{ items: NodeTypeDetail[]; total: number }> =>
    apiGet('/node-types'),

  get: (id: string): Promise<NodeTypeDetail> =>
    apiGet(`/node-types/${id}`),

  create: (data: NodeTypeCreate): Promise<{ id: string }> =>
    apiPost('/node-types', data),

  update: (id: string, data: NodeTypeUpdate): Promise<{ id: string }> =>
    apiPut(`/node-types/${id}`, data),

  delete: (id: string): Promise<{ id: string }> =>
    apiDelete(`/node-types/${id}`),

  createField: (typeId: string, data: NodeTypeFieldCreate): Promise<{ id: number }> =>
    apiPost(`/node-types/${typeId}/fields`, data),

  updateField: (typeId: string, fieldId: number, data: NodeTypeFieldUpdate): Promise<{ id: number }> =>
    apiPut(`/node-types/${typeId}/fields/${fieldId}`, data),

  deleteField: (typeId: string, fieldId: number): Promise<{ id: number }> =>
    apiDelete(`/node-types/${typeId}/fields/${fieldId}`),

  batchDelete: (ids: string[]): Promise<BatchDeleteResult> =>
    apiPost('/node-types/batch-delete', { ids }),

  export: (ids?: string[]): Promise<{ items: NodeTypeDetail[] }> =>
    apiPost('/node-types/export', { ids }),
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

  createField: (typeId: string, data: EdgeTypeFieldCreate): Promise<{ id: number }> =>
    apiPost(`/edge-types/${typeId}/fields`, data),

  updateField: (typeId: string, fieldId: number, data: EdgeTypeFieldUpdate): Promise<{ id: number }> =>
    apiPut(`/edge-types/${typeId}/fields/${fieldId}`, data),

  deleteField: (typeId: string, fieldId: number): Promise<{ id: number }> =>
    apiDelete(`/edge-types/${typeId}/fields/${fieldId}`),

  batchDelete: (ids: string[]): Promise<BatchDeleteResult> =>
    apiPost('/edge-types/batch-delete', { ids }),

  export: (ids?: string[]): Promise<{ items: EdgeTypeDetail[] }> =>
    apiPost('/edge-types/export', { ids }),
}
