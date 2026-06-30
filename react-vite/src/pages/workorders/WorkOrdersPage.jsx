import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { useSearchParams, useLocation } from 'react-router-dom';
import {
  Table, Card, Input, Select, Button, Space, Tag, Badge, Modal,
  Typography, message, Empty, Form, DatePicker, Divider,
  Row, Col, Statistic, Descriptions, Timeline, Drawer,
} from 'antd';
import {
  PlusOutlined, SearchOutlined, ReloadOutlined, EyeOutlined,
  EditOutlined, DeleteOutlined, ExclamationCircleOutlined,
  SendOutlined, FileTextOutlined, ClockCircleOutlined, ToolOutlined, CheckCircleOutlined,
  InboxOutlined, SwapOutlined, CheckOutlined, CloseOutlined,
} from '@ant-design/icons';
import { api } from '../../services/api';
import { useTheme } from '../../hooks/useTheme';
import {
  orderStatusMap, orderLevelMap, orderSourceMap, orderStatusBadge,
} from '../../services/constants';

const { Title, Text } = Typography;
const { RangePicker } = DatePicker;

const levelColorMap = {
  normal: 'default',
  medium: 'default',
  urgent: 'orange',
  critical: 'red',
};

export default function WorkOrdersPage() {
  const { tokens } = useTheme();
  const [form] = Form.useForm();
  const [searchParams, setSearchParams] = useSearchParams();
  const location = useLocation();

  // Data state
  const [allOrders, setAllOrders] = useState([]);
  const [loading, setLoading] = useState(false);

  // Filter state - initialize from URL params
  const [search, setSearch] = useState(searchParams.get('search') || '');
  const [levelFilter, setLevelFilter] = useState(undefined);
  const [statusFilter, setStatusFilter] = useState(searchParams.get('status') || undefined);

  // Modal state
  const [modalOpen, setModalOpen] = useState(false);
  const [modalLoading, setModalLoading] = useState(false);
  const [editingOrder, setEditingOrder] = useState(null);

  // View drawer state
  const [viewOpen, setViewOpen] = useState(false);
  const [viewingOrder, setViewingOrder] = useState(null);
  const [relatedData, setRelatedData] = useState({ parts: [], recycles: [] });

  // Spare part request from work order
  const [partReqOpen, setPartReqOpen] = useState(false);
  const [partReqLoading, setPartReqLoading] = useState(false);
  const [partReqForm] = Form.useForm();

  // Device recycle from work order
  const [recycleOpen, setRecycleOpen] = useState(false);
  const [recycleLoading, setRecycleLoading] = useState(false);
  const [recycleForm] = Form.useForm();
  const [devices, setDevices] = useState([]);

  // Counts state
  const [counts, setCounts] = useState({ total: 0, pending: 0, dispatched: 0, in_progress: 0, closed: 0 });
  const [sites, setSites] = useState([]);

  // Fetch sites for dropdown
  useEffect(() => {
    api.get('/sites').then(data => {
      const list = Array.isArray(data) ? data : (data?.sites || []);
      setSites(list);
    }).catch(() => {});
    // Fetch devices for recycle dropdown
    api.get('/devices').then(data => {
      const list = Array.isArray(data) ? data : (data?.devices || []);
      setDevices(list);
    }).catch(() => {});
  }, []);

  // ---- Spare part request from work order ----
  const handlePartReqOpen = useCallback(() => {
    partReqForm.resetFields();
    if (viewingOrder) {
      partReqForm.setFieldsValue({
        site_id: viewingOrder.site_id,
        work_order_no: viewingOrder.order_no,
      });
    }
    setPartReqOpen(true);
  }, [partReqForm, viewingOrder]);

  const handlePartReqOk = useCallback(async () => {
    try {
      const values = await partReqForm.validateFields();
      setPartReqLoading(true);
      const result = await api.post('/parts/requests', {
        ...values,
        work_order_no: viewingOrder?.order_no || '',
      });
      if (result && !result.error) {
        message.success(`备件申请已提交 (${result.request_no})`);
        setPartReqOpen(false);
        // Refresh related data
        if (viewingOrder?.order_no) {
          const data = await api.get(`/workorders/${viewingOrder.order_no}/related`);
          if (data) setRelatedData({ parts: data.parts || [], recycles: relatedData.recycles });
        }
      } else {
        message.error(result?.error || '提交失败');
      }
    } catch { /* validation error */ }
    setPartReqLoading(false);
  }, [partReqForm, viewingOrder, relatedData.recycles]);

  // ---- Device recycle from work order ----
  const handleRecycleOpen = useCallback(() => {
    recycleForm.resetFields();
    setRecycleOpen(true);
  }, [recycleForm]);

  const handleRecycleOk = useCallback(async () => {
    try {
      const values = await recycleForm.validateFields();
      setRecycleLoading(true);
      const result = await api.post('/device-recycle', {
        ...values,
        work_order_no: viewingOrder?.order_no || '',
      });
      if (result && !result.error) {
        message.success('设备回收已登记');
        setRecycleOpen(false);
        // Refresh related data
        if (viewingOrder?.order_no) {
          const data = await api.get(`/workorders/${viewingOrder.order_no}/related`);
          if (data) setRelatedData({ parts: relatedData.parts, recycles: data.recycles || [] });
        }
      } else {
        message.error(result?.error || '登记失败');
      }
    } catch { /* validation error */ }
    setRecycleLoading(false);
  }, [recycleForm, viewingOrder, relatedData.parts]);

  const fetchOrders = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.get('/workorders');
      const list = Array.isArray(data) ? data : [];
      setAllOrders(list);
      const computedCounts = { total: list.length, pending: 0, dispatched: 0, in_progress: 0, closed: 0 };
      list.forEach(o => { if (computedCounts[o.status] !== undefined) computedCounts[o.status]++; });
      setCounts(computedCounts);
    } catch (err) {
      message.error('加载工单失败');
      setAllOrders([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchOrders();
  }, [fetchOrders]);

  // Sync filters from URL params when navigating with ?search= or ?status=
  useEffect(() => {
    const urlSearch = searchParams.get('search') || '';
    const urlStatus = searchParams.get('status') || undefined;
    setSearch(urlSearch);
    setStatusFilter(urlStatus);
    // Refetch data when navigating from other pages with URL params
    fetchOrders();
  }, [location.search, fetchOrders]);

  // Client-side filtering
  const filteredOrders = useMemo(() => {
    let list = allOrders;
    if (search) {
      const q = search.toLowerCase();
      list = list.filter((o) =>
        (o.order_no && o.order_no.toLowerCase().includes(q)) ||
        (o.title && o.title.toLowerCase().includes(q)) ||
        (o.site_name && o.site_name.toLowerCase().includes(q))
      );
    }
    if (levelFilter) {
      list = list.filter((o) => o.level === levelFilter);
    }
    if (statusFilter) {
      list = list.filter((o) => o.status === statusFilter);
    }
    return list;
  }, [allOrders, search, levelFilter, statusFilter]);

  const handleSearch = (value) => {
    setSearch(value);
  };

  const handleLevelChange = (value) => {
    setLevelFilter(value);
  };

  const handleStatusChange = (value) => {
    setStatusFilter(value);
  };

  const handleReset = () => {
    setSearch('');
    setLevelFilter(undefined);
    setStatusFilter(undefined);
  };

  const handleCreate = () => {
    setEditingOrder(null);
    form.resetFields();
    setModalOpen(true);
  };

  const handleView = async (record) => {
    setViewingOrder(record);
    setViewOpen(true);
    setRelatedData({ parts: [], recycles: [] });
    // Fetch related spare parts and device recycles
    const orderNo = record.order_no;
    if (orderNo) {
      try {
        const data = await api.get(`/workorders/${orderNo}/related`);
        if (data) {
          setRelatedData({
            parts: data.parts || [],
            recycles: data.recycles || [],
          });
        }
      } catch { /* ignore */ }
    }
  };

  const handleEdit = (record) => {
    setEditingOrder(record);
    form.setFieldsValue({
      title: record.title,
      level: record.level,
      source: record.source,
      site_id: record.site_name || record.site_id,
      assignee: record.assignee,
      description: record.description,
    });
    setModalOpen(true);
  };

  const handleModalOk = async () => {
    try {
      const values = await form.validateFields();
      setModalLoading(true);
      let result;
      if (editingOrder) {
        result = await api.put(`/workorders/${editingOrder.order_no}/status`, {
          ...values,
          status: values.status || editingOrder.status,
        });
      } else {
        result = await api.post('/workorders', values);
      }
      if (result && !result.error) {
        message.success(editingOrder ? '工单已更新' : '工单已创建');
        setModalOpen(false);
        setEditingOrder(null);
        fetchOrders();
      } else {
        message.error(result?.error || (editingOrder ? '更新失败' : '创建失败'));
      }
    } catch {
      // validation error, do nothing
    } finally {
      setModalLoading(false);
    }
  };

  const handleDelete = (record) => {
    Modal.confirm({
      title: '确认删除',
      icon: <ExclamationCircleOutlined />,
      content: `确认删除工单 ${record.order_no || record.id}？此操作不可撤销。`,
      okText: '删除',
      okType: 'danger',
      cancelText: '取消',
      onOk: async () => {
        const result = await api.delete(`/workorders/${record.order_no}`);
        if (result && !result.error) {
          message.success('工单已删除');
          fetchOrders();
        } else {
          message.error('删除失败');
        }
      },
    });
  };

  // Work order verification handlers
  const handleSubmitReview = useCallback(async (record) => {
    Modal.confirm({
      title: '提交核验',
      icon: <ExclamationCircleOutlined />,
      content: `确认将工单 ${record.order_no} 提交核验？`,
      okText: '确认提交',
      cancelText: '取消',
      onOk: async () => {
        const result = await api.post(`/workorders/${record.order_no}/submit-review`, {});
        if (result && !result.error) {
          message.success('工单已提交核验');
          fetchOrders();
        } else {
          message.error(result?.error || '提交失败');
        }
      },
    });
  }, [fetchOrders]);

  const handleApprove = useCallback(async (record) => {
    Modal.confirm({
      title: '核验通过',
      icon: <CheckCircleOutlined />,
      content: `确认工单 ${record.order_no} 核验通过？`,
      okText: '确认通过',
      cancelText: '取消',
      onOk: async () => {
        const result = await api.post(`/workorders/${record.order_no}/approve`, {});
        if (result && !result.error) {
          message.success('工单核验通过');
          fetchOrders();
        } else {
          message.error(result?.error || '操作失败');
        }
      },
    });
  }, [fetchOrders]);

  const handleReject = useCallback(async (record) => {
    Modal.confirm({
      title: '退回工单',
      icon: <ExclamationCircleOutlined />,
      content: `确认退回工单 ${record.order_no}？工单将返回重新处理。`,
      okText: '确认退回',
      okType: 'danger',
      cancelText: '取消',
      onOk: async () => {
        const result = await api.post(`/workorders/${record.order_no}/reject`, {});
        if (result && !result.error) {
          message.success('工单已退回');
          fetchOrders();
        } else {
          message.error(result?.error || '操作失败');
        }
      },
    });
  }, [fetchOrders]);

  const columns = [
    {
      title: '工单号',
      dataIndex: 'order_no',
      key: 'order_no',
      width: 120,
      fixed: 'left',
      render: (text, record) => (
        <Text strong style={{ color: tokens.colorPrimary, fontSize: 13 }}>
          {text || `#${record.id}`}
        </Text>
      ),
    },
    {
      title: '站点',
      dataIndex: 'site_name',
      key: 'site_name',
      width: 100,
      ellipsis: true,
      render: (text) => text || '-',
    },
    {
      title: '来源',
      dataIndex: 'source',
      key: 'source',
      width: 70,
      render: (val) => orderSourceMap[val] || val || '-',
    },
    {
      title: '级别',
      dataIndex: 'level',
      key: 'level',
      width: 70,
      render: (val) => {
        const label = orderLevelMap[val] || val || '-';
        const color = levelColorMap[val] || 'default';
        return val ? <Tag color={color}>{label}</Tag> : '-';
      },
    },
    {
      title: '标题',
      dataIndex: 'title',
      key: 'title',
      width: 160,
      ellipsis: true,
      render: (text) => text || '-',
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 80,
      render: (val) => {
        const label = orderStatusMap[val] || val || '-';
        const badge = orderStatusBadge[val] || 'default';
        return val ? <Badge status={badge} text={label} /> : '-';
      },
    },
    {
      title: '负责人',
      dataIndex: 'assignee',
      key: 'assignee',
      width: 70,
      ellipsis: true,
      render: (text) => text || '-',
    },
    {
      title: 'SLA',
      dataIndex: 'sla_deadline',
      key: 'sla_deadline',
      width: 100,
      render: (val) => {
        if (!val) return '-';
        const isOverdue = new Date(val) < new Date();
        return (
          <Text style={{ color: isOverdue ? tokens.colorError : tokens.colorTextSecondary, fontSize: 13 }}>
            {isOverdue ? '已超时' : val}
          </Text>
        );
      },
    },
    {
      title: '操作',
      key: 'actions',
      width: 280,
      fixed: 'right',
      render: (_, record) => (
        <Space size={0} split={<Divider type="vertical" style={{ margin: '0 2px', borderColor: tokens.colorBorderSecondary }} />}>
          <Button type="link" size="small" icon={<EyeOutlined />}
            onClick={() => handleView(record)}>
            查看
          </Button>
          <Button type="link" size="small" icon={<EditOutlined />}
            onClick={() => handleEdit(record)}>
            编辑
          </Button>
          <Button type="link" size="small" icon={<DeleteOutlined />}
            danger
            onClick={() => handleDelete(record)}>
            删除
          </Button>
          {record.status === 'in_progress' && (
            <Button type="link" size="small" icon={<SendOutlined />}
              style={{ color: '#722ed1' }}
              onClick={() => handleSubmitReview(record)}>
              提交核验
            </Button>
          )}
          {record.status === 'reviewing' && (
            <>
              <Button type="link" size="small" icon={<CheckOutlined />}
                style={{ color: tokens.colorSuccess }}
                onClick={() => handleApprove(record)}>
                通过
              </Button>
              <Button type="link" size="small" icon={<CloseOutlined />}
                danger
                onClick={() => handleReject(record)}>
                退回
              </Button>
            </>
          )}
        </Space>
      ),
    },
  ];

  const statusOptions = Object.entries(orderStatusMap).map(([value, label]) => ({ value, label }));
  const levelOptions = [
    { value: 'normal', label: '一般' },
    { value: 'urgent', label: '紧急' },
    { value: 'critical', label: '重大' },
  ];

  return (
    <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', padding: 24 }}>
      {/* Page Header */}
      <div style={{ marginBottom: 20, display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12, flexShrink: 0 }}>
        <Title level={4} style={{ margin: 0, color: tokens.colorText }}>工单管理</Title>
        <Space>
          <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}
            style={{ background: `linear-gradient(135deg, ${tokens.colorPrimary}, ${tokens.colorPrimaryHover})`, border: 'none' }}>
            新建工单
          </Button>
        </Space>
      </div>

      {/* Stats Cards */}
      <Row gutter={[12, 12]} style={{ marginBottom: 16, flexShrink: 0 }}>
        {[
          { title: '工单总数', value: counts.total, color: tokens.colorPrimary, icon: <FileTextOutlined /> },
          { title: '待受理', value: counts.pending, color: tokens.colorWarning, icon: <ClockCircleOutlined /> },
          { title: '已派发', value: counts.dispatched, color: tokens.colorInfo, icon: <SendOutlined /> },
          { title: '处置中', value: counts.in_progress, color: tokens.colorPrimary, icon: <ToolOutlined /> },
          { title: '已完成', value: counts.closed, color: tokens.colorSuccess, icon: <CheckCircleOutlined /> },
        ].map(item => (
          <Col flex="1" key={item.title}>
            <Card size="small" style={{ background: tokens.colorBgContainer, border: `1px solid ${tokens.colorBorder}` }} bodyStyle={{ padding: '12px 16px' }}>
              <Statistic title={<Text style={{ fontSize: 12, color: tokens.colorTextSecondary }}>{item.title}</Text>} value={item.value} prefix={React.cloneElement(item.icon, { style: { fontSize: 14 } })} valueStyle={{ color: item.color, fontSize: 22, fontWeight: 600 }} />
            </Card>
          </Col>
        ))}
      </Row>

      {/* Filters */}
      <Card style={{ marginBottom: 16, borderRadius: 10, flexShrink: 0 }} bodyStyle={{ padding: '16px 20px' }}>
        <Space wrap size={12} style={{ width: '100%' }}>
          <Input
            placeholder="搜索工单号、标题、站点..."
            prefix={<SearchOutlined style={{ color: tokens.colorTextTertiary }} />}
            allowClear
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onPressEnter={(e) => handleSearch(e.target.value)}
            style={{ width: 280, borderRadius: 8 }}
          />
          <Select
            placeholder="级别"
            allowClear
            value={levelFilter}
            onChange={handleLevelChange}
            style={{ width: 120 }}
            options={levelOptions}
          />
          <Select
            placeholder="状态"
            allowClear
            value={statusFilter}
            onChange={handleStatusChange}
            style={{ width: 130 }}
            options={statusOptions}
          />
          <Button icon={<SearchOutlined />} onClick={() => handleSearch(search)}>查询</Button>
          <Button icon={<ReloadOutlined />} onClick={handleReset}>重置</Button>
        </Space>
      </Card>

      {/* Table */}
      <Card style={{ borderRadius: 10, flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }} bodyStyle={{ padding: 0, flex: 1, display: 'flex', flexDirection: 'column' }}>
        <style>{`.hide-scrollbar::-webkit-scrollbar{display:none}.hide-scrollbar{-ms-overflow-style:none;scrollbar-width:none}`}</style>
        <div className="hide-scrollbar" style={{ flex: 1, overflow: 'auto' }}>
          <Table
            columns={columns}
            dataSource={filteredOrders}
            rowKey={(r) => r.order_no || r.id}
            loading={loading}
            pagination={false}
            locale={{ emptyText: <Empty description="暂无工单数据" /> }}
            size="middle"
          />
        </div>
      </Card>

      {/* Create/Edit Modal */}
      <Modal
        title={editingOrder ? '编辑工单' : '新建工单'}
        open={modalOpen}
        onOk={handleModalOk}
        onCancel={() => { setModalOpen(false); setEditingOrder(null); }}
        confirmLoading={modalLoading}
        okText={editingOrder ? '保存' : '创建'}
        cancelText="取消"
        width={560}
        destroyOnClose
      >
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item name="title" label="标题" rules={[{ required: true, message: '请输入工单标题' }]}>
            <Input placeholder="请输入工单标题" />
          </Form.Item>
          <Row gutter={12}>
            <Col span={12}>
              <Form.Item name="level" label="级别" rules={[{ required: true, message: '请选择级别' }]}>
                <Select placeholder="请选择级别" options={levelOptions} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="source" label="来源" rules={[{ required: true, message: '请选择来源' }]}>
                <Select
                  placeholder="请选择来源"
                  options={Object.entries(orderSourceMap).map(([value, label]) => ({ value, label }))}
                />
              </Form.Item>
            </Col>
          </Row>
          {editingOrder && (
            <Form.Item name="status" label="状态">
              <Select placeholder="请选择状态" options={statusOptions} />
            </Form.Item>
          )}
          <Form.Item name="site_id" label="站点">
            <Select placeholder="请选择站点" allowClear showSearch
              filterOption={(input, option) => (option.label || '').toLowerCase().includes(input.toLowerCase())}
              options={sites.map(s => ({ value: s.id, label: `${s.name || s.code} (${s.code || s.id})` }))} />
          </Form.Item>
          <Form.Item name="assignee" label="负责人">
            <Input placeholder="负责人姓名" />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={3} placeholder="工单详细描述" />
          </Form.Item>
        </Form>
      </Modal>
      {/* View Drawer */}
      <Drawer
        title={
          <Space>
            <FileTextOutlined />
            <span>工单详情</span>
            {viewingOrder && <Tag color={levelColorMap[viewingOrder.level] || 'default'}>{orderLevelMap[viewingOrder.level] || viewingOrder.level}</Tag>}
          </Space>
        }
        open={viewOpen}
        onClose={() => { setViewOpen(false); setViewingOrder(null); }}
        width={520}
      >
        {viewingOrder && (
          <div>
            <Descriptions column={1} size="small" bordered>
              <Descriptions.Item label="工单号">
                <Text strong style={{ color: tokens.colorPrimary }}>{viewingOrder.order_no || `#${viewingOrder.id}`}</Text>
              </Descriptions.Item>
              <Descriptions.Item label="标题">{viewingOrder.title || '-'}</Descriptions.Item>
              <Descriptions.Item label="站点">{viewingOrder.site_name || '-'}</Descriptions.Item>
              <Descriptions.Item label="来源">{orderSourceMap[viewingOrder.source] || viewingOrder.source || '-'}</Descriptions.Item>
              <Descriptions.Item label="级别">
                {viewingOrder.level ? <Tag color={levelColorMap[viewingOrder.level] || 'default'}>{orderLevelMap[viewingOrder.level] || viewingOrder.level}</Tag> : '-'}
              </Descriptions.Item>
              <Descriptions.Item label="状态">
                {viewingOrder.status ? <Badge status={orderStatusBadge[viewingOrder.status] || 'default'} text={orderStatusMap[viewingOrder.status] || viewingOrder.status} /> : '-'}
              </Descriptions.Item>
              <Descriptions.Item label="负责人">{viewingOrder.assignee || '-'}</Descriptions.Item>
              <Descriptions.Item label="SLA截止">
                {viewingOrder.sla_deadline ? (
                  <Text style={{ color: new Date(viewingOrder.sla_deadline) < new Date() ? tokens.colorError : tokens.colorText }}>
                    {new Date(viewingOrder.sla_deadline) < new Date() ? '已超时 · ' : ''}{viewingOrder.sla_deadline}
                  </Text>
                ) : '-'}
              </Descriptions.Item>
              <Descriptions.Item label="创建时间">{viewingOrder.created_at || '-'}</Descriptions.Item>
              <Descriptions.Item label="描述">{viewingOrder.description || '暂无描述'}</Descriptions.Item>
              {/* 备件使用 - 融合在现有区块中 */}
              {relatedData.parts.length > 0 && (
                <Descriptions.Item label="备件使用">
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                    {relatedData.parts.map((p, i) => (
                      <div key={p.id || i} style={{ fontSize: 12 }}>
                        <Tag color="blue" style={{ fontSize: 11, marginRight: 4 }}>{p.request_no || `#${p.id}`}</Tag>
                        <Text>{p.part_name}</Text>
                        <Text type="secondary" style={{ marginLeft: 8 }}>×{p.quantity}</Text>
                        <Tag color={p.status === 'approved' ? 'green' : p.status === 'rejected' ? 'red' : 'orange'} style={{ fontSize: 11, marginLeft: 4 }}>
                          {p.status === 'approved' ? '已批准' : p.status === 'rejected' ? '已驳回' : '待审批'}
                        </Tag>
                      </div>
                    ))}
                  </div>
                </Descriptions.Item>
              )}
              {/* 设备更换 - 融合在现有区块中 */}
              {relatedData.recycles.length > 0 && (
                <Descriptions.Item label="设备更换">
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                    {relatedData.recycles.map((r, i) => (
                      <div key={r.id || i} style={{ fontSize: 12 }}>
                        <Tag color="purple" style={{ fontSize: 11, marginRight: 4 }}>{r.device_code || `#${r.id}`}</Tag>
                        <Text>{r.device_name}</Text>
                        <Tag color={r.destination === 'scrap' ? 'red' : 'blue'} style={{ fontSize: 11, marginLeft: 4 }}>
                          {r.destination === 'scrap' ? '报废' : r.destination === 'repair' ? '维修' : r.destination === 'replace' ? '更换' : r.destination || '回收'}
                        </Tag>
                      </div>
                    ))}
                  </div>
                </Descriptions.Item>
              )}
            </Descriptions>

            <div style={{ marginTop: 24 }}>
              <Text strong style={{ fontSize: 14, display: 'flex', alignItems: 'center', gap: 6, marginBottom: 16 }}>
                <ClockCircleOutlined /> 处理流程
              </Text>
              <Timeline
                items={[
                  { color: 'green', children: <div><Text strong>工单创建</Text><div style={{ fontSize: 12, color: tokens.colorTextTertiary }}>{viewingOrder.created_at || '—'}</div></div> },
                  { color: viewingOrder.status !== 'pending' ? 'green' : 'gray', children: <div><Text strong>受理</Text><div style={{ fontSize: 12, color: tokens.colorTextTertiary }}>{viewingOrder.accepted_at || '待受理'}</div></div> },
                  { color: ['dispatched', 'in_progress', 'reviewing', 'acceptance', 'closed'].includes(viewingOrder.status) ? 'green' : 'gray', children: <div><Text strong>派发处置</Text><div style={{ fontSize: 12, color: tokens.colorTextTertiary }}>{viewingOrder.dispatched_at || '待派发'}</div></div> },
                  // 设备更换节点 - 融合在Timeline中
                  ...relatedData.recycles.map((r, i) => ({
                    color: 'blue',
                    children: (
                      <div key={`recycle-${r.id || i}`}>
                        <Text strong>设备更换</Text>
                        <div style={{ fontSize: 12, color: tokens.colorTextSecondary }}>
                          {r.device_name} ({r.device_code}) → {r.destination === 'scrap' ? '报废' : r.destination === 'repair' ? '维修' : r.destination === 'replace' ? '更换' : '回收'}
                        </div>
                        <div style={{ fontSize: 11, color: tokens.colorTextTertiary }}>{r.recycle_date || r.created_at || ''}</div>
                      </div>
                    ),
                  })),
                  { color: ['reviewing', 'acceptance', 'closed'].includes(viewingOrder.status) ? 'green' : 'gray', children: <div><Text strong>审核验收</Text><div style={{ fontSize: 12, color: tokens.colorTextTertiary }}>{viewingOrder.reviewed_at || '待审核'}</div></div> },
                  { color: viewingOrder.status === 'closed' ? 'green' : 'gray', children: <div><Text strong>办结</Text><div style={{ fontSize: 12, color: tokens.colorTextTertiary }}>{viewingOrder.closed_at || '未完成'}</div></div> },
                ]}
              />
            </div>

            {/* 操作按钮：从工单发起备件申请/设备回收 */}
            {['in_progress', 'dispatched', 'accepted'].includes(viewingOrder.status) && (
              <div style={{ marginTop: 20, paddingTop: 16, borderTop: `1px solid ${tokens.colorBorder}` }}>
                <Text strong style={{ fontSize: 13, display: 'block', marginBottom: 10 }}>关联操作</Text>
                <Space size={8} wrap>
                  <Button size="small" icon={<InboxOutlined />} onClick={handlePartReqOpen}>
                    申请备件
                  </Button>
                  <Button size="small" icon={<SwapOutlined />} onClick={handleRecycleOpen}>
                    设备回收
                  </Button>
                </Space>
              </div>
            )}
          </div>
        )}
      </Drawer>

      {/* ===== Spare Part Request Modal (from work order) ===== */}
      <Modal
        title="申请备件"
        open={partReqOpen}
        onOk={handlePartReqOk}
        onCancel={() => { setPartReqOpen(false); partReqForm.resetFields(); }}
        confirmLoading={partReqLoading}
        okText="提交申请"
        cancelText="取消"
        destroyOnClose
      >
        <div style={{ marginBottom: 12, padding: '8px 12px', borderRadius: 8, background: 'rgba(24,144,255,0.06)', border: '1px solid rgba(24,144,255,0.15)' }}>
          <Text style={{ fontSize: 12, color: tokens.colorTextSecondary }}>
            关联工单：<Text strong style={{ color: tokens.colorPrimary }}>{viewingOrder?.order_no}</Text>
          </Text>
        </div>
        <Form form={partReqForm} layout="vertical" style={{ marginTop: 8 }}>
          <Form.Item name="part_name" label="备件名称" rules={[{ required: true, message: '请输入备件名称' }]}>
            <Input placeholder="请输入需要申请的备件名称" />
          </Form.Item>
          <Form.Item name="quantity" label="数量" rules={[{ required: true, message: '请输入数量' }]}>
            <Input type="number" min={1} placeholder="申请数量" />
          </Form.Item>
          <Form.Item name="reason" label="用途说明">
            <Input.TextArea rows={2} placeholder="说明备件用途" />
          </Form.Item>
          <Form.Item name="site_id" hidden>
            <Input />
          </Form.Item>
        </Form>
      </Modal>

      {/* ===== Device Recycle Modal (from work order) ===== */}
      <Modal
        title="设备回收登记"
        open={recycleOpen}
        onOk={handleRecycleOk}
        onCancel={() => { setRecycleOpen(false); recycleForm.resetFields(); }}
        confirmLoading={recycleLoading}
        okText="确认登记"
        cancelText="取消"
        destroyOnClose
      >
        <div style={{ marginBottom: 12, padding: '8px 12px', borderRadius: 8, background: 'rgba(24,144,255,0.06)', border: '1px solid rgba(24,144,255,0.15)' }}>
          <Text style={{ fontSize: 12, color: tokens.colorTextSecondary }}>
            关联工单：<Text strong style={{ color: tokens.colorPrimary }}>{viewingOrder?.order_no}</Text>
          </Text>
        </div>
        <Form form={recycleForm} layout="vertical" style={{ marginTop: 8 }}>
          <Form.Item name="device_id" label="回收设备" rules={[{ required: true, message: '请选择设备' }]}>
            <Select placeholder="请选择需要回收的设备" showSearch allowClear
              filterOption={(input, option) => (option.label || '').toLowerCase().includes(input.toLowerCase())}
              options={devices.map(d => ({
                value: d.id,
                label: `${d.device_name || d.device_code} (${d.device_code || d.id})`,
              }))} />
          </Form.Item>
          <Form.Item name="reason" label="回收原因" rules={[{ required: true, message: '请输入原因' }]}>
            <Input placeholder="如: 设备故障更换、到期报废" />
          </Form.Item>
          <Form.Item name="destination" label="回收方式" rules={[{ required: true, message: '请选择回收方式' }]}>
            <Select placeholder="请选择" options={[
              { value: 'repair', label: '维修' },
              { value: 'replace', label: '更换' },
              { value: 'scrap', label: '报废' },
              { value: 'return', label: '退回' },
            ]} />
          </Form.Item>
          <Form.Item name="operator" label="操作人">
            <Input placeholder="操作人姓名" />
          </Form.Item>
          <Form.Item name="remark" label="备注">
            <Input.TextArea rows={2} placeholder="可选备注" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
