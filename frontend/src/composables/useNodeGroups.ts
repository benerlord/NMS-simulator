import { ref, computed, provide, inject, type InjectionKey, type Ref, type ComputedRef } from 'vue'
import { nodeGroupApi } from '@/api/nodeGroup'
import type {
  NodeGroupItem,
  NodeGroupCreate,
  NodeGroupUpdate,
  GroupGraphData,
  MaterializeResult,
  MaterializeProgress,
} from '@/api/nodeGroup'

export interface UseNodeGroupsReturn {
  groups: Ref<NodeGroupItem[]>
  groupGraph: Ref<GroupGraphData | null>
  materializing: Ref<Record<string, MaterializeProgress>>
  loading: Ref<boolean>
  materializedGroups: ComputedRef<NodeGroupItem[]>
  fetchGroups: () => Promise<void>
  fetchGroupGraph: () => Promise<void>
  createGroup: (data: NodeGroupCreate) => Promise<string>
  updateGroup: (id: string, data: NodeGroupUpdate) => Promise<void>
  deleteGroup: (id: string) => Promise<void>
  materializeGroup: (id: string) => Promise<MaterializeResult>
}

export const NODE_GROUPS_KEY: InjectionKey<UseNodeGroupsReturn> = Symbol('nodeGroups')

export function createUseNodeGroups(topologyId: string, onRefresh?: () => Promise<void>): UseNodeGroupsReturn {
  const groups = ref<NodeGroupItem[]>([])
  const groupGraph = ref<GroupGraphData | null>(null)
  const materializing = ref<Record<string, MaterializeProgress>>({})
  const loading = ref(false)

  const materializedGroups = computed(() =>
    groups.value.filter((g) => g.isMaterialized),
  )

  async function fetchGroups() {
    try {
      const result = await nodeGroupApi.list(topologyId)
      groups.value = result.items
    } catch {
      // Let caller handle error
    }
  }

  async function fetchGroupGraph() {
    try {
      groupGraph.value = await nodeGroupApi.getGroupGraph(topologyId)
    } catch {
      groupGraph.value = null
    }
  }

  async function refreshAll() {
    // fetch graphData first so initGraph re-render has fresh data when groupGraph triggers watch
    if (onRefresh) await onRefresh()
    await fetchGroups()
    await fetchGroupGraph()
  }

  async function createGroup(data: NodeGroupCreate): Promise<string> {
    const result = await nodeGroupApi.create(topologyId, data)
    await refreshAll()
    return result.id
  }

  async function updateGroup(id: string, data: NodeGroupUpdate): Promise<void> {
    await nodeGroupApi.update(id, data)
    await refreshAll()
  }

  async function deleteGroup(id: string): Promise<void> {
    await nodeGroupApi.delete(id)
    await refreshAll()
  }

  async function materializeGroup(id: string): Promise<MaterializeResult> {
    materializing.value = {
      ...materializing.value,
      [id]: { phase: 'nodes', current: 0, total: 0, pct: 0, elapsedMs: 0 },
    }
    try {
      const result = await nodeGroupApi.materialize(id)
      materializing.value = {
        ...materializing.value,
        [id]: { phase: 'done', current: result.materializedNodes, total: result.materializedNodes, pct: 100, elapsedMs: result.elapsedMs },
      }
      await refreshAll()
      return result
    } finally {
      // Remove progress after a short delay so UI can show completion
      setTimeout(() => {
        const next = { ...materializing.value }
        delete next[id]
        materializing.value = next
      }, 3000)
    }
  }

  return {
    groups,
    groupGraph,
    materializing,
    loading,
    materializedGroups,
    fetchGroups,
    fetchGroupGraph,
    createGroup,
    updateGroup,
    deleteGroup,
    materializeGroup,
  }
}

export function useNodeGroups(topologyId: string, onRefresh?: () => Promise<void>): UseNodeGroupsReturn {
  const existing = inject<UseNodeGroupsReturn | null>(NODE_GROUPS_KEY, null)
  if (existing) return existing

  const instance = createUseNodeGroups(topologyId, onRefresh)
  provide(NODE_GROUPS_KEY, instance)
  return instance
}
