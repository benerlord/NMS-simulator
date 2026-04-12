import { useState, useEffect, useCallback } from 'react';
import {
  Typography, Table, Button, Space, Tag, Switch, Input, Tabs, Modal,
  Form, Select, Slider, InputNumber, Collapse, Descriptions, message,
  Popconfirm, Upload, Card, Row, Col, Spin, Drawer, Divider,
} from 'antd';
import {
  PlusOutlined, EditOutlined, DeleteOutlined, PlayCircleOutlined,
  ExportOutlined, ImportOutlined, ReloadOutlined, CopyOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import * as api from '../../api/apiConfigs';
import ConfigForm from './ConfigForm';
import TestPanel from './TestPanel';

const { Search } = Input;

const METHOD_COLORS: Record<string, string> = {
  GET: 'green', POST: 'blue', PUT: 'orange', DELETE: 'red', PATCH: 'purple',
};

interface ApiConfigItem {
  id: string;
  name: string;
  group_name: string;
  method: string;
  path: string;
  enabled: number;
  data_source: string;
  auth: string;
  query: string;
  response: string;
  fault: string;
  created_at: string;
  updated_at: string;
}

const ApiConfig = () => {
  const [configs, setConfigs] = useState<ApiConfigItem[]>([]);
  const [groups, setGroups] = useState<Array<{ name: string; count: number }>>([]);
  const [loading, setLoading] = useState(false);
  const [keyword, setKeyword] = useState('');
  const [activeGroup, setActiveGroup] = useState<string | undefined>(undefined);
  const [editVisible, setEditVisible] = useState(false);
  const [editingConfig, setEditingConfig] = useState<ApiConfigItem | null>(null);
  const [testVisible, setTestVisible] = useState(false);
  const [testingConfig, setTestingConfig] = useState<ApiConfigItem | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [cfgRes, grpRes] = await Promise.all([
        api.listConfigs({ keyword: keyword || undefined, group: activeGroup }),
        api.listGroups(),
      ]);
      setConfigs((cfgRes as any).data?.items || []);
      setGroups((grpRes as any).data || []);
    } finally {
      setLoading(false);
    }
  }, [keyword, activeGroup]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleToggle = async (id: string, enabled: boolean) => {
    await api.toggleEnabled(id, enabled);
    fetchData();
  };

  const handleDelete = async (id: string) => {
    await api.deleteConfig(id);
    message.success('已删除');
    fetchData();
  };

  const handleEdit = (record: ApiConfigItem) => {
    setEditingConfig(record);
    setEditVisible(true);
  };

  const handleCreate = () => {
    setEditingConfig(null);
    setEditVisible(true);
  };

  const handleTest = (record: ApiConfigItem) => {
    setTestingConfig(record);
    setTestVisible(true);
  };

  const handleSave = async (values: Record<string, unknown>) => {
    if (editingConfig) {
      await api.updateConfig(editingConfig.id, values);
      message.success('已更新');
    } else {
      await api.createConfig(values);
      message.success('已创建');
    }
    setEditVisible(false);
    fetchData();
  };

  const handleExport = async () => {
    try {
      const res = await api.exportConfigs(activeGroup);
      const blob = new Blob([JSON.stringify(res, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'api_configs.json';
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      // error handled by interceptor
    }
  };

  const handleImport = async (file: File) => {
    try {
      const text = await file.text();
      const configs = JSON.parse(text);
      const arr = Array.isArray(configs) ? configs : [configs];
      await api.importConfigs(arr, false);
      message.success('导入成功');
      fetchData();
    } catch {
      message.error('导入失败');
    }
    return false;
  };

  const columns: ColumnsType<ApiConfigItem> = [
    {
      title: '方法',
      dataIndex: 'method',
      width: 80,
      render: (m: string) => <Tag color={METHOD_COLORS[m] || 'default'}>{m}</Tag>,
    },
    { title: '路径', dataIndex: 'path', ellipsis: true },
    { title: '名称', dataIndex: 'name', ellipsis: true },
    { title: '分组', dataIndex: 'group_name', width: 100 },
    {
      title: '数据源',
      dataIndex: 'data_source',
      width: 80,
      render: (ds: string) => {
        try {
          const parsed = JSON.parse(ds);
          return <Tag>{parsed.type || 'sql'}</Tag>;
        } catch { return <Tag>sql</Tag>; }
      },
    },
    {
      title: '启用',
      dataIndex: 'enabled',
      width: 70,
      render: (v: number, record) => (
        <Switch size="small" checked={!!v} onChange={(c) => handleToggle(record.id, c)} />
      ),
    },
    {
      title: '操作',
      width: 180,
      render: (_, record) => (
        <Space size="small">
          <Button type="link" size="small" icon={<PlayCircleOutlined />} onClick={() => handleTest(record)}>测试</Button>
          <Button type="link" size="small" icon={<EditOutlined />} onClick={() => handleEdit(record)}>编辑</Button>
          <Popconfirm title="确认删除?" onConfirm={() => handleDelete(record.id)}>
            <Button type="link" size="small" danger icon={<DeleteOutlined />}>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const groupTabs = [
    { key: '__all__', label: `全部 (${configs.length})` },
    ...groups.map(g => ({ key: g.name || '__default__', label: `${g.name || '未分组'} (${g.count})` })),
  ];

  return (
    <div>
      <Row justify="space-between" align="middle" style={{ marginBottom: 16 }}>
        <Col>
          <Typography.Title level={4} style={{ margin: 0 }}>HTTP 接口配置</Typography.Title>
        </Col>
        <Col>
          <Space>
            <Search placeholder="搜索名称/路径" allowClear style={{ width: 200 }}
              onSearch={setKeyword} />
            <Button icon={<PlusOutlined />} type="primary" onClick={handleCreate}>新建</Button>
            <Button icon={<ExportOutlined />} onClick={handleExport}>导出</Button>
            <Upload accept=".json" showUploadList={false} beforeUpload={handleImport as any}>
              <Button icon={<ImportOutlined />}>导入</Button>
            </Upload>
          </Space>
        </Col>
      </Row>

      <Tabs
        activeKey={activeGroup || '__all__'}
        items={groupTabs}
        onChange={(k) => setActiveGroup(k === '__all__' ? undefined : (k === '__default__' ? '' : k))}
        style={{ marginBottom: 8 }}
      />

      <Table
        rowKey="id"
        columns={columns}
        dataSource={configs}
        loading={loading}
        size="small"
        pagination={{ pageSize: 20, showSizeChanger: true, showTotal: (t) => `共 ${t} 条` }}
      />

      <Drawer
        title={editingConfig ? '编辑接口配置' : '新建接口配置'}
        open={editVisible}
        onClose={() => setEditVisible(false)}
        width={720}
        destroyOnClose
      >
        <ConfigForm
          initialValues={editingConfig}
          onSave={handleSave}
          onCancel={() => setEditVisible(false)}
        />
      </Drawer>

      <Drawer
        title={`测试执行 - ${testingConfig?.name || ''}`}
        open={testVisible}
        onClose={() => setTestVisible(false)}
        width={720}
        destroyOnClose
      >
        {testingConfig && <TestPanel config={testingConfig} />}
      </Drawer>
    </div>
  );
};

export default ApiConfig;
