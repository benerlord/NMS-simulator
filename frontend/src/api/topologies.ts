import client from './client';

// ---- Topologies ----
export const listTopologies = (keyword?: string) =>
  client.get('/topologies', { params: { keyword } });

export const createTopology = (data: { name: string; description?: string }) =>
  client.post('/topologies', data);

export const getTopology = (id: string) =>
  client.get(`/topologies/${id}`);

export const updateTopology = (id: string, data: { name?: string; description?: string }) =>
  client.put(`/topologies/${id}`, data);

export const deleteTopology = (id: string) =>
  client.delete(`/topologies/${id}`);

export const saveTopology = (id: string) =>
  client.post(`/topologies/${id}/save`);

export const loadTopology = (id: string) =>
  client.post(`/topologies/${id}/load`);

export const listVersions = (id: string) =>
  client.get(`/topologies/${id}/versions`);

export const restoreVersion = (id: string, version: number) =>
  client.post(`/topologies/${id}/versions/${version}/restore`);

export const exportTopology = (id: string) =>
  client.get(`/topologies/${id}/export`);

export const validateTopology = (id: string) =>
  client.post(`/topologies/${id}/validate`);

export const fixTopology = (id: string) =>
  client.post(`/topologies/${id}/validate/fix`);

export const layoutTopology = (id: string, algorithm: string, options?: Record<string, unknown>) =>
  client.post(`/topologies/${id}/layout`, { algorithm, options: options || {} });

export const updateCanvas = (id: string, data: Record<string, unknown>) =>
  client.put(`/topologies/${id}/canvas`, data);

// ---- Devices ----
export const listDevices = (topoId: string, params?: Record<string, unknown>) =>
  client.get(`/topologies/${topoId}/devices`, { params });

export const createDevice = (topoId: string, data: Record<string, unknown>) =>
  client.post(`/topologies/${topoId}/devices`, data);

export const getDevice = (topoId: string, deviceId: string) =>
  client.get(`/topologies/${topoId}/devices/${deviceId}`);

export const updateDevice = (topoId: string, deviceId: string, data: Record<string, unknown>) =>
  client.put(`/topologies/${topoId}/devices/${deviceId}`, data);

export const deleteDevice = (topoId: string, deviceId: string) =>
  client.delete(`/topologies/${topoId}/devices/${deviceId}`);

export const batchUpdateDevices = (topoId: string, data: Record<string, unknown>) =>
  client.put(`/topologies/${topoId}/devices/batch`, data);

export const batchDeleteDevices = (topoId: string, ids: string[]) =>
  client.delete(`/topologies/${topoId}/devices/batch`, { data: { ids } });

// ---- Ports ----
export const listPorts = (topoId: string, deviceId: string, params?: Record<string, unknown>) =>
  client.get(`/topologies/${topoId}/devices/${deviceId}/ports`, { params });

export const createPort = (topoId: string, deviceId: string, data: Record<string, unknown>) =>
  client.post(`/topologies/${topoId}/devices/${deviceId}/ports`, data);

export const generatePorts = (topoId: string, deviceId: string, data: Record<string, unknown>) =>
  client.post(`/topologies/${topoId}/devices/${deviceId}/ports/generate`, data);

export const updatePort = (topoId: string, portId: string, data: Record<string, unknown>) =>
  client.put(`/topologies/${topoId}/ports/${portId}`, data);

export const deletePort = (topoId: string, portId: string) =>
  client.delete(`/topologies/${topoId}/ports/${portId}`);

export const batchUpdatePorts = (topoId: string, deviceId: string, data: Record<string, unknown>) =>
  client.put(`/topologies/${topoId}/devices/${deviceId}/ports/batch`, data);

// ---- Links ----
export const listLinks = (topoId: string) =>
  client.get(`/topologies/${topoId}/links`);

export const createLink = (topoId: string, data: Record<string, unknown>) =>
  client.post(`/topologies/${topoId}/links`, data);

export const updateLink = (topoId: string, linkId: string, data: Record<string, unknown>) =>
  client.put(`/topologies/${topoId}/links/${linkId}`, data);

export const deleteLink = (topoId: string, linkId: string) =>
  client.delete(`/topologies/${topoId}/links/${linkId}`);

export const batchDeleteLinks = (topoId: string, ids: string[]) =>
  client.delete(`/topologies/${topoId}/links/batch`, { data: { ids } });

// ---- Alarms ----
export const listAlarms = (topoId: string, params?: Record<string, unknown>) =>
  client.get(`/topologies/${topoId}/alarms`, { params });

export const createAlarm = (topoId: string, data: Record<string, unknown>) =>
  client.post(`/topologies/${topoId}/alarms`, data);

export const clearAlarm = (topoId: string, alarmId: string) =>
  client.post(`/topologies/${topoId}/alarms/${alarmId}/clear`);

export const deleteAlarm = (topoId: string, alarmId: string) =>
  client.delete(`/topologies/${topoId}/alarms/${alarmId}`);

// ---- Metrics ----
export const listMetrics = (topoId: string, params?: Record<string, unknown>) =>
  client.get(`/topologies/${topoId}/metrics`, { params });

export const createMetric = (topoId: string, data: Record<string, unknown>) =>
  client.post(`/topologies/${topoId}/metrics`, data);

export const deleteMetric = (topoId: string, metricId: string) =>
  client.delete(`/topologies/${topoId}/metrics/${metricId}`);

// ---- Device Types ----
export const listDeviceTypes = () =>
  client.get('/device-types');

export const createDeviceType = (data: Record<string, unknown>) =>
  client.post('/device-types', data);

export const updateDeviceType = (id: string, data: Record<string, unknown>) =>
  client.put(`/device-types/${id}`, data);

export const deleteDeviceType = (id: string) =>
  client.delete(`/device-types/${id}`);
