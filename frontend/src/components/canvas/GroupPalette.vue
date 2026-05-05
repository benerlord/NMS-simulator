<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { Modal, message } from 'ant-design-vue'
import { useNodeGroups } from '@/composables/useNodeGroups'
import { useNodeTypes } from '@/composables/useTypes'
import type { NodeGroupItem } from '@/api/nodeGroup'

const emit = defineEmits<{
  create: []
  edit: [groupId: string]
  zoomToGroup: [groupId: string]
}>()

const props = defineProps<{
  topologyId: string
}>()

const { groups, loading, fetchGroups, deleteGroup } = useNodeGroups(props.topologyId)
const { nodeTypes, fetchNodeTypes } = useNodeTypes()

const nodeTypeMap = computed(() => {
  const m: Record<string, string> = {}
  for (const nt of nodeTypes.value) {
    m[nt.id] = nt.name
  }
  return m
})

// Context menu
interface CtxMenuItem {
  key: string
  label: string
  danger?: boolean
  disabled?: boolean
  action: () => void
}

const ctxMenu = ref<{
  visible: boolean
  x: number
  y: number
  items: CtxMenuItem[]
}>({ visible: false, x: 0, y: 0, items: [] })

function onContextMenu(e: MouseEvent, grp: NodeGroupItem) {
  const items: CtxMenuItem[] = []

  items.push({
    key: 'edit',
    label: '编辑组定义',
    action: () => emit('edit', grp.id),
  })
  items.push({
    key: 'zoom',
    label: '缩放到此组',
    action: () => emit('zoomToGroup', grp.id),
  })
  items.push({
    key: 'delete',
    label: '删除此组',
    danger: true,
    action: () => confirmDelete(grp),
  })

  ctxMenu.value = { visible: true, x: e.clientX, y: e.clientY, items }
}

function closeContextMenu() {
  ctxMenu.value.visible = false
}

onBeforeUnmount(() => {
  document.removeEventListener('click', closeContextMenu)
})

// Drag support
function onDragStart(e: DragEvent, grp: NodeGroupItem) {
  if (!e.dataTransfer) return
  e.dataTransfer.setData(
    'application/node-group',
    JSON.stringify({ id: grp.id, groupName: grp.groupName, nodeCount: grp.nodeCount }),
  )
  e.dataTransfer.effectAllowed = 'copy'
}

function confirmDelete(grp: NodeGroupItem) {
  Modal.confirm({
    title: '删除节点组',
    content: `确认删除"${grp.groupName}"？其展开的所有节点和边将一并删除，此操作不可撤销。`,
    okText: '删除',
    okType: 'danger',
    cancelText: '取消',
    onOk: () => performDelete(grp.id),
  })
}

async function performDelete(groupId: string) {
  try {
    await deleteGroup(groupId)
    message.success('节点组已删除')
  } catch (err: any) {
    message.error(`删除失败: ${err.message ?? '未知错误'}`)
  }
}

onMounted(() => {
  fetchGroups()
  fetchNodeTypes()
  document.addEventListener('click', closeContextMenu)
})
</script>

<template>
  <div class="group-palette">
    <div class="palette-header">
      <span class="palette-title">节点组</span>
      <a-button type="link" size="small" class="palette-add-btn" @click="emit('create')">
        + 新建
      </a-button>
    </div>

    <div v-if="loading" class="palette-loading">
      <a-spin size="small" />
    </div>

    <div v-else class="palette-content">
      <!-- Empty state -->
      <div v-if="groups.length === 0" class="empty-state" @click="emit('create')">
        <span class="empty-text">暂无节点组，点击新建</span>
      </div>

      <!-- Group list -->
      <div
        v-for="grp in groups"
        :key="grp.id"
        class="group-item"
        draggable="true"
        @dragstart="onDragStart($event, grp)"
        @contextmenu.prevent.stop="onContextMenu($event, grp)"
      >
        <div class="group-item-main">
          <span class="status-dot" />
          <div class="group-info">
            <div class="group-name">{{ grp.groupName }}</div>
            <div class="group-meta">
              <span class="group-type">{{ nodeTypeMap[grp.nodeTypeId] ?? grp.nodeTypeId }}</span>
              <span class="group-count">×{{ grp.nodeCount }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Context menu -->
    <Teleport to="body">
      <div
        v-if="ctxMenu.visible"
        class="group-context-menu"
        :style="{ left: ctxMenu.x + 'px', top: ctxMenu.y + 'px' }"
        @click.stop
      >
        <div
          v-for="item in ctxMenu.items"
          :key="item.key"
          class="ctx-menu-item"
          :class="{ 'ctx-danger': item.danger, 'ctx-disabled': item.disabled }"
          @click="item.action(); closeContextMenu()"
        >
          {{ item.label }}
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.group-palette {
  width: 200px;
  background: #fff;
  border-right: 1px solid #e8e8e8;
  border-top: 1px solid #e8e8e8;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.palette-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  border-bottom: 1px solid #e8e8e8;
}

.palette-title {
  font-weight: 500;
  font-size: 13px;
  color: rgba(0, 0, 0, 0.85);
}

.palette-add-btn {
  font-size: 12px;
  padding: 0;
  height: auto;
}

.palette-loading {
  display: flex;
  justify-content: center;
  padding: 24px;
}

.palette-content {
  flex: 1;
  overflow-y: auto;
  padding: 4px;
}

.empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px 12px;
  cursor: pointer;
}

.empty-text {
  font-size: 12px;
  color: rgba(0, 0, 0, 0.35);
}

.group-item {
  padding: 6px 8px;
  margin: 2px 0;
  border: 1px solid #e8e8e8;
  border-radius: 4px;
  cursor: grab;
  transition: all 0.2s;
}

.group-item:hover {
  background: #e6f7ff;
  border-color: #1890ff;
}

.group-item:active {
  cursor: grabbing;
}

.group-item-main {
  display: flex;
  align-items: center;
  gap: 8px;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.group-info {
  flex: 1;
  min-width: 0;
}

.group-name {
  font-size: 13px;
  font-weight: 500;
  color: rgba(0, 0, 0, 0.85);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.group-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 2px;
}

.group-type {
  font-size: 11px;
  color: rgba(0, 0, 0, 0.35);
}

.group-count {
  font-size: 11px;
  color: rgba(0, 0, 0, 0.45);
  font-weight: 500;
}

</style>

<style>
/* Global: context menu — not scoped since Teleported to body */
.group-context-menu {
  position: fixed;
  z-index: 9999;
  background: #fff;
  border-radius: 4px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
  padding: 4px 0;
  min-width: 140px;
}

.ctx-menu-item {
  padding: 8px 16px;
  font-size: 13px;
  color: rgba(0, 0, 0, 0.85);
  cursor: pointer;
  transition: background 0.2s;
}

.ctx-menu-item:hover {
  background: #f5f5f5;
}

.ctx-menu-item.ctx-danger {
  color: #ff4d4f;
}

.ctx-menu-item.ctx-danger:hover {
  background: #fff1f0;
}

.ctx-menu-item.ctx-disabled {
  color: rgba(0, 0, 0, 0.25);
  cursor: not-allowed;
}
</style>
