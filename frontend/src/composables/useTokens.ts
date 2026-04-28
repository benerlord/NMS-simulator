import { ref, shallowRef } from 'vue'
import {
  tokenApi,
  type TokenCreate,
  type TokenItem,
  type TokenListParams,
} from '@/api/token'

export interface UseTokensOptions {
  page?: number
  pageSize?: number
  notExpired?: boolean
  revoked?: boolean | null
}

export function useTokens(options: UseTokensOptions = {}) {
  const items = shallowRef<TokenItem[]>([])
  const total = ref(0)
  const loading = ref(false)

  const page = ref(options.page ?? 1)
  const pageSize = ref(options.pageSize ?? 20)
  const notExpired = ref<boolean>(options.notExpired ?? false)
  const revoked = ref<boolean | null>(options.revoked ?? null)

  async function fetchTokens() {
    loading.value = true
    try {
      const params: TokenListParams = {
        page: page.value,
        pageSize: pageSize.value,
      }
      if (notExpired.value) params.notExpired = true
      if (revoked.value !== null) params.revoked = revoked.value

      const result = await tokenApi.list(params)
      items.value = result.items
      total.value = result.total
    } finally {
      loading.value = false
    }
  }

  async function createToken(data: TokenCreate): Promise<TokenItem> {
    const result = await tokenApi.create(data)
    await fetchTokens()
    return result
  }

  async function revokeToken(token: string): Promise<TokenItem> {
    const result = await tokenApi.revoke(token)
    await fetchTokens()
    return result
  }

  async function deleteExpired(): Promise<number> {
    const result = await tokenApi.deleteExpired()
    await fetchTokens()
    return result.deleted
  }

  function onPageChange(p: number, ps: number) {
    page.value = p
    pageSize.value = ps
    fetchTokens()
  }

  function onFilterChange(filters: {
    notExpired?: boolean
    revoked?: boolean | null
  }) {
    if (filters.notExpired !== undefined) notExpired.value = filters.notExpired
    if (filters.revoked !== undefined) revoked.value = filters.revoked
    page.value = 1
    fetchTokens()
  }

  return {
    items,
    total,
    loading,
    page,
    pageSize,
    notExpired,
    revoked,
    fetchTokens,
    createToken,
    revokeToken,
    deleteExpired,
    onPageChange,
    onFilterChange,
  }
}
