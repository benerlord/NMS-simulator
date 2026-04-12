import { useEffect, useState } from 'react';
import { Drawer, Table, Button, Popconfirm, message } from 'antd';
import * as api from '../../api/topologies';

interface Version {
  id: number;
  topology_id: string;
  version: number;
  data: string;
  created_at: string;
}

interface VersionDrawerProps {
  open: boolean;
  topoId: string | null;
  onClose: () => void;
  onRestore: () => void;
}

const VersionDrawer: React.FC<VersionDrawerProps> = ({ open, topoId, onClose, onRestore }) => {
  const [versions, setVersions] = useState<Version[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (open && topoId) {
      setLoading(true);
      api.listVersions(topoId)
        .then(res => setVersions(res.data?.items || []))
        .finally(() => setLoading(false));
    }
  }, [open, topoId]);

  const handleRestore = async (version: number) => {
    if (!topoId) return;
    await api.restoreVersion(topoId, version);
    message.success(`已恢复到版本 ${version}`);
    onRestore();
    onClose();
  };

  const columns = [
    { title: '版本', dataIndex: 'version', key: 'version', width: 80 },
    {
      title: '时间', dataIndex: 'created_at', key: 'created_at',
      render: (t: string) => t ? new Date(t).toLocaleString() : '-',
    },
    {
      title: '操作', key: 'action', width: 100,
      render: (_: unknown, record: Version) => (
        <Popconfirm title={`确认恢复到版本 ${record.version}？`} onConfirm={() => handleRestore(record.version)}>
          <Button type="link" size="small">恢复</Button>
        </Popconfirm>
      ),
    },
  ];

  return (
    <Drawer title="版本历史" open={open} onClose={onClose} width={450}>
      <Table
        dataSource={versions}
        columns={columns}
        rowKey="id"
        size="small"
        loading={loading}
        pagination={false}
      />
    </Drawer>
  );
};

export default VersionDrawer;
