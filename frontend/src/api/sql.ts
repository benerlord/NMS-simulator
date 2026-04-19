import http from './http'
import type { ApiEnvelope } from './http'
import { apiPost } from './http'

export interface SqlViewItem {
  name: string
  columns: string[]
  sql: string
}

export interface SqlViewsData {
  nodeViews: SqlViewItem[]
  edgeViews: SqlViewItem[]
  generic: SqlViewItem[]
}

// NOTE: The /admin/api/sql/views endpoint requires the query parameter named
// `topologyId` (FastAPI alias). The global request interceptor in http.ts
// snake-cases object params — which would turn `topologyId` into
// `topology_id` and produce a 422. Build the URL inline to bypass that.
export async function fetchSqlViews(topologyId: string): Promise<SqlViewsData> {
  const url = `/sql/views?topologyId=${encodeURIComponent(topologyId)}`
  const resp = await http.get<ApiEnvelope<SqlViewsData>>(url)
  return resp.data.data as SqlViewsData
}

export interface SqlExecuteRequest {
  topologyId: string
  sql: string
  params?: Record<string, unknown>
  page?: number
  pageSize?: number
}

export interface SqlExecuteResult {
  items: Array<Record<string, unknown>>
  total: number
  page: number
  pageSize: number
  generatedSql: string
  boundParams: Record<string, unknown>
  durationMs: number
}

export async function executeSql(
  body: SqlExecuteRequest,
): Promise<SqlExecuteResult> {
  return apiPost<SqlExecuteResult>('/sql/execute', {
    topologyId: body.topologyId,
    sql: body.sql,
    params: body.params ?? {},
    page: body.page ?? 1,
    pageSize: body.pageSize ?? 10,
  })
}

export const sqlApi = {
  listViews: fetchSqlViews,
  execute: executeSql,
}

export default sqlApi
