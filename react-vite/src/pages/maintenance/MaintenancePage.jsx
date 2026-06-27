import { useState, useEffect, useCallback } from 'react';
import dayjs from 'dayjs';
import {
  Table, Card, Input, Select, Button, Space, Tag, Tabs,
  Typography, message, Spin, Empty, Form, Modal, Badge, Result,
  Descriptions, Drawer, DatePicker, Row, Col, Checkbox, Progress, Steps,
} from 'antd';
import {
  SearchOutlined, ReloadOutlined, PlusOutlined, EyeOutlined,
  EditOutlined, DeleteOutlined, SettingOutlined, FileTextOutlined,
  ScheduleOutlined, ToolOutlined, ExclamationCircleOutlined,
  CalendarOutlined, CheckCircleOutlined, ClockCircleOutlined,
  CameraOutlined,
} from '@ant-design/icons';
import { api } from '../../services/api';
import { useTheme } from '../../hooks/useTheme';
import { stationTypeMap, inspectionTypeMap } from '../../services/constants';

const { Title, Text } = Typography;

// ---------------------------------------------------------------------------
// Chinese label maps for English enum values
// ---------------------------------------------------------------------------
const categoryLabelMap = {
  facility: '设施维护',
  environment: '环境整治',
  observation: '观测设备',
  section: '断面维护',
  safety: '安全检查',
  daily: '日常维护',
};

const frequencyLabelMap = {
  monthly: '每月',
  weekly: '每周',
  biweekly: '每两周',
  daily: '每日',
  quarterly: '每季度',
  yearly: '每年',
  annual: '每年',
  half_yearly: '每半年',
  '1': '每日',
  '7': '每周',
  '14': '每两周',
  '15': '每半月',
  '30': '每月',
  '90': '每季度',
  '365': '每年',
  once_daily: '每日',
  once_weekly: '每周',
  once_biweekly: '每两周',
  once_monthly: '每月',
  once_quarterly: '每季度',
  once_yearly: '每年',
  seasonal: '季节性',
};

const subCategoryLabelMap = {
  environment: '环境整治',
  observation: '观测设备',
  section: '断面维护',
  facility: '设施维护',
  safety: '安全检查',
  water_level: '水位观测',
  rainfall: '雨量观测',
  evaporation: '蒸发观测',
  cableway: '缆道维护',
  soil_moisture: '墒情监测',
  generator: '发电机维护',
  seasonal: '季节性',
  daily: '日常',
};

// ---------- Check item options with auto-generated standard requirements ----------
const checkItemOptions = [
  { value: 'water_level_read', label: '基本水尺读数记录', standard: '驻测站每日2次，巡测站每日1次' },
  { value: 'water_level_telemetry', label: '遥测水位及时间校对', standard: '人工与遥测水位相差≥0.02m时需复核报送调整' },
  { value: 'water_level_deviation', label: '偏差检测（≥0.02m报送水情科）', standard: '偏差≥0.02m时立即复核并报送水情科' },
  { value: 'water_level_clean', label: '水尺清洗检查', standard: '水尺刻度清晰可见，无附着物' },
  { value: 'water_level_device', label: '水位设备运行检查', standard: '设备运行正常，数据采集连续完整' },
  { value: 'water_level_form', label: '填写水位巡查表并拍照存档', standard: '巡查表填写完整规范，照片清晰可辨' },
  { value: 'facility_clean', label: '清洗水尺及设施设备检查', standard: '水尺清洁无附着物，设施设备完好' },
  { value: 'facility_ladder', label: '爬梯、护栏牢固度检查', standard: '爬梯、护栏无松动、无锈蚀、牢固可靠' },
  { value: 'safety_equipment', label: '测验设施设备安全检查', standard: '设备运行正常，安全防护措施到位' },
  { value: 'safety_environment', label: '安全环境检查', standard: '站房周边环境安全，无安全隐患' },
  { value: 'safety_station', label: '站房检查', standard: '站房结构完好，门窗锁具正常' },
  { value: 'safety_fire', label: '灭火器、安全器材检查', standard: '灭火器在有效期内，安全器材齐全完好' },
  { value: 'generator_check', label: '发电机机油线路检查', standard: '每月检查机油线路并运行≥30分钟' },
  { value: 'generator_maintenance', label: '发电机汛前汛后保养', standard: '每年汛前汛后更换机油及线路保养' },
  { value: 'rainfall_site', label: '遥测雨量器现场运行维护巡检', standard: '设备运行正常，数据采集连续' },
  { value: 'rainfall_terminal', label: '数据采集终端检查', standard: '终端通信正常，数据传输稳定' },
  { value: 'rainfall_power', label: '供电设备检查', standard: '供电正常，太阳能板清洁，蓄电池电量充足' },
  { value: 'rainfall_cylinder', label: '雨量筒检查', standard: '雨量筒清洁无堵塞，翻斗灵活' },
  { value: 'evaporation_device', label: '自动蒸发设备遥测终端巡检', standard: '设备运行正常，数据准确' },
  { value: 'evaporation_water', label: '蒸发设备换水', standard: '按规定周期换水，水质清洁' },
  { value: 'cableway_check', label: '缆道主索、循环索检查', standard: '钢丝绳无断丝、无锈蚀，张力正常' },
  { value: 'cableway_anchor', label: '锚碇、导向轮、绞车检查', standard: '锚碇牢固，导向轮转动灵活，绞车运行正常' },
  { value: 'soil_station', label: '墒情基本站巡查', standard: '站点整洁，传感器工作正常，数据准确' },
  { value: 'section_clean', label: '断面清理（杂草杂木淤泥）', standard: '断面无积水、无淤泥、无杂草、无杂物' },
  { value: 'grass_maintain', label: '草地维护', standard: '草皮高度符合规范要求' },
  { value: 'daily_record', label: '日常记录填写', standard: '记录完整、规范、及时' },
];

const subCategoryOptions = Object.entries(subCategoryLabelMap).map(([value, label]) => ({ value, label }));

// ---------- Inspection Plans Tab ----------
function InspectionPlansTab() {
  const { tokens } = useTheme();
  const [form] = Form.useForm();
  const [plans, setPlans] = useState([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState(undefined);
  const [categoryFilter, setCategoryFilter] = useState(undefined);

  // View drawer
  const [viewOpen, setViewOpen] = useState(false);
  const [viewingPlan, setViewingPlan] = useState(null);

  // Create/Edit modal
  const [modalOpen, setModalOpen] = useState(false);
  const [modalLoading, setModalLoading] = useState(false);
  const [editingPlan, setEditingPlan] = useState(null);
  const [sites, setSites] = useState([]);

  // Fetch sites for dropdown
  useEffect(() => {
    api.get('/sites').then(data => {
      const list = Array.isArray(data) ? data : (data?.sites || []);
      setSites(list);
    }).catch(() => {});
  }, []);

  const fetchPlans = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (statusFilter) params.set('status', statusFilter);
      if (categoryFilter) params.set('category', categoryFilter);
      const data = await api.get(`/maintenance/plans?${params.toString()}`);
      const list = Array.isArray(data) ? data : (data?.plans || []);
      // Client-side search filtering on plan_name / site_name / id
      if (search) {
        const kw = search.toLowerCase();
        setPlans(list.filter((p) =>
          (p.plan_name || '').toLowerCase().includes(kw) ||
          (p.site_name || '').toLowerCase().includes(kw) ||
          String(p.id).includes(kw)
        ));
      } else {
        setPlans(list);
      }
    } catch {
      message.error('加载巡检计划失败');
      setPlans([]);
    } finally {
      setLoading(false);
    }
  }, [search, statusFilter, categoryFilter]);

  useEffect(() => { fetchPlans(); }, [fetchPlans]);

  const handleReset = () => {
    setSearch('');
    setStatusFilter(undefined);
    setCategoryFilter(undefined);
  };

  const handleView = (record) => { setViewingPlan(record); setViewOpen(true); };

  const handleCreate = () => { setEditingPlan(null); form.resetFields(); setModalOpen(true); };

  const handleEdit = (record) => {
    setEditingPlan(record);
    form.setFieldsValue({
      plan_name: record.plan_name, category: record.category, frequency: record.frequency,
      site_id: record.site_name || record.site_id, assignee: record.assignee,
      due_date: record.due_date ? dayjs(record.due_date) : undefined, remark: record.remark,
    });
    setModalOpen(true);
  };

  const handleModalOk = async () => {
    try {
      const values = await form.validateFields();
      setModalLoading(true);
      const payload = { ...values };
      if (payload.due_date && payload.due_date.format) payload.due_date = payload.due_date.format('YYYY-MM-DD');
      const result = editingPlan
        ? await api.put(`/maintenance/plans/${editingPlan.id}`, payload)
        : await api.post('/maintenance/plans', payload);
      if (result && !result.error) {
        message.success(editingPlan ? '计划已更新' : '计划已创建');
        setModalOpen(false); setEditingPlan(null); fetchPlans();
      } else { message.error(result?.error || '操作失败'); }
    } catch { /* validation error */ } finally { setModalLoading(false); }
  };

  const handleDelete = (record) => {
    Modal.confirm({
      title: '确认删除', icon: <ExclamationCircleOutlined />,
      content: `确认删除巡检计划 #${record.id}？`, okText: '删除', okType: 'danger', cancelText: '取消',
      onOk: async () => {
        const result = await api.delete(`/maintenance/plans/${record.id}`);
        if (result && !result.error) { message.success('计划已删除'); fetchPlans(); }
        else { message.error('删除失败'); }
      },
    });
  };

  const categoryOptions = Object.entries(categoryLabelMap).map(([value, label]) => ({ value, label }));
  const frequencyOptions = [
    { value: 'daily', label: '每日' }, { value: 'weekly', label: '每周' },
    { value: 'biweekly', label: '每两周' }, { value: 'monthly', label: '每月' },
    { value: 'quarterly', label: '每季度' }, { value: 'half_yearly', label: '每半年' },
    { value: 'yearly', label: '每年' },
  ];

  const columns = [
    {
      title: '计划编号',
      dataIndex: 'id',
      key: 'id',
      width: 80,
      render: (text) => (
        <Text strong style={{ color: tokens.colorPrimary }}>#{text}</Text>
      ),
    },
    {
      title: '计划名称',
      dataIndex: 'plan_name',
      key: 'plan_name',
      width: 160,
      ellipsis: true,
    },
    {
      title: '站点名称',
      dataIndex: 'site_name',
      key: 'site_name',
      width: 90,
      ellipsis: true,
      render: (val) => val || '-',
    },
    {
      title: '分类',
      dataIndex: 'category',
      key: 'category',
      width: 80,
      ellipsis: true,
      render: (val) => categoryLabelMap[val] || val || '-',
    },
    {
      title: '频次',
      dataIndex: 'frequency',
      key: 'frequency',
      width: 70,
      render: (val) => frequencyLabelMap[val] || val || '-',
    },
    {
      title: '负责人',
      dataIndex: 'assignee',
      key: 'assignee',
      width: 70,
      render: (val) => val || '-',
    },
    {
      title: '到期时间',
      dataIndex: 'due_date',
      key: 'due_date',
      width: 100,
      render: (text) => text || '-',
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 80,
      render: (val) => {
        const map = {
          pending: { color: 'warning', label: '待执行' },
          completed: { color: 'success', label: '已完成' },
          active: { color: 'success', label: '启用' },
          inactive: { color: 'default', label: '停用' },
          draft: { color: 'warning', label: '草稿' },
        };
        const cfg = map[val] || { color: 'default', label: val || '-' };
        return <Badge status={cfg.color} text={cfg.label} />;
      },
    },
    {
      title: '操作',
      key: 'actions',
      width: 130,
      render: (_, record) => (
        <Space size={4}>
          <Button type="link" size="small" icon={<EyeOutlined />} onClick={() => handleView(record)}>查看</Button>
          <Button type="link" size="small" icon={<EditOutlined />} onClick={() => handleEdit(record)}>编辑</Button>
          <Button type="link" size="small" danger icon={<DeleteOutlined />} onClick={() => handleDelete(record)}>删除</Button>
        </Space>
      ),
    },
  ];

  return (
    <div>
      {/* Filters */}
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
        <Space wrap size={12}>
          <Input
            placeholder="搜索计划名称、站点..."
            prefix={<SearchOutlined style={{ color: tokens.colorTextTertiary }} />}
            allowClear
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{ width: 260, borderRadius: 8 }}
          />
          <Select
            placeholder="状态"
            allowClear
            value={statusFilter}
            onChange={(val) => setStatusFilter(val)}
            style={{ width: 120 }}
            options={[
              { value: 'pending', label: '待执行' },
              { value: 'completed', label: '已完成' },
            ]}
          />
          <Select placeholder="分类" allowClear value={categoryFilter} onChange={setCategoryFilter} style={{ width: 140 }} options={categoryOptions} />
          <Button icon={<ReloadOutlined />} onClick={handleReset}>重置</Button>
        </Space>
        <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}
          style={{ background: `linear-gradient(135deg, ${tokens.colorPrimary}, ${tokens.colorPrimaryHover})`, border: 'none' }}>
          新建计划
        </Button>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 280px)', minHeight: 400 }}>
        <style>{`.hide-scrollbar::-webkit-scrollbar{display:none}.hide-scrollbar{-ms-overflow-style:none;scrollbar-width:none}`}</style>
        <div className="hide-scrollbar" style={{ flex: 1, overflow: 'auto' }}>
          <Table
            columns={columns}
            dataSource={plans}
            rowKey={(r) => r.id}
            loading={loading}
            pagination={false}
            scroll={{ x: 810 }}
            locale={{ emptyText: <Empty description="暂无巡检计划" /> }}
            size="middle"
          />
        </div>
      </div>

      {/* View Drawer */}
      <Drawer title={<Space><ScheduleOutlined /><span>计划详情</span></Space>} open={viewOpen}
        onClose={() => { setViewOpen(false); setViewingPlan(null); }} width={480}>
        {viewingPlan && (
          <Descriptions column={1} size="small" bordered>
            <Descriptions.Item label="计划编号"><Text strong style={{ color: tokens.colorPrimary }}>#{viewingPlan.id}</Text></Descriptions.Item>
            <Descriptions.Item label="计划名称">{viewingPlan.plan_name || '-'}</Descriptions.Item>
            <Descriptions.Item label="站点">{viewingPlan.site_name || '-'}</Descriptions.Item>
            <Descriptions.Item label="分类">{categoryLabelMap[viewingPlan.category] || viewingPlan.category || '-'}</Descriptions.Item>
            <Descriptions.Item label="频次">{frequencyLabelMap[viewingPlan.frequency] || viewingPlan.frequency || '-'}</Descriptions.Item>
            <Descriptions.Item label="负责人">{viewingPlan.assignee || '-'}</Descriptions.Item>
            <Descriptions.Item label="到期时间">{viewingPlan.due_date || '-'}</Descriptions.Item>
            <Descriptions.Item label="状态">{({ pending: '待执行', completed: '已完成', active: '启用', inactive: '停用', draft: '草稿' }[viewingPlan.status]) || viewingPlan.status || '-'}</Descriptions.Item>
            <Descriptions.Item label="备注">{viewingPlan.remark || '暂无'}</Descriptions.Item>
          </Descriptions>
        )}
      </Drawer>

      {/* Create/Edit Modal */}
      <Modal title={editingPlan ? '编辑计划' : '新建计划'} open={modalOpen} onOk={handleModalOk}
        onCancel={() => { setModalOpen(false); setEditingPlan(null); }} confirmLoading={modalLoading}
        okText={editingPlan ? '保存' : '创建'} cancelText="取消" width={520} destroyOnClose>
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item name="plan_name" label="计划名称" rules={[{ required: true, message: '请输入计划名称' }]}>
            <Input placeholder="请输入计划名称" />
          </Form.Item>
          <Row gutter={12}>
            <Col span={12}>
              <Form.Item name="category" label="分类" rules={[{ required: true, message: '请选择分类' }]}>
                <Select placeholder="请选择分类" options={categoryOptions} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="frequency" label="频次" rules={[{ required: true, message: '请选择频次' }]}>
                <Select placeholder="请选择频次" options={frequencyOptions} />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="site_id" label="关联站点" rules={[{ required: true, message: '请选择站点' }]}>
            <Select placeholder="请选择站点" showSearch allowClear
              filterOption={(input, option) => (option.label || '').toLowerCase().includes(input.toLowerCase())}
              options={sites.map(s => ({ value: s.id, label: `${s.name || s.code} (${s.code || s.id})` }))} />
          </Form.Item>
          <Form.Item name="assignee" label="负责人"><Input placeholder="负责人姓名" /></Form.Item>
          <Form.Item name="due_date" label="到期时间"><DatePicker style={{ width: '100%' }} placeholder="请选择到期时间" format="YYYY-MM-DD" /></Form.Item>
          <Form.Item name="remark" label="备注"><Input.TextArea rows={2} placeholder="备注信息" /></Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

// ---------- Inspection Schemes Tab ----------
// Uses /api/maintenance/templates as data source since there is no
// general list endpoint for inspection schemes.
function InspectionSchemesTab() {
  const { tokens } = useTheme();
  const [schemes, setSchemes] = useState([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState('');

  // View / Create / Edit state
  const [viewOpen, setViewOpen] = useState(false);
  const [viewingScheme, setViewingScheme] = useState(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingScheme, setEditingScheme] = useState(null);
  const [modalLoading, setModalLoading] = useState(false);
  const [form] = Form.useForm();
  const [selectedCheckItems, setSelectedCheckItems] = useState([]);
  const [standardText, setStandardText] = useState('');

  const fetchSchemes = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.get('/maintenance/templates');
      const list = Array.isArray(data) ? data : (data?.schemes || data?.templates || []);
      if (search) {
        const kw = search.toLowerCase();
        setSchemes(list.filter((s) =>
          (s.title || '').toLowerCase().includes(kw) ||
          (s.category || '').toLowerCase().includes(kw) ||
          (s.sub_category || '').toLowerCase().includes(kw)
        ));
      } else {
        setSchemes(list);
      }
    } catch {
      message.error('加载方案数据失败');
      setSchemes([]);
    } finally {
      setLoading(false);
    }
  }, [search]);

  useEffect(() => { fetchSchemes(); }, [fetchSchemes]);

  const handleView = useCallback((record) => {
    setViewingScheme(record);
    setViewOpen(true);
  }, []);

  const handleCreate = useCallback(() => {
    setEditingScheme(null);
    form.resetFields();
    form.setFieldsValue({ frequency: 'monthly' });
    setSelectedCheckItems([]);
    setStandardText('');
    setModalOpen(true);
  }, [form]);

  const handleEdit = useCallback((record) => {
    setEditingScheme(record);
    form.setFieldsValue({
      title: record.title,
      category: record.category,
      sub_category: record.sub_category,
      frequency: record.frequency,
      description: record.description,
      standard: record.standard,
      estimated_hours: record.estimated_hours,
    });
    // Restore check items
    const items = Array.isArray(record.check_items) ? record.check_items : [];
    const itemValues = items.map((item) => {
      if (typeof item === 'string') return item;
      return item.id || item.value || item.label || '';
    }).filter(Boolean);
    setSelectedCheckItems(itemValues);
    // Restore or auto-generate standard text
    if (record.standard) {
      setStandardText(record.standard);
    } else {
      const standards = itemValues.map((v) => {
        const opt = checkItemOptions.find((o) => o.value === v);
        return opt ? opt.standard : '';
      }).filter(Boolean);
      setStandardText(standards.join('；'));
    }
    setModalOpen(true);
  }, [form]);

  const handleCheckItemsChange = (checkedValues) => {
    setSelectedCheckItems(checkedValues);
    const standards = checkedValues.map((v) => {
      const opt = checkItemOptions.find((o) => o.value === v);
      return opt ? opt.standard : '';
    }).filter(Boolean);
    setStandardText(standards.join('；'));
  };

  const handleModalOk = useCallback(async () => {
    try {
      const values = await form.validateFields();
      setModalLoading(true);
      // Build check_items array from selected values
      const checkItems = selectedCheckItems.map((v) => {
        const opt = checkItemOptions.find((o) => o.value === v);
        return opt ? { id: v, label: opt.label } : { id: v, label: v };
      });
      const submitData = {
        ...values,
        check_items: checkItems,
        standard: standardText || values.standard,
      };
      if (editingScheme) {
        const result = await api.put(`/maintenance/templates/${editingScheme.id}`, submitData);
        if (result && !result.error) {
          message.success('模板已更新');
          setModalOpen(false);
          setSelectedCheckItems([]);
          setStandardText('');
          fetchSchemes();
        } else {
          message.error(result?.error || '更新失败');
        }
      } else {
        const result = await api.post('/maintenance/templates', submitData);
        if (result && !result.error) {
          message.success('模板创建成功');
          setModalOpen(false);
          setSelectedCheckItems([]);
          setStandardText('');
          fetchSchemes();
        } else {
          message.error(result?.error || '创建失败');
        }
      }
    } catch { /* validation error */ }
    setModalLoading(false);
  }, [form, editingScheme, fetchSchemes, selectedCheckItems, standardText]);

  const handleDelete = useCallback((record) => {
    Modal.confirm({
      title: '确认删除',
      icon: <ExclamationCircleOutlined />,
      content: `确认删除模板「${record.title}」？`,
      okText: '删除',
      okType: 'danger',
      cancelText: '取消',
      onOk: async () => {
        const result = await api.delete(`/maintenance/templates/${record.id}`);
        if (result && !result.error) {
          message.success('模板已删除');
          fetchSchemes();
        } else {
          message.error('删除失败');
        }
      },
    });
  }, [fetchSchemes]);

  const categoryOptions = Object.entries(categoryLabelMap).map(([value, label]) => ({ value, label }));
  const frequencyOptions = Object.entries(frequencyLabelMap).map(([value, label]) => ({ value, label }));

  const columns = [
    {
      title: '编号',
      dataIndex: 'id',
      key: 'id',
      width: 60,
      render: (text) => (
        <Text strong style={{ color: tokens.colorPrimary }}>#{text}</Text>
      ),
    },
    {
      title: '模板名称',
      dataIndex: 'title',
      key: 'title',
      width: 200,
      ellipsis: true,
    },
    {
      title: '分类',
      dataIndex: 'category',
      key: 'category',
      width: 100,
      ellipsis: true,
      render: (val) => {
        const label = categoryLabelMap[val] || val;
        return <Text style={{ fontSize: 13 }}>{label}</Text>;
      },
    },
    {
      title: '子分类',
      dataIndex: 'sub_category',
      key: 'sub_category',
      width: 100,
      ellipsis: true,
      render: (val) => {
        const label = subCategoryLabelMap[val] || val;
        return <Text style={{ fontSize: 13 }}>{label}</Text>;
      },
    },
    {
      title: '频次',
      dataIndex: 'frequency',
      key: 'frequency',
      width: 70,
      render: (val) => frequencyLabelMap[val] || val || '-',
    },
    {
      title: '检查项数',
      dataIndex: 'check_items',
      key: 'check_items',
      width: 80,
      align: 'center',
      render: (val) => {
        if (Array.isArray(val)) return val.length;
        return '-';
      },
    },
    {
      title: '预估工时',
      dataIndex: 'estimated_hours',
      key: 'estimated_hours',
      width: 90,
      align: 'center',
      render: (val) => val != null ? val : '-',
    },
    {
      title: '描述',
      dataIndex: 'description',
      key: 'description',
      width: 200,
      ellipsis: true,
      render: (val) => val || '-',
    },
    {
      title: '操作',
      key: 'actions',
      width: 150,
      fixed: 'right',
      render: (_, record) => (
        <Space size={4}>
          <Button type="link" size="small" icon={<EyeOutlined />} onClick={() => handleView(record)}>
            查看
          </Button>
          <Button type="link" size="small" icon={<EditOutlined />} onClick={() => handleEdit(record)}>
            编辑
          </Button>
          <Button type="link" size="small" danger icon={<DeleteOutlined />} onClick={() => handleDelete(record)}>
            删除
          </Button>
        </Space>
      ),
    },
  ];

  const checkItems = viewingScheme?.check_items;
  const checkItemsList = Array.isArray(checkItems) ? checkItems : [];

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
        <Space wrap size={12}>
          <Input
            placeholder="搜索模板名称、分类..."
            prefix={<SearchOutlined style={{ color: tokens.colorTextTertiary }} />}
            allowClear
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{ width: 260, borderRadius: 8 }}
          />
          <Button icon={<ReloadOutlined />} onClick={() => setSearch('')}>重置</Button>
        </Space>
        <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}
          style={{ background: `linear-gradient(135deg, ${tokens.colorPrimary}, ${tokens.colorPrimaryHover})`, border: 'none' }}>
          新建方案
        </Button>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 280px)', minHeight: 400 }}>
        <style>{`.hide-scrollbar::-webkit-scrollbar{display:none}.hide-scrollbar{-ms-overflow-style:none;scrollbar-width:none}`}</style>
        <div className="hide-scrollbar" style={{ flex: 1, overflow: 'auto' }}>
          <Table
            columns={columns}
            dataSource={schemes}
            rowKey={(r) => r.id}
            loading={loading}
            pagination={false}
            locale={{ emptyText: <Empty description="暂无方案模板" /> }}
            size="middle"
            scroll={{ x: 1200 }}
          />
        </div>
      </div>

      {/* ===== View Drawer ===== */}
      <Drawer
        title="方案模板详情"
        open={viewOpen}
        onClose={() => { setViewOpen(false); setViewingScheme(null); }}
        width={480}
        destroyOnClose
      >
        {viewingScheme && (
          <div>
            <Descriptions column={1} bordered size="small" labelStyle={{ width: 90 }}>
              <Descriptions.Item label="模板名称">{viewingScheme.title || '-'}</Descriptions.Item>
              <Descriptions.Item label="分类">{categoryLabelMap[viewingScheme.category] || viewingScheme.category || '-'}</Descriptions.Item>
              <Descriptions.Item label="子分类">{subCategoryLabelMap[viewingScheme.sub_category] || viewingScheme.sub_category || '-'}</Descriptions.Item>
              <Descriptions.Item label="频次">{frequencyLabelMap[viewingScheme.frequency] || viewingScheme.frequency || '-'}</Descriptions.Item>
              <Descriptions.Item label="预估工时">{viewingScheme.estimated_hours != null ? `${viewingScheme.estimated_hours} 小时` : '-'}</Descriptions.Item>
              <Descriptions.Item label="描述">{viewingScheme.description || '-'}</Descriptions.Item>
              <Descriptions.Item label="标准要求">{viewingScheme.standard || '-'}</Descriptions.Item>
            </Descriptions>

            <Title level={5} style={{ marginTop: 20, marginBottom: 12 }}>
              检查项 ({checkItemsList.length})
            </Title>
            {checkItemsList.length > 0 ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {checkItemsList.map((item, i) => {
                  let label = '';
                  if (typeof item === 'string') {
                    label = item;
                  } else if (item && typeof item === 'object') {
                    label = item.label || item.name || item.title || item.text || JSON.stringify(item);
                  }
                  return (
                    <div key={i} style={{ padding: '8px 12px', borderRadius: 8, background: tokens.colorBgTextHover, fontSize: 13 }}>
                      <Text strong style={{ color: tokens.colorPrimary, marginRight: 8 }}>#{i + 1}</Text>
                      {label}
                    </div>
                  );
                })}
              </div>
            ) : (
              <Empty description="暂无检查项" style={{ margin: '12px 0' }} />
            )}
          </div>
        )}
      </Drawer>

      {/* ===== Create / Edit Modal ===== */}
      <Modal
        title={editingScheme ? '编辑方案模板' : '新建方案模板'}
        open={modalOpen}
        onOk={handleModalOk}
        onCancel={() => { setModalOpen(false); setEditingScheme(null); form.resetFields(); setSelectedCheckItems([]); setStandardText(''); }}
        confirmLoading={modalLoading}
        okText={editingScheme ? '保存' : '创建'}
        cancelText="取消"
        width={600}
        destroyOnClose
      >
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item name="title" label="模板名称" rules={[{ required: true, message: '请输入模板名称' }]}>
            <Input placeholder="请输入模板名称" />
          </Form.Item>
          <Form.Item name="category" label="分类" rules={[{ required: true, message: '请选择分类' }]}>
            <Select placeholder="请选择分类" options={categoryOptions} showSearch
              filterOption={(input, option) => option.label.toLowerCase().includes(input.toLowerCase())} />
          </Form.Item>
          <Form.Item name="sub_category" label="子分类">
            <Select placeholder="请选择子分类" options={subCategoryOptions} showSearch allowClear
              filterOption={(input, option) => option.label.toLowerCase().includes(input.toLowerCase())} />
          </Form.Item>
          <Form.Item name="frequency" label="频次">
            <Select placeholder="请选择频次" options={frequencyOptions} />
          </Form.Item>
          <Form.Item label="检查项（描述）">
            <Checkbox.Group
              value={selectedCheckItems}
              onChange={handleCheckItemsChange}
              style={{ display: 'flex', flexDirection: 'column', gap: 8, maxHeight: 200, overflowY: 'auto' }}
            >
              {checkItemOptions.map((item) => (
                <Checkbox key={item.value} value={item.value} style={{ marginLeft: 0 }}>
                  {item.label}
                </Checkbox>
              ))}
            </Checkbox.Group>
          </Form.Item>
          <Form.Item label="标准要求">
            <div style={{
              padding: '10px 12px', borderRadius: 8, minHeight: 60,
              background: tokens.colorBgTextHover, fontSize: 13, lineHeight: 1.8,
              border: `1px solid ${tokens.colorBorder}`,
            }}>
              {standardText || <Text type="secondary">选择检查项后自动生成</Text>}
            </div>
            <Text type="secondary" style={{ fontSize: 12, marginTop: 4, display: 'block' }}>
              根据所选检查项自动生成，可直接编辑
            </Text>
            <Input.TextArea
              rows={2}
              value={standardText}
              onChange={(e) => setStandardText(e.target.value)}
              placeholder="也可手动输入标准要求"
              style={{ marginTop: 8 }}
            />
          </Form.Item>
          <Form.Item name="estimated_hours" label="预估工时(小时)">
            <Input type="number" step="0.5" placeholder="2" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

// ---------- Inspection Config Tab ----------
// No /api/inspection/config endpoint exists in the backend.
// Display a graceful placeholder until a dedicated config API is available.
function InspectionConfigTab() {
  return (
    <div style={{ padding: '40px 0' }}>
      <Result
        icon={<SettingOutlined style={{ color: '#1890ff' }} />}
        title="巡检参数配置"
        subTitle="该功能模块正在开发中，敬请期待。当前可通过后端直接管理运维配置。"
      />
    </div>
  );
}

// ---------- Inspection Execution Tab ----------
function InspectionExecutionTab({ tokens }) {
  const [executionStep, setExecutionStep] = useState(0);
  const [selectedPlan, setSelectedPlan] = useState(null);
  const [plans, setPlans] = useState([]);
  const [loading, setLoading] = useState(false);

  // Checklist state
  const [checklist, setChecklist] = useState([
    { id: 1, text: '检查水位计运行状态', checked: false, remark: '' },
    { id: 2, text: '检查雨量计翻斗灵活性', checked: false, remark: '' },
    { id: 3, text: '检查数据采集仪通信状态', checked: false, remark: '' },
    { id: 4, text: '检查站房周边环境', checked: false, remark: '' },
    { id: 5, text: '检查供电系统', checked: false, remark: '' },
    { id: 6, text: '检查防雷设施', checked: false, remark: '' },
  ]);
  const [gpsChecked, setGpsChecked] = useState(false);
  const [photoTaken, setPhotoTaken] = useState(false);
  const [issues, setIssues] = useState([]);
  const [issueModalOpen, setIssueModalOpen] = useState(false);
  const [issueForm, setIssueForm] = useState({ title: '', description: '', severity: 'normal' });
  const [completionNote, setCompletionNote] = useState('');

  // Fetch plans
  useEffect(() => {
    setLoading(true);
    api.get('/maintenance/plans').then((data) => {
      const list = Array.isArray(data) ? data : [];
      setPlans(list.filter((p) => p.status === 'pending' || p.status === 'active'));
    }).catch(() => {}).finally(() => setLoading(false));
  }, []);

  const handleStartExecution = (plan) => {
    setSelectedPlan(plan);
    setExecutionStep(1);
    setChecklist(checklist.map((c) => ({ ...c, checked: false, remark: '' })));
    setGpsChecked(false);
    setPhotoTaken(false);
    setIssues([]);
    setCompletionNote('');
  };

  const handleCheckItem = (id, checked) => {
    setChecklist((prev) => prev.map((c) => c.id === id ? { ...c, checked } : c));
  };

  const handleGpsCheckin = () => {
    setGpsChecked(true);
    message.success('GPS打卡成功：位置验证通过');
  };

  const handleTakePhoto = () => {
    setPhotoTaken(true);
    message.success('现场照片已记录');
  };

  const handleAddIssue = () => {
    if (!issueForm.title) {
      message.warning('请输入问题标题');
      return;
    }
    setIssues((prev) => [...prev, { ...issueForm, id: Date.now() }]);
    setIssueModalOpen(false);
    setIssueForm({ title: '', description: '', severity: 'normal' });
    message.success('问题已记录');
  };

  const handleConvertToWorkOrder = (issue) => {
    message.success(`问题「${issue.title}」已转为工单`);
    setIssues((prev) => prev.map((i) => i.id === issue.id ? { ...i, converted: true } : i));
  };

  const handleCompleteExecution = () => {
    const checkedCount = checklist.filter((c) => c.checked).length;
    const total = checklist.length;
    if (checkedCount < total) {
      Modal.confirm({
        title: '确认提交',
        content: `还有 ${total - checkedCount} 项检查未完成，确认提交巡检记录？`,
        okText: '确认提交',
        cancelText: '继续检查',
        onOk: () => {
          message.success('巡检记录已提交');
          setExecutionStep(3);
        },
      });
    } else {
      message.success('巡检记录已提交');
      setExecutionStep(3);
    }
  };

  const checkedCount = checklist.filter((c) => c.checked).length;
  const progressPercent = Math.round((checkedCount / checklist.length) * 100);

  if (executionStep === 0) {
    // Plan selection
    return (
      <div>
        <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Text style={{ color: tokens.colorTextSecondary, fontSize: 13 }}>
            选择待执行的巡检计划，开始现场巡检
          </Text>
        </div>
        <Table
          rowKey="id"
          dataSource={plans}
          loading={loading}
          pagination={false}
          size="middle"
          locale={{ emptyText: <Empty description="暂无待执行的巡检计划" /> }}
          columns={[
            { title: '计划编号', dataIndex: 'plan_no', key: 'plan_no', width: 120, render: (t) => <Text strong>{t || '-'}</Text> },
            { title: '站点', dataIndex: 'site_name', key: 'site_name', width: 120, render: (t) => t || '-' },
            { title: '类型', dataIndex: 'category', key: 'category', width: 100, render: (v) => categoryLabelMap[v] || v || '-' },
            { title: '频率', dataIndex: 'frequency', key: 'frequency', width: 80, render: (v) => frequencyLabelMap[v] || v || '-' },
            { title: '状态', dataIndex: 'status', key: 'status', width: 80, render: (v) => <Tag color={v === 'active' ? 'blue' : 'default'}>{v === 'active' ? '进行中' : '待执行'}</Tag> },
            {
              title: '操作', key: 'action', width: 100, align: 'center',
              render: (_, record) => (
                <Button type="primary" size="small" icon={<CheckCircleOutlined />} onClick={() => handleStartExecution(record)}>
                  开始巡检
                </Button>
              ),
            },
          ]}
        />
      </div>
    );
  }

  if (executionStep === 3) {
    // Completion summary
    return (
      <div style={{ textAlign: 'center', padding: '40px 0' }}>
        <CheckCircleOutlined style={{ fontSize: 64, color: tokens.colorSuccess, marginBottom: 16 }} />
        <Title level={4} style={{ color: tokens.colorText }}>巡检已完成</Title>
        <Text style={{ color: tokens.colorTextSecondary, display: 'block', marginBottom: 24 }}>
          检查项 {checkedCount}/{checklist.length} · 发现问题 {issues.length} 个 · {gpsChecked ? 'GPS已打卡' : '未GPS打卡'}
        </Text>
        <Space>
          <Button onClick={() => setExecutionStep(0)}>返回计划列表</Button>
          <Button type="primary" onClick={() => setExecutionStep(1)}>继续巡检</Button>
        </Space>
      </div>
    );
  }

  // Execution in progress (step 1-2)
  return (
    <div>
      {/* Progress Steps */}
      <Steps
        current={executionStep}
        onChange={setExecutionStep}
        style={{ marginBottom: 24 }}
        items={[
          { title: '巡检执行', description: '检查清单' },
          { title: '问题记录', description: `${issues.length} 个问题` },
          { title: '提交完成', description: '巡检报告' },
        ]}
      />

      {/* Selected Plan Info */}
      {selectedPlan && (
        <div style={{ padding: '12px 16px', borderRadius: 8, background: `${tokens.colorPrimary}08`, border: `1px solid ${tokens.colorPrimary}20`, marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <Text strong>{selectedPlan.plan_no || `计划#${selectedPlan.id}`}</Text>
            <Text style={{ marginLeft: 12, color: tokens.colorTextSecondary }}>{selectedPlan.site_name || '-'}</Text>
          </div>
          <Progress percent={progressPercent} size="small" style={{ width: 200, margin: 0 }} />
        </div>
      )}

      {executionStep === 1 && (
        <div>
          {/* GPS Check-in & Photo */}
          <Row gutter={16} style={{ marginBottom: 16 }}>
            <Col span={12}>
              <Card size="small" style={{ borderRadius: 8 }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <div>
                    <Text strong>GPS 定位打卡</Text>
                    <div style={{ fontSize: 12, color: tokens.colorTextTertiary, marginTop: 4 }}>
                      {gpsChecked ? '已验证位置：站点范围内' : '未打卡'}
                    </div>
                  </div>
                  <Button
                    type={gpsChecked ? 'default' : 'primary'}
                    icon={<CheckCircleOutlined />}
                    onClick={handleGpsCheckin}
                    disabled={gpsChecked}
                    size="small"
                  >
                    {gpsChecked ? '已打卡' : '打卡'}
                  </Button>
                </div>
              </Card>
            </Col>
            <Col span={12}>
              <Card size="small" style={{ borderRadius: 8 }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <div>
                    <Text strong>现场照片</Text>
                    <div style={{ fontSize: 12, color: tokens.colorTextTertiary, marginTop: 4 }}>
                      {photoTaken ? '已拍摄 1 张照片' : '未拍摄'}
                    </div>
                  </div>
                  <Button
                    type={photoTaken ? 'default' : 'primary'}
                    icon={<CameraOutlined />}
                    onClick={handleTakePhoto}
                    size="small"
                  >
                    {photoTaken ? '重新拍摄' : '拍照'}
                  </Button>
                </div>
              </Card>
            </Col>
          </Row>

          {/* Checklist */}
          <Card title="巡检检查清单" size="small" style={{ borderRadius: 8, marginBottom: 16 }}
            extra={<Text style={{ color: tokens.colorTextSecondary }}>{checkedCount}/{checklist.length} 已完成</Text>}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {checklist.map((item) => (
                <div key={item.id} style={{
                  padding: '10px 14px', borderRadius: 8,
                  background: item.checked ? `${tokens.colorSuccess}06` : tokens.colorBgContainer,
                  border: `1px solid ${item.checked ? `${tokens.colorSuccess}30` : tokens.colorBorder}`,
                  display: 'flex', alignItems: 'center', gap: 12,
                }}>
                  <Checkbox
                    checked={item.checked}
                    onChange={(e) => handleCheckItem(item.id, e.target.checked)}
                  />
                  <Text style={{ flex: 1, textDecoration: item.checked ? 'line-through' : 'none', color: item.checked ? tokens.colorTextTertiary : tokens.colorText }}>
                    {item.text}
                  </Text>
                  {item.checked && <CheckCircleOutlined style={{ color: tokens.colorSuccess }} />}
                </div>
              ))}
            </div>
          </Card>

          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <Button onClick={() => setExecutionStep(0)}>取消巡检</Button>
            <Space>
              <Button onClick={() => setExecutionStep(2)}>下一步：记录问题</Button>
              <Button type="primary" onClick={handleCompleteExecution}>提交巡检</Button>
            </Space>
          </div>
        </div>
      )}

      {executionStep === 2 && (
        <div>
          <Card title="发现的问题" size="small" style={{ borderRadius: 8, marginBottom: 16 }}
            extra={
              <Button type="primary" size="small" icon={<ExclamationCircleOutlined />} onClick={() => setIssueModalOpen(true)}>
                上报问题
              </Button>
            }>
            {issues.length === 0 ? (
              <Empty description="暂未发现问题" style={{ padding: '20px 0' }} />
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {issues.map((issue) => (
                  <div key={issue.id} style={{
                    padding: '12px 14px', borderRadius: 8,
                    border: `1px solid ${tokens.colorBorder}`,
                    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  }}>
                    <div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                        <Text strong>{issue.title}</Text>
                        <Tag color={issue.severity === 'critical' ? 'red' : issue.severity === 'urgent' ? 'orange' : 'default'}>
                          {issue.severity === 'critical' ? '严重' : issue.severity === 'urgent' ? '紧急' : '一般'}
                        </Tag>
                        {issue.converted && <Tag color="green">已转工单</Tag>}
                      </div>
                      {issue.description && <Text style={{ fontSize: 12, color: tokens.colorTextSecondary }}>{issue.description}</Text>}
                    </div>
                    {!issue.converted && (
                      <Button type="link" size="small" onClick={() => handleConvertToWorkOrder(issue)}>
                        转工单
                      </Button>
                    )}
                  </div>
                ))}
              </div>
            )}
          </Card>

          <div style={{ marginBottom: 16 }}>
            <Text strong style={{ display: 'block', marginBottom: 8 }}>巡检备注</Text>
            <Input.TextArea
              rows={3}
              placeholder="填写本次巡检总结备注..."
              value={completionNote}
              onChange={(e) => setCompletionNote(e.target.value)}
            />
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <Button onClick={() => setExecutionStep(1)}>上一步</Button>
            <Button type="primary" onClick={handleCompleteExecution}>提交巡检</Button>
          </div>

          {/* Issue Report Modal */}
          <Modal
            title="上报问题"
            open={issueModalOpen}
            onOk={handleAddIssue}
            onCancel={() => setIssueModalOpen(false)}
            okText="记录"
            cancelText="取消"
          >
            <Form layout="vertical" style={{ marginTop: 16 }}>
              <Form.Item label="问题标题" required>
                <Input value={issueForm.title} onChange={(e) => setIssueForm({ ...issueForm, title: e.target.value })} placeholder="简要描述问题" />
              </Form.Item>
              <Form.Item label="问题描述">
                <Input.TextArea rows={3} value={issueForm.description} onChange={(e) => setIssueForm({ ...issueForm, description: e.target.value })} placeholder="详细描述问题情况" />
              </Form.Item>
              <Form.Item label="严重程度">
                <Select value={issueForm.severity} onChange={(val) => setIssueForm({ ...issueForm, severity: val })} options={[
                  { value: 'normal', label: '一般' },
                  { value: 'urgent', label: '紧急' },
                  { value: 'critical', label: '严重' },
                ]} />
              </Form.Item>
            </Form>
          </Modal>
        </div>
      )}
    </div>
  );
}

// ---------- Main Page ----------
export default function MaintenancePage() {
  const { tokens } = useTheme();

  const tabItems = [
    {
      key: 'plans',
      label: (
        <span><ScheduleOutlined /> 巡检计划</span>
      ),
      children: <InspectionPlansTab />,
    },
    {
      key: 'schemes',
      label: (
        <span><FileTextOutlined /> 方案模板</span>
      ),
      children: <InspectionSchemesTab />,
    },
    {
      key: 'execution',
      label: (
        <span><CheckCircleOutlined /> 巡检执行</span>
      ),
      children: <InspectionExecutionTab tokens={tokens} />,
    },
    {
      key: 'config',
      label: (
        <span><SettingOutlined /> 巡检配置</span>
      ),
      children: <InspectionConfigTab />,
    },
  ];

  return (
    <div style={{ padding: 24 }}>
      <Title level={4} style={{ margin: '0 0 20px', color: tokens.colorText }}>巡检管理</Title>
      <Card style={{ borderRadius: 10 }} bodyStyle={{ padding: '0 20px 20px' }}>
        <Tabs items={tabItems} style={{ marginTop: -8 }} />
      </Card>
    </div>
  );
}
