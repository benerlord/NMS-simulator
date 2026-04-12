import { useState, useEffect } from 'react';
import {
  Button, Input, Row, Col, Typography, Descriptions, Table, Tag, Space, Spin, Divider,
} from 'antd';
import { PlayCircleOutlined, PlusOutlined, DeleteOutlined } from '@ant-design/icons';
import * as api from '../../api/apiConfigs';
import MonacoField from './MonacoField';

interface Props {
  config: Record<string, any>;
}

const TestPanel = ({ config }: Props) => {
  const [paramInputs, setParamInputs] = useState<Array<{ key: string; value: string }>>([]);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<Record<string, any> | null>(null);

  useEffect(() => {
    // Pre-populate params from config query definition
    const query = tryParse(config.query);
    const paramDefs = query.params || [];
    setParamInputs(paramDefs.map((p: any) => ({
      key: p.param || '',
      value: p.default || '',
    })));
  }, [config]);

  const addParam = () => {
    setParamInputs([...paramInputs, { key: '', value: '' }]);
  };

  const removeParam = (index: number) => {
    setParamInputs(paramInputs.filter((_, i) => i !== index));
  };

  const updateParam = (index: number, field: 'key' | 'value', val: string) => {
    const updated = [...paramInputs];
    updated[index][field] = val;
    setParamInputs(updated);
  };

  const handleExecute = async () => {
    setLoading(true);
    setResult(null);
    try {
      const params: Record<string, string> = {};
      paramInputs.forEach(p => {
        if (p.key && p.value) params[p.key] = p.value;
      });
      const res = await api.testConfig(config.id, params);
      setResult((res as any).data || {});
    } catch {
      // handled by interceptor
    } finally {
      setLoading(false);
    }
  };

  const ds = tryParse(config.data_source);

  return (
    <div>
      <Descriptions column={2} size="small" bordered style={{ marginBottom: 16 }}>
        <Descriptions.Item label="方法">
          <Tag color={config.method === 'GET' ? 'green' : 'blue'}>{config.method}</Tag>
        </Descriptions.Item>
        <Descriptions.Item label="路径">{config.path}</Descriptions.Item>
        <Descriptions.Item label="数据源"><Tag>{ds.type || 'sql'}</Tag></Descriptions.Item>
        <Descriptions.Item label="配置ID">{config.id}</Descriptions.Item>
      </Descriptions>

      <Typography.Text strong>请求参数</Typography.Text>
      <div style={{ margin: '8px 0' }}>
        {paramInputs.map((p, i) => (
          <Row gutter={8} key={i} style={{ marginBottom: 4 }}>
            <Col span={10}>
              <Input size="small" placeholder="参数名" value={p.key}
                onChange={e => updateParam(i, 'key', e.target.value)} />
            </Col>
            <Col span={10}>
              <Input size="small" placeholder="参数值" value={p.value}
                onChange={e => updateParam(i, 'value', e.target.value)} />
            </Col>
            <Col span={4}>
              <Button size="small" danger icon={<DeleteOutlined />} onClick={() => removeParam(i)} />
            </Col>
          </Row>
        ))}
        <Button type="dashed" size="small" icon={<PlusOutlined />} onClick={addParam} style={{ marginTop: 4 }}>
          添加参数
        </Button>
      </div>

      <Button type="primary" icon={<PlayCircleOutlined />} onClick={handleExecute} loading={loading}
        style={{ marginTop: 8, marginBottom: 16 }}>
        执行测试
      </Button>

      {result && (
        <>
          <Divider />
          {result.executionTime !== undefined && (
            <Typography.Text type="secondary" style={{ marginBottom: 8, display: 'block' }}>
              执行耗时: {result.executionTime}ms
            </Typography.Text>
          )}

          {result.executedSql && (
            <>
              <Typography.Text strong>执行 SQL</Typography.Text>
              <MonacoField value={result.executedSql} onChange={() => {}} language="sql" height={80} />
            </>
          )}

          {result.queryResult && (
            <>
              <Typography.Text strong style={{ display: 'block', marginTop: 12 }}>
                查询结果 (共 {result.queryResult.total ?? result.queryResult.items?.length ?? 0} 条)
              </Typography.Text>
              {result.queryResult.items?.length > 0 && (
                <Table
                  size="small"
                  dataSource={result.queryResult.items}
                  columns={Object.keys(result.queryResult.items[0]).map(k => ({
                    title: k, dataIndex: k, key: k, ellipsis: true,
                    render: (v: any) => v === null ? <Tag>NULL</Tag> : String(v),
                  }))}
                  rowKey={(_, i) => String(i)}
                  scroll={{ x: 'max-content' }}
                  pagination={{ pageSize: 10, size: 'small' }}
                  style={{ marginTop: 8 }}
                />
              )}
            </>
          )}

          {result.renderedResponse && (
            <>
              <Typography.Text strong style={{ display: 'block', marginTop: 12 }}>渲染结果</Typography.Text>
              <MonacoField
                value={JSON.stringify(result.renderedResponse, null, 2)}
                onChange={() => {}} language="json" height={200}
              />
            </>
          )}

          {result.error && (
            <Typography.Text type="danger" style={{ display: 'block', marginTop: 12 }}>
              错误: {result.error}
            </Typography.Text>
          )}
        </>
      )}
    </div>
  );
};

function tryParse(val: any): any {
  if (!val) return {};
  if (typeof val === 'object') return val;
  try { return JSON.parse(val); } catch { return {}; }
}

export default TestPanel;
