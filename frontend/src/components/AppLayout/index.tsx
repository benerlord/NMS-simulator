import { useState } from 'react';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { Layout, Menu, Typography } from 'antd';
import {
  DashboardOutlined,
  ApartmentOutlined,
  ApiOutlined,
  WifiOutlined,
  FolderOutlined,
  CloudServerOutlined,
  DatabaseOutlined,
  FileTextOutlined,
  SettingOutlined,
} from '@ant-design/icons';

const { Header, Sider, Content } = Layout;

const menuItems = [
  { key: '/dashboard', icon: <DashboardOutlined />, label: '仪表盘' },
  { key: '/topology', icon: <ApartmentOutlined />, label: '拓扑编辑器' },
  { key: '/api-config', icon: <ApiOutlined />, label: 'HTTP 接口配置' },
  { key: '/snmp-config', icon: <WifiOutlined />, label: 'SNMP 配置' },
  { key: '/sftp-config', icon: <FolderOutlined />, label: 'SFTP 配置' },
  { key: '/kafka-config', icon: <CloudServerOutlined />, label: 'Kafka 配置' },
  { key: '/data', icon: <DatabaseOutlined />, label: '数据查看' },
  { key: '/logs', icon: <FileTextOutlined />, label: '日志查看' },
  { key: '/settings', icon: <SettingOutlined />, label: '系统设置' },
];

const AppLayout = () => {
  const [collapsed, setCollapsed] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider
        collapsible
        collapsed={collapsed}
        onCollapse={setCollapsed}
        theme="dark"
      >
        <div style={{ height: 32, margin: 16, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <Typography.Text strong style={{ color: '#fff', fontSize: collapsed ? 14 : 16, whiteSpace: 'nowrap' }}>
            {collapsed ? 'NMS' : 'NMS Simulator'}
          </Typography.Text>
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[location.pathname]}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
        />
      </Sider>
      <Layout>
        <Header style={{ padding: '0 24px', background: '#fff', display: 'flex', alignItems: 'center' }}>
          <Typography.Title level={4} style={{ margin: 0 }}>
            网管系统模拟工具
          </Typography.Title>
        </Header>
        <Content style={{ margin: 24, padding: 24, background: '#fff', borderRadius: 8, minHeight: 280 }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
};

export default AppLayout;
