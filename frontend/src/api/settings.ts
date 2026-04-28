import { apiGet, apiPut } from './http'

export interface SettingItem {
  key: string
  value: string | number | null
  updatedAt: string | null
}

export interface SettingsRuntime {
  appHost: string
  appPort: number
  logLevel: string
  dbPath: string
}

export interface SettingsSnapshot {
  items: SettingItem[]
  runtime: SettingsRuntime
}

export interface SettingsUpdate {
  autosaveInterval?: number
  mockPathPrefix?: string
}

export const settingsApi = {
  list: (): Promise<SettingsSnapshot> => apiGet('/settings'),

  get: (key: string): Promise<SettingItem> => apiGet(`/settings/${key}`),

  update: (data: SettingsUpdate): Promise<SettingsSnapshot> =>
    apiPut('/settings', data),
}
