import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import AppLayout from './components/AppLayout';
import Dashboard from './pages/Dashboard';
import TopologyEditor from './pages/TopologyEditor';
import ApiConfig from './pages/ApiConfig';
import SnmpConfig from './pages/SnmpConfig';
import SftpConfig from './pages/SftpConfig';
import KafkaConfig from './pages/KafkaConfig';
import DataViewer from './pages/DataViewer';
import LogViewer from './pages/LogViewer';
import Settings from './pages/Settings';

const App = () => (
  <BrowserRouter>
    <Routes>
      <Route element={<AppLayout />}>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/topology" element={<TopologyEditor />} />
        <Route path="/api-config" element={<ApiConfig />} />
        <Route path="/snmp-config" element={<SnmpConfig />} />
        <Route path="/sftp-config" element={<SftpConfig />} />
        <Route path="/kafka-config" element={<KafkaConfig />} />
        <Route path="/data" element={<DataViewer />} />
        <Route path="/logs" element={<LogViewer />} />
        <Route path="/settings" element={<Settings />} />
      </Route>
    </Routes>
  </BrowserRouter>
);

export default App;
