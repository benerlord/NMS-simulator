import { useState, useEffect, useCallback } from 'react';
import {
  Typography, Table, Tag, Row, Col, Button, Space, Select, Input, Popconfirm, message,
  Descriptions, Drawer,
} from 'antd';
import { DeleteOutlined, ReloadOutlined, ExportOutlined, EyeOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import * as api from '../../api/apiConfigs';

const { Search } = Input;

const METHOD_COLORS: Record<string, string> = {
  GET: 'green', POST: 'blue', PUT: 'orange', DELETE: 'red', PATCH: 'purple',
};

const STATUS_COLORS: Record<string, string> = {
  '2': 'green', '3': 'cyan', '4': 'orange', '5': 'red',
};

interface LogItem {
  id: string;
  timestamp: string;
  method: string;
  path: string;
  query_string: string;
  headers: string;
  request_body: string;
  status_code: number;
  response_body: string;
  duration: number;
  config_id: string;
  config_name: string;
  client_ip: string;
  error: string;
}

const LogViewer = () => {
  const [logs, setLogs] = useState<LogItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [methodFilter, setMethodFilter] = useState<string | undefined>(undefined);
  const [pathFilter, setPathFilter] = useState('');
  const [detailLog, setDetailLog] = useState<LogItem | null>(null);

  const fetchLogs = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.listRequestLogs({
        limit: pageSize,
        offset: (page - 1) * pageSize,
        method: methodFilter,
        path: pathFilter || undefined,
      });
      const data = (res as any).data || {};
      setLogs(data.items || []);
      setTotal(data.total || 0);
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, methodFilter, pathFilter]);

  useEffect(() => { fetchLogs(); }, [fetchLogs]);

  const handleClear = async () => {
    await api.clearRequestLogs();
    message.success('日志已清空');
    fetchLogs();
  };

  const handleExport = () => {
    const blob = new Blob([JSON.stringify(logs, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'request_logs.json';
    a.click();
    URL.revokeObjectURL(url);
  };

  const columns: ColumnsType<LogItem> = [
    {
      title: '时间', dataIndex: 'timestamp', width: 170,
      render: (v: string) => v?.replace('T', ' ').slice(0, 19),
    },
    {
      title: '方法', dataIndex: 'method', width: 70,
      render: (m: string) => <Tag color={METHOD_COLORS[m] || 'default'}>{m}</Tag>,
    },
    { title: '路径', dataIndex: 'path', ellipsis: true },
    {
      title: '状态', dataIndex: 'status_code', width: 70,
      render: (s: number) => {
        const cat = String(s).charAt(0);
        return <Tag color={STATUS_COLORS[cat] || 'default'}>{s}</Tag>;
      },
    },
    {
      title: '耗时', dataIndex: 'duration', width: 80,
      render: (d: number) => `${d}ms`,
    },
    { title: '配置', dataIndex: 'config_name', width: 120, ellipsis: true },
    {
      title: '错误', dataIndex: 'error', ellipsis: true, width: 150,
      render: (e: string) => e ? <Typography.Text type="danger">{e}</Typography.Text> : '-',
    },
    {
      title: '操作', width: 60,
      render: (_, record) => (
        <Button type="link" size="small" icon={<EyeOutlined />} onClick={() => setDetailLog(record)} />
      ),
    },
  ];

  return (
    <div>
      <Row justify="space-between" align="middle" style={{ marginBottom: 16 }}>
        <Col>
          <Typography.Title level={4} style={{ margin: 0 }}>请求日志</Typography.Title>
        </Col>
        <Col>
          <Space>
            <Select
              allowClear
              placeholder="方法"
              style={{ width: 100 }}
              value={methodFilter}
              onChange={setMethodFilter}
              options={['GET', 'POST', 'PUT', 'DELETE', 'PATCH'].map(m => ({ value: m, label: m }))}
            />
            <Search placeholder="路径搜索" allowClear style={{ width: 200 }} onSearch={setPathFilter} />
            <Button icon={<ReloadOutlined />} onClick={fetchLogs}>刷新</Button>
            <Button icon={<ExportOutlined />} onClick={handleExport}>导出</Button>
            <Popconfirm title="确认清空所有日志?" onConfirm={handleClear}>
              <Button danger icon={<DeleteOutlined />}>清空</Button>
            </Popconfirm>
          </Space>
        </Col>
      </Row>

      <Table
        rowKey="id"
        columns={columns}
        dataSource={logs}
        loading={loading}
        size="small"
        pagination={{
          current: page,
          pageSize,
          total,
          showSizeChanger: true,
          showTotal: (t) => `共 ${t} 条`,
          onChange: (p, ps) => { setPage(p); setPageSize(ps); },
        }}
      />

      <Drawer
        title="请求详情"
        open={!!detailLog}
        onClose={() => setDetailLog(null)}
        width={640}
      >
        {detailLog && (
          <Descriptions column={1} size="small" bordered>
            <Descriptions.Item label="ID">{detailLog.id}</Descriptions.Item>
            <Descriptions.Item label="时间">{detailLog.timestamp}</Descriptions.Item>
            <Descriptions.Item label="方法">{detailLog.method}</Descriptions.Item>
            <Descriptions.Item label="路径">{detailLog.path}</Descriptions.Item>
            <Descriptions.Item label="查询串">{detailLog.query_string || '-'}</Descriptions.Item>
            <Descriptions.Item label="状态码">{detailLog.status_code}</Descriptions.Item>
            <Descriptions.Item label="耗时">{detailLog.duration}ms</Descriptions.Item>
            <Descriptions.Item label="客户端IP">{detailLog.client_ip || '-'}</Descriptions.Item>
            <Descriptions.Item label="配置名">{detailLog.config_name || '-'}</Descriptions.Item>
            <Descriptions.Item label="配置ID">{detailLog.config_id || '-'}</Descriptions.Item>
            <Descriptions.Item label="错误">{detailLog.error || '-'}</Descriptions.Item>
            <Descriptions.Item label="请求头">
              <pre style={{ maxHeight: 150, overflow: 'auto', fontSize: 12, margin: 0 }}>
                {formatJson(detailLog.headers)}
              </pre>
            </Descriptions.Item>
            <Descriptions.Item label="请求体">
              <pre style={{ maxHeight: 150, overflow: 'auto', fontSize: 12, margin: 0 }}>
                {formatJson(detailLog.request_body)}
              </pre>
            </Descriptions.Item>
            <Descriptions.Item label="响应体">
              <pre style={{ maxHeight: 300, overflow: 'auto', fontSize: 12, margin: 0 }}>
                {formatJson(detailLog.response_body)}
              </pre>
            </Descriptions.Item>
          </Descriptions>
        )}
      </Drawer>
    </div>
  );
};

function formatJson(val: string | null): string {
  if (!val) return '-';
  try {
    return JSON.stringify(JSON.parse(val), null, 2);
  } catch {
    return val;
  }
}

export default LogViewer;
