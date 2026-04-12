import { useEffect, useState } from 'react';
import { Drawer, Form, Input, Select, Button, Space, InputNumber, message, Divider, Tag } from 'antd';
import type { Device, DeviceType, Port } from './types';

interface DeviceDrawerProps {
  open: boolean;
  device: Device | null;
  deviceTypes: DeviceType[];
  isNew: boolean;
  onClose: () => void;
  onSave: (data: Record<string, unknown>, isNew: boolean) => Promise<void>;
  onDelete: (id: string) => void;
  onManagePorts: (deviceId: string) => void;
}

const DeviceDrawer: React.FC<DeviceDrawerProps> = ({
  open, device, deviceTypes, isNew, onClose, onSave, onDelete, onManagePorts,
}) => {
  const [form] = Form.useForm();
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (open) {
      if (device && !isNew) {
        form.setFieldsValue({
          name: device.name,
          type: device.type,
          ip: device.ip,
          vendor: device.vendor,
          model: device.model,
          status: device.status,
          dnTemplate: device.dn ? undefined : 'NE={id}',
        });
      } else {
        form.resetFields();
        form.setFieldsValue({
          type: deviceTypes[0]?.id || 'router',
          status: 'online',
          portCount: 4,
          portType: 'GE',
          portSpeed: '1Gbps',
          dnTemplate: 'NE={id}',
        });
      }
    }
  }, [open, device, isNew, form, deviceTypes]);

  const handleSave = async () => {
    try {
      const values = await form.validateFields();
      setSaving(true);
      const data: Record<string, unknown> = {
        name: values.name,
        type: values.type,
        ip: values.ip,
        vendor: values.vendor,
        model: values.model,
        status: values.status,
      };
      if (isNew) {
        data.dnTemplate = values.dnTemplate;
        if (values.portCount > 0) {
          data.portConfig = {
            count: values.portCount,
            type: values.portType || 'GE',
            speed: values.portSpeed || '1Gbps',
          };
        }
      }
      await onSave(data, isNew);
      onClose();
    } catch {
      // validation error
    } finally {
      setSaving(false);
    }
  };

  return (
    <Drawer
      title={isNew ? '创建设备' : `编辑设备: ${device?.name || ''}`}
      open={open}
      onClose={onClose}
      width={400}
      extra={
        <Space>
          {!isNew && device && (
            <>
              <Button onClick={() => onManagePorts(device.id)}>管理端口</Button>
              <Button danger onClick={() => { onDelete(device.id); onClose(); }}>删除</Button>
            </>
          )}
          <Button type="primary" loading={saving} onClick={handleSave}>保存</Button>
        </Space>
      }
    >
      <Form form={form} layout="vertical" size="small">
        <Form.Item name="name" label="设备名称" rules={[{ required: true, message: '请输入设备名称' }]}>
          <Input placeholder="如: Router-1" />
        </Form.Item>
        <Form.Item name="type" label="设备类型" rules={[{ required: true }]}>
          <Select>
            {deviceTypes.map(dt => (
              <Select.Option key={dt.id} value={dt.id}>{dt.name}</Select.Option>
            ))}
          </Select>
        </Form.Item>
        <Form.Item name="ip" label="管理 IP">
          <Input placeholder="如: 192.168.1.1" />
        </Form.Item>
        <Form.Item name="vendor" label="厂商">
          <Input placeholder="如: Huawei" />
        </Form.Item>
        <Form.Item name="model" label="型号">
          <Input placeholder="如: NE40E" />
        </Form.Item>
        <Form.Item name="status" label="状态">
          <Select>
            <Select.Option value="online">在线</Select.Option>
            <Select.Option value="offline">离线</Select.Option>
            <Select.Option value="maintenance">维护</Select.Option>
          </Select>
        </Form.Item>

        {isNew && (
          <>
            <Divider>DN 配置</Divider>
            <Form.Item name="dnTemplate" label="DN 模板">
              <Input placeholder="NE={id}" />
            </Form.Item>

            <Divider>端口配置</Divider>
            <Form.Item name="portCount" label="端口数量">
              <InputNumber min={0} max={1000} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="portType" label="端口类型">
              <Select>
                <Select.Option value="GE">GE</Select.Option>
                <Select.Option value="10GE">10GE</Select.Option>
                <Select.Option value="40GE">40GE</Select.Option>
                <Select.Option value="100GE">100GE</Select.Option>
                <Select.Option value="ETH">ETH</Select.Option>
              </Select>
            </Form.Item>
            <Form.Item name="portSpeed" label="端口速率">
              <Select>
                <Select.Option value="1Gbps">1Gbps</Select.Option>
                <Select.Option value="10Gbps">10Gbps</Select.Option>
                <Select.Option value="40Gbps">40Gbps</Select.Option>
                <Select.Option value="100Gbps">100Gbps</Select.Option>
              </Select>
            </Form.Item>
          </>
        )}
      </Form>
    </Drawer>
  );
};

export default DeviceDrawer;
