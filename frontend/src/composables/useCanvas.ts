import { shallowRef, ref } from 'vue'
import { apiGet, apiPatch } from '@/api/http'
import type { TopologyGraph } from '@/api/topology'

export interface CanvasNodePosition {
  nodeId: string
  x: number
  y: number
}

export function useCanvas(topologyId: string) {
  const graph = shallowRef<unknown>(null)
  const graphData = shallowRef<TopologyGraph | null>(null)
  const loading = ref(false)
  const saving = ref(false)
  const dirty = ref(false)
  const saveError = ref(false)
  const lastSavedAt = ref<Date | null>(null)

  async function fetchGraph() {
    loading.value = true
    try {
      const data = await apiGet<TopologyGraph>(`/topologies/${topologyId}/graph`)
      graphData.value = data
    } finally {
      loading.value = false
    }
  }

  async function savePositions(positions: CanvasNodePosition[]) {
    saving.value = true
    saveError.value = false
    try {
      await apiPatch(`/topologies/${topologyId}/canvas`, { nodes: positions })
      dirty.value = false
      lastSavedAt.value = new Date()
    } catch {
      saveError.value = true
      throw new Error('保存失败')
    } finally {
      saving.value = false
    }
  }

  function markDirty() {
    dirty.value = true
    saveError.value = false
  }

  function clearSaveError() {
    saveError.value = false
  }

  return {
    graph,
    graphData,
    loading,
    saving,
    dirty,
    saveError,
    lastSavedAt,
    fetchGraph,
    savePositions,
    markDirty,
    clearSaveError,
  }
}
