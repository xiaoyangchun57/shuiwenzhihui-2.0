import { useState, useEffect, useCallback } from 'react';
import dayjs from 'dayjs';
import {
  Table, Card, Input, Select, Button, Space, Tag, Tabs,
  Typography, message, Spin, Empty, Form, Modal, Badge, Result,
  Descriptions, Drawer, DatePicker, Row, Col, Checkbox, Progress,
  Popconfirm, Switch, InputNumber, Statistic, Tooltip, Divider, Alert,
} from 'antd';
import {
  SearchOutlined, ReloadOutlined, PlusOutlined, EyeOutlined,
  EditOutlined, DeleteOutlined, SettingOutlined, FileTextOutlined,
  ScheduleOutlined, CheckCircleOutlined, ClockCircleOutlined,
  ThunderboltOutlined,
  StopOutlined, AlertOutlined,
} from '@ant-design/icons';
import { api } from '../../services/api';
import { useTheme } from '../../hooks/useTheme';
import { stationTypeMap } from '../../services/constants';

const { Title, Text } = Typography;
const { TextArea } = Input;

// ===== 常量映射 =====
const categoryOptions = [
  '水位观测', '雨量监测', '蒸发监测', '站院环境', '设施设备',
  '安全检查', '发电机', '缆道系统', '断面环境', '墒情监测', '安全防护', '自定义',
];
const frequencyOptions = [
  { value: 'daily', label: '每日' },
  { value: 'weekly', label: '每周' },
  { value: 'monthly', label: '每月' },
  { value: 'quarterly', label: '每季度' },
  { value: 'semi_annual', label: '每半年' },
  { value: 'annual', label: '每年' },
];
const frequencyLabelMap = { daily: '每日', weekly: '每周', monthly: '每月', quarterly: '每季度', semi_annual: '每半年', annual: '每年' };
const freqLevelMap = { high: '高频', mid: '中频', low: '低频', annual: '年度' };
const freqLevelColor = { high: 'red', mid: 'orange', low: 'blue', annual: 'green' };
const siteTypeLabelMap = {
  hydrology: '水文站', water_level: '水位站', rainfall: '雨量站',
  evaporation: '蒸发站', soil_moisture: '墒情站', groundwater: '地下水站',
  station_yard: '站院', reservoir: '水库', sluice: '闸坝', dike: '堤防', pump: '泵站',
};
const statusMap = { draft: { text: '草稿', color: 'default' }, active: { text: '执行中', color: 'processing' }, completed: { text: '已完成', color: 'success' } };

// ==================== PlanTab: 巡检计划（含统计+生成+完成率） ====================
function PlanTab({ tokens }) {
  const [plans, setPlans] = useState([]);
  const [loading, setLoading] = useState(false);
  const [statusFilter, setStatusFilter] = useState('');
  const [selectedPlan, setSelectedPlan] = useState(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [planDetail, setPlanDetail] = useState(null);
  // 统计与生成
  const [stats, setStats] = useState(null);
  const [statsLoading, setStatsLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [remindDays, setRemindDays] = useState(1);
  const [resultModalOpen, setResultModalOpen] = useState(false);
  const [generateResult, setGenerateResult] = useState(null);

  const loadPlans = useCallback(async () => {
    setLoading(true);
    try {
      const params = statusFilter ? `?status=${statusFilter}` : '';
      const data = await api.get(`/inspection-v2/plans${params}`);
      setPlans(data);
    } catch { message.error('加载计划失败'); }
    setLoading(false);
  }, [statusFilter]);

  const loadStats = useCallback(async () => {
    setStatsLoading(true);
    try {
      const data = await api.get('/inspection-v2/stats');
      setStats(data);
    } catch { /* ignore */ }
    setStatsLoading(false);
  }, []);

  useEffect(() => { loadPlans(); loadStats(); }, [loadPlans, loadStats]);

  const handleViewDetail = async (plan) => {
    try {
      const data = await api.get(`/inspection-v2/plans/${plan.id}`);
      setPlanDetail(data);
      setDetailOpen(true);
    } catch { message.error('加载详情失败'); }
  };

  const handleDelete = async (id) => {
    await api.delete(`/inspection-v2/plans/${id}`);
    message.success('已删除');
    loadPlans();
    loadStats();
  };

  const handleSubmitItem = async (planId, itemId, result) => {
    try {
      await api.put(`/inspection-v2/plans/${planId}/items/${itemId}`, { result });
      const data = await api.get(`/inspection-v2/plans/${planId}`);
      setPlanDetail(data);
      loadPlans();
      loadStats();
      message.success('已提交');
    } catch { message.error('提交失败'); }
  };

  const handleGenerate = async () => {
    setGenerating(true);
    try {
      const data = await api.post('/inspection-v2/plans/generate', { remind_days: remindDays, period: 'daily' });
      setGenerateResult(data);
      setResultModalOpen(true);
      loadPlans();
      loadStats();
    } catch { message.error('生成失败'); }
    setGenerating(false);
  };

  // 完成率计算
  const totalItems = plans.reduce((s, p) => s + (p.total_items || 0), 0);
  const completedItems = plans.reduce((s, p) => s + (p.completed_items || 0), 0);
  const overallRate = totalItems > 0 ? Math.round(completedItems / totalItems * 1000) / 10 : 0;

  const planColumns = [
    { title: 'ID', dataIndex: 'id', width: 60 },
    { title: '计划名称', dataIndex: 'plan_name', width: 240,
      render: (t, r) => <a onClick={() => handleViewDetail(r)}>{t}</a> },
    { title: '负责人', dataIndex: 'assignee', width: 120 },
    { title: '周期', dataIndex: 'period', width: 80, render: p => <Tag>{frequencyLabelMap[p] || p}</Tag> },
    { title: '生成日期', dataIndex: 'generate_date', width: 120 },
    { title: '检查项', width: 120, render: (_, r) => `${r.completed_items || 0} / ${r.total_items || 0}` },
    { title: '完成率', dataIndex: 'completion_rate', width: 150,
      render: v => <Progress percent={v} size="small" strokeColor={v >= 100 ? '#52c41a' : v > 50 ? '#faad14' : '#1890ff'} /> },
    { title: '状态', dataIndex: 'status', width: 100,
      render: s => { const m = statusMap[s] || {}; return <Tag color={m.color}>{m.text || s}</Tag>; } },
    { title: '操作', width: 120, render: (_, r) => (
      <Space>
        <Button type="link" size="small" icon={<EyeOutlined />} onClick={() => handleViewDetail(r)} />
        <Popconfirm title="删除此计划？" onConfirm={() => handleDelete(r.id)}>
          <Button type="link" size="small" danger icon={<DeleteOutlined />} />
        </Popconfirm>
      </Space>
    )},
  ];

  return (
    <div>
      {/* 第一行：排程统计 + 完成率 */}
      <Spin spinning={statsLoading}>
        <Row gutter={16} style={{ marginBottom: 16 }}>
          <Col span={6}>
            <Card size="small">
              <Statistic title="到期检查项" value={stats?.due_items || 0} valueStyle={{ color: '#cf1322', fontSize: 28 }} />
            </Card>
          </Col>
          <Col span={6}>
            <Card size="small">
              <Statistic title="逾期检查项" value={stats?.overdue_items || 0} valueStyle={{ color: '#ff4d4f', fontSize: 28 }}
                prefix={<AlertOutlined />} />
            </Card>
          </Col>
          <Col span={6}>
            <Card size="small">
              <Statistic title="临近到期(7天)" value={stats?.upcoming_items || 0} valueStyle={{ color: '#fa8c16', fontSize: 28 }} />
            </Card>
          </Col>
          <Col span={6}>
            <Card size="small">
              <Statistic title="总体完成率" value={overallRate} suffix="%" precision={1}
                valueStyle={{ color: overallRate > 80 ? '#3f8600' : overallRate > 50 ? '#fa8c16' : '#cf1322', fontSize: 28 }} />
            </Card>
          </Col>
        </Row>
      </Spin>

      {/* 第二行：生成计划操作栏 */}
      <Card size="small" style={{ marginBottom: 16 }}>
        <Space align="center" wrap>
          <Text strong>生成巡检计划：</Text>
          <Text type="secondary">提前提醒天数</Text>
          <InputNumber min={0} max={30} value={remindDays} onChange={setRemindDays} size="small" style={{ width: 80 }} />
          <Text type="secondary" style={{ fontSize: 12 }}>（将生成 next_due_date 在今天 + {remindDays} 天内的所有检查项）</Text>
          <Button type="primary" icon={<ThunderboltOutlined />} onClick={handleGenerate} loading={generating} size="small">
            生成巡检计划
          </Button>
          <Button icon={<ReloadOutlined />} onClick={() => { loadPlans(); loadStats(); }} size="small">刷新</Button>
        </Space>
      </Card>

      {/* 第三行：计划列表 */}
      <Table dataSource={plans} columns={planColumns} rowKey="id" loading={loading} size="small"
        pagination={{ pageSize: 15, showTotal: t => `共 ${t} 个计划` }}
        locale={{ emptyText: <Empty description="暂无巡检计划，点击上方按钮生成" /> }} />

      {/* 计划详情 Drawer */}
      <Drawer title={planDetail?.plan_name || '计划详情'} width={720} open={detailOpen} onClose={() => setDetailOpen(false)}>
        {planDetail && (
          <div>
            <Descriptions column={3} size="small" style={{ marginBottom: 16 }}>
              <Descriptions.Item label="负责人">{planDetail.assignee}</Descriptions.Item>
              <Descriptions.Item label="生成日期">{planDetail.generate_date}</Descriptions.Item>
              <Descriptions.Item label="完成率">{planDetail.completion_rate}%</Descriptions.Item>
              <Descriptions.Item label="总检查项">{planDetail.total_items}</Descriptions.Item>
              <Descriptions.Item label="已完成">{planDetail.completed_items}</Descriptions.Item>
              <Descriptions.Item label="涉及站点">{planDetail.site_groups?.length || 0} 个</Descriptions.Item>
            </Descriptions>
            <Divider style={{ margin: '12px 0' }} />
            {planDetail.site_groups?.map(group => (
              <Card key={group.site_id} size="small" title={<Space>{group.site_name}<Tag>{group.items.length} 项</Tag></Space>}
                style={{ marginBottom: 12 }}>
                {group.items.map(item => (
                  <div key={item.id} style={{ display: 'flex', alignItems: 'center', padding: '6px 0', borderBottom: '1px solid #f0f0f0' }}>
                    <div style={{ flex: 1 }}>
                      <Text>{item.item_name}</Text>
                      <Text type="secondary" style={{ marginLeft: 8, fontSize: 12 }}>
                        {item.category} {item.frequency && `| ${frequencyLabelMap[item.frequency] || item.frequency}`}
                      </Text>
                    </div>
                    <div style={{ width: 200, textAlign: 'right' }}>
                      {item.result ? (
                        <Tag color={item.result === 'normal' ? 'green' : item.result === 'abnormal' ? 'red' : 'default'}>
                          {item.result === 'normal' ? '正常' : item.result === 'abnormal' ? '异常' : item.result}
                        </Tag>
                      ) : (
                        <Space>
                          <Button size="small" type="primary" ghost onClick={() => handleSubmitItem(planDetail.id, item.id, 'normal')}>正常</Button>
                          <Button size="small" danger ghost onClick={() => handleSubmitItem(planDetail.id, item.id, 'abnormal')}>异常</Button>
                        </Space>
                      )}
                      {item.check_time && <Text type="secondary" style={{ fontSize: 11, marginLeft: 8 }}>{item.check_time}</Text>}
                    </div>
                  </div>
                ))}
              </Card>
            ))}
          </div>
        )}
      </Drawer>

      {/* 生成结果弹窗 */}
      <Modal
        title="巡检计划生成结果"
        open={resultModalOpen}
        onCancel={() => setResultModalOpen(false)}
        footer={<Button type="primary" onClick={() => setResultModalOpen(false)}>知道了</Button>}
        width={480}
      >
        {generateResult && (
          <div style={{ textAlign: 'center', padding: '16px 0' }}>
            <CheckCircleOutlined style={{ fontSize: 48, color: '#52c41a', marginBottom: 16 }} />
            <Title level={4} style={{ marginBottom: 24 }}>计划生成成功</Title>
            <Descriptions column={2} size="small" bordered>
              <Descriptions.Item label="生成日期">{generateResult.date}</Descriptions.Item>
              <Descriptions.Item label="计划数">
                <Text strong style={{ fontSize: 16, color: '#1890ff' }}>{generateResult.plans_created}</Text> 个
              </Descriptions.Item>
              <Descriptions.Item label="检查项总数">
                <Text strong style={{ fontSize: 16, color: '#1890ff' }}>{generateResult.total_items}</Text> 项
              </Descriptions.Item>
              <Descriptions.Item label="涉及站点">
                <Text strong style={{ fontSize: 16, color: '#1890ff' }}>{generateResult.due_sites}</Text> 个
              </Descriptions.Item>
            </Descriptions>
          </div>
        )}
      </Modal>
    </div>
  );
}

// ==================== TemplateTab: 方案模板管理 ====================
function TemplateTab({ tokens }) {
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(false);
  const [categoryFilter, setCategoryFilter] = useState('');
  const [selectedTpl, setSelectedTpl] = useState(null);
  const [itemsDrawerOpen, setItemsDrawerOpen] = useState(false);
  const [tplItems, setTplItems] = useState([]);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingTpl, setEditingTpl] = useState(null);
  const [form] = Form.useForm();

  const loadTemplates = useCallback(async () => {
    setLoading(true);
    try {
      const params = categoryFilter ? `?category=${encodeURIComponent(categoryFilter)}` : '';
      const data = await api.get(`/inspection-v2/templates${params}`);
      setTemplates(data);
    } catch { message.error('加载模板失败'); }
    setLoading(false);
  }, [categoryFilter]);

  useEffect(() => { loadTemplates(); }, [loadTemplates]);

  const loadItems = async (tid) => {
    try {
      const data = await api.get(`/inspection-v2/templates/${tid}/items`);
      setTplItems(data);
    } catch { message.error('加载检查项失败'); }
  };

  const handleViewItems = (tpl) => {
    setSelectedTpl(tpl);
    setItemsDrawerOpen(true);
    loadItems(tpl.id);
  };

  const handleCreate = () => {
    setEditingTpl(null);
    form.resetFields();
    form.setFieldsValue({ frequency: 'monthly', status: 'active' });
    setModalOpen(true);
  };

  const handleEdit = (tpl) => {
    setEditingTpl(tpl);
    form.setFieldsValue(tpl);
    setModalOpen(true);
  };

  const handleDelete = async (id) => {
    try {
      await api.delete(`/inspection-v2/templates/${id}`);
      message.success('已删除');
      loadTemplates();
    } catch { message.error('删除失败'); }
  };

  const handleModalOk = async () => {
    try {
      const values = await form.validateFields();
      if (editingTpl) {
        await api.put(`/inspection-v2/templates/${editingTpl.id}`, values);
        message.success('已更新');
      } else {
        await api.post('/inspection-v2/templates', values);
        message.success('已创建');
      }
      setModalOpen(false);
      loadTemplates();
    } catch { /* validation error */ }
  };

  const handleAddItem = async () => {
    if (!selectedTpl) return;
    const itemName = `新检查项-${tplItems.length + 1}`;
    try {
      await api.post(`/inspection-v2/templates/${selectedTpl.id}/items`, { item_name: itemName });
      loadItems(selectedTpl.id);
      loadTemplates();
    } catch { message.error('添加失败'); }
  };

  const handleDeleteItem = async (itemId) => {
    try {
      await api.delete(`/inspection-v2/templates/${selectedTpl.id}/items/${itemId}`);
      loadItems(selectedTpl.id);
      loadTemplates();
    } catch { message.error('删除失败'); }
  };

  const handleUpdateItem = async (itemId, changes) => {
    try {
      await api.put(`/inspection-v2/templates/${selectedTpl.id}/items/${itemId}`, changes);
      loadItems(selectedTpl.id);
    } catch { message.error('更新失败'); }
  };

  const columns = [
    { title: 'ID', dataIndex: 'id', width: 60 },
    { title: '模板名称', dataIndex: 'template_name', width: 200,
      render: (t, r) => <a onClick={() => handleViewItems(r)}>{t}</a> },
    { title: '分类', dataIndex: 'category', width: 120, render: t => <Tag>{t}</Tag> },
    { title: '频次', dataIndex: 'frequency', width: 100, render: f => <Tag color="blue">{frequencyLabelMap[f] || f}</Tag> },
    { title: '检查项数', dataIndex: 'item_count', width: 100, align: 'center' },
    { title: '描述', dataIndex: 'description', ellipsis: true },
    { title: '操作', width: 150, render: (_, r) => (
      <Space>
        <Button type="link" size="small" icon={<EyeOutlined />} onClick={() => handleViewItems(r)}>检查项</Button>
        <Button type="link" size="small" icon={<EditOutlined />} onClick={() => handleEdit(r)} />
        <Popconfirm title="确认删除此模板？" onConfirm={() => handleDelete(r.id)}>
          <Button type="link" size="small" danger icon={<DeleteOutlined />} />
        </Popconfirm>
      </Space>
    )},
  ];

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <Space>
          <Select value={categoryFilter} onChange={setCategoryFilter} style={{ width: 160 }} placeholder="按分类筛选"
            allowClear options={[{ value: '', label: '全部分类' }, ...categoryOptions.map(c => ({ value: c, label: c }))]} />
          <Button icon={<ReloadOutlined />} onClick={loadTemplates}>刷新</Button>
        </Space>
        <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>新建模板</Button>
      </div>
      <Table dataSource={templates} columns={columns} rowKey="id" loading={loading} size="small"
        pagination={{ pageSize: 20, showTotal: t => `共 ${t} 个模板` }} />

      {/* 检查项 Drawer */}
      <Drawer title={selectedTpl ? `${selectedTpl.template_name} - 检查项` : '检查项'} width={640}
        open={itemsDrawerOpen} onClose={() => setItemsDrawerOpen(false)}
        extra={<Button type="primary" size="small" icon={<PlusOutlined />} onClick={handleAddItem}>添加检查项</Button>}>
        <Table dataSource={tplItems} rowKey="id" size="small" pagination={false}
          columns={[
            { title: '排序', dataIndex: 'sort_order', width: 60 },
            { title: '检查项名称', dataIndex: 'item_name',
              render: (t, r) => <Input defaultValue={t} size="small" onBlur={e => {
                if (e.target.value !== t) handleUpdateItem(r.id, { item_name: e.target.value });
              }} /> },
            { title: '分类', dataIndex: 'category', width: 100, render: t => <Tag>{t || '-'}</Tag> },
            { title: '频次级别', dataIndex: 'frequency_level', width: 100,
              render: (v, r) => <Select size="small" value={v} style={{ width: 80 }}
                options={Object.entries(freqLevelMap).map(([k, l]) => ({ value: k, label: l }))}
                onChange={val => handleUpdateItem(r.id, { frequency_level: val })} /> },
            { title: '需拍照', dataIndex: 'photo_required', width: 80, align: 'center',
              render: (v, r) => <Switch size="small" checked={!!v} onChange={val => handleUpdateItem(r.id, { photo_required: val ? 1 : 0 })} /> },
            { title: '', width: 50, render: (_, r) => (
              <Popconfirm title="删除？" onConfirm={() => handleDeleteItem(r.id)}>
                <Button type="link" size="small" danger icon={<DeleteOutlined />} />
              </Popconfirm>
            )},
          ]} />
      </Drawer>

      {/* 新建/编辑 Modal */}
      <Modal title={editingTpl ? '编辑模板' : '新建模板'} open={modalOpen} onOk={handleModalOk}
        onCancel={() => setModalOpen(false)} width={520}>
        <Form form={form} layout="vertical">
          <Form.Item name="template_name" label="模板名称" rules={[{ required: true, message: '请输入模板名称' }]}>
            <Input placeholder="如：水位观测日常方案" />
          </Form.Item>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="category" label="分类" rules={[{ required: true, message: '请选择分类' }]}>
                <Select options={categoryOptions.map(c => ({ value: c, label: c }))} placeholder="选择分类" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="frequency" label="频次" rules={[{ required: true }]}>
                <Select options={frequencyOptions} placeholder="选择频次" />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="description" label="描述"><TextArea rows={3} placeholder="模板描述" /></Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

// ==================== ConfigTab: 巡检配置（仅匹配规则+跳过审核） ====================
function ConfigTab({ tokens }) {
  const [activeSubTab, setActiveSubTab] = useState('rules');

  const subTabs = [
    { key: 'rules', label: '匹配规则', icon: <SettingOutlined /> },
    { key: 'skip', label: '跳过审核', icon: <StopOutlined /> },
  ];

  return (
    <div>
      <Tabs activeKey={activeSubTab} onChange={setActiveSubTab} items={subTabs.map(t => ({
        key: t.key, label: <span>{t.icon} {t.label}</span>,
      }))} />
      {activeSubTab === 'rules' && <MatchRulesPanel />}
      {activeSubTab === 'skip' && <SkipAuditPanel />}
    </div>
  );
}

// --- 子面板1：匹配规则 ---
function MatchRulesPanel() {
  const [configs, setConfigs] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [form] = Form.useForm();
  const [siteTypeFilter, setSiteTypeFilter] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = siteTypeFilter ? `?site_type=${siteTypeFilter}` : '';
      const [cfgs, tpls] = await Promise.all([
        api.get(`/inspection-v2/configs${params}`),
        api.get('/inspection-v2/templates'),
      ]);
      setConfigs(cfgs);
      setTemplates(tpls);
    } catch { message.error('加载配置失败'); }
    setLoading(false);
  }, [siteTypeFilter]);

  useEffect(() => { load(); }, [load]);

  const handleCreate = async () => {
    try {
      const values = await form.validateFields();
      await api.post('/inspection-v2/configs', values);
      message.success('已创建');
      setModalOpen(false);
      form.resetFields();
      load();
    } catch { /* validation */ }
  };

  const handleDelete = async (id) => {
    await api.delete(`/inspection-v2/configs/${id}`);
    message.success('已删除');
    load();
  };

  const handleToggle = async (id, isActive) => {
    await api.put(`/inspection-v2/configs/${id}`, { is_active: isActive ? 1 : 0 });
    load();
  };

  const columns = [
    { title: '站点类型', dataIndex: 'site_type', width: 120,
      render: t => <Tag color="blue">{siteTypeLabelMap[t] || t}</Tag> },
    { title: '关联模板', dataIndex: 'template_name', width: 200 },
    { title: '模板分类', dataIndex: 'tpl_category', width: 120, render: t => <Tag>{t}</Tag> },
    { title: '模板频次', dataIndex: 'tpl_frequency', width: 100, render: f => frequencyLabelMap[f] || f },
    { title: '检查项数', dataIndex: 'item_count', width: 100, align: 'center' },
    { title: '状态', dataIndex: 'is_active', width: 80,
      render: v => <Switch size="small" checked={!!v} onChange={val => handleToggle(v, val)} /> },
    { title: '操作', width: 80, render: (_, r) => (
      <Popconfirm title="删除此配置？" onConfirm={() => handleDelete(r.id)}>
        <Button type="link" size="small" danger icon={<DeleteOutlined />} />
      </Popconfirm>
    )},
  ];

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <Space>
          <Select value={siteTypeFilter} onChange={setSiteTypeFilter} style={{ width: 160 }} allowClear
            placeholder="按站点类型筛选"
            options={[{ value: '', label: '全部类型' }, ...Object.entries(siteTypeLabelMap).map(([k, v]) => ({ value: k, label: v }))]} />
        </Space>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => { form.resetFields(); setModalOpen(true); }}>添加规则</Button>
      </div>
      <Table dataSource={configs} columns={columns} rowKey="id" loading={loading} size="small" pagination={{ pageSize: 15 }} />

      <Modal title="添加匹配规则" open={modalOpen} onOk={handleCreate} onCancel={() => setModalOpen(false)}>
        <Form form={form} layout="vertical">
          <Form.Item name="site_type" label="站点类型" rules={[{ required: true }]}>
            <Select options={Object.entries(siteTypeLabelMap).map(([k, v]) => ({ value: k, label: v }))} placeholder="选择站点类型" />
          </Form.Item>
          <Form.Item name="template_id" label="关联模板" rules={[{ required: true }]}>
            <Select options={templates.map(t => ({ value: t.id, label: `${t.template_name} (${frequencyLabelMap[t.frequency] || t.frequency})` }))}
              placeholder="选择方案模板" showSearch optionFilterProp="label" />
          </Form.Item>
          <Form.Item name="remark" label="备注"><Input placeholder="可选" /></Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

// --- 子面板2：跳过审核 ---
function SkipAuditPanel() {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    (async () => {
      setLoading(true);
      try {
        const data = await api.get('/inspections/skip/history');
        setLogs(data);
      } catch { /* ignore */ }
      setLoading(false);
    })();
  }, []);

  return (
    <Table dataSource={logs} rowKey="id" loading={loading} size="small"
      pagination={{ pageSize: 15 }}
      columns={[
        { title: '站点', dataIndex: 'site_id', width: 80 },
        { title: '检查项', dataIndex: 'check_item' },
        { title: '原因', dataIndex: 'reason', ellipsis: true },
        { title: '跳过次数', dataIndex: 'skip_count', width: 100, align: 'center',
          render: v => <Text type={v >= 3 ? 'danger' : undefined}>{v}</Text> },
        { title: '时间', dataIndex: 'created_at', width: 180 },
      ]} />
  );
}

// ==================== 主页面 ====================
export default function MaintenancePage() {
  const { tokens } = useTheme();
  const [activeTab, setActiveTab] = useState('plans');

  return (
    <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', padding: 24 }}>
      <div style={{ marginBottom: 20, flexShrink: 0 }}>
        <Title level={4} style={{ margin: 0, color: tokens.colorText }}>巡检管理</Title>
      </div>
      <Card style={{ flex: 1, minHeight: 0 }}>
        <Tabs activeKey={activeTab} onChange={setActiveTab} items={[
          {
            key: 'plans',
            label: <span><ScheduleOutlined /> 巡检计划</span>,
            children: <PlanTab tokens={tokens} />,
          },
          {
            key: 'templates',
            label: <span><FileTextOutlined /> 方案模板</span>,
            children: <TemplateTab tokens={tokens} />,
          },
          {
            key: 'config',
            label: <span><SettingOutlined /> 巡检配置</span>,
            children: <ConfigTab tokens={tokens} />,
          },
        ]} />
      </Card>
    </div>
  );
}
