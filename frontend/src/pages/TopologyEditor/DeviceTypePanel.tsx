import { Typography, Card } from 'antd';
import {
  GlobalOutlined, ClusterOutlined, SafetyCertificateOutlined,
  DesktopOutlined, LaptopOutlined,
} from '@ant-design/icons';
import type { DeviceType } from './types';

const TYPE_ICONS: Record<string, React.ReactNode> = {
  router: <GlobalOutlined />,
  switch: <ClusterOutlined />,
  firewall: <SafetyCertificateOutlined />,
  server: <DesktopOutlined />,
  host: <LaptopOutlined />,
};

interface DeviceTypePanelProps {
  deviceTypes: DeviceType[];
  onDragStart: (type: DeviceType, e: React.DragEvent) => void;
}

const DeviceTypePanel: React.FC<DeviceTypePanelProps> = ({ deviceTypes, onDragStart }) => {
  return (
    <div style={{
      width: 160, background: '#fff', borderRight: '1px solid #f0f0f0',
      padding: 12, overflowY: 'auto',
    }}>
      <Typography.Text strong style={{ fontSize: 12, color: '#8c8c8c', marginBottom: 8, display: 'block' }}>
        设备类型
      </Typography.Text>
      {deviceTypes.map(dt => (
        <Card
          key={dt.id}
          size="small"
          hoverable
          draggable
          onDragStart={(e) => onDragStart(dt, e)}
          style={{ marginBottom: 8, cursor: 'grab', textAlign: 'center' }}
          styles={{ body: { padding: '8px 4px' } }}
        >
          <div style={{ fontSize: 24, color: '#1890ff', marginBottom: 4 }}>
            {TYPE_ICONS[dt.id] || TYPE_ICONS[dt.category || ''] || <DesktopOutlined />}
          </div>
          <Typography.Text ellipsis style={{ fontSize: 12 }}>{dt.name}</Typography.Text>
        </Card>
      ))}
    </div>
  );
};

export default DeviceTypePanel;
