import { useState } from 'react';
import { Form, Input, Button, Typography, message } from 'antd';
import { UserOutlined, LockOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../hooks/useAuth';
import { useTheme } from '../../hooks/useTheme';

const { Title, Text } = Typography;

export default function LoginPage() {
  const navigate = useNavigate();
  const { login, loading } = useAuth();
  const { tokens, isDark } = useTheme();
  const [error, setError] = useState('');

  const onFinish = async (values) => {
    setError('');
    const result = await login(values.username, values.password);
    if (result.success) {
      message.success('登录成功');
      navigate('/');
    } else {
      setError(result.error || '用户名或密码错误');
    }
  };

  return (
    <div
      style={{
        height: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: isDark
          ? 'linear-gradient(135deg, #0a1628 0%, #0e1f38 50%, #0a1628 100%)'
          : 'linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 50%, #f0f9ff 100%)',
      }}
    >
      <div
        style={{
          width: 380,
          padding: '40px 36px',
          borderRadius: 16,
          background: isDark
            ? 'linear-gradient(135deg, rgba(12,28,52,0.9), rgba(8,20,42,0.95))'
            : '#ffffff',
          border: `1px solid ${tokens.colorBorder}`,
          boxShadow: isDark
            ? '0 0 60px rgba(0,201,167,0.08), 0 8px 32px rgba(0,0,0,0.4)'
            : '0 8px 40px rgba(0,0,0,0.08)',
        }}
      >
        {/* Logo / Title */}
        <div style={{ textAlign: 'center', marginBottom: 32 }}>
          <div
            style={{
              width: 56,
              height: 56,
              borderRadius: 14,
              background: `linear-gradient(135deg, ${tokens.colorPrimary}, ${tokens.colorPrimaryHover})`,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              margin: '0 auto 16px',
              boxShadow: `0 4px 16px ${tokens.glowAccent}`,
            }}
          >
            <svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="white" strokeWidth="2">
              <path d="M12 2L2 7l10 5 10-5-10-5z" />
              <path d="M2 17l10 5 10-5" />
              <path d="M2 12l10 5 10-5" />
            </svg>
          </div>
          <Title level={4} style={{ color: tokens.colorText, margin: 0, letterSpacing: 2 }}>
            水文智慧运维平台
          </Title>
          <Text style={{ color: tokens.colorTextTertiary, fontSize: 13 }}>
            水文监测智慧运维管理系统
          </Text>
        </div>

        {/* Login Form */}
        <Form onFinish={onFinish} size="large" autoComplete="off">
          <Form.Item name="username" rules={[{ required: true, message: '请输入用户名' }]}>
            <Input
              prefix={<UserOutlined style={{ color: tokens.colorTextTertiary }} />}
              placeholder="用户名"
              style={{ borderRadius: 8, height: 44 }}
            />
          </Form.Item>

          <Form.Item name="password" rules={[{ required: true, message: '请输入密码' }]}>
            <Input.Password
              prefix={<LockOutlined style={{ color: tokens.colorTextTertiary }} />}
              placeholder="密码"
              style={{ borderRadius: 8, height: 44 }}
              onKeyDown={(e) => { if (e.key === 'Enter') e.target.closest('form')?.requestSubmit(); }}
            />
          </Form.Item>

          {error && (
            <div style={{ color: tokens.colorError, fontSize: 13, textAlign: 'center', marginBottom: 12 }}>
              {error}
            </div>
          )}

          <Form.Item>
            <Button
              type="primary"
              htmlType="submit"
              block
              loading={loading}
              style={{
                height: 44,
                borderRadius: 8,
                fontSize: 15,
                fontWeight: 500,
                letterSpacing: 2,
                background: `linear-gradient(135deg, ${tokens.colorPrimary}, ${tokens.colorPrimaryHover})`,
                border: 'none',
                boxShadow: `0 4px 12px ${tokens.glowAccent}`,
              }}
            >
              登 录
            </Button>
          </Form.Item>
        </Form>

        <div style={{ textAlign: 'center' }}>
          <Text style={{ fontSize: 11, color: tokens.colorTextQuaternary }}>
            请联系管理员获取账号信息
          </Text>
        </div>
      </div>
    </div>
  );
}
