import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { ConfigProvider, App as AntApp } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import { AuthProvider, useAuth } from './hooks/useAuth';
import { ThemeProvider, useTheme } from './hooks/useTheme';
import MainLayout from './layouts/MainLayout';
import LoginPage from './pages/login/LoginPage';
import CockpitPage from './pages/cockpit/CockpitPage';
import SitesPage from './pages/sites/SitesPage';
import AlertsPage from './pages/alerts/AlertsPage';
import WorkOrdersPage from './pages/workorders/WorkOrdersPage';
import MaintenancePage from './pages/maintenance/MaintenancePage';
import EquipmentPage from './pages/equipment/EquipmentPage';
import AnalysisPage from './pages/analysis/AnalysisPage';
import UsersPage from './pages/users/UsersPage';

function ProtectedRoute({ children }) {
  const { isAuthenticated } = useAuth();
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  return children;
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="/"
        element={
          <ProtectedRoute>
            <MainLayout />
          </ProtectedRoute>
        }
      >
        <Route index element={<CockpitPage />} />
        <Route path="sites" element={<SitesPage />} />
        <Route path="alerts" element={<AlertsPage />} />
        <Route path="workorders" element={<WorkOrdersPage />} />
        <Route path="maintenance" element={<MaintenancePage />} />
        <Route path="equipment" element={<EquipmentPage />} />
        <Route path="analysis" element={<AnalysisPage />} />
        <Route path="users" element={<UsersPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <ThemeProvider>
          <ThemedApp />
        </ThemeProvider>
      </AuthProvider>
    </BrowserRouter>
  );
}

function ThemedApp() {
  const { themeConfig } = useTheme();
  return (
    <ConfigProvider theme={themeConfig} locale={zhCN}>
      <AntApp>
        <AppRoutes />
      </AntApp>
    </ConfigProvider>
  );
}
