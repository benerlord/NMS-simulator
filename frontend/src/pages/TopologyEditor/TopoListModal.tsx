import { useEffect, useState } from 'react';
import { Modal, Table, Button, Space, Input, message, Popconfirm, Tag } from 'antd';
import { PlusOutlined, DeleteOutlined } from '@ant-design/icons';
import type { TopologyInfo } from './types';
import * as api from '../../api/topologies';

interface TopoListModalProps {
  open: boolean;
  currentTopoId: string | null;
  onClose: () => void;
  onLoad: (id: string) => void;
  onNew: () => void;
}

const TopoListModal: React.FC<TopoListModalProps> = ({ open, currentTopoId, onClose, onLoad, onNew }) => {
  const [topos, setTopos] = useState<TopologyInfo[]>([]);
  const [loading, setLoading] = useState(false);

  const loadList = async () => {
    setLoading(true);
    try {
      const res = await api.listTopologies();
      setTopos(res.data?.items || []);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (open) loadList();
  }, [open]);

  const handleDelete = async (id: string) => {
    await api.deleteTopology(id);
    message.success('拓扑已删除');
    loadList();
  };

  const columns = [
    {
      title: '名称', dataIndex: 'name', key: 'name',
      render: (name: string, record: TopologyInfo) => (
        <Space>
          {name}
          {record.id === currentTopoId && <Tag color="blue">当前</Tag>}
        </Space>
      ),
    },
    { title: '描述', dataIndex: 'description', key: 'description', ellipsis: true },
    { title: '版本', dataIndex: 'version', key: 'version', width: 70 },
    {
      title: '更新时间', dataIndex: 'updated_at', key: 'updated_at', width: 180,
      render: (t: string) => t ? new Date(t).toLocaleString() : '-',
    },
    {
      title: '操作', key: 'action', width: 160,
      render: (_: unknown, record: TopologyInfo) => (
        <Space>
          <Button type="link" size="small" onClick={() => { onLoad(record.id); onClose(); }}>
            加载
          </Button>
          <Popconfirm title="确认删除此拓扑？" onConfirm={() => handleDelete(record.id)}>
            <Button type="link" size="small" danger>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <Modal
      title="拓扑列表"
      open={open}
      onCancel={onClose}
      width={700}
      footer={
        <Button icon={<PlusOutlined />} type="primary" onClick={() => { onNew(); onClose(); }}>
          新建拓扑
        </Button>
      }
    >
      <Table
        dataSource={topos}
        columns={columns}
        rowKey="id"
        size="small"
        loading={loading}
        pagination={false}
      />
    </Modal>
  );
};

export default TopoListModal;
