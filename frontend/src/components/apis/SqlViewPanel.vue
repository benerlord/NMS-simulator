<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Collapse, Empty, Spin, Tooltip, Tag } from 'ant-design-vue'
import { ReloadOutlined } from '@ant-design/icons-vue'
import { fetchSqlViews, type SqlViewItem, type SqlViewsData } from '@/api/sql'

interface Props {
  topologyId: string | null | undefined
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'insert', text: string): void
}>()

const loading = ref(false)
const data = ref<SqlViewsData | null>(null)
const errorMsg = ref<string | null>(null)

const activeKeys = ref<string[]>(['node', 'edge', 'generic'])

const nodeViews = computed<SqlViewItem[]>(() => data.value?.nodeViews ?? [])
const edgeViews = computed<SqlViewItem[]>(() => data.value?.edgeViews ?? [])
const genericViews = computed<SqlViewItem[]>(() => data.value?.generic ?? [])

async function load() {
  if (!props.topologyId) {
    data.value = null
    errorMsg.value = null
    return
  }
  loading.value = true
  errorMsg.value = null
  try {
    data.value = await fetchSqlViews(props.topologyId)
  } catch (err) {
    errorMsg.value = err instanceof Error ? err.message : '加载视图失败'
    data.value = null
  } finally {
    loading.value = false
  }
}

watch(
  () => props.topologyId,
  () => {
    load()
  },
  { immediate: true },
)

function insertViewName(view: SqlViewItem) {
  emit('insert', view.name)
}

function insertColumn(column: string) {
  emit('insert', column)
}

function insertFromClause(view: SqlViewItem) {
  emit('insert', `SELECT * FROM ${view.name}`)
}
</script>

<template>
  <div class="sql-view-panel">
    <div class="panel-header">
      <span class="panel-title">可用视图</span>
      <Tooltip title="刷新">
        <button
          class="refresh-btn"
          type="button"
          :disabled="!topologyId || loading"
          @click="load"
        >
          <ReloadOutlined :spin="loading" />
        </button>
      </Tooltip>
    </div>

    <div class="panel-body">
      <Spin :spinning="loading" size="small">
        <Empty
          v-if="!topologyId"
          description="请先绑定拓扑以加载视图"
          :image="Empty.PRESENTED_IMAGE_SIMPLE"
        />
        <Empty
          v-else-if="errorMsg"
          :description="errorMsg"
          :image="Empty.PRESENTED_IMAGE_SIMPLE"
        />
        <Empty
          v-else-if="!data"
          description="暂无视图"
          :image="Empty.PRESENTED_IMAGE_SIMPLE"
        />
        <Collapse
          v-else
          v-model:active-key="activeKeys"
          :bordered="false"
          class="view-collapse"
        >
          <Collapse.Panel key="node" :header="`节点视图 (${nodeViews.length})`">
            <Empty
              v-if="nodeViews.length === 0"
              description="拓扑内未发现节点"
              :image="Empty.PRESENTED_IMAGE_SIMPLE"
            />
            <div v-for="v in nodeViews" :key="v.name" class="view-item">
              <div class="view-item-header">
                <span class="view-name" @click="insertViewName(v)">{{ v.name }}</span>
                <Tooltip title="插入 SELECT * FROM ...">
                  <button class="view-action" type="button" @click="insertFromClause(v)">
                    SELECT *
                  </button>
                </Tooltip>
              </div>
              <div class="view-columns">
                <Tag
                  v-for="c in v.columns"
                  :key="c"
                  class="col-tag"
                  @click="insertColumn(c)"
                >
                  {{ c }}
                </Tag>
              </div>
            </div>
          </Collapse.Panel>

          <Collapse.Panel key="edge" :header="`边视图 (${edgeViews.length})`">
            <Empty
              v-if="edgeViews.length === 0"
              description="拓扑内未发现边"
              :image="Empty.PRESENTED_IMAGE_SIMPLE"
            />
            <div v-for="v in edgeViews" :key="v.name" class="view-item">
              <div class="view-item-header">
                <span class="view-name" @click="insertViewName(v)">{{ v.name }}</span>
                <Tooltip title="插入 SELECT * FROM ...">
                  <button class="view-action" type="button" @click="insertFromClause(v)">
                    SELECT *
                  </button>
                </Tooltip>
              </div>
              <div class="view-columns">
                <Tag
                  v-for="c in v.columns"
                  :key="c"
                  class="col-tag"
                  @click="insertColumn(c)"
                >
                  {{ c }}
                </Tag>
              </div>
            </div>
          </Collapse.Panel>

          <Collapse.Panel key="generic" :header="`通用视图 (${genericViews.length})`">
            <div v-for="v in genericViews" :key="v.name" class="view-item">
              <div class="view-item-header">
                <span class="view-name" @click="insertViewName(v)">{{ v.name }}</span>
                <Tooltip title="插入 SELECT * FROM ...">
                  <button class="view-action" type="button" @click="insertFromClause(v)">
                    SELECT *
                  </button>
                </Tooltip>
              </div>
              <div class="view-columns">
                <Tag
                  v-for="c in v.columns"
                  :key="c"
                  class="col-tag"
                  @click="insertColumn(c)"
                >
                  {{ c }}
                </Tag>
              </div>
            </div>
          </Collapse.Panel>
        </Collapse>
      </Spin>
    </div>
  </div>
</template>

<style scoped>
.sql-view-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  border: 1px solid #d9d9d9;
  border-radius: 6px;
  background: #fafafa;
  overflow: hidden;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 10px;
  background: #f0f0f0;
  border-bottom: 1px solid #e8e8e8;
  font-size: 12px;
}

.panel-title {
  font-weight: 600;
  color: #595959;
}

.refresh-btn {
  background: none;
  border: none;
  cursor: pointer;
  padding: 2px 6px;
  border-radius: 4px;
  color: #595959;
}

.refresh-btn:hover:not(:disabled) {
  background: rgba(0, 0, 0, 0.04);
  color: #1677ff;
}

.refresh-btn:disabled {
  color: #bfbfbf;
  cursor: not-allowed;
}

.panel-body {
  flex: 1;
  overflow: auto;
  padding: 4px;
}

.view-collapse :deep(.ant-collapse-header) {
  font-size: 12px;
  padding: 6px 12px !important;
}

.view-collapse :deep(.ant-collapse-content-box) {
  padding: 4px 8px !important;
}

.view-item {
  padding: 6px 4px;
  border-bottom: 1px dashed #eee;
}

.view-item:last-child {
  border-bottom: none;
}

.view-item-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 4px;
}

.view-name {
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 12px;
  font-weight: 600;
  color: #1677ff;
  cursor: pointer;
  user-select: none;
}

.view-name:hover {
  text-decoration: underline;
}

.view-action {
  background: none;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  padding: 1px 6px;
  font-size: 11px;
  font-family: 'Consolas', 'Monaco', monospace;
  color: #595959;
  cursor: pointer;
}

.view-action:hover {
  border-color: #1677ff;
  color: #1677ff;
}

.view-columns {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.col-tag {
  cursor: pointer;
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 11px;
  margin: 0;
  user-select: none;
}

.col-tag:hover {
  color: #1677ff;
  border-color: #1677ff;
}
</style>
