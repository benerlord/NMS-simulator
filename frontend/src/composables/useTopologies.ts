import { shallowRef, ref, watch } from 'vue'
import { apiGet, apiPost, apiPut, apiDelete } from '@/api/http'
import type {
  TopologyListItem,
  TopologyDetail,
  TopologyCreate,
  TopologyUpdate,
  TopologyExportDoc,
  TopologyImportResult,
  PageResult,
} from '@/api/topology'

export interface UseTopologiesOptions {
  page?: number
  pageSize?: number
  name?: string
  sort?: string
}

export function useTopologies(options: UseTopologiesOptions = {}) {
  const items = shallowRef<TopologyListItem[]>([])
  const total = ref(0)
  const loading = ref(false)

  const page = ref(options.page ?? 1)
  const pageSize = ref(options.pageSize ?? 20)
  const name = ref(options.name ?? '')
  const sort = ref(options.sort ?? 'updated_at,desc')

  async function fetchTopologies() {
    loading.value = true
    try {
      const params: Record<string, unknown> = {
        page: page.value,
        pageSize: pageSize.value,
        sort: sort.value,
      }
      if (name.value) params.name = name.value

      const result = await apiGet<PageResult<TopologyListItem>>('/topologies', params)
      items.value = result.items
      total.value = result.total
    } finally {
      loading.value = false
    }
  }

  async function createTopology(data: TopologyCreate): Promise<TopologyDetail> {
    const result = await apiPost<TopologyDetail>('/topologies', data)
    await fetchTopologies()
    return result
  }

  async function updateTopology(id: string, data: TopologyUpdate): Promise<TopologyDetail> {
    const result = await apiPut<TopologyDetail>(`/topologies/${id}`, data)
    await fetchTopologies()
    return result
  }

  async function deleteTopology(id: string): Promise<void> {
    await apiDelete(`/topologies/${id}`)
    await fetchTopologies()
  }

  async function deleteAllTopologies(): Promise<{ deletedCount: number }> {
    const result = await apiDelete<{ deletedCount: number }>('/topologies')
    await fetchTopologies()
    return result ?? { deletedCount: 0 }
  }

  async function exportTopology(id: string): Promise<TopologyExportDoc> {
    return apiGet<TopologyExportDoc>(`/topologies/${id}/export`)
  }

  async function importTopology(doc: TopologyExportDoc): Promise<TopologyImportResult> {
    // Send as pre-stringified JSON so the request interceptor's snakeizeKeys
    // does not mutate user-defined attr keys inside `nodes[].attrs`/`edges[].attrs`.
    // Backend's CamelModel with `populate_by_name=True` already accepts camelCase.
    const result = await apiPost<TopologyImportResult>(
      '/topologies/import',
      JSON.stringify(doc) as unknown,
    )
    await fetchTopologies()
    return result
  }

  function onPageChange(p: number, ps: number) {
    page.value = p
    pageSize.value = ps
    fetchTopologies()
  }

  function onSearch(n: string) {
    name.value = n
    page.value = 1
    fetchTopologies()
  }

  function onSort(s: string) {
    sort.value = s
    fetchTopologies()
  }

  // Auto-fetch on mount
  watch([page, pageSize, name, sort], () => {}, { immediate: true })

  return {
    items,
    total,
    loading,
    page,
    pageSize,
    name,
    sort,
    fetchTopologies,
    createTopology,
    updateTopology,
    deleteTopology,
    deleteAllTopologies,
    exportTopology,
    importTopology,
    onPageChange,
    onSearch,
    onSort,
  }
}
