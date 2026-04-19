<script setup lang="ts">
import { computed } from 'vue'
import { Button, Space, Tooltip, Tag } from 'ant-design-vue'
import {
  SaveOutlined,
  UndoOutlined,
  RedoOutlined,
  ZoomInOutlined,
  ZoomOutOutlined,
  ExpandOutlined,
  LinkOutlined,
} from '@ant-design/icons-vue'

interface Props {
  saving: boolean
  dirty: boolean
  canUndo: boolean
  canRedo: boolean
  saveError?: boolean
  lastSavedAt?: Date | null
  connectingMode?: boolean
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'save'): void
  (e: 'undo'): void
  (e: 'redo'): void
  (e: 'zoomIn'): void
  (e: 'zoomOut'): void
  (e: 'fit'): void
  (e: 'toggleConnect'): void
}>()

function formatTime(date: Date | null): string {
  if (!date) return ''
  return `${date.getHours().toString().padStart(2, '0')}:${date.getMinutes().toString().padStart(2, '0')}`
}

const statusTag = computed(() => {
  if (props.saving) return { color: 'blue', text: '保存中...' }
  if (props.saveError) return { color: 'red', text: '保存失败（重试中）' }
  if (props.dirty) return { color: 'orange', text: '未保存' }
  if (props.lastSavedAt) {
    return { color: 'green', text: `已保存 ${formatTime(props.lastSavedAt)}` }
  }
  return { color: 'green', text: '已保存' }
})
</script>

<template>
  <div class="canvas-toolbar">
    <Space>
      <Tooltip title="保存">
        <Button
          type="primary"
          :loading="saving"
          :disabled="!dirty"
          @click="emit('save')"
        >
          <template #icon><SaveOutlined /></template>
          保存
        </Button>
      </Tooltip>

      <Tooltip title="撤销">
        <Button :disabled="!canUndo" @click="emit('undo')">
          <template #icon><UndoOutlined /></template>
        </Button>
      </Tooltip>

      <Tooltip title="重做">
        <Button :disabled="!canRedo" @click="emit('redo')">
          <template #icon><RedoOutlined /></template>
        </Button>
      </Tooltip>

      <Tooltip title="放大">
        <Button @click="emit('zoomIn')">
          <template #icon><ZoomInOutlined /></template>
        </Button>
      </Tooltip>

      <Tooltip title="缩小">
        <Button @click="emit('zoomOut')">
          <template #icon><ZoomOutOutlined /></template>
        </Button>
      </Tooltip>

      <Tooltip title="适应画布">
        <Button @click="emit('fit')">
          <template #icon><ExpandOutlined /></template>
        </Button>
      </Tooltip>

      <Tooltip :title="connectingMode ? '取消连线' : '连线模式'">
        <Button
          :type="connectingMode ? 'primary' : 'default'"
          @click="emit('toggleConnect')"
        >
          <template #icon><LinkOutlined /></template>
        </Button>
      </Tooltip>
    </Space>

    <Tag :color="statusTag.color">{{ statusTag.text }}</Tag>
  </div>
</template>

<style scoped>
.canvas-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 16px;
  background: #fff;
  border-bottom: 1px solid #e8e8e8;
}
</style>
