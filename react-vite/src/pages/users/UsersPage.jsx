import { useState, useEffect, useCallback } from 'react';
import {
  Table, Card, Input, Select, Button, Space, Tag, Badge, Modal,
  Typography, message, Spin, Empty, Form, Switch,
} from 'antd';
import {
  SearchOutlined, ReloadOutlined, PlusOutlined, EditOutlined,
  DeleteOutlined, LockOutlined, ExclamationCircleOutlined,
  UserOutlined, SafetyOutlined,
} from '@ant-design/icons';
import { api } from '../../services/api';
import { useTheme } from '../../hooks/useTheme';

const { Title, Text } = Typography;

const roleMap = {
  admin: { label: '管理员', color: 'red', icon: <SafetyOutlined /> },
  manager: { label: '管理者', color: 'orange' },
  operator: { label: '运维人员', color: 'blue' },
  inspector: { label: '巡检员', color: 'cyan' },
  viewer: { label: '查看者', color: 'default' },
};

export default function UsersPage() {
  const { tokens } = useTheme();
  const [form] = Form.useForm();

  // Data state
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(false);

  // Filter state
  const [search, setSearch] = useState('');
  const [roleFilter, setRoleFilter] = useState(undefined);
  const [statusFilter, setStatusFilter] = useState(undefined);

  // Modal state
  const [modalOpen, setModalOpen] = useState(false);
  const [modalLoading, setModalLoading] = useState(false);
  const [editingUser, setEditingUser] = useState(null);

  const fetchUsers = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (search) params.set('search', search);
      if (roleFilter) params.set('role', roleFilter);
      if (statusFilter) params.set('status', statusFilter);
      const data = await api.get(`/users?${params.toString()}`);
      setUsers(Array.isArray(data) ? data : (data?.users || []));
    } catch {
      message.error('加载用户数据失败');
      setUsers([]);
    } finally {
      setLoading(false);
    }
  }, [search, roleFilter, statusFilter]);

  useEffect(() => { fetchUsers(); }, [fetchUsers]);

  const handleReset = () => {
    setSearch('');
    setRoleFilter(undefined);
    setStatusFilter(undefined);
  };

  const handleCreate = () => {
    setEditingUser(null);
    form.resetFields();
    setModalOpen(true);
  };

  const handleEdit = (record) => {
    setEditingUser(record);
    form.setFieldsValue({
      username: record.username,
      name: record.name,
      role: record.role,
      phone: record.phone,
      sites: record.sites?.join(', ') || record.assigned_sites?.join(', ') || '',
      status: record.status || 'active',
    });
    setModalOpen(true);
  };

  const handleModalOk = async () => {
    try {
      const values = await form.validateFields();
      setModalLoading(true);

      // Process sites field
      const payload = { ...values };
      if (typeof payload.sites === 'string') {
        payload.sites = payload.sites.split(',').map(s => s.trim()).filter(Boolean);
      }

      const url = editingUser ? `/users/${editingUser.id}` : '/users';
      const method = editingUser ? 'put' : 'post';
      const result = await api[method](url, payload);

      if (result && !result.error) {
        message.success(editingUser ? '用户信息已更新' : '用户创建成功');
        setModalOpen(false);
        fetchUsers();
      } else {
        message.error(result?.error || '操作失败');
      }
    } catch {
      // validation error
    } finally {
      setModalLoading(false);
    }
  };

  const handleDelete = (record) => {
    Modal.confirm({
      title: '确认删除',
      icon: <ExclamationCircleOutlined />,
      content: `确认删除用户 ${record.name || record.username}？此操作不可撤销。`,
      okText: '删除',
      okType: 'danger',
      cancelText: '取消',
      onOk: async () => {
        const result = await api.delete(`/users/${record.id}`);
        if (result && !result.error) {
          message.success('用户已删除');
          fetchUsers();
        } else {
          message.error('删除失败');
        }
      },
    });
  };

  const handleToggleStatus = async (record) => {
    const newStatus = record.status === 'active' ? 'inactive' : 'active';
    const result = await api.put(`/users/${record.id}`, { status: newStatus });
    if (result && !result.error) {
      message.success(newStatus === 'active' ? '已启用' : '已停用');
      fetchUsers();
    } else {
      message.error('操作失败');
    }
  };

  const handleResetPassword = (record) => {
    Modal.confirm({
      title: '重置密码',
      icon: <LockOutlined />,
      content: `确认重置 ${record.name || record.username} 的密码？`,
      okText: '确认重置',
      cancelText: '取消',
      onOk: async () => {
        const result = await api.post(`/users/${record.id}/reset-password`, {});
        if (result && !result.error) {
          message.success('密码已重置');
        } else {
          message.error('重置失败');
        }
      },
    });
  };

  const columns = [
    {
      title: '用户名',
      dataIndex: 'username',
      key: 'username',
      width: 100,
      render: (text, record) => (
        <Space>
          <div style={{
            width: 28, height: 28, borderRadius: '50%',
            background: `linear-gradient(135deg, ${tokens.colorPrimary}, ${tokens.colorPrimaryHover})`,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            color: '#fff', fontSize: 12, fontWeight: 600, flexShrink: 0,
          }}>
            {(record.name || text || '?')[0].toUpperCase()}
          </div>
          <Text strong>{text}</Text>
        </Space>
      ),
    },
    {
      title: '姓名',
      dataIndex: 'name',
      key: 'name',
      width: 70,
      render: (text) => text || '-',
    },
    {
      title: '角色',
      dataIndex: 'role',
      key: 'role',
      width: 90,
      render: (val) => {
        const cfg = roleMap[val] || { label: val || '-', color: 'default' };
        return <Tag color={cfg.color} icon={cfg.icon}>{cfg.label}</Tag>;
      },
    },
    {
      title: '手机号',
      dataIndex: 'phone',
      key: 'phone',
      width: 110,
      render: (text) => text || '-',
    },
    {
      title: '负责站点',
      dataIndex: 'sites',
      key: 'sites',
      width: 180,
      ellipsis: true,
      render: (val, record) => {
        const sites = val || record.assigned_sites || [];
        if (Array.isArray(sites) && sites.length > 0) {
          return (
            <Space size={2} wrap>
              {sites.slice(0, 2).map((s, i) => <Tag key={i} style={{ fontSize: 11 }}>{s}</Tag>)}
              {sites.length > 2 && <Tag style={{ fontSize: 11 }}>+{sites.length - 2}</Tag>}
            </Space>
          );
        }
        return <Text style={{ color: tokens.colorTextTertiary }}>-</Text>;
      },
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 70,
      render: (val) => {
        const isActive = val === 'active';
        return <Badge status={isActive ? 'success' : 'default'} text={isActive ? '启用' : '停用'} />;
      },
    },
    {
      title: '操作',
      key: 'actions',
      width: 140,
      render: (_, record) => (
        <Space size={4}>
          <Button type="link" size="small" icon={<EditOutlined />}
            onClick={() => handleEdit(record)}>
            编辑
          </Button>
          <Button type="link" size="small"
            onClick={() => handleToggleStatus(record)}>
            {record.status === 'active' ? '停用' : '启用'}
          </Button>
          <Button type="link" size="small" icon={<LockOutlined />}
            onClick={() => handleResetPassword(record)}>
            重置
          </Button>
          <Button type="link" size="small" danger icon={<DeleteOutlined />}
            onClick={() => handleDelete(record)}>
            删除
          </Button>
        </Space>
      ),
    },
  ];

  const roleOptions = Object.entries(roleMap).map(([value, cfg]) => ({ value, label: cfg.label }));

  return (
    <div style={{ padding: 24 }}>
      {/* Header */}
      <div style={{ marginBottom: 20, display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12 }}>
        <Title level={4} style={{ margin: 0, color: tokens.colorText }}>用户管理</Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}
          style={{ background: `linear-gradient(135deg, ${tokens.colorPrimary}, ${tokens.colorPrimaryHover})`, border: 'none' }}>
          添加用户
        </Button>
      </div>

      {/* Filters */}
      <Card style={{ marginBottom: 16, borderRadius: 10 }} bodyStyle={{ padding: '16px 20px' }}>
        <Space wrap size={12}>
          <Input
            placeholder="搜索用户名、姓名、手机号..."
            prefix={<SearchOutlined style={{ color: tokens.colorTextTertiary }} />}
            allowClear
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onPressEnter={() => fetchUsers()}
            style={{ width: 280, borderRadius: 8 }}
          />
          <Select
            placeholder="角色"
            allowClear
            value={roleFilter}
            onChange={(val) => setRoleFilter(val)}
            style={{ width: 130 }}
            options={roleOptions}
          />
          <Select
            placeholder="状态"
            allowClear
            value={statusFilter}
            onChange={(val) => setStatusFilter(val)}
            style={{ width: 120 }}
            options={[
              { value: 'active', label: '启用' },
              { value: 'inactive', label: '停用' },
            ]}
          />
          <Button icon={<SearchOutlined />} onClick={() => fetchUsers()}>查询</Button>
          <Button icon={<ReloadOutlined />} onClick={handleReset}>重置</Button>
        </Space>
      </Card>

      {/* Table */}
      <Card style={{ borderRadius: 10 }} bodyStyle={{ padding: 0 }}>
        <div style={{ overflow: 'auto', maxHeight: 'calc(100vh - 280px)' }} className="hide-scrollbar">
          <style>{`.hide-scrollbar::-webkit-scrollbar{display:none}.hide-scrollbar{-ms-overflow-style:none;scrollbar-width:none}`}</style>
          <Table
            columns={columns}
            dataSource={users}
            rowKey={(r) => r.id || r.username}
            loading={loading}
            pagination={false}
            scroll={{ x: 760 }}
            locale={{ emptyText: <Empty description="暂无用户数据" /> }}
            size="middle"
          />
        </div>
      </Card>

      {/* Create/Edit Modal */}
      <Modal
        title={editingUser ? '编辑用户' : '添加用户'}
        open={modalOpen}
        onOk={handleModalOk}
        onCancel={() => setModalOpen(false)}
        confirmLoading={modalLoading}
        okText={editingUser ? '保存' : '创建'}
        cancelText="取消"
        width={520}
        destroyOnClose
      >
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item name="username" label="用户名"
            rules={[{ required: true, message: '请输入用户名' }, { min: 3, message: '用户名至少3个字符' }]}>
            <Input prefix={<UserOutlined style={{ color: tokens.colorTextTertiary }} />} placeholder="请输入用户名" disabled={!!editingUser} />
          </Form.Item>
          {!editingUser && (
            <Form.Item name="password" label="密码"
              rules={[{ required: true, message: '请输入密码' }, { min: 6, message: '密码至少6个字符' }]}>
              <Input.Password prefix={<LockOutlined style={{ color: tokens.colorTextTertiary }} />} placeholder="请输入密码" />
            </Form.Item>
          )}
          <Form.Item name="name" label="姓名" rules={[{ required: true, message: '请输入姓名' }]}>
            <Input placeholder="请输入姓名" />
          </Form.Item>
          <Form.Item name="role" label="角色" rules={[{ required: true, message: '请选择角色' }]}>
            <Select placeholder="请选择角色" options={roleOptions} />
          </Form.Item>
          <Form.Item name="phone" label="手机号">
            <Input placeholder="请输入手机号" />
          </Form.Item>
          <Form.Item name="sites" label="负责站点">
            <Input placeholder="多个站点用逗号分隔" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
