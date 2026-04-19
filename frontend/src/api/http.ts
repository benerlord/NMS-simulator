import axios, { type AxiosInstance, type AxiosResponse } from 'axios'
import { message } from 'ant-design-vue'

import { camelizeKeys, snakeizeKeys } from './case'

export interface ApiEnvelope<T = unknown> {
  code: number
  data?: T
  message?: string
  details?: Record<string, unknown>
}

export class ApiError extends Error {
  code: number
  details?: Record<string, unknown>

  constructor(code: number, msg: string, details?: Record<string, unknown>) {
    super(msg)
    this.code = code
    this.details = details
  }
}

const http: AxiosInstance = axios.create({
  baseURL: '/admin/api',
  timeout: 15_000,
  headers: { 'Content-Type': 'application/json' },
})

http.interceptors.request.use((config) => {
  if (config.data && typeof config.data === 'object') {
    config.data = snakeizeKeys(config.data)
  }
  if (config.params && typeof config.params === 'object') {
    config.params = snakeizeKeys(config.params)
  }
  return config
})

http.interceptors.response.use(
  (resp: AxiosResponse<ApiEnvelope>) => {
    const body = camelizeKeys<ApiEnvelope>(resp.data)
    if (body && typeof body.code === 'number' && body.code !== 0) {
      const err = new ApiError(body.code, body.message ?? 'request failed', body.details)
      message.error(`[${err.code}] ${err.message}`)
      return Promise.reject(err)
    }
    resp.data = body
    return resp
  },
  (error) => {
    const status = error.response?.status
    const raw = error.response?.data
    const body = raw ? camelizeKeys<ApiEnvelope>(raw) : undefined
    const code = body?.code ?? status ?? -1
    const msg = body?.message ?? error.message ?? 'network error'
    message.error(`[${code}] ${msg}`)
    return Promise.reject(new ApiError(code, msg, body?.details))
  },
)

export async function apiGet<T>(url: string, params?: Record<string, unknown>): Promise<T> {
  const resp = await http.get<ApiEnvelope<T>>(url, { params })
  return resp.data.data as T
}

export async function apiPost<T>(url: string, data?: unknown): Promise<T> {
  const resp = await http.post<ApiEnvelope<T>>(url, data)
  return resp.data.data as T
}

export async function apiPut<T>(url: string, data?: unknown): Promise<T> {
  const resp = await http.put<ApiEnvelope<T>>(url, data)
  return resp.data.data as T
}

export async function apiPatch<T>(url: string, data?: unknown): Promise<T> {
  const resp = await http.patch<ApiEnvelope<T>>(url, data)
  return resp.data.data as T
}

export async function apiDelete<T = void>(url: string): Promise<T> {
  const resp = await http.delete<ApiEnvelope<T>>(url)
  return resp.data.data as T
}

export default http
