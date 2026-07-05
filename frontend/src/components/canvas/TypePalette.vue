<script setup lang="ts">
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import { AutoComplete } from 'ant-design-vue'
import { ImportOutlined } from '@ant-design/icons-vue'
import { apiGet } from '@/api/http'
import { useNodeTypes } from '@/composables/useTypes'
import type { TopologyDetail } from '@/api/topology'
import type { NodeTypeDetail } from '@/api/types'

interface Props {
  topologyId?: string | null
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'bulk-import', nodeType: NodeTypeDetail): void
}>()

function onBulkImportClick(event: MouseEvent, nodeType: NodeTypeDetail) {
  event.stopPropagation()
  emit('bulk-import', nodeType)
}

const { nodeTypes, nodeTypesLoading, fetchNodeTypes } = useNodeTypes()

const domainId = ref<string | null>(null)
const searchText = ref('')

async function loadDomainId(topoId: string) {
  try {
    const detail = await apiGet<TopologyDetail>(`/topologies/${topoId}`)
    domainId.value = detail.domainId ?? null
  } catch {
    domainId.value = null
  }
}

async function loadTypes() {
  fetchNodeTypes(domainId.value ? { domainId: domainId.value } : undefined)
}

onMounted(async () => {
  if (props.topologyId) await loadDomainId(props.topologyId)
  loadTypes()
})

watch(() => props.topologyId, async (newId) => {
  if (newId) {
    await loadDomainId(newId)
  } else {
    domainId.value = null
  }
  loadTypes()
})

const CATEGORY_LABELS: Record<string, string> = {
  physical: '物理设备',
  virtual: '虚拟设备',
  cloud: '云资源',
  application: '应用',
}

function getCategoryLabel(category: string): string {
  return CATEGORY_LABELS[category] ?? category
}

const groupedTypes = computed(() => {
  const acc: Record<string, NodeTypeDetail[]> = {}
  for (const nt of nodeTypes.value) {
    if (!acc[nt.category]) acc[nt.category] = []
    acc[nt.category].push(nt)
  }
  return acc
})

const searchOptions = computed(() => {
  if (!searchText.value.trim()) return []
  const kw = searchText.value.toLowerCase()
  return nodeTypes.value
    .filter(nt =>
      nt.name.toLowerCase().includes(kw) ||
      nt.code.toLowerCase().includes(kw) ||
      nt.category.toLowerCase().includes(kw)
    )
    .slice(0, 10)
    .map(nt => ({
      value: nt.id,
      label: `${nt.name} — ${nt.code}`,
    }))
})

function onSearchSelect(id: unknown) {
  searchText.value = ''
  nextTick(() => {
    const el = document.getElementById(`type-item-${id}`)
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' })
      el.classList.add('highlight-flash')
      setTimeout(() => el.classList.remove('highlight-flash'), 1200)
    }
  })
}

const collapsedCategories = ref(new Set<string>())

function toggleCategory(category: string) {
  if (collapsedCategories.value.has(category)) {
    collapsedCategories.value.delete(category)
  } else {
    collapsedCategories.value.add(category)
  }
}

function onDragStart(event: DragEvent, nodeType: NodeTypeDetail) {
  if (event.dataTransfer) {
    event.dataTransfer.setData('application/node-type', JSON.stringify(nodeType))
    event.dataTransfer.effectAllowed = 'copy'
  }
}
</script>

<template>
  <div class="type-palette">
    <div class="palette-header">
      <span class="palette-title">节点类型</span>
    </div>

    <div class="palette-search">
      <AutoComplete
        v-model:value="searchText"
        :options="searchOptions"
        placeholder="搜索..."
        :style="{ width: '100%' }"
        :dropdown-style="{ minWidth: '220px' }"
        @select="onSearchSelect"
        allow-clear
      />
    </div>

    <a-spin v-if="nodeTypesLoading" />

    <div v-else class="palette-content">
      <template v-if="nodeTypes.length === 0">
        <div class="palette-empty">暂无可用节点类型</div>
      </template>
      <div
        v-for="(types, category) in groupedTypes"
        :key="category"
        class="category-group"
      >
        <div class="category-label" @click="toggleCategory(category)">
          <span class="category-arrow">{{ collapsedCategories.has(category) ? '▶' : '▼' }}</span>
          {{ getCategoryLabel(category) }} ({{ types.length }})
        </div>
        <div
          v-show="!collapsedCategories.has(category)"
          class="category-body"
        >
          <div
            v-for="nt in types"
            :key="nt.id"
            :id="`type-item-${nt.id}`"
            class="node-type-item"
            draggable="true"
            @dragstart="onDragStart($event, nt)"
          >
            <span class="node-type-name">{{ nt.name }}</span>
            <span class="node-type-code">{{ nt.code }}</span>
            <span
              class="bulk-import-btn"
              title="批量 JSON 导入"
              @click="onBulkImportClick($event, nt)"
              @mousedown.stop
              @dragstart.prevent.stop
            >
              <ImportOutlined />
            </span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.type-palette {
  width: 200px;
  background: #fff;
  border-right: 1px solid #e8e8e8;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.palette-header {
  padding: 12px 16px;
  border-bottom: 1px solid #e8e8e8;
}

.palette-title {
  font-weight: 500;
  font-size: 14px;
  color: rgba(0, 0, 0, 0.85);
}

.palette-search {
  padding: 8px 12px;
  border-bottom: 1px solid #f0f0f0;
}

.palette-empty {
  text-align: center;
  color: rgba(0, 0, 0, 0.35);
  padding: 32px 8px;
  font-size: 13px;
}

.palette-content {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.category-group {
  margin-bottom: 12px;
}

.category-label {
  font-size: 12px;
  color: rgba(0, 0, 0, 0.45);
  padding: 4px 8px;
  cursor: pointer;
  user-select: none;
  display: flex;
  align-items: center;
}

.category-label:hover {
  color: rgba(0, 0, 0, 0.65);
}

.category-arrow {
  display: inline-block;
  width: 14px;
  font-size: 10px;
  margin-right: 2px;
}

.category-body {
  max-height: 240px;
  overflow-y: auto;
}

.node-type-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  margin: 2px 0;
  background: #fafafa;
  border: 1px solid #e8e8e8;
  border-radius: 4px;
  cursor: grab;
  transition: all 0.2s;
}

.node-type-item:hover {
  background: #e6f7ff;
  border-color: #1890ff;
}

.node-type-item:active {
  cursor: grabbing;
}

.node-type-item.highlight-flash {
  background: #fff7e6;
  border-color: #fa8c16;
  box-shadow: 0 0 8px rgba(250, 140, 22, 0.3);
}

.node-type-name {
  font-size: 13px;
  color: rgba(0, 0, 0, 0.85);
}

.node-type-code {
  font-size: 11px;
  color: rgba(0, 0, 0, 0.35);
}

.bulk-import-btn {
  margin-left: 4px;
  color: #bfbfbf;
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.15s, color 0.15s;
  padding: 2px 4px;
}

.node-type-item:hover .bulk-import-btn {
  opacity: 1;
}

.bulk-import-btn:hover {
  color: #1890ff;
}
</style>
