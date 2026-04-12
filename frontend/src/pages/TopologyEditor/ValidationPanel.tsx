import { Drawer, Table, Button, Space, Tag, Typography, Statistic, Row, Col, message } from 'antd';
import { CheckCircleOutlined, CloseCircleOutlined, WarningOutlined, ToolOutlined } from '@ant-design/icons';
import type { ValidationIssue } from './types';

interface ValidationResult {
  stats: { devices: number; ports: number; links: number; alarms: number; metrics: number };
  issues: ValidationIssue[];
  errorCount: number;
  warningCount: number;
}

interface ValidationPanelProps {
  open: boolean;
  result: ValidationResult | null;
  loading: boolean;
  onClose: () => void;
  onFix: () => void;
  onLocate: (target: string) => void;
}

const ValidationPanel: React.FC<ValidationPanelProps> = ({
  open, result, loading, onClose, onFix, onLocate,
}) => {
  if (!result) return null;

  const allPassed = result.errorCount === 0 && result.warningCount === 0;

  const columns = [
    {
      title: '级别', dataIndex: 'level', key: 'level', width: 80,
      render: (level: string) => (
        <Tag color={level === 'error' ? 'red' : 'orange'} icon={level === 'error' ? <CloseCircleOutlined /> : <WarningOutlined />}>
          {level === 'error' ? '错误' : '警告'}
        </Tag>
      ),
    },
    { title: '类型', dataIndex: 'type', key: 'type', width: 140 },
    { title: '描述', dataIndex: 'message', key: 'message' },
    {
      title: '可修复', dataIndex: 'fixable', key: 'fixable', width: 80,
      render: (f: boolean) => f ? <Tag color="green">是</Tag> : <Tag>否</Tag>,
    },
    {
      title: '操作', key: 'action', width: 80,
      render: (_: unknown, record: ValidationIssue) => record.target ? (
        <Button type="link" size="small" onClick={() => onLocate(record.target!)}>定位</Button>
      ) : null,
    },
  ];

  return (
    <Drawer
      title="拓扑验证"
      open={open}
      onClose={onClose}
      width={700}
      placement="bottom"
      height={400}
      extra={
        result.issues.some(i => i.fixable) ? (
          <Button icon={<ToolOutlined />} type="primary" onClick={onFix} loading={loading}>
            一键修复
          </Button>
        ) : null
      }
    >
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={4}><Statistic title="设备" value={result.stats.devices} /></Col>
        <Col span={4}><Statistic title="端口" value={result.stats.ports} /></Col>
        <Col span={4}><Statistic title="链路" value={result.stats.links} /></Col>
        <Col span={4}><Statistic title="错误" value={result.errorCount} valueStyle={{ color: result.errorCount > 0 ? '#ff4d4f' : undefined }} /></Col>
        <Col span={4}><Statistic title="警告" value={result.warningCount} valueStyle={{ color: result.warningCount > 0 ? '#faad14' : undefined }} /></Col>
      </Row>

      {allPassed ? (
        <div style={{ textAlign: 'center', padding: 32 }}>
          <CheckCircleOutlined style={{ fontSize: 48, color: '#52c41a' }} />
          <Typography.Title level={4} style={{ color: '#52c41a', marginTop: 16 }}>验证通过</Typography.Title>
        </div>
      ) : (
        <Table
          dataSource={result.issues}
          columns={columns}
          rowKey={(_, i) => String(i)}
          size="small"
          pagination={false}
          scroll={{ y: 200 }}
        />
      )}
    </Drawer>
  );
};

export default ValidationPanel;
