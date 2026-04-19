import { shallowRef, ref } from 'vue'
import {
  apiConfigApi,
  type ApiConfigCreate,
  type ApiConfigDetail,
  type ApiConfigItem,
  type ApiConfigListParams,
  type ApiConfigUpdate,
  type HttpMethod,
} from '@/api/api_config'

export interface UseApiConfigsOptions {
  page?: number
  pageSize?: number
  method?: HttpMethod | null
  enabled?: boolean | null
  path?: string | null
  topologyId?: string | null
}

export function useApiConfigs(options: UseApiConfigsOptions = {}) {
  const items = shallowRef<ApiConfigItem[]>([])
  const total = ref(0)
  const loading = ref(false)

  const page = ref(options.page ?? 1)
  const pageSize = ref(options.pageSize ?? 20)
  const method = ref<HttpMethod | null>(options.method ?? null)
  const enabled = ref<boolean | null>(options.enabled ?? null)
  const path = ref<string | null>(options.path ?? null)
  const topologyId = ref<string | null>(options.topologyId ?? null)

  async function fetchApis() {
    loading.value = true
    try {
      const params: ApiConfigListParams = {
        page: page.value,
        pageSize: pageSize.value,
      }
      if (method.value) params.method = method.value
      if (enabled.value !== null) params.enabled = enabled.value
      if (path.value) params.path = path.value
      if (topologyId.value) params.topologyId = topologyId.value

      const result = await apiConfigApi.list(params)
      items.value = result.items
      total.value = result.total
    } finally {
      loading.value = false
    }
  }

  async function createApi(data: ApiConfigCreate): Promise<ApiConfigDetail> {
    const result = await apiConfigApi.create(data)
    await fetchApis()
    return result
  }

  async function updateApi(id: string, data: ApiConfigUpdate): Promise<ApiConfigDetail> {
    const result = await apiConfigApi.update(id, data)
    await fetchApis()
    return result
  }

  async function toggleEnabled(id: string, value: boolean) {
    await apiConfigApi.patchEnabled(id, value)
    await fetchApis()
  }

  async function deleteApi(id: string) {
    await apiConfigApi.delete(id)
    await fetchApis()
  }

  function onPageChange(p: number, ps: number) {
    page.value = p
    pageSize.value = ps
    fetchApis()
  }

  function onFilterChange(filters: {
    method?: HttpMethod | null
    enabled?: boolean | null
    path?: string | null
  }) {
    if (filters.method !== undefined) method.value = filters.method
    if (filters.enabled !== undefined) enabled.value = filters.enabled
    if (filters.path !== undefined) path.value = filters.path
    page.value = 1
    fetchApis()
  }

  return {
    items,
    total,
    loading,
    page,
    pageSize,
    method,
    enabled,
    path,
    topologyId,
    fetchApis,
    createApi,
    updateApi,
    toggleEnabled,
    deleteApi,
    onPageChange,
    onFilterChange,
  }
}
