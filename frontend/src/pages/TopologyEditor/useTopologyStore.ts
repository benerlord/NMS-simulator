/**
 * Lightweight state management for topology editor.
 * Uses React useState + context pattern instead of external state lib.
 */
import { useState, useCallback, useRef } from 'react';
import type { Device, Port, Link, DeviceType, TopologyInfo } from './types';
import * as api from '../../api/topologies';

export function useTopologyStore() {
  const [topoId, setTopoId] = useState<string | null>(null);
  const [topoInfo, setTopoInfo] = useState<TopologyInfo | null>(null);
  const [devices, setDevices] = useState<Device[]>([]);
  const [links, setLinks] = useState<Link[]>([]);
  const [deviceTypes, setDeviceTypes] = useState<DeviceType[]>([]);
  const [dirty, setDirty] = useState(false);
  const [loading, setLoading] = useState(false);
  const portsCache = useRef<Map<string, Port[]>>(new Map());

  const markDirty = useCallback(() => setDirty(true), []);

  const fetchDeviceTypes = useCallback(async () => {
    const res = await api.listDeviceTypes();
    setDeviceTypes(res.data?.items || []);
  }, []);

  const loadTopo = useCallback(async (id: string) => {
    setLoading(true);
    try {
      await api.loadTopology(id);
      const topoRes = await api.getTopology(id);
      setTopoInfo(topoRes.data);
      setTopoId(id);

      const devRes = await api.listDevices(id, { pageSize: 10000 });
      const devs: Device[] = devRes.data?.items || [];
      setDevices(devs);

      const linkRes = await api.listLinks(id);
      setLinks(linkRes.data?.items || []);

      portsCache.current.clear();
      setDirty(false);
    } finally {
      setLoading(false);
    }
  }, []);

  const saveTopo = useCallback(async () => {
    if (!topoId) return;
    setLoading(true);
    try {
      await api.saveTopology(topoId);
      setDirty(false);
    } finally {
      setLoading(false);
    }
  }, [topoId]);

  const addDevice = useCallback(async (data: Record<string, unknown>) => {
    if (!topoId) return null;
    const res = await api.createDevice(topoId, data);
    const dev: Device = res.data;
    setDevices(prev => [...prev, dev]);
    markDirty();
    return dev;
  }, [topoId, markDirty]);

  const editDevice = useCallback(async (deviceId: string, data: Record<string, unknown>) => {
    if (!topoId) return null;
    const res = await api.updateDevice(topoId, deviceId, data);
    const updated: Device = res.data;
    setDevices(prev => prev.map(d => d.id === deviceId ? updated : d));
    markDirty();
    return updated;
  }, [topoId, markDirty]);

  const removeDevice = useCallback(async (deviceId: string) => {
    if (!topoId) return;
    await api.deleteDevice(topoId, deviceId);
    setDevices(prev => prev.filter(d => d.id !== deviceId));
    setLinks(prev => prev.filter(l => l.sourceDeviceId !== deviceId && l.targetDeviceId !== deviceId));
    portsCache.current.delete(deviceId);
    markDirty();
  }, [topoId, markDirty]);

  const batchRemoveDevices = useCallback(async (ids: string[]) => {
    if (!topoId) return;
    await api.batchDeleteDevices(topoId, ids);
    const idSet = new Set(ids);
    setDevices(prev => prev.filter(d => !idSet.has(d.id)));
    setLinks(prev => prev.filter(l => !idSet.has(l.sourceDeviceId) && !idSet.has(l.targetDeviceId)));
    ids.forEach(id => portsCache.current.delete(id));
    markDirty();
  }, [topoId, markDirty]);

  const fetchPorts = useCallback(async (deviceId: string): Promise<Port[]> => {
    if (!topoId) return [];
    const res = await api.listPorts(topoId, deviceId);
    const ports: Port[] = res.data?.items || [];
    portsCache.current.set(deviceId, ports);
    return ports;
  }, [topoId]);

  const addLink = useCallback(async (data: Record<string, unknown>) => {
    if (!topoId) return null;
    const res = await api.createLink(topoId, data);
    const link: Link = res.data;
    setLinks(prev => [...prev, link]);
    // Invalidate ports cache for both devices
    portsCache.current.delete(data.sourceDeviceId as string);
    portsCache.current.delete(data.targetDeviceId as string);
    markDirty();
    return link;
  }, [topoId, markDirty]);

  const removeLink = useCallback(async (linkId: string) => {
    if (!topoId) return;
    const link = links.find(l => l.id === linkId);
    await api.deleteLink(topoId, linkId);
    setLinks(prev => prev.filter(l => l.id !== linkId));
    if (link) {
      portsCache.current.delete(link.sourceDeviceId);
      portsCache.current.delete(link.targetDeviceId);
    }
    markDirty();
  }, [topoId, links, markDirty]);

  return {
    topoId, topoInfo, devices, links, deviceTypes,
    dirty, loading,
    setTopoId, setTopoInfo,
    fetchDeviceTypes, loadTopo, saveTopo,
    addDevice, editDevice, removeDevice, batchRemoveDevices,
    fetchPorts, portsCache,
    addLink, removeLink,
    markDirty, setDirty,
    setDevices, setLinks,
  };
}
