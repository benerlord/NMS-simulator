import client from './client';

// ==== API Configs ====

export const listConfigs = (params?: { keyword?: string; group?: string; enabled?: boolean; dataSourceType?: string }) =>
  client.get('/api-configs', { params });

export const getConfig = (id: string) =>
  client.get(`/api-configs/${id}`);

export const createConfig = (data: Record<string, unknown>) =>
  client.post('/api-configs', data);

export const updateConfig = (id: string, data: Record<string, unknown>) =>
  client.put(`/api-configs/${id}`, data);

export const deleteConfig = (id: string) =>
  client.delete(`/api-configs/${id}`);

export const toggleEnabled = (id: string, enabled: boolean) =>
  client.put(`/api-configs/${id}/enabled`, { enabled });

export const testConfig = (id: string, params: Record<string, unknown>) =>
  client.post(`/api-configs/${id}/test`, { params });

export const listGroups = () =>
  client.get('/api-configs/groups');

export const getDefaultSql = (collection: string) =>
  client.get(`/api-configs/default-sql/${collection}`);

export const exportConfigs = (group?: string) =>
  client.get('/api-configs/export', { params: group ? { group } : {} });

export const importConfigs = (configs: unknown[], overwrite?: boolean) =>
  client.post('/api-configs/import', { configs, overwrite });

// ==== Sessions ====

export const listSessions = () =>
  client.get('/sessions');

export const deleteSession = (token: string) =>
  client.delete(`/sessions/${token}`);

export const clearSessions = () =>
  client.delete('/sessions');

export const getSessionConfig = () =>
  client.get('/sessions/config');

export const updateSessionConfig = (data: Record<string, unknown>) =>
  client.put('/sessions/config', data);

// ==== Protocols ====

export const listProtocols = () =>
  client.get('/protocols');

export const startProtocol = (name: string) =>
  client.post(`/protocols/${name}/start`);

export const stopProtocol = (name: string) =>
  client.post(`/protocols/${name}/stop`);

export const restartProtocol = (name: string) =>
  client.post(`/protocols/${name}/restart`);

export const getProtocolHealth = (name: string) =>
  client.get(`/protocols/${name}/health`);

export const startAllProtocols = () =>
  client.post('/protocols/start-all');

export const stopAllProtocols = () =>
  client.post('/protocols/stop-all');

export const getMockConfig = () =>
  client.get('/protocols/http-mock/config');

export const updateMockConfig = (data: Record<string, unknown>) =>
  client.put('/protocols/http-mock/config', data);

export const listMockRoutes = () =>
  client.get('/protocols/http-mock/routes');

export const listRequestLogs = (params?: { limit?: number; offset?: number; method?: string; path?: string }) =>
  client.get('/protocols/http-mock/logs', { params });

export const clearRequestLogs = () =>
  client.delete('/protocols/http-mock/logs');

// ==== Settings ====

export const listSettings = (category?: string) =>
  client.get('/settings', { params: category ? { category } : {} });

export const updateSetting = (key: string, value: string) =>
  client.put(`/settings/${key}`, { value });

export const batchUpdateSettings = (settings: Array<{ key: string; value: string }>) =>
  client.put('/settings', { settings });
