import { apiGet, apiPost, apiPut, apiDelete } from './http'

export interface AlarmSchemaFieldItem {
  id: number
  alarmSchemaId: string
  fieldKey: string
  fieldLabel: string
  fieldType: 'text' | 'number' | 'select' | 'boolean'
  maxLength?: number | null
  defaultValue?: string | null
  options?: string | null
  required: boolean
  sortOrder: number
  mappingTarget?: string | null
}

export interface AlarmSchemaFieldInput {
  fieldKey: string
  fieldLabel: string
  fieldType: 'text' | 'number' | 'select' | 'boolean'
  maxLength?: number | null
  defaultValue?: string | null
  options?: string | null
  required?: boolean
  sortOrder?: number
  mappingTarget?: string | null
}

export interface AlarmSchemaItem {
  id: string
  code: string
  name: string
  description?: string | null
  createdAt: string
  updatedAt: string
  displayFieldKey?: string | null
}

export interface AlarmSchemaDetail extends AlarmSchemaItem {
  fields: AlarmSchemaFieldItem[]
}

export interface AlarmSchemaCreate {
  code: string
  name: string
  description?: string | null
  displayFieldKey?: string | null
  fields: AlarmSchemaFieldInput[]
}

export interface AlarmSchemaUpdate {
  name?: string
  description?: string | null
  displayFieldKey?: string | null
  fields?: AlarmSchemaFieldInput[]
}

export const alarmSchemaApi = {
  list: (): Promise<AlarmSchemaItem[]> =>
    apiGet('/alarm-schemas'),

  get: (id: string): Promise<AlarmSchemaDetail> =>
    apiGet(`/alarm-schemas/${id}`),

  create: (data: AlarmSchemaCreate): Promise<AlarmSchemaDetail> =>
    apiPost('/alarm-schemas', data),

  update: (id: string, data: AlarmSchemaUpdate): Promise<AlarmSchemaDetail> =>
    apiPut(`/alarm-schemas/${id}`, data),

  delete: (id: string): Promise<null> =>
    apiDelete(`/alarm-schemas/${id}`),
}
