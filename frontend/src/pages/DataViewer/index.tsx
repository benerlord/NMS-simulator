import { useState, useEffect, useCallback } from 'react';
import {
  Typography, Tabs, Table, Input, Select, Tag, Row, Col, Button, Space, message,
} from 'antd';
import { SearchOutlined, PlayCircleOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import * as topoApi from '../../api/topologies';

const { Search } = Input;

const DataViewer = () => {
  const [activeTab, setActiveTab] = useState('devices');
  const [topoId, setTopoId] = useState<string | null>(null);
  const [topos, setTopos] = useState<Array<{ id: string; name: string }>>([]);
  const [data, setData] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [keyword, setKeyword] = useState('');

  useEffect(() => {
    topoApi.listTopologies().then((res: any) => {
      const items = res.data?.items || [];
      setTopos(items);
      const active = items.find((t: any) => t.is_active);
      if (active) setTopoId(active.id);
      else if (items.length > 0) setTopoId(items[0].id);
    });
  }, []);

  const fetchData = useCallback(async () => {
    if (!topoId) return;
    setLoading(true);
    try {
      let res: any;
      if (activeTab === 'devices') {
        res = await topoApi.listDevices(topoId, keyword ? { keyword } : {});
      } else if (activeTab === 'alarms') {
        res = await topoApi.listAlarms(topoId, keyword ? { keyword } : {});
      } else if (activeTab === 'metrics') {
        res = await topoApi.listMetrics(topoId, keyword ? { keyword } : {});
      }
      setData(res?.data?.items || []);
    } finally {
      setLoading(false);
    }
  }, [topoId, activeTab, keyword]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const deviceColumns: ColumnsType<any> = [
    { title: '名称', dataIndex: 'name', ellipsis: true },
    { title: 'DN', dataIndex: 'dn', ellipsis: true },
    { title: '类型', dataIndex: 'type', width: 80, render: (v: string) => <Tag>{v}</Tag> },
    { title: 'IP', dataIndex: 'ip', width: 130 },
    { title: '厂商', dataIndex: 'vendor', width: 100 },
    { title: '型号', dataIndex: 'model', width: 100 },
    {
      title: '状态', dataIndex: 'status', width: 80,
      render: (v: string) => <Tag color={v === 'active' ? 'green' : v === 'down' ? 'red' : 'default'}>{v}</Tag>,
    },
  ];

  const alarmColumns: ColumnsType<any> = [
    { title: '设备', dataIndex: 'deviceName', ellipsis: true },
    { title: '级别', dataIndex: 'level', width: 80, render: (v: string) => {
      const colors: Record<string, string> = { critical: 'red', major: 'orange', minor: 'gold', warning: 'blue' };
      return <Tag color={colors[v] || 'default'}>{v}</Tag>;
    }},
    { title: '类型', dataIndex: 'alarmType', width: 100 },
    { title: '描述', dataIndex: 'description', ellipsis: true },
    { title: '状态', dataIndex: 'status', width: 80, render: (v: string) => <Tag color={v === 'active' ? 'red' : 'green'}>{v}</Tag> },
    { title: '发生时间', dataIndex: 'occurTime', width: 170 },
  ];

  const metricColumns: ColumnsType<any> = [
    { title: '设备', dataIndex: 'deviceName', ellipsis: true },
    { title: '指标', dataIndex: 'metricName', width: 120 },
    { title: '值', dataIndex: 'value', width: 100 },
    { title: '单位', dataIndex: 'unit', width: 60 },
    { title: '采集时间', dataIndex: 'collectTime', width: 170 },
  ];

  const columnsMap: Record<string, ColumnsType<any>> = {
    devices: deviceColumns,
    alarms: alarmColumns,
    metrics: metricColumns,
  };

  return (
    <div>
      <Row justify="space-between" align="middle" style={{ marginBottom: 16 }}>
        <Col>
          <Typography.Title level={4} style={{ margin: 0 }}>数据查看</Typography.Title>
        </Col>
        <Col>
          <Space>
            <Select
              style={{ width: 200 }}
              placeholder="选择拓扑"
              value={topoId}
              onChange={setTopoId}
              options={topos.map(t => ({ value: t.id, label: t.name }))}
            />
            <Search placeholder="搜索" allowClear style={{ width: 200 }} onSearch={setKeyword} />
          </Space>
        </Col>
      </Row>

      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={[
          { key: 'devices', label: '设备' },
          { key: 'alarms', label: '告警' },
          { key: 'metrics', label: '指标' },
        ]}
      />

      <Table
        rowKey="id"
        columns={columnsMap[activeTab] || []}
        dataSource={data}
        loading={loading}
        size="small"
        pagination={{ pageSize: 20, showSizeChanger: true, showTotal: (t) => `共 ${t} 条` }}
      />
    </div>
  );
};

export default DataViewer;
