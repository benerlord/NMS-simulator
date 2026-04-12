import { useEffect, useState } from 'react';
import { Drawer, Table, Button, Space, Tag, Input, Select, Modal, Form, InputNumber, message } from 'antd';
import { PlusOutlined, ThunderboltOutlined } from '@ant-design/icons';
import type { Port, Device } from './types';
import * as api from '../../api/topologies';

interface PortPanelProps {
  open: boolean;
  device: Device | null;
  topoId: string | null;
  onClose: () => void;
  onPortsChanged: () => void;
}

const PortPanel: React.FC<PortPanelProps> = ({ open, device, topoId, onClose, onPortsChanged }) => {
  const [ports, setPorts] = useState<Port[]>([]);
  const [loading, setLoading] = useState(false);
  const [statusFilter, setStatusFilter] = useState<string | undefined>();
  const [keyword, setKeyword] = useState('');
  const [genOpen, setGenOpen] = useState(false);
  const [genForm] = Form.useForm();

  const loadPorts = async () => {
    if (!topoId || !device) return;
    setLoading(true);
    try {
      const res = await api.listPorts(topoId, device.id, { status: statusFilter, keyword: keyword || undefined });
      setPorts(res.data?.items || []);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (open && device) loadPorts();
  }, [open, device, statusFilter, keyword]);

  const handleDelete = async (portId: string) => {
    if (!topoId) return;
    await api.deletePort(topoId, portId);
    message.success('端口已删除');
    loadPorts();
    onPortsChanged();
  };

  const handleGenerate = async () => {
    if (!topoId || !device) return;
    try {
      const values = await genForm.validateFields();
      await api.generatePorts(topoId, device.id, values);
      message.success(`已生成 ${values.count} 个端口`);
      setGenOpen(false);
      loadPorts();
      onPortsChanged();
    } catch { /* validation */ }
  };

  const columns = [
    { title: '名称', dataIndex: 'name', key: 'name', width: 140 },
    { title: 'DN', dataIndex: 'dn', key: 'dn', width: 200, ellipsis: true },
    { title: '类型', dataIndex: 'type', key: 'type', width: 80 },
    { title: '速率', dataIndex: 'speed', key: 'speed', width: 80 },
    {
      title: '状态', dataIndex: 'status', key: 'status', width: 100,
      render: (s: string) => (
        <Tag color={s === 'connected' ? 'blue' : s === 'free' ? 'green' : 'red'}>{s}</Tag>
      ),
    },
    {
      title: '操作', key: 'action', width: 80,
      render: (_: unknown, record: Port) => (
        <Button type="link" size="small" danger onClick={() => handleDelete(record.id)}
          disabled={record.status === 'connected'}>
          删除
        </Button>
      ),
    },
  ];

  return (
    <>
      <Drawer
        title={`端口管理 - ${device?.name || ''}`}
        open={open}
        onClose={onClose}
        width={700}
        extra={
          <Space>
            <Button icon={<ThunderboltOutlined />} onClick={() => { genForm.resetFields(); genForm.setFieldsValue({ count: 8, type: 'GE', speed: '1Gbps' }); setGenOpen(true); }}>
              批量生成
            </Button>
          </Space>
        }
      >
        <Space style={{ marginBottom: 12 }}>
          <Input.Search placeholder="搜索端口" allowClear onSearch={setKeyword} style={{ width: 200 }} />
          <Select
            value={statusFilter}
            onChange={setStatusFilter}
            allowClear
            placeholder="状态筛选"
            style={{ width: 120 }}
          >
            <Select.Option value="free">空闲</Select.Option>
            <Select.Option value="connected">已连接</Select.Option>
            <Select.Option value="down">禁用</Select.Option>
          </Select>
        </Space>
        <Table
          dataSource={ports}
          columns={columns}
          rowKey="id"
          size="small"
          loading={loading}
          pagination={false}
          scroll={{ y: 500 }}
        />
      </Drawer>

      <Modal
        title="批量生成端口"
        open={genOpen}
        onOk={handleGenerate}
        onCancel={() => setGenOpen(false)}
        destroyOnClose
      >
        <Form form={genForm} layout="vertical" size="small">
          <Form.Item name="count" label="数量" rules={[{ required: true }]}>
            <InputNumber min={1} max={1000} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="type" label="类型">
            <Select>
              <Select.Option value="GE">GE</Select.Option>
              <Select.Option value="10GE">10GE</Select.Option>
              <Select.Option value="40GE">40GE</Select.Option>
              <Select.Option value="100GE">100GE</Select.Option>
            </Select>
          </Form.Item>
          <Form.Item name="speed" label="速率">
            <Select>
              <Select.Option value="1Gbps">1Gbps</Select.Option>
              <Select.Option value="10Gbps">10Gbps</Select.Option>
              <Select.Option value="40Gbps">40Gbps</Select.Option>
              <Select.Option value="100Gbps">100Gbps</Select.Option>
            </Select>
          </Form.Item>
          <Form.Item name="prefix" label="前缀">
            <Input placeholder="如: GE0/0/" />
          </Form.Item>
          <Form.Item name="startIndex" label="起始编号">
            <InputNumber min={0} style={{ width: '100%' }} />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
};

export default PortPanel;
