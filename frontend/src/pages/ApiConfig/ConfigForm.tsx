import { useState, useEffect } from 'react';
import {
  Form, Input, Select, Switch, Button, Space, Tabs, Slider,
  InputNumber, Row, Col, Table, Collapse, Typography, Divider,
} from 'antd';
import { PlusOutlined, DeleteOutlined } from '@ant-design/icons';
import * as api from '../../api/apiConfigs';
import MonacoField from './MonacoField';

const METHODS = ['GET', 'POST', 'PUT', 'DELETE', 'PATCH'];
const AUTH_TYPES = [
  { value: 'none', label: '无认证' },
  { value: 'xtoken', label: 'X-Token' },
  { value: 'basic', label: 'Basic Auth' },
];
const COLLECTIONS = ['devices', 'ports', 'links', 'alarms', 'metrics'];

interface Props {
  initialValues: Record<string, any> | null;
  onSave: (values: Record<string, unknown>) => void;
  onCancel: () => void;
}

const ConfigForm = ({ initialValues, onSave, onCancel }: Props) => {
  const [form] = Form.useForm();
  const [dsType, setDsType] = useState('sql');
  const [params, setParams] = useState<Array<{ param: string; sqlParam: string; default: string }>>([]);
  const [sqlText, setSqlText] = useState('');
  const [staticBody, setStaticBody] = useState('{\n  \n}');
  const [responseTemplate, setResponseTemplate] = useState('');

  useEffect(() => {
    if (initialValues) {
      const ds = tryParse(initialValues.data_source);
      const query = tryParse(initialValues.query);
      const resp = tryParse(initialValues.response);
      const auth = tryParse(initialValues.auth);
      const fault = tryParse(initialValues.fault);

      form.setFieldsValue({
        name: initialValues.name,
        method: initialValues.method,
        path: initialValues.path,
        group: initialValues.group_name,
        enabled: !!initialValues.enabled,
        authType: auth.type || 'none',
        authHeaderName: auth.headerName || 'X-Auth-Token',
        paginationEnabled: query.pagination?.enabled ?? false,
        pageNoParam: query.pagination?.pageNoParam || 'pageNo',
        pageSizeParam: query.pagination?.pageSizeParam || 'pageSize',
        defaultPageSize: query.pagination?.defaultPageSize || 100,
        delay: fault.delay || 0,
        errorRate: fault.errorRate || 0,
        errorStatus: fault.errorStatus || 500,
        contentType: resp.contentType || 'application/json',
      });

      setDsType(ds.type || 'sql');
      setSqlText(ds.sql || '');
      setStaticBody(ds.body ? JSON.stringify(ds.body, null, 2) : '{\n  \n}');
      setParams(query.params || []);
      setResponseTemplate(resp.template ? JSON.stringify(resp.template, null, 2) : '');
    } else {
      form.setFieldsValue({
        method: 'GET',
        enabled: true,
        authType: 'none',
        authHeaderName: 'X-Auth-Token',
        paginationEnabled: false,
        pageNoParam: 'pageNo',
        pageSizeParam: 'pageSize',
        defaultPageSize: 100,
        delay: 0,
        errorRate: 0,
        errorStatus: 500,
        contentType: 'application/json',
      });
    }
  }, [initialValues, form]);

  const loadDefaultSql = async (collection: string) => {
    try {
      const res = await api.getDefaultSql(collection);
      const data = (res as any).data;
      setSqlText(data.sql || '');
    } catch { /* handled */ }
  };

  const addParam = () => {
    setParams([...params, { param: '', sqlParam: '', default: '' }]);
  };

  const removeParam = (index: number) => {
    setParams(params.filter((_, i) => i !== index));
  };

  const updateParam = (index: number, field: string, value: string) => {
    const updated = [...params];
    (updated[index] as any)[field] = value;
    setParams(updated);
  };

  const handleSubmit = () => {
    form.validateFields().then((values) => {
      const authObj: Record<string, any> = { type: values.authType };
      if (values.authType === 'xtoken') authObj.headerName = values.authHeaderName;

      const dataSource: Record<string, any> = { type: dsType };
      if (dsType === 'sql') {
        dataSource.sql = sqlText;
      } else {
        try { dataSource.body = JSON.parse(staticBody); } catch { dataSource.body = {}; }
      }

      const query: Record<string, any> = {
        params: params.map(p => ({ param: p.param, sqlParam: p.sqlParam, default: p.default || null })),
        pagination: {
          enabled: values.paginationEnabled,
          pageNoParam: values.pageNoParam,
          pageSizeParam: values.pageSizeParam,
          defaultPageSize: values.defaultPageSize,
        },
      };

      let template = {};
      try { template = JSON.parse(responseTemplate); } catch { /* keep empty */ }

      const result = {
        name: values.name,
        method: values.method,
        path: values.path,
        group: values.group || '',
        enabled: values.enabled,
        auth: authObj,
        dataSource,
        query,
        response: { contentType: values.contentType, template },
        fault: { delay: values.delay || 0, errorRate: values.errorRate || 0, errorStatus: values.errorStatus || 500 },
      };

      onSave(result);
    });
  };

  return (
    <Form form={form} layout="vertical" size="small">
      <Tabs defaultActiveKey="basic" items={[
        {
          key: 'basic',
          label: '基本信息',
          children: (
            <>
              <Form.Item label="名称" name="name" rules={[{ required: true, message: '请输入名称' }]}>
                <Input />
              </Form.Item>
              <Row gutter={16}>
                <Col span={8}>
                  <Form.Item label="方法" name="method" rules={[{ required: true }]}>
                    <Select options={METHODS.map(m => ({ value: m, label: m }))} />
                  </Form.Item>
                </Col>
                <Col span={16}>
                  <Form.Item label="路径" name="path" rules={[{ required: true, message: '请输入路径' }]}>
                    <Input placeholder="/api/example" />
                  </Form.Item>
                </Col>
              </Row>
              <Row gutter={16}>
                <Col span={12}>
                  <Form.Item label="分组" name="group">
                    <Input placeholder="可选分组名" />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item label="启用" name="enabled" valuePropName="checked">
                    <Switch />
                  </Form.Item>
                </Col>
              </Row>
              <Divider>认证</Divider>
              <Row gutter={16}>
                <Col span={12}>
                  <Form.Item label="认证方式" name="authType">
                    <Select options={AUTH_TYPES} />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item label="Token Header 名" name="authHeaderName">
                    <Input />
                  </Form.Item>
                </Col>
              </Row>
            </>
          ),
        },
        {
          key: 'datasource',
          label: '数据源',
          children: (
            <>
              <Form.Item label="数据源类型">
                <Select value={dsType} onChange={setDsType}
                  options={[{ value: 'sql', label: 'SQL 查询' }, { value: 'static', label: '静态数据' }]} />
              </Form.Item>
              {dsType === 'sql' ? (
                <>
                  <Form.Item label="快速加载默认 SQL">
                    <Select placeholder="选择数据集" allowClear onChange={loadDefaultSql}
                      options={COLLECTIONS.map(c => ({ value: c, label: c }))} />
                  </Form.Item>
                  <Form.Item label="SQL 语句">
                    <MonacoField value={sqlText} onChange={setSqlText} language="sql" height={180} />
                  </Form.Item>
                  <Divider>参数绑定</Divider>
                  {params.map((p, i) => (
                    <Row gutter={8} key={i} style={{ marginBottom: 8 }}>
                      <Col span={7}>
                        <Input placeholder="URL 参数名" value={p.param}
                          onChange={e => updateParam(i, 'param', e.target.value)} />
                      </Col>
                      <Col span={7}>
                        <Input placeholder="SQL 参数名 :xxx" value={p.sqlParam}
                          onChange={e => updateParam(i, 'sqlParam', e.target.value)} />
                      </Col>
                      <Col span={7}>
                        <Input placeholder="默认值" value={p.default}
                          onChange={e => updateParam(i, 'default', e.target.value)} />
                      </Col>
                      <Col span={3}>
                        <Button danger icon={<DeleteOutlined />} onClick={() => removeParam(i)} />
                      </Col>
                    </Row>
                  ))}
                  <Button type="dashed" icon={<PlusOutlined />} onClick={addParam} block>添加参数</Button>
                  <Divider>分页</Divider>
                  <Form.Item label="启用分页" name="paginationEnabled" valuePropName="checked">
                    <Switch />
                  </Form.Item>
                  <Row gutter={16}>
                    <Col span={8}>
                      <Form.Item label="页码参数" name="pageNoParam"><Input /></Form.Item>
                    </Col>
                    <Col span={8}>
                      <Form.Item label="每页数参数" name="pageSizeParam"><Input /></Form.Item>
                    </Col>
                    <Col span={8}>
                      <Form.Item label="默认每页数" name="defaultPageSize"><InputNumber min={1} max={1000} style={{ width: '100%' }} /></Form.Item>
                    </Col>
                  </Row>
                </>
              ) : (
                <Form.Item label="静态 JSON 数据">
                  <MonacoField value={staticBody} onChange={setStaticBody} language="json" height={300} />
                </Form.Item>
              )}
            </>
          ),
        },
        {
          key: 'response',
          label: '响应模板',
          children: (
            <>
              <Form.Item label="Content-Type" name="contentType">
                <Input />
              </Form.Item>
              <Form.Item label="响应模板 JSON">
                <MonacoField value={responseTemplate} onChange={setResponseTemplate} language="json" height={200} />
              </Form.Item>
              <Typography.Text type="secondary">
                可用占位符: {'{{items}}'} {'{{total}}'} {'{{pageNo}}'} {'{{pageSize}}'}
              </Typography.Text>
            </>
          ),
        },
        {
          key: 'fault',
          label: '故障模拟',
          children: (
            <>
              <Form.Item label="延迟 (ms)" name="delay">
                <Slider min={0} max={10000} step={100} />
              </Form.Item>
              <Form.Item label="错误率" name="errorRate">
                <Slider min={0} max={1} step={0.01} />
              </Form.Item>
              <Form.Item label="错误状态码" name="errorStatus">
                <Select options={[500, 502, 503, 504, 429, 408].map(s => ({ value: s, label: String(s) }))} />
              </Form.Item>
            </>
          ),
        },
      ]} />

      <Divider />
      <Space>
        <Button type="primary" onClick={handleSubmit}>保存</Button>
        <Button onClick={onCancel}>取消</Button>
      </Space>
    </Form>
  );
};

function tryParse(val: any): any {
  if (!val) return {};
  if (typeof val === 'object') return val;
  try { return JSON.parse(val); } catch { return {}; }
}

export default ConfigForm;
