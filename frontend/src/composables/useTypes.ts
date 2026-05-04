import { ref, computed } from 'vue'
import { nodeTypeApi, edgeTypeApi } from '@/api/types'
import type {
  NodeTypeDetail,
  NodeTypeCreate,
  NodeTypeUpdate,
  NodeTypeFieldCreate,
  NodeTypeFieldUpdate,
  EdgeTypeDetail,
  EdgeTypeCreate,
  EdgeTypeUpdate,
  EdgeTypeFieldCreate,
  EdgeTypeFieldUpdate,
} from '@/api/types'

// ============ Node Types ============

export function useNodeTypes() {
  const nodeTypes = ref<NodeTypeDetail[]>([])
  const nodeTypesLoading = ref(false)
  const nodeTypesError = ref<string | null>(null)

  async function fetchNodeTypes() {
    nodeTypesLoading.value = true
    nodeTypesError.value = null
    try {
      const res = await nodeTypeApi.list()
      nodeTypes.value = res.items
    } catch (e: any) {
      nodeTypesError.value = e.message ?? '获取节点类型失败'
    } finally {
      nodeTypesLoading.value = false
    }
  }

  async function createNodeType(data: NodeTypeCreate) {
    const result = await nodeTypeApi.create(data)
    await fetchNodeTypes()
    return result
  }

  async function updateNodeType(id: string, data: NodeTypeUpdate) {
    const result = await nodeTypeApi.update(id, data)
    await fetchNodeTypes()
    return result
  }

  async function deleteNodeType(id: string) {
    const result = await nodeTypeApi.delete(id)
    await fetchNodeTypes()
    return result
  }

  async function deleteNodeTypes(ids: string[]) {
    const result = await nodeTypeApi.batchDelete(ids)
    await fetchNodeTypes()
    return result
  }

  async function createNodeTypeField(typeId: string, data: NodeTypeFieldCreate) {
    const result = await nodeTypeApi.createField(typeId, data)
    await fetchNodeTypes()
    return result
  }

  async function updateNodeTypeField(typeId: string, fieldId: number, data: NodeTypeFieldUpdate) {
    const result = await nodeTypeApi.updateField(typeId, fieldId, data)
    await fetchNodeTypes()
    return result
  }

  async function deleteNodeTypeField(typeId: string, fieldId: number) {
    const result = await nodeTypeApi.deleteField(typeId, fieldId)
    await fetchNodeTypes()
    return result
  }

  const nodeTypesByCategory = computed(() => {
    const grouped: Record<string, NodeTypeDetail[]> = {}
    for (const nt of nodeTypes.value) {
      if (!grouped[nt.category]) grouped[nt.category] = []
      grouped[nt.category].push(nt)
    }
    return grouped
  })

  return {
    nodeTypes,
    nodeTypesLoading,
    nodeTypesError,
    nodeTypesByCategory,
    fetchNodeTypes,
    createNodeType,
    updateNodeType,
    deleteNodeType,
    deleteNodeTypes,
    createNodeTypeField,
    updateNodeTypeField,
    deleteNodeTypeField,
  }
}

// ============ Edge Types ============

export function useEdgeTypes() {
  const edgeTypes = ref<EdgeTypeDetail[]>([])
  const edgeTypesLoading = ref(false)
  const edgeTypesError = ref<string | null>(null)

  async function fetchEdgeTypes() {
    edgeTypesLoading.value = true
    edgeTypesError.value = null
    try {
      const res = await edgeTypeApi.list()
      edgeTypes.value = res.items
    } catch (e: any) {
      edgeTypesError.value = e.message ?? '获取边类型失败'
    } finally {
      edgeTypesLoading.value = false
    }
  }

  async function createEdgeType(data: EdgeTypeCreate) {
    const result = await edgeTypeApi.create(data)
    await fetchEdgeTypes()
    return result
  }

  async function updateEdgeType(id: string, data: EdgeTypeUpdate) {
    const result = await edgeTypeApi.update(id, data)
    await fetchEdgeTypes()
    return result
  }

  async function deleteEdgeType(id: string) {
    const result = await edgeTypeApi.delete(id)
    await fetchEdgeTypes()
    return result
  }

  async function deleteEdgeTypes(ids: string[]) {
    const result = await edgeTypeApi.batchDelete(ids)
    await fetchEdgeTypes()
    return result
  }

  async function createEdgeTypeField(typeId: string, data: EdgeTypeFieldCreate) {
    const result = await edgeTypeApi.createField(typeId, data)
    await fetchEdgeTypes()
    return result
  }

  async function updateEdgeTypeField(typeId: string, fieldId: number, data: EdgeTypeFieldUpdate) {
    const result = await edgeTypeApi.updateField(typeId, fieldId, data)
    await fetchEdgeTypes()
    return result
  }

  async function deleteEdgeTypeField(typeId: string, fieldId: number) {
    const result = await edgeTypeApi.deleteField(typeId, fieldId)
    await fetchEdgeTypes()
    return result
  }

  return {
    edgeTypes,
    edgeTypesLoading,
    edgeTypesError,
    fetchEdgeTypes,
    createEdgeType,
    updateEdgeType,
    deleteEdgeType,
    deleteEdgeTypes,
    createEdgeTypeField,
    updateEdgeTypeField,
    deleteEdgeTypeField,
  }
}
