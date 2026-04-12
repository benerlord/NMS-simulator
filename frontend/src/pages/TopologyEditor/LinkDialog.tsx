import { useEffect, useState } from 'react';
import { Modal, Form, Select, Space, Tag } from 'antd';
import type { Device, Port } from './types';

interface LinkDialogProps {
  open: boolean;
  sourceDeviceId: string | null;
  targetDeviceId: string | null;
  devices: Device[];
  fetchPorts: (deviceId: string) => Promise<Port[]>;
  onConfirm: (data: Record<string, unknown>) => Promise<void>;
  onCancel: () => void;
}

const LinkDialog: React.FC<LinkDialogProps> = ({
  open, sourceDeviceId, targetDeviceId, devices, fetchPorts, onConfirm, onCancel,
}) => {
  const [form] = Form.useForm();
  const [srcPorts, setSrcPorts] = useState<Port[]>([]);
  const [tgtPorts, setTgtPorts] = useState<Port[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (open) {
      form.resetFields();
      form.setFieldsValue({ type: 'physical' });
      if (sourceDeviceId) {
        form.setFieldsValue({ sourceDeviceId });
        fetchPorts(sourceDeviceId).then(ports => setSrcPorts(ports.filter(p => p.status === 'free')));
      }
      if (targetDeviceId) {
        form.setFieldsValue({ targetDeviceId });
        fetchPorts(targetDeviceId).then(ports => setTgtPorts(ports.filter(p => p.status === 'free')));
      }
    }
  }, [open, sourceDeviceId, targetDeviceId, fetchPorts, form]);

  const handleSourceDevChange = async (devId: string) => {
    form.setFieldValue('sourcePortId', undefined);
    const ports = await fetchPorts(devId);
    setSrcPorts(ports.filter(p => p.status === 'free'));
  };

  const handleTargetDevChange = async (devId: string) => {
    form.setFieldValue('targetPortId', undefined);
    const ports = await fetchPorts(devId);
    setTgtPorts(ports.filter(p => p.status === 'free'));
  };

  const handleOk = async () => {
    try {
      const values = await form.validateFields();
      setLoading(true);
      await onConfirm(values);
    } catch {
      // validation
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal
      title="创建链路"
      open={open}
      onOk={handleOk}
      onCancel={onCancel}
      confirmLoading={loading}
      destroyOnClose
    >
      <Form form={form} layout="vertical" size="small">
        <Form.Item name="sourceDeviceId" label="源设备" rules={[{ required: true }]}>
          <Select onChange={handleSourceDevChange} showSearch optionFilterProp="children">
            {devices.map(d => (
              <Select.Option key={d.id} value={d.id}>{d.name}</Select.Option>
            ))}
          </Select>
        </Form.Item>
        <Form.Item name="sourcePortId" label="源端口" rules={[{ required: true, message: '请选择源端口' }]}>
          <Select placeholder={srcPorts.length === 0 ? '无空闲端口' : '选择端口'}>
            {srcPorts.map(p => (
              <Select.Option key={p.id} value={p.id}>
                {p.name} <Tag color="green" style={{ marginLeft: 4 }}>{p.type}</Tag>
              </Select.Option>
            ))}
          </Select>
        </Form.Item>
        <Form.Item name="targetDeviceId" label="目标设备" rules={[{ required: true }]}>
          <Select onChange={handleTargetDevChange} showSearch optionFilterProp="children">
            {devices.map(d => (
              <Select.Option key={d.id} value={d.id}>{d.name}</Select.Option>
            ))}
          </Select>
        </Form.Item>
        <Form.Item name="targetPortId" label="目标端口" rules={[{ required: true, message: '请选择目标端口' }]}>
          <Select placeholder={tgtPorts.length === 0 ? '无空闲端口' : '选择端口'}>
            {tgtPorts.map(p => (
              <Select.Option key={p.id} value={p.id}>
                {p.name} <Tag color="green" style={{ marginLeft: 4 }}>{p.type}</Tag>
              </Select.Option>
            ))}
          </Select>
        </Form.Item>
        <Form.Item name="type" label="链路类型">
          <Select>
            <Select.Option value="physical">物理链路</Select.Option>
            <Select.Option value="logical">逻辑链路</Select.Option>
            <Select.Option value="aggregate">聚合链路</Select.Option>
          </Select>
        </Form.Item>
      </Form>
    </Modal>
  );
};

export default LinkDialog;
