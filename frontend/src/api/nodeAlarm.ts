import { apiGet, apiPost, apiPut, apiDelete } from './http'

export interface NodeAlarmItem {
  id: string
  nodeId: string
  alarmIndex: number
  attrs: Record<string, string | null>
  createdAt: string
  updatedAt: string
}

export const nodeAlarmApi = {
  listByNode: (nodeId: string): Promise<NodeAlarmItem[]> =>
    apiGet(`/nodes/${nodeId}/alarms`),

  create: (nodeId: string, attrs?: Record<string, string | null>): Promise<NodeAlarmItem> =>
    apiPost(`/nodes/${nodeId}/alarms`, { attrs: attrs ?? null }),

  updateAttrs: (alarmId: string, attrs: Record<string, string | null>): Promise<NodeAlarmItem> =>
    apiPut(`/alarms/${alarmId}/attrs`, { attrs }),

  delete: (alarmId: string): Promise<null> =>
    apiDelete(`/alarms/${alarmId}`),
}
