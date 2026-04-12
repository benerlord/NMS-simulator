import { useEffect, useRef, useState, useCallback } from 'react';
import { message, Modal, Input, Spin } from 'antd';
import type { Graph } from '@antv/x6';
import { createGraph, deviceToNode, linkToEdge } from './graph';
import { useTopologyStore } from './useTopologyStore';
import type { Device, DeviceType, Port, ValidationIssue } from './types';
import Toolbar from './Toolbar';
import DeviceTypePanel from './DeviceTypePanel';
import DeviceDrawer from './DeviceDrawer';
import LinkDialog from './LinkDialog';
import PortPanel from './PortPanel';
import TopoListModal from './TopoListModal';
import VersionDrawer from './VersionDrawer';
import ValidationPanel from './ValidationPanel';
import * as api from '../../api/topologies';

const TopologyEditor = () => {
  const containerRef = useRef<HTMLDivElement>(null);
  const graphRef = useRef<Graph | null>(null);
  const store = useTopologyStore();

  // UI state
  const [selectedNodeIds, setSelectedNodeIds] = useState<string[]>([]);
  const [deviceDrawerOpen, setDeviceDrawerOpen] = useState(false);
  const [editingDevice, setEditingDevice] = useState<Device | null>(null);
  const [isNewDevice, setIsNewDevice] = useState(false);
  const [linkDialogOpen, setLinkDialogOpen] = useState(false);
  const [linkSourceId, setLinkSourceId] = useState<string | null>(null);
  const [linkTargetId, setLinkTargetId] = useState<string | null>(null);
  const [portPanelOpen, setPortPanelOpen] = useState(false);
  const [portDevice, setPortDevice] = useState<Device | null>(null);
  const [topoListOpen, setTopoListOpen] = useState(false);
  const [versionOpen, setVersionOpen] = useState(false);
  const [validationOpen, setValidationOpen] = useState(false);
  const [validationResult, setValidationResult] = useState<any>(null);
  const [validationLoading, setValidationLoading] = useState(false);
  const [newTopoName, setNewTopoName] = useState('');

  // Pending drop position for creating device via drag
  const pendingDropRef = useRef<{ x: number; y: number; type: DeviceType } | null>(null);

  // Init graph
  useEffect(() => {
    if (!containerRef.current || graphRef.current) return;
    const graph = createGraph(containerRef.current);
    graphRef.current = graph;

    // Selection events
    graph.on('selection:changed', ({ selected }) => {
      const nodeIds = selected
        .filter(cell => cell.isNode())
        .map(cell => cell.id);
      setSelectedNodeIds(nodeIds);
    });

    // Double-click node to edit
    graph.on('node:dblclick', ({ node }) => {
      const dev = store.devices.find(d => d.id === node.id);
      if (dev) {
        setEditingDevice(dev);
        setIsNewDevice(false);
        setDeviceDrawerOpen(true);
      }
    });

    // Edge connected (from canvas drag)
    graph.on('edge:connected', ({ edge }) => {
      const sourceId = edge.getSourceCellId();
      const targetId = edge.getTargetCellId();
      if (sourceId && targetId && sourceId !== targetId) {
        // Remove the temporary edge, open dialog
        graph.removeEdge(edge.id);
        setLinkSourceId(sourceId);
        setLinkTargetId(targetId);
        setLinkDialogOpen(true);
      }
    });

    // Right-click context menu on node
    graph.on('node:contextmenu', ({ node, e }) => {
      e.preventDefault();
      const dev = store.devices.find(d => d.id === node.id);
      if (!dev) return;

      // Simple approach: use Modal.confirm as context menu
      Modal.confirm({
        title: dev.name,
        content: '选择操作',
        okText: '编辑属性',
        cancelText: '取消',
        onOk() {
          setEditingDevice(dev);
          setIsNewDevice(false);
          setDeviceDrawerOpen(true);
        },
      });
    });

    // Node position changed -> save to store
    graph.on('node:moved', ({ node }) => {
      const pos = node.getPosition();
      const dev = store.devices.find(d => d.id === node.id);
      if (dev) {
        dev.x = pos.x;
        dev.y = pos.y;
        store.markDirty();
      }
    });

    // Right-click on blank area
    graph.on('blank:contextmenu', ({ e }) => {
      e.preventDefault();
    });

    return () => {
      graph.dispose();
      graphRef.current = null;
    };
  }, []);

  // Load device types on mount
  useEffect(() => {
    store.fetchDeviceTypes();
  }, []);

  // Sync graph with store data
  useEffect(() => {
    const graph = graphRef.current;
    if (!graph) return;

    // Clear graph
    graph.clearCells();

    // Add device nodes
    store.devices.forEach(dev => {
      const nodeData = deviceToNode(dev);
      graph.addNode(nodeData);
    });

    // Add link edges
    store.links.forEach(link => {
      const edgeData = linkToEdge(link, store.devices);
      if (edgeData) {
        graph.addEdge(edgeData);
      }
    });

    // Fit to content if there are nodes
    if (store.devices.length > 0) {
      setTimeout(() => graph.zoomToFit({ padding: 60, maxScale: 1.5 }), 100);
    }
  }, [store.devices, store.links]);

  // ---- Handlers ----

  const handleDragStart = useCallback((type: DeviceType, e: React.DragEvent) => {
    e.dataTransfer.setData('device-type', JSON.stringify(type));
    e.dataTransfer.effectAllowed = 'copy';
  }, []);

  const handleDrop = useCallback(async (e: React.DragEvent) => {
    e.preventDefault();
    const graph = graphRef.current;
    if (!graph || !store.topoId) return;

    const typeData = e.dataTransfer.getData('device-type');
    if (!typeData) return;

    const type: DeviceType = JSON.parse(typeData);
    const rect = containerRef.current!.getBoundingClientRect();
    const point = graph.clientToLocal(e.clientX - rect.left, e.clientY - rect.top);

    // Open device creation drawer with position
    pendingDropRef.current = { x: point.x, y: point.y, type };
    setEditingDevice(null);
    setIsNewDevice(true);
    setDeviceDrawerOpen(true);
  }, [store.topoId]);

  const handleDeviceSave = useCallback(async (data: Record<string, unknown>, isNew: boolean) => {
    if (isNew) {
      const drop = pendingDropRef.current;
      if (drop) {
        data.x = drop.x;
        data.y = drop.y;
        if (!data.type) data.type = drop.type.id;
      }
      const dev = await store.addDevice(data);
      if (dev) {
        message.success(`设备 "${dev.name}" 已创建`);
      }
      pendingDropRef.current = null;
    } else if (editingDevice) {
      const dev = await store.editDevice(editingDevice.id, data);
      if (dev) {
        message.success(`设备 "${dev.name}" 已更新`);
        // Update node on graph
        const graph = graphRef.current;
        const node = graph?.getCellById(dev.id);
        if (node && node.isNode()) {
          node.setAttrs({
            label: { text: dev.name },
            dn: { text: dev.dn || '' },
          });
        }
      }
    }
  }, [store, editingDevice]);

  const handleDeviceDelete = useCallback(async (deviceId: string) => {
    Modal.confirm({
      title: '确认删除设备？',
      content: '关联的端口和链路也将被删除',
      okText: '删除',
      okButtonProps: { danger: true },
      onOk: async () => {
        await store.removeDevice(deviceId);
        message.success('设备已删除');
      },
    });
  }, [store]);

  const handleLinkConfirm = useCallback(async (data: Record<string, unknown>) => {
    const link = await store.addLink(data);
    if (link) {
      message.success('链路已创建');
      setLinkDialogOpen(false);
    }
  }, [store]);

  const handleSave = useCallback(async () => {
    // Also save canvas positions
    if (store.topoId && graphRef.current) {
      const positions: Record<string, { x: number; y: number }> = {};
      graphRef.current.getNodes().forEach(node => {
        const pos = node.getPosition();
        positions[node.id] = { x: pos.x, y: pos.y };
      });
      await api.updateCanvas(store.topoId, { nodePositions: positions });
    }
    await store.saveTopo();
    message.success('拓扑已保存');
  }, [store]);

  const handleNewTopo = useCallback(() => {
    Modal.confirm({
      title: '新建拓扑',
      content: (
        <Input
          placeholder="拓扑名称"
          onChange={(e) => setNewTopoName(e.target.value)}
        />
      ),
      onOk: async () => {
        if (!newTopoName.trim()) {
          message.warning('请输入拓扑名称');
          return;
        }
        const res = await api.createTopology({ name: newTopoName.trim() });
        const id = res.data?.id;
        if (id) {
          await store.loadTopo(id);
          message.success('拓扑已创建');
        }
        setNewTopoName('');
      },
    });
  }, [newTopoName, store]);

  const handleValidate = useCallback(async () => {
    if (!store.topoId) return;
    setValidationLoading(true);
    try {
      const res = await api.validateTopology(store.topoId);
      setValidationResult(res.data);
      setValidationOpen(true);
    } finally {
      setValidationLoading(false);
    }
  }, [store.topoId]);

  const handleFix = useCallback(async () => {
    if (!store.topoId) return;
    setValidationLoading(true);
    try {
      await api.fixTopology(store.topoId);
      // Re-validate
      const res = await api.validateTopology(store.topoId);
      setValidationResult(res.data);
      // Reload topology to get fresh data
      await store.loadTopo(store.topoId);
      message.success('已修复可修复的问题');
    } finally {
      setValidationLoading(false);
    }
  }, [store]);

  const handleLayout = useCallback(async (algo: string) => {
    if (!store.topoId) return;
    const res = await api.layoutTopology(store.topoId, algo);
    const positions = res.data?.nodePositions;
    if (positions && graphRef.current) {
      const graph = graphRef.current;
      Object.entries(positions).forEach(([nodeId, pos]) => {
        const node = graph.getCellById(nodeId);
        if (node && node.isNode()) {
          node.setPosition(pos as { x: number; y: number });
        }
      });
      store.markDirty();
      message.success('布局已应用');
    }
  }, [store]);

  const handleBatchDelete = useCallback(() => {
    if (selectedNodeIds.length === 0) return;
    Modal.confirm({
      title: `确认删除 ${selectedNodeIds.length} 个设备？`,
      content: '关联的端口和链路也将被删除',
      okText: '删除',
      okButtonProps: { danger: true },
      onOk: async () => {
        await store.batchRemoveDevices(selectedNodeIds);
        setSelectedNodeIds([]);
        message.success(`已删除 ${selectedNodeIds.length} 个设备`);
      },
    });
  }, [selectedNodeIds, store]);

  const handleSearch = useCallback((keyword: string) => {
    if (!keyword || !graphRef.current) return;
    const kw = keyword.toLowerCase();
    const dev = store.devices.find(d => d.name.toLowerCase().includes(kw));
    if (dev) {
      const graph = graphRef.current;
      const node = graph.getCellById(dev.id);
      if (node && node.isNode()) {
        graph.centerCell(node);
        graph.select(node);
      }
    } else {
      message.info('未找到匹配的设备');
    }
  }, [store.devices]);

  const handleFitView = useCallback(() => {
    graphRef.current?.zoomToFit({ padding: 60, maxScale: 1.5 });
  }, []);

  const handleLocateDevice = useCallback((target: string) => {
    if (!graphRef.current) return;
    const node = graphRef.current.getCellById(target);
    if (node && node.isNode()) {
      graphRef.current.centerCell(node);
      graphRef.current.select(node);
    }
  }, []);

  const handleExport = useCallback(async () => {
    if (!store.topoId) return;
    const res = await api.exportTopology(store.topoId);
    const blob = new Blob([JSON.stringify(res.data || res, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${store.topoInfo?.name || 'topology'}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }, [store.topoId, store.topoInfo]);

  const handleImport = useCallback(() => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.json';
    input.onchange = async (e) => {
      const file = (e.target as HTMLInputElement).files?.[0];
      if (!file) return;
      const formData = new FormData();
      formData.append('file', file);
      try {
        const res = await fetch('/api/topologies/import', { method: 'POST', body: formData });
        const data = await res.json();
        if (data.code === 0 && data.data?.id) {
          await store.loadTopo(data.data.id);
          message.success('拓扑已导入');
        } else {
          message.error(data.message || '导入失败');
        }
      } catch {
        message.error('导入失败');
      }
    };
    input.click();
  }, [store]);

  const handleVersionRestore = useCallback(async () => {
    if (store.topoId) {
      await store.loadTopo(store.topoId);
    }
  }, [store]);

  const handleManagePorts = useCallback((deviceId: string) => {
    const dev = store.devices.find(d => d.id === deviceId);
    if (dev) {
      setPortDevice(dev);
      setPortPanelOpen(true);
    }
  }, [store.devices]);

  // Show "no topology" prompt if nothing loaded
  const showEmptyState = !store.topoId;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', margin: -24, background: '#f5f5f5' }}>
      <Toolbar
        topoInfo={store.topoInfo}
        dirty={store.dirty}
        loading={store.loading}
        selectedCount={selectedNodeIds.length}
        onSave={handleSave}
        onOpenTopoList={() => setTopoListOpen(true)}
        onNewTopo={handleNewTopo}
        onValidate={handleValidate}
        onLayout={handleLayout}
        onBatchDelete={handleBatchDelete}
        onSearch={handleSearch}
        onFitView={handleFitView}
        onExport={handleExport}
        onImport={handleImport}
        onVersions={() => setVersionOpen(true)}
      />

      <div style={{ flex: 1, display: 'flex', overflow: 'hidden', position: 'relative' }}>
        <DeviceTypePanel deviceTypes={store.deviceTypes} onDragStart={handleDragStart} />

        <div
          ref={containerRef}
          style={{ flex: 1, position: 'relative' }}
          onDrop={handleDrop}
          onDragOver={(e) => e.preventDefault()}
        >
          {store.loading && (
            <div style={{ position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%)', zIndex: 10 }}>
              <Spin size="large" />
            </div>
          )}
          {showEmptyState && !store.loading && (
            <div style={{
              position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%)',
              textAlign: 'center', color: '#8c8c8c', zIndex: 5,
            }}>
              <p style={{ fontSize: 18, marginBottom: 8 }}>请先选择或创建拓扑</p>
              <p>点击工具栏的 <b>打开</b> 或 <b>新建</b> 按钮开始</p>
            </div>
          )}
        </div>
      </div>

      {/* Dialogs & Drawers */}
      <DeviceDrawer
        open={deviceDrawerOpen}
        device={editingDevice}
        deviceTypes={store.deviceTypes}
        isNew={isNewDevice}
        onClose={() => setDeviceDrawerOpen(false)}
        onSave={handleDeviceSave}
        onDelete={handleDeviceDelete}
        onManagePorts={handleManagePorts}
      />

      <LinkDialog
        open={linkDialogOpen}
        sourceDeviceId={linkSourceId}
        targetDeviceId={linkTargetId}
        devices={store.devices}
        fetchPorts={store.fetchPorts}
        onConfirm={handleLinkConfirm}
        onCancel={() => setLinkDialogOpen(false)}
      />

      <PortPanel
        open={portPanelOpen}
        device={portDevice}
        topoId={store.topoId}
        onClose={() => setPortPanelOpen(false)}
        onPortsChanged={store.markDirty}
      />

      <TopoListModal
        open={topoListOpen}
        currentTopoId={store.topoId}
        onClose={() => setTopoListOpen(false)}
        onLoad={(id) => store.loadTopo(id)}
        onNew={handleNewTopo}
      />

      <VersionDrawer
        open={versionOpen}
        topoId={store.topoId}
        onClose={() => setVersionOpen(false)}
        onRestore={handleVersionRestore}
      />

      <ValidationPanel
        open={validationOpen}
        result={validationResult}
        loading={validationLoading}
        onClose={() => setValidationOpen(false)}
        onFix={handleFix}
        onLocate={handleLocateDevice}
      />
    </div>
  );
};

export default TopologyEditor;
