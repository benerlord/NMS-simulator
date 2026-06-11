import { ref } from 'vue'
import { message } from 'ant-design-vue'
import {
  alarmSchemaApi,
  type AlarmSchemaItem,
  type AlarmSchemaDetail,
  type AlarmSchemaCreate,
  type AlarmSchemaUpdate,
} from '@/api/alarmSchema'

export function useAlarmSchemas() {
  const schemas = ref<AlarmSchemaItem[]>([])
  const loading = ref(false)

  async function fetchSchemas() {
    loading.value = true
    try {
      schemas.value = await alarmSchemaApi.list()
    } finally {
      loading.value = false
    }
  }

  async function getDetail(id: string): Promise<AlarmSchemaDetail | null> {
    try {
      return await alarmSchemaApi.get(id)
    } catch {
      return null
    }
  }

  async function createSchema(data: AlarmSchemaCreate): Promise<boolean> {
    try {
      await alarmSchemaApi.create(data)
      message.success('创建成功')
      await fetchSchemas()
      return true
    } catch (e: any) {
      message.error(e?.message || '创建失败')
      return false
    }
  }

  async function updateSchema(id: string, data: AlarmSchemaUpdate): Promise<boolean> {
    try {
      await alarmSchemaApi.update(id, data)
      message.success('更新成功')
      await fetchSchemas()
      return true
    } catch (e: any) {
      message.error(e?.message || '更新失败')
      return false
    }
  }

  async function deleteSchema(id: string): Promise<boolean> {
    try {
      await alarmSchemaApi.delete(id)
      message.success('删除成功')
      await fetchSchemas()
      return true
    } catch (e: any) {
      const refs = e?.details?.referencedBy
      if (Array.isArray(refs) && refs.length > 0) {
        message.error(`告警模板被以下拓扑引用，无法删除：${refs.join(', ')}`)
      } else {
        message.error(e?.message || '删除失败')
      }
      return false
    }
  }

  return { schemas, loading, fetchSchemas, getDetail, createSchema, updateSchema, deleteSchema }
}
