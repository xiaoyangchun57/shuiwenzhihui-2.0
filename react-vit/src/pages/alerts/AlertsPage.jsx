import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Table, Card, Input, Select, Button, Space, Tag, Badge,
  Statistic, Row, Col, Typography, message, Modal,
} from 'antd';
import {
  AlertOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  ExclamationCircleOutlined,
  SearchOutlined,
} from '@ant-design/icons';
import { api } from '../../services/api';
import { alertLevelColor, alertLevelLabel, alertStatusMap } from '../../services/constants';
import { useTheme } from '../../hooks/useTheme';

const { Text } = Typography;

// ---------------------------------------------------------------------------
// Status color / badge mapping
// ---------------------------------------------------------------------------
const statusColorMap = {
  pending: '#faad14',
  acknowledged: '#1890ff',
  resolved: '#52c41a',
};

const statusIconMap = {
  pending: <ExclamationCircleOutlined />,
  acknowledged: <ClockCircleOutlined />,
  resolved: <CheckCircleOutlined />,
};

// ---------------------------------------------------------------------------
// Date-range presets
// ---------------------------------------------------------------------------
const dateRangeOptions = [
  { label: '今日', value: 'today' },
  { label: '本周', value: 'week' },
  { label: '本月', value: 'month' },
];

// ---------------------------------------------------------------------------
// Helper: check if a date string falls within a named range
// ---------------------------------------------------------------------------
function isInDateRange(dateStr, range) {
  if (!dateStr || !range) return true;
  const d = new Date(dateStr);
  if (isNaN(d.getTime())) return true;
  const now = new Date();

  if (range === 'today') {
    return (
      d.getFullYear() === now.getFullYear() &&
      d.getMonth() === now.getMonth() &&
      d.getDate() === now.getDate()
    );
  }
  if (range === 'week') {
    const weekAgo = new Date(now);
    weekAgo.setDate(weekAgo.getDate() - 7);
    return d >= weekAgo;
  }
  if (range === 'month') {
    return d.getFullYear() === now.getFullYear() && d.getMonth() === now.getMonth();
  }
  return true;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------
export default function AlertsPage() {
  const { tokens, isDark } = useTheme();

  // ---- State ---------------------------------------------------------------
  const [allAlerts, setAllAlerts] = useState([]);       // full list from backend
  const [counts, setCounts] = useState({ total: 0, pending: 0, acknowledged: 0, resolved: 0 });
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const [page, setPage] = useState(1);
  const [pageSize] = useState(20);

  const [searchText, setSearchText] = useState('');
  const [statusFilter, setStatusFilter] = useState(null);   // null = all
  const [dateRange, setDateRange] = useState('today');

  const [selectedRowKeys, setSelectedRowKeys] = useState([]);
  const [actionLoading, setActionLoading] = useState({});    // { [alertId]: true }
  const [batchLoading, setBatchLoading] = useState(false);

  // ---- Fetching (backend returns a plain array) ----------------------------
  const fetchAlerts = useCallback(async () => {
    setLoading(true);
    setError(null);

    const data = await api.get('/alerts');

    if (!data) {
      setError('加载告警数据失败，请检查网络后重试');
      setAllAlerts([]);
    } else {
      const list = Array.isArray(data) ? data : [];
      setAllAlerts(list);
    }

    setLoading(false);
  }, []);

  useEffect(() => {
    fetchAlerts();
  }, [fetchAlerts]);

  // ---- Compute counts from the full list -----------------------------------
  useEffect(() => {
    const pending = allAlerts.filter((a) => a.status === 'pending').length;
    const acknowledged = allAlerts.filter((a) => a.status === 'acknowledged').length;
    const resolved = allAlerts.filter((a) => a.status === 'resolved').length;
    setCounts({
      total: allAlerts.length,
      pending,
      acknowledged,
      resolved,
    });
  }, [allAlerts]);

  // ---- Client-side filtering -----------------------------------------------
  const filteredAlerts = useMemo(() => {
    let list = allAlerts;

    // Status filter
    if (statusFilter) {
      list = list.filter((a) => a.status === statusFilter);
    }

    // Date range filter
    if (dateRange) {
      list = list.filter((a) => isInDateRange(a.created_at, dateRange));
    }

    // Search text filter (site_name, site_code, message)
    if (searchText.trim()) {
      const q = searchText.trim().toLowerCase();
      list = list.filter(
        (a) =>
          (a.site_name && a.site_name.toLowerCase().includes(q)) ||
          (a.site_code && a.site_code.toLowerCase().includes(q)) ||
          (a.message && a.message.toLowerCase().includes(q)),
      );
    }

    return list;
  }, [allAlerts, statusFilter, dateRange, searchText]);

  // ---- Client-side pagination ----------------------------------------------
  const paginatedAlerts = useMemo(() => {
    const start = (page - 1) * pageSize;
    return filteredAlerts.slice(start, start + pageSize);
  }, [filteredAlerts, page, pageSize]);

  // Keep total in sync with filtered results
  useEffect(() => {
    setTotal(filteredAlerts.length);
  }, [filteredAlerts]);

  // Reset to page 1 when filters change
  useEffect(() => {
    setPage(1);
  }, [statusFilter, dateRange, searchText]);

  // ---- Single-row actions (all POST) ---------------------------------------
  const handleResolve = useCallback(async (record) => {
    setActionLoading((prev) => ({ ...prev, [record.id]: true }));
    const result = await api.post(`/alerts/${record.id}/resolve`);
    if (result && !result.error) {
      message.success(`告警「${record.site_name || record.id}」已办结`);
      fetchAlerts();
    } else {
      message.error(result?.error || '操作失败，请重试');
    }
    setActionLoading((prev) => ({ ...prev, [record.id]: false }));
  }, [fetchAlerts]);

  const handleAcknowledge = useCallback(async (record) => {
    setActionLoading((prev) => ({ ...prev, [record.id]: true }));
    const result = await api.post(`/alerts/${record.id}/acknowledge`);
    if (result && !result.error) {
      message.success(`告警「${record.site_name || record.id}」已确认`);
      fetchAlerts();
    } else {
      message.error(result?.error || '确认失败，请重试');
    }
    setActionLoading((prev) => ({ ...prev, [record.id]: false }));
  }, [fetchAlerts]);

  const handleUrge = useCallback(async (record) => {
    setActionLoading((prev) => ({ ...prev, [record.id]: true }));
    const result = await api.post(`/alerts/${record.id}/urge`);
    if (result && !result.error) {
      message.success(`已对告警「${record.site_name || record.id}」发起督办`);
      fetchAlerts();
    } else {
      message.error(result?.error || '督办失败，请重试');
    }
    setActionLoading((prev) => ({ ...prev, [record.id]: false }));
  }, [fetchAlerts]);

  const handleConvert = useCallback(async (record) => {
    Modal.confirm({
      title: '转为工单',
      icon: <ExclamationCircleOutlined />,
      content: `确认将告警「${record.site_name || record.id}」转为工单？`,
      okText: '确认',
      cancelText: '取消',
      onOk: async () => {
        setActionLoading((prev) => ({ ...prev, [record.id]: true }));
        const result = await api.post(`/alerts/${record.id}/confirm-convert`);
        if (result && !result.error) {
          message.success('已成功转为工单');
          fetchAlerts();
        } else {
          message.error(result?.error || '转工单失败，请重试');
        }
        setActionLoading((prev) => ({ ...prev, [record.id]: false }));
      },
    });
  }, [fetchAlerts]);

  // ---- Batch actions (POST via batch endpoint) -----------------------------
  const runBatch = useCallback(async (action, label) => {
    if (selectedRowKeys.length === 0) return;

    Modal.confirm({
      title: `批量${label}`,
      icon: <ExclamationCircleOutlined />,
      content: `确认对选中的 ${selectedRowKeys.length} 条告警执行「${label}」操作？`,
      okText: '确认',
      cancelText: '取消',
      onOk: async () => {
        setBatchLoading(true);
        const result = await api.post('/alerts/batch', {
          ids: selectedRowKeys,
          action,
        });
        if (result && !result.error) {
          message.success(`批量${label}成功，共 ${selectedRowKeys.length} 条`);
        } else {
          message.warning(result?.error || `批量${label}失败，请重试`);
        }
        setSelectedRowKeys([]);
        setBatchLoading(false);
        fetchAlerts();
      },
    });
  }, [selectedRowKeys, fetchAlerts]);

  const handleBatchResolve = useCallback(() => {
    runBatch('resolve', '办结');
  }, [runBatch]);

  const handleBatchUrge = useCallback(() => {
    runBatch('urge', '督办');
  }, [runBatch]);

  const handleBatchConvert = useCallback(() => {
    runBatch('confirm-convert', '转工单');
  }, [runBatch]);

  // ---- Table columns -------------------------------------------------------
  const columns = useMemo(() => [
    {
      title: '站点 & 等级',
      key: 'site_level',
      width: 200,
      render: (_, record) => (
        <div>
          <Text strong style={{ color: tokens.colorText, display: 'block', marginBottom: 2 }}>
            {record.site_name || record.site_code || '-'}
          </Text>
          <Tag
            color={alertLevelColor[record.level] || '#999'}
            style={{ fontSize: 12, borderRadius: 4 }}
          >
            {alertLevelLabel[record.level] || record.level || '未知'}
          </Tag>
        </div>
      ),
    },
    {
      title: '告警信息',
      dataIndex: 'message',
      key: 'message',
      ellipsis: true,
      render: (text) => (
        <Text style={{ color: tokens.colorText }} title={text}>
          {text || '-'}
        </Text>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 110,
      render: (status) => (
        <Tag
          icon={statusIconMap[status]}
          color={statusColorMap[status] || '#999'}
          style={{ borderRadius: 4 }}
        >
          {alertStatusMap[status] || status || '未知'}
        </Tag>
      ),
    },
    {
      title: '告警时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 170,
      sorter: (a, b) => new Date(a.created_at) - new Date(b.created_at),
      render: (text) => (
        <Text style={{ color: tokens.colorTextSecondary, fontSize: 13 }}>
          {text ? new Date(text).toLocaleString('zh-CN') : '-'}
        </Text>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 200,
      render: (_, record) => {
        const isLoading = !!actionLoading[record.id];
        const isResolved = record.status === 'resolved';

        return (
          <Space size={4}>
            {!isResolved && (
              <Button
                type="link"
                size="small"
                loading={isLoading}
                onClick={() => handleResolve(record)}
                style={{ color: tokens.colorSuccess || '#52c41a' }}
              >
                办结
              </Button>
            )}
            {!isResolved && (
              <Button
                type="link"
                size="small"
                loading={isLoading}
                onClick={() => handleUrge(record)}
                style={{ color: tokens.colorWarning || '#faad14' }}
              >
                督办
              </Button>
            )}
            <Button
              type="link"
              size="small"
              loading={isLoading}
              onClick={() => handleConvert(record)}
            >
              转工单
            </Button>
          </Space>
        );
      },
    },
  ], [tokens, actionLoading, handleResolve, handleUrge, handleConvert]);

  // ---- Row selection -------------------------------------------------------
  const rowSelection = useMemo(() => ({
    selectedRowKeys,
    onChange: (keys) => setSelectedRowKeys(keys),
  }), [selectedRowKeys]);

  // ---- Styles --------------------------------------------------------------
  const cardStyle = useMemo(() => ({
    borderRadius: 12,
    background: isDark
      ? 'linear-gradient(135deg, rgba(12,28,52,0.85), rgba(8,20,42,0.9))'
      : '#ffffff',
    border: `1px solid ${tokens.colorBorder}`,
    boxShadow: isDark
      ? '0 2px 12px rgba(0,0,0,0.3)'
      : '0 2px 8px rgba(0,0,0,0.06)',
  }), [isDark, tokens.colorBorder]);

  const statCardStyle = useMemo(() => ({
    ...cardStyle,
    height: '100%',
  }), [cardStyle]);

  // ---- Stat cards config ---------------------------------------------------
  const statCards = useMemo(() => [
    {
      title: '告警总数',
      value: counts.total,
      icon: <AlertOutlined style={{ fontSize: 22, color: tokens.colorPrimary }} />,
      color: tokens.colorPrimary,
    },
    {
      title: '待处理',
      value: counts.pending,
      icon: <ExclamationCircleOutlined style={{ fontSize: 22, color: '#faad14' }} />,
      color: '#faad14',
    },
    {
      title: '处理中',
      value: counts.acknowledged,
      icon: <ClockCircleOutlined style={{ fontSize: 22, color: '#1890ff' }} />,
      color: '#1890ff',
    },
    {
      title: '已办结',
      value: counts.resolved,
      icon: <CheckCircleOutlined style={{ fontSize: 22, color: '#52c41a' }} />,
      color: '#52c41a',
    },
  ], [counts, tokens.colorPrimary]);

  // ---- Render --------------------------------------------------------------
  return (
    <div style={{ padding: '24px 0' }}>
      {/* Page Header */}
      <div style={{ marginBottom: 24 }}>
        <Typography.Title level={4} style={{ color: tokens.colorText, margin: 0 }}>
          <AlertOutlined style={{ marginRight: 8 }} />
          告警管理中心
        </Typography.Title>
        <Text style={{ color: tokens.colorTextTertiary, fontSize: 13 }}>
          实时监控水文站点告警信息，及时处理与追踪
        </Text>
      </div>

      {/* Stat Metric Cards */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        {statCards.map((item) => (
          <Col xs={12} sm={12} md={6} key={item.title}>
            <Card
              style={statCardStyle}
              bodyStyle={{ padding: '20px 24px' }}
              hoverable
            >
              <Statistic
                title={
                  <Text style={{ color: tokens.colorTextSecondary, fontSize: 13 }}>
                    {item.title}
                  </Text>
                }
                value={item.value}
                prefix={item.icon}
                valueStyle={{
                  color: item.color,
                  fontWeight: 600,
                  fontSize: 28,
                }}
              />
            </Card>
          </Col>
        ))}
      </Row>

      {/* Filter Bar */}
      <Card style={cardStyle} bodyStyle={{ padding: '16px 24px' }}>
        <Row gutter={[12, 12]} align="middle">
          <Col flex="auto">
            <Space wrap size={12}>
              <Input
                placeholder="搜索站点名称或告警内容..."
                prefix={<SearchOutlined style={{ color: tokens.colorTextTertiary }} />}
                allowClear
                value={searchText}
                onChange={(e) => setSearchText(e.target.value)}
                onPressEnter={fetchAlerts}
                style={{ width: 280, borderRadius: 8 }}
              />
              <Select
                placeholder="告警状态"
                allowClear
                value={statusFilter}
                onChange={(val) => setStatusFilter(val ?? null)}
                style={{ width: 140 }}
                options={Object.entries(alertStatusMap).map(([value, label]) => ({
                  value,
                  label,
                }))}
              />
              <Select
                value={dateRange}
                onChange={setDateRange}
                style={{ width: 120 }}
                options={dateRangeOptions}
              />
            </Space>
          </Col>
          <Col>
            <Button
              onClick={fetchAlerts}
              loading={loading}
              style={{ borderRadius: 8 }}
            >
              刷新
            </Button>
          </Col>
        </Row>

        {/* Batch Operations Bar */}
        {selectedRowKeys.length > 0 && (
          <div
            style={{
              marginTop: 16,
              padding: '10px 16px',
              borderRadius: 8,
              background: isDark
                ? 'rgba(24, 144, 255, 0.08)'
                : 'rgba(24, 144, 255, 0.06)',
              border: `1px solid ${isDark ? 'rgba(24,144,255,0.25)' : 'rgba(24,144,255,0.2)'}`,
              display: 'flex',
              alignItems: 'center',
              gap: 12,
            }}
          >
            <Text style={{ color: tokens.colorTextSecondary, fontSize: 13 }}>
              已选择 <Badge count={selectedRowKeys.length} style={{ backgroundColor: tokens.colorPrimary }} /> 条告警
            </Text>
            <Space size={8}>
              <Button
                size="small"
                type="primary"
                loading={batchLoading}
                onClick={handleBatchResolve}
                icon={<CheckCircleOutlined />}
              >
                批量办结
              </Button>
              <Button
                size="small"
                loading={batchLoading}
                onClick={handleBatchUrge}
                icon={<ClockCircleOutlined />}
              >
                批量督办
              </Button>
              <Button
                size="small"
                loading={batchLoading}
                onClick={handleBatchConvert}
                icon={<AlertOutlined />}
              >
                批量转工单
              </Button>
              <Button
                size="small"
                type="text"
                onClick={() => setSelectedRowKeys([])}
              >
                取消选择
              </Button>
            </Space>
          </div>
        )}
      </Card>

      {/* Alerts Table */}
      <Card
        style={{ ...cardStyle, marginTop: 16 }}
        bodyStyle={{ padding: 0 }}
      >
        {/* Error State */}
        {error && (
          <div
            style={{
              padding: '32px 24px',
              textAlign: 'center',
            }}
          >
            <ExclamationCircleOutlined style={{ fontSize: 40, color: '#ff4d4f', marginBottom: 12 }} />
            <div>
              <Text style={{ color: tokens.colorError, fontSize: 14 }}>{error}</Text>
            </div>
            <Button
              type="primary"
              style={{ marginTop: 16, borderRadius: 8 }}
              onClick={fetchAlerts}
            >
              重新加载
            </Button>
          </div>
        )}

        {/* Table (also handles loading + empty states natively) */}
        {!error && (
          <Table
            rowKey="id"
            columns={columns}
            dataSource={paginatedAlerts}
            loading={loading}
            rowSelection={rowSelection}
            pagination={{
              current: page,
              pageSize,
              total,
              showSizeChanger: false,
              showQuickJumper: total > pageSize * 3,
              showTotal: (t) => `共 ${t} 条告警`,
              onChange: (p) => setPage(p),
              locale: {
                items_per_page: '条/页',
                jump_to: '跳至',
                page: '页',
              },
            }}
            locale={{
              emptyText: (
                <div style={{ padding: '40px 0' }}>
                  <CheckCircleOutlined style={{ fontSize: 40, color: '#52c41a', marginBottom: 12 }} />
                  <div>
                    <Text style={{ color: tokens.colorTextTertiary }}>
                      当前筛选条件下暂无告警记录
                    </Text>
                  </div>
                </div>
              ),
            }}
            scroll={{ x: 880 }}
            size="middle"
            style={{ borderRadius: 12, overflow: 'hidden' }}
          />
        )}
      </Card>
    </div>
  );
}
