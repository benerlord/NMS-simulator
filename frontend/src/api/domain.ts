import { apiGet, apiPost, apiPut, apiDelete } from './http'

export interface DomainItem {
  id: string
  name: string
  description: string | null
  topologyCount: number
  createdAt: string
  updatedAt: string
}

export interface DomainCreate {
  name: string
  description?: string | null
}

export interface DomainUpdate {
  name?: string | null
  description?: string | null
}

export const domainApi = {
  list: (): Promise<{ items: DomainItem[]; total: number }> =>
    apiGet('/domains'),

  create: (data: DomainCreate): Promise<{ id: string }> =>
    apiPost('/domains', data),

  update: (id: string, data: DomainUpdate): Promise<{ id: string }> =>
    apiPut(`/domains/${id}`, data),

  delete: (id: string): Promise<{ id: string }> =>
    apiDelete(`/domains/${id}`),

  fetchCategories: (domainId: string): Promise<string[]> =>
    apiGet(`/domains/${domainId}/categories`),

  renameCategory: (domainId: string, name: string, newName: string): Promise<{ domainId: string; oldName: string; newName: string }> =>
    apiPut(`/domains/${encodeURIComponent(domainId)}/categories/${encodeURIComponent(name)}`, { newName }),

  deleteCategory: (domainId: string, name: string): Promise<{ domainId: string; name: string }> =>
    apiDelete(`/domains/${encodeURIComponent(domainId)}/categories/${encodeURIComponent(name)}`),
}
