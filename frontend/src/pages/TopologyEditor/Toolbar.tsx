import { Button, Space, Input, Select, Tooltip, Typography, Badge, Dropdown, Modal } from 'antd';
import {
  SaveOutlined, FolderOpenOutlined, PlusOutlined,
  CheckCircleOutlined, LayoutOutlined, UndoOutlined,
  DeleteOutlined, SearchOutlined, FullscreenOutlined,
  ExportOutlined, ImportOutlined,
} from '@ant-design/icons';
import type { TopologyInfo } from './types';

interface ToolbarProps {
  topoInfo: TopologyInfo | null;
  dirty: boolean;
  loading: boolean;
  selectedCount: number;
  onSave: () => void;
  onOpenTopoList: () => void;
  onNewTopo: () => void;
  onValidate: () => void;
  onLayout: (algo: string) => void;
  onBatchDelete: () => void;
  onSearch: (keyword: string) => void;
  onFitView: () => void;
  onExport: () => void;
  onImport: () => void;
  onVersions: () => void;
}

const Toolbar: React.FC<ToolbarProps> = ({
  topoInfo, dirty, loading, selectedCount,
  onSave, onOpenTopoList, onNewTopo, onValidate,
  onLayout, onBatchDelete, onSearch, onFitView,
  onExport, onImport, onVersions,
}) => {
  const layoutItems = [
    { key: 'grid', label: '网格布局' },
    { key: 'circular', label: '圆形布局' },
    { key: 'hierarchical', label: '层次布局' },
    { key: 'force', label: '力导向布局' },
  ];

  return (
    <div style={{
      padding: '8px 16px', background: '#fff', borderBottom: '1px solid #f0f0f0',
      display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap',
    }}>
      <Space size={4}>
        <Tooltip title="打开拓扑列表">
          <Button icon={<FolderOpenOutlined />} onClick={onOpenTopoList} />
        </Tooltip>
        <Tooltip title="新建拓扑">
          <Button icon={<PlusOutlined />} onClick={onNewTopo} />
        </Tooltip>
      </Space>

      <div style={{ borderLeft: '1px solid #f0f0f0', height: 24, margin: '0 4px' }} />

      <Typography.Text strong style={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {topoInfo?.name || '未选择拓扑'}
        {dirty && <span style={{ color: '#faad14' }}> *</span>}
      </Typography.Text>

      <div style={{ borderLeft: '1px solid #f0f0f0', height: 24, margin: '0 4px' }} />

      <Space size={4}>
        <Tooltip title="保存">
          <Button icon={<SaveOutlined />} type={dirty ? 'primary' : 'default'} loading={loading} onClick={onSave} disabled={!topoInfo} />
        </Tooltip>
        <Tooltip title="版本历史">
          <Button icon={<UndoOutlined />} onClick={onVersions} disabled={!topoInfo} />
        </Tooltip>
        <Tooltip title="导出">
          <Button icon={<ExportOutlined />} onClick={onExport} disabled={!topoInfo} />
        </Tooltip>
        <Tooltip title="导入">
          <Button icon={<ImportOutlined />} onClick={onImport} />
        </Tooltip>
      </Space>

      <div style={{ borderLeft: '1px solid #f0f0f0', height: 24, margin: '0 4px' }} />

      <Space size={4}>
        <Tooltip title="验证">
          <Button icon={<CheckCircleOutlined />} onClick={onValidate} disabled={!topoInfo} />
        </Tooltip>
        <Dropdown menu={{ items: layoutItems, onClick: ({ key }) => onLayout(key) }} disabled={!topoInfo}>
          <Button icon={<LayoutOutlined />}>自动布局</Button>
        </Dropdown>
        <Tooltip title="适应画布">
          <Button icon={<FullscreenOutlined />} onClick={onFitView} />
        </Tooltip>
      </Space>

      {selectedCount > 0 && (
        <>
          <div style={{ borderLeft: '1px solid #f0f0f0', height: 24, margin: '0 4px' }} />
          <Badge count={selectedCount} style={{ backgroundColor: '#1890ff' }}>
            <Button icon={<DeleteOutlined />} danger onClick={onBatchDelete}>
              批量删除
            </Button>
          </Badge>
        </>
      )}

      <div style={{ flex: 1 }} />

      <Input.Search
        placeholder="搜索设备"
        allowClear
        style={{ width: 200 }}
        onSearch={onSearch}
        prefix={<SearchOutlined />}
      />
    </div>
  );
};

export default Toolbar;
