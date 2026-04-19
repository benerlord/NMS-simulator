<script setup lang="ts">
import { onMounted } from 'vue'
import { useNodeTypes } from '@/composables/useTypes'
import type { NodeTypeDetail } from '@/api/types'

const { nodeTypes, nodeTypesLoading, fetchNodeTypes } = useNodeTypes()

onMounted(() => {
  fetchNodeTypes()
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

    <a-spin v-if="nodeTypesLoading" />

    <div v-else class="palette-content">
      <div
        v-for="(types, category) in nodeTypes.reduce((acc, nt) => {
          if (!acc[nt.category]) acc[nt.category] = []
          acc[nt.category].push(nt)
          return acc
        }, {} as Record<string, NodeTypeDetail[]>)"
        :key="category"
        class="category-group"
      >
        <div class="category-label">{{ getCategoryLabel(category) }}</div>
        <div
          v-for="nt in types"
          :key="nt.id"
          class="node-type-item"
          draggable="true"
          @dragstart="onDragStart($event, nt)"
        >
          <span class="node-type-name">{{ nt.name }}</span>
          <span class="node-type-code">{{ nt.code }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.type-palette {
  width: 180px;
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

.node-type-name {
  font-size: 13px;
  color: rgba(0, 0, 0, 0.85);
}

.node-type-code {
  font-size: 11px;
  color: rgba(0, 0, 0, 0.35);
}
</style>
