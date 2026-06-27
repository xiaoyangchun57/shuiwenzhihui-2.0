import { useState, useEffect } from 'react';
import { Layout, Menu, Space, Button, Dropdown, Typography } from 'antd';
import {
  DashboardOutlined,
  EnvironmentOutlined,
  AlertOutlined,
  FileTextOutlined,
  ToolOutlined,
  TeamOutlined,
  SunOutlined,
  MoonOutlined,
  UserOutlined,
  LogoutOutlined,
  ClockCircleOutlined,
} from '@ant-design/icons';
import { useNavigate, useLocation, Outlet } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import { useTheme } from '../hooks/useTheme';

const { Header, Content } = Layout;
const { Text } = Typography;

const navItems = [
  { key: '/', icon: <DashboardOutlined />, label: '信息中心' },
  { key: '/sites', icon: <EnvironmentOutlined />, label: '站点管理' },
  { key: '/alerts', icon: <AlertOutlined />, label: '预警中心' },
  { key: '/workorders', icon: <FileTextOutlined />, label: '工单管理' },
  {
    key: 'ops',
    icon: <ToolOutlined />,
    label: '运维管理',
    children: [
      { key: '/maintenance', label: '巡检管理' },
      { key: '/equipment', label: '设备管理' },
      { key: '/analysis', label: '统计分析' },
    ],
  },
];

export default function MainLayout() {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, logout } = useAuth();
  const { isDark, toggleTheme, tokens } = useTheme();
  const [clock, setClock] = useState('');

  // Clock
  useEffect(() => {
    const tick = () => {
      const now = new Date();
      setClock(
        `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')} ${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}:${String(now.getSeconds()).padStart(2, '0')}`
      );
    };
    tick();
    const interval = setInterval(tick, 1000);
    return () => clearInterval(interval);
  }, []);

  const selectedKey = '/' + (location.pathname.split('/')[1] || '');
  const adminItem = user?.role === 'admin'
    ? { key: '/users', icon: <TeamOutlined />, label: '人员管理' }
    : null;

  const allNavItems = adminItem ? [...navItems, adminItem] : navItems;

  const userMenuItems = [
    {
      key: 'logout',
      icon: <LogoutOutlined />,
      label: '退出登录',
      onClick: () => { logout(); navigate('/login'); },
    },
  ];

  return (
    <Layout style={{ height: '100vh', background: tokens.colorBgLayout }}>
      <Header
        style={{
          display: 'flex',
          alignItems: 'center',
          padding: '0 24px',
          background: tokens.navBg,
          borderBottom: `1px solid ${tokens.colorBorder}`,
          boxShadow: tokens.shadowNav,
          position: 'relative',
          zIndex: 100,
          height: 44,
          gap: 16,
          overflow: 'hidden',
        }}
      >
        {/* Logo */}
        <div
          style={{
            fontSize: 17,
            fontWeight: 600,
            color: tokens.colorPrimary,
            letterSpacing: 2,
            whiteSpace: 'nowrap',
            marginRight: 8,
            cursor: 'pointer',
          }}
          onClick={() => navigate('/')}
        >
          水文智慧运维平台
        </div>

        {/* Nav Menu */}
        <Menu
          mode="horizontal"
          selectedKeys={[selectedKey]}
          items={allNavItems}
          onClick={({ key }) => navigate(key)}
          style={{
            flex: 1,
            background: 'transparent',
            borderBottom: 'none',
            lineHeight: '42px',
          }}
        />

        {/* Right side: clock, theme, user */}
        <Space size={12} align="center">
          <Text style={{ fontSize: 13, color: tokens.colorTextSecondary, whiteSpace: 'nowrap', fontFamily: 'monospace', letterSpacing: 1 }}>
            <ClockCircleOutlined style={{ marginRight: 4 }} />
            {clock}
          </Text>

          <Button
            type="text"
            icon={isDark ? <SunOutlined /> : <MoonOutlined />}
            onClick={toggleTheme}
            style={{
              color: tokens.colorPrimary,
              border: `1px solid ${tokens.colorBorder}`,
              borderRadius: '50%',
              width: 32,
              height: 32,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          />

          <Dropdown menu={{ items: userMenuItems }} placement="bottomRight">
            <div style={{ cursor: 'pointer', padding: '2px 8px', borderRadius: 6, background: tokens.colorPrimaryBg, border: `1px solid ${tokens.colorBorder}`, display: 'flex', alignItems: 'center', gap: 6, height: 30, lineHeight: 1 }}>
              <UserOutlined style={{ color: tokens.colorPrimary, fontSize: 13 }} />
              <Text style={{ fontSize: 12, color: tokens.colorPrimary, lineHeight: 1 }}>{user?.username || user?.name || '--'}</Text>
              <Text style={{ fontSize: 10, color: tokens.colorTextTertiary, padding: '0 4px', borderRadius: 3, background: tokens.colorPrimaryBg, lineHeight: '16px' }}>
                {user?.role === 'admin' ? '管理员' : '操作员'}
              </Text>
            </div>
          </Dropdown>
        </Space>
      </Header>

      <Content style={{ position: 'relative', overflow: 'hidden', flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
        <Outlet />
      </Content>
    </Layout>
  );
}
