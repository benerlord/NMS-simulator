import { apiGet } from './http'

export interface AvailableNodeFields {
  systemFields: string[]
  customFields: string[]
}

export const nodeFieldsApi = {
  available: () => apiGet<AvailableNodeFields>('/node-fields/available'),
}
