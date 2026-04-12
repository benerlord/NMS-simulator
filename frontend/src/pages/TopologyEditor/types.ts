export interface Device {
  id: string;
  name: string;
  type: string;
  dn: string;
  ip?: string;
  vendor?: string;
  model?: string;
  status: string;
  x?: number;
  y?: number;
  customFields?: Record<string, unknown>;
}

export interface Port {
  id: string;
  deviceId: string;
  name: string;
  dn: string;
  type: string;
  speed: string;
  status: string;
  index: number;
}

export interface Link {
  id: string;
  name?: string;
  sourceDeviceId: string;
  sourcePortId: string;
  targetDeviceId: string;
  targetPortId: string;
  type: string;
  bandwidth?: string;
  status: string;
}

export interface DeviceType {
  id: string;
  name: string;
  icon?: string;
  category?: string;
  built_in?: number;
  defaultPortCount?: number;
  portPrefix?: string;
  dnTemplate?: string;
  fields?: Array<{ name: string; label: string; type: string; options?: string[] }>;
}

export interface ValidationIssue {
  level: string;
  type: string;
  message: string;
  target?: string;
  fixable: boolean;
  suggestion?: string;
}

export interface TopologyInfo {
  id: string;
  name: string;
  description?: string;
  version?: number;
  is_active?: number;
  created_at?: string;
  updated_at?: string;
}
