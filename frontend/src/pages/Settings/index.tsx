import { useState, useEffect, useCallback } from 'react';
import {
  Typography, Tabs, Form, Input, InputNumber, Switch, Button, Card, Row, Col,
  Tag, Space, Table, Popconfirm, message, Descriptions, Divider, Spin,
} from 'antd';
import {
  PlayCircleOutlined, PauseCircleOutlined, ReloadOutlined, DeleteOutlined,
  SaveOutlined, PlusOutlined, CheckOutlined,
} from '@ant-design/icons';
import * as api from '../../api/apiConfigs';

// ==== System Settings Tab ====

const SystemSettings = () => {
  const [settings, setSettings] = useState<Record<string, any[]>>({});
  const [values, setValues] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);

  const fetchSettings = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.listSettings();
      const items = (res as any).data?.items || [];
      const grouped: Record<string, any[]> = {};
      const vals: Record<string, string> = {};
      items.forEach((item: any) => {
        const cat = item.category || 'general';
        if (!grouped[cat]) grouped[cat] = [];
        grouped[cat].push(item);
        vals[item.key] = item.value;
      });
      setSettings(grouped);
      setValues(vals);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchSettings(); }, [fetchSettings]);

  const handleSave = async () => {
    const settingsArr = Object.entries(values).map(([key, value]) => ({ key, value }));
    await api.batchUpdateSettings(settingsArr);
    message.success('设置已保存');
  };

  const categoryLabels: Record<string, string> = {
    general: '基本设置',
    auto_save: '自动保存',
    history: '历史记录',
    log: '日志设置',
  };

  if (loading) return <Spin />;

  return (
    <div>
      {Object.entries(settings).map(([cat, items]) => (
        <Card key={cat} title={categoryLabels[cat] || cat} size="small" style={{ marginBottom: 16 }}>
          {items.map((item: any) => (
            <Row key={item.key} gutter={16} style={{ marginBottom: 12 }} align="middle">
              <Col span={6}>
                <Typography.Text strong>{item.key}</Typography.Text>
                <br />
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>{item.description}</Typography.Text>
              </Col>
              <Col span={18}>
                {item.value === 'true' || item.value === 'false' ? (
                  <Switch
                    checked={values[item.key] === 'true'}
                    onChange={(c) => setValues({ ...values, [item.key]: c ? 'true' : 'false' })}
                  />
                ) : (
                  <Input
                    value={values[item.key]}
                    onChange={(e) => setValues({ ...values, [item.key]: e.target.value })}
                    style={{ maxWidth: 300 }}
                  />
                )}
              </Col>
            </Row>
          ))}
        </Card>
      ))}
      <Button type="primary" icon={<SaveOutlined />} onClick={handleSave}>保存设置</Button>
    </div>
  );
};

// ==== Protocol Management Tab ====

const ProtocolManager = () => {
  const [protocols, setProtocols] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [routes, setRoutes] = useState<any[]>([]);
  const [mockConfig, setMockConfig] = useState<any>(null);

  const fetchProtocols = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.listProtocols();
      setProtocols((res as any).data || []);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchProtocols(); }, [fetchProtocols]);

  const handleStart = async (name: string) => {
    await api.startProtocol(name);
    message.success('已启动');
    fetchProtocols();
  };

  const handleStop = async (name: string) => {
    await api.stopProtocol(name);
    message.success('已停止');
    fetchProtocols();
  };

  const handleRestart = async (name: string) => {
    await api.restartProtocol(name);
    message.success('已重启');
    fetchProtocols();
  };

  const loadRoutes = async () => {
    try {
      const res = await api.listMockRoutes();
      setRoutes((res as any).data?.items || []);
    } catch { /* handled */ }
  };

  const loadMockConfig = async () => {
    try {
      const res = await api.getMockConfig();
      setMockConfig((res as any).data || {});
    } catch { /* handled */ }
  };

  useEffect(() => { loadMockConfig(); }, []);

  return (
    <div>
      <Row gutter={16}>
        {protocols.map((p: any) => (
          <Col key={p.name} span={12}>
            <Card
              title={
                <Space>
                  {p.displayName || p.name}
                  <Tag color={p.status === 'running' ? 'green' : 'default'}>{p.status}</Tag>
                </Space>
              }
              size="small"
              extra={
                <Space>
                  {p.status !== 'running' ? (
                    <Button size="small" type="primary" icon={<PlayCircleOutlined />}
                      onClick={() => handleStart(p.name)}>启动</Button>
                  ) : (
                    <>
                      <Button size="small" danger icon={<PauseCircleOutlined />}
                        onClick={() => handleStop(p.name)}>停止</Button>
                      <Button size="small" icon={<ReloadOutlined />}
                        onClick={() => handleRestart(p.name)}>重启</Button>
                    </>
                  )}
                </Space>
              }
              style={{ marginBottom: 16 }}
            >
              <Descriptions size="small" column={2}>
                <Descriptions.Item label="端口">{p.port}</Descriptions.Item>
                <Descriptions.Item label="启动时间">{p.startedAt || '-'}</Descriptions.Item>
                {p.stats && (
                  <>
                    <Descriptions.Item label="请求数">{p.stats.totalRequests}</Descriptions.Item>
                    <Descriptions.Item label="活跃路由">{p.stats.activeRoutes}</Descriptions.Item>
                  </>
                )}
              </Descriptions>
            </Card>
          </Col>
        ))}
      </Row>

      {mockConfig && (
        <Card title="HTTP Mock 配置" size="small" style={{ marginBottom: 16 }}>
          <Descriptions size="small" column={2}>
            <Descriptions.Item label="监听地址">{mockConfig.host}</Descriptions.Item>
            <Descriptions.Item label="端口">{mockConfig.port}</Descriptions.Item>
          </Descriptions>
        </Card>
      )}

      <Card title="活跃路由" size="small" extra={<Button size="small" onClick={loadRoutes}>加载路由</Button>}>
        {routes.length > 0 ? (
          <Table
            size="small"
            rowKey={(r, i) => `${r.method}-${r.path}-${i}`}
            dataSource={routes}
            columns={[
              { title: '方法', dataIndex: 'method', width: 80, render: (m: string) => <Tag color={m === 'GET' ? 'green' : 'blue'}>{m}</Tag> },
              { title: '路径', dataIndex: 'path' },
              { title: '名称', dataIndex: 'name' },
            ]}
            pagination={false}
          />
        ) : (
          <Typography.Text type="secondary">点击"加载路由"查看当前活跃路由</Typography.Text>
        )}
      </Card>
    </div>
  );
};

// ==== Token Management Tab ====

const TokenManager = () => {
  const [config, setConfig] = useState<any>(null);
  const [tokens, setTokens] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [credentials, setCredentials] = useState<Array<{ username: string; password: string }>>([]);
  const [tokenExpiry, setTokenExpiry] = useState(1800);
  const [testUser, setTestUser] = useState('');
  const [testPass, setTestPass] = useState('');
  const [testResult, setTestResult] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [cfgRes, tokRes] = await Promise.all([
        api.getSessionConfig(),
        api.listSessions(),
      ]);
      const cfg = (cfgRes as any).data || {};
      setConfig(cfg);
      setTokenExpiry(cfg.tokenExpiry || 1800);
      setCredentials(cfg.credentials || []);
      setTokens((tokRes as any).data?.items || []);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleSaveConfig = async () => {
    await api.updateSessionConfig({ tokenExpiry, credentials });
    message.success('认证配置已保存');
    fetchData();
  };

  const handleDeleteToken = async (token: string) => {
    await api.deleteSession(token);
    fetchData();
  };

  const handleClearTokens = async () => {
    await api.clearSessions();
    message.success('已清空所有 Token');
    fetchData();
  };

  const addCredential = () => {
    setCredentials([...credentials, { username: '', password: '' }]);
  };

  const removeCredential = (index: number) => {
    setCredentials(credentials.filter((_, i) => i !== index));
  };

  const updateCredential = (index: number, field: 'username' | 'password', value: string) => {
    const updated = [...credentials];
    updated[index] = { ...updated[index], [field]: value };
    setCredentials(updated);
  };

  const handleTestLogin = async () => {
    if (!testUser || !testPass) {
      message.warning('请输入用户名和密码');
      return;
    }
    try {
      // Test login by using the mock server endpoint indirectly
      // We'll just validate against the current credentials
      const matched = credentials.some(c => c.username === testUser && c.password === testPass);
      setTestResult(matched ? '认证成功 (凭据匹配)' : '认证失败 (凭据不匹配)');
    } catch {
      setTestResult('测试失败');
    }
  };

  const tokenColumns = [
    { title: 'Token', dataIndex: 'token', ellipsis: true },
    { title: '创建时间', dataIndex: 'createdAt', width: 170 },
    { title: '过期时间', dataIndex: 'expiresAt', width: 170 },
    {
      title: '操作', width: 80,
      render: (_: any, record: any) => (
        <Popconfirm title="确认删除?" onConfirm={() => handleDeleteToken(record.token)}>
          <Button type="link" size="small" danger icon={<DeleteOutlined />} />
        </Popconfirm>
      ),
    },
  ];

  return (
    <Spin spinning={loading}>
      <Card title="认证配置" size="small" style={{ marginBottom: 16 }}>
        <Row gutter={16} style={{ marginBottom: 16 }}>
          <Col span={8}>
            <Typography.Text>Token 有效期 (秒)</Typography.Text>
            <InputNumber min={60} max={86400} value={tokenExpiry} onChange={(v) => setTokenExpiry(v || 1800)}
              style={{ width: '100%', marginTop: 4 }} />
          </Col>
        </Row>

        <Typography.Text strong>凭据列表</Typography.Text>
        <div style={{ marginTop: 8 }}>
          {credentials.map((c, i) => (
            <Row gutter={8} key={i} style={{ marginBottom: 4 }}>
              <Col span={10}>
                <Input size="small" placeholder="用户名" value={c.username}
                  onChange={e => updateCredential(i, 'username', e.target.value)} />
              </Col>
              <Col span={10}>
                <Input.Password size="small" placeholder="密码" value={c.password}
                  onChange={e => updateCredential(i, 'password', e.target.value)} />
              </Col>
              <Col span={4}>
                <Button size="small" danger icon={<DeleteOutlined />} onClick={() => removeCredential(i)} />
              </Col>
            </Row>
          ))}
          <Button type="dashed" size="small" icon={<PlusOutlined />} onClick={addCredential}>添加凭据</Button>
        </div>
        <Divider />
        <Button type="primary" icon={<SaveOutlined />} onClick={handleSaveConfig}>保存配置</Button>
      </Card>

      <Card title="活跃 Token" size="small" style={{ marginBottom: 16 }}
        extra={
          <Popconfirm title="确认清空所有 Token?" onConfirm={handleClearTokens}>
            <Button size="small" danger icon={<DeleteOutlined />}>清空</Button>
          </Popconfirm>
        }>
        <Table
          size="small"
          rowKey="token"
          dataSource={tokens}
          columns={tokenColumns}
          pagination={{ pageSize: 10 }}
        />
      </Card>

      <Card title="测试登录" size="small">
        <Row gutter={8}>
          <Col span={8}>
            <Input size="small" placeholder="用户名" value={testUser} onChange={e => setTestUser(e.target.value)} />
          </Col>
          <Col span={8}>
            <Input.Password size="small" placeholder="密码" value={testPass} onChange={e => setTestPass(e.target.value)} />
          </Col>
          <Col span={8}>
            <Button size="small" type="primary" icon={<CheckOutlined />} onClick={handleTestLogin}>测试</Button>
          </Col>
        </Row>
        {testResult && (
          <Typography.Text style={{ marginTop: 8, display: 'block' }}
            type={testResult.includes('成功') ? 'success' : 'danger'}>
            {testResult}
          </Typography.Text>
        )}
      </Card>
    </Spin>
  );
};

// ==== Main Settings Page ====

const Settings = () => (
  <div>
    <Typography.Title level={4} style={{ marginBottom: 16 }}>系统设置</Typography.Title>
    <Tabs
      defaultActiveKey="settings"
      items={[
        { key: 'settings', label: '系统设置', children: <SystemSettings /> },
        { key: 'protocols', label: '协议管理', children: <ProtocolManager /> },
        { key: 'tokens', label: 'Token 管理', children: <TokenManager /> },
      ]}
    />
  </div>
);

export default Settings;
