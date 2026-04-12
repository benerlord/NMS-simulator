import { useState, useEffect } from 'react';
import { Typography, Card, Row, Col, Statistic, Tag, Space, Button, message } from 'antd';
import {
  ApartmentOutlined, ApiOutlined, PlayCircleOutlined, PauseCircleOutlined,
  FileTextOutlined, DatabaseOutlined,
} from '@ant-design/icons';
import * as topoApi from '../../api/topologies';
import * as api from '../../api/apiConfigs';

const Dashboard = () => {
  const [stats, setStats] = useState({
    topologies: 0,
    apiConfigs: 0,
    protocols: [] as any[],
    requestLogs: 0,
  });
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const fetchStats = async () => {
      setLoading(true);
      try {
        const [topoRes, cfgRes, protoRes, logRes] = await Promise.all([
          topoApi.listTopologies(),
          api.listConfigs(),
          api.listProtocols(),
          api.listRequestLogs({ limit: 1 }),
        ]);
        setStats({
          topologies: (topoRes as any).data?.items?.length || 0,
          apiConfigs: (cfgRes as any).data?.total || 0,
          protocols: (protoRes as any).data || [],
          requestLogs: (logRes as any).data?.total || 0,
        });
      } catch { /* handled */ }
      finally { setLoading(false); }
    };
    fetchStats();
  }, []);

  const handleStartAll = async () => {
    await api.startAllProtocols();
    message.success('已启动所有协议');
    window.location.reload();
  };

  const handleStopAll = async () => {
    await api.stopAllProtocols();
    message.success('已停止所有协议');
    window.location.reload();
  };

  return (
    <div>
      <Typography.Title level={4}>仪表盘</Typography.Title>

      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={6}>
          <Card>
            <Statistic title="拓扑数" value={stats.topologies} prefix={<ApartmentOutlined />} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="接口配置数" value={stats.apiConfigs} prefix={<ApiOutlined />} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="请求日志数" value={stats.requestLogs} prefix={<FileTextOutlined />} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="协议状态"
              value={stats.protocols.filter((p: any) => p.status === 'running').length}
              suffix={`/ ${stats.protocols.length}`}
              prefix={<DatabaseOutlined />}
            />
          </Card>
        </Col>
      </Row>

      <Card title="协议服务" extra={
        <Space>
          <Button size="small" type="primary" icon={<PlayCircleOutlined />} onClick={handleStartAll}>全部启动</Button>
          <Button size="small" danger icon={<PauseCircleOutlined />} onClick={handleStopAll}>全部停止</Button>
        </Space>
      }>
        <Row gutter={16}>
          {stats.protocols.map((p: any) => (
            <Col key={p.name} span={8}>
              <Card size="small">
                <Space>
                  <Typography.Text strong>{p.displayName || p.name}</Typography.Text>
                  <Tag color={p.status === 'running' ? 'green' : 'default'}>{p.status}</Tag>
                </Space>
                {p.port && <div><Typography.Text type="secondary">端口: {p.port}</Typography.Text></div>}
                {p.stats && (
                  <div>
                    <Typography.Text type="secondary">
                      请求: {p.stats.totalRequests} | 路由: {p.stats.activeRoutes}
                    </Typography.Text>
                  </div>
                )}
              </Card>
            </Col>
          ))}
        </Row>
      </Card>
    </div>
  );
};

export default Dashboard;
