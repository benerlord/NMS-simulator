import { apiGet, apiPost, apiDelete } from './http'

export type TokenAuthType = 'xtoken' | 'basic'

export interface TokenItem {
  token: string
  issuedAt: string
  expiresAt: string
  revoked: boolean
  issuedByApi: string | null
  meta: Record<string, unknown>
}

export interface TokenCreate {
  token: string
  expiresAt: string
  authType?: TokenAuthType
  issuedByApi?: string | null
  meta?: Record<string, unknown>
}

export interface TokenListParams {
  revoked?: boolean | null
  notExpired?: boolean
  page?: number
  pageSize?: number
}

export interface TokenListResult {
  items: TokenItem[]
  total: number
  page: number
  pageSize: number
}

export const tokenApi = {
  list: (params?: TokenListParams): Promise<TokenListResult> =>
    apiGet('/tokens', params as Record<string, unknown> | undefined),

  create: (data: TokenCreate): Promise<TokenItem> => apiPost('/tokens', data),

  revoke: (token: string): Promise<TokenItem> =>
    apiPost(`/tokens/${encodeURIComponent(token)}/revoke`, {}),

  deleteExpired: (): Promise<{ deleted: number }> => apiDelete('/tokens/expired'),
}
