<script setup lang="ts">
import { ref, onMounted } from 'vue'
import NodeTypeTable from '@/components/types/NodeTypeTable.vue'
import EdgeTypeTable from '@/components/types/EdgeTypeTable.vue'

const nodeTypeTableRef = ref<InstanceType<typeof NodeTypeTable>>()
const edgeTypeTableRef = ref<InstanceType<typeof EdgeTypeTable>>()

onMounted(() => {
  nodeTypeTableRef.value?.refresh()
  edgeTypeTableRef.value?.refresh()
})
</script>

<template>
  <div class="types-view">
    <a-tabs default-active-key="node-types">
      <a-tab-pane key="node-types" tab="节点类型">
        <NodeTypeTable ref="nodeTypeTableRef" />
      </a-tab-pane>
      <a-tab-pane key="edge-types" tab="边类型">
        <EdgeTypeTable ref="edgeTypeTableRef" />
      </a-tab-pane>
    </a-tabs>
  </div>
</template>

<style scoped>
.types-view {
  padding: 0;
}
</style>
