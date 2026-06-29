import { useState, useEffect, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  Table, Card, Input, Select, Button, Space, Tag, Tabs,
  Typography, message, Spin, Empty, Badge, Modal, Form,
  Statistic, Row, Col, Descriptions, Drawer,
} from 'antd';
import {
  SearchOutlined, ReloadOutlined, PlusOutlined, EyeOutlined,
  EditOutlined, DeleteOutlined, ToolOutlined, DatabaseOutlined,
  InboxOutlined, SwapOutlined, ExclamationCircleOutlined,
  CheckCircleOutlined, WarningOutlined, StopOutlined,
  ArrowUpOutlined, ArrowDownOutlined,
} from '@ant-design/icons';
import { api } from '../../services/api';
import { useTheme } from '../../hooks/useTheme';
import { useAuth } from '../../hooks/useAuth';
import { deviceTypeMap } from '../../services/constants';

const { Title, Text } = Typography;

// ---------- Simulated device model & manufacturer data ----------
const deviceModelMap = {
  rainfall_gauge: 'RG-50',
  electronic_rainfall: 'ERR-100',
  radar_water_level: 'VL-30',
  pressure_water_level: 'PWL-200',
  flow_meter: 'FM-80',
  hydro_collector: 'HC-600',
  current_meter: 'LS25-3A',
  rainfall_meter: 'SL3-1',
  water_level_meter: 'UHZ-40',
  soil_moisture_sensor: 'TDR-100',
  soil_temperature: 'GTS-8',
  evaporation_pan: 'E601B',
  weather_screen: 'PHZ-2',
  anemometer: 'WA-200',
};

const deviceMfrMap = {
  rainfall_gauge: { name: '南京水文仪器有限公司', tel: '025-84312567' },
  electronic_rainfall: { name: '武汉长江水文科技有限公司', tel: '027-86771234' },
  radar_water_level: { name: '成都测测科技有限公司', tel: '028-85193456' },
  pressure_water_level: { name: '南京水文仪器有限公司', tel: '025-84312567' },
  flow_meter: { name: '杭州水文智能设备有限公司', tel: '0571-88256789' },
  hydro_collector: { name: '北京华水科技有限公司', tel: '010-62351234' },
  current_meter: { name: '重庆水文仪器厂', tel: '023-65120123' },
  rainfall_meter: { name: '武汉长江水文科技有限公司', tel: '027-86771234' },
  water_level_meter: { name: '南京水文仪器有限公司', tel: '025-84312567' },
  soil_moisture_sensor: { name: '托普云农科技股份有限公司', tel: '0571-86823567' },
  soil_temperature: { name: '托普云农科技股份有限公司', tel: '0571-86823567' },
  evaporation_pan: { name: '重庆水文仪器厂', tel: '023-65120123' },
  weather_screen: { name: '杭州水文智能设备有限公司', tel: '0571-88256789' },
  anemometer: { name: '北京华水科技有限公司', tel: '010-62351234' },
};

// ---------- Simulated spare parts spec & manufacturer data ----------
const spareSpecMap = {
  '翻斗雨量计核心组件': 'RG-50-CORE',
  '雷达水位计探头': 'VL-30-PROBE',
  '压力传感器': 'PS-200A',
  '流速仪转子': 'LS25-ROTOR',
  '数据采集模块': 'DAQ-600',
  '太阳能板': 'SP-50W',
  '蓄电池': 'BAT-12V38AH',
  '通信模块': '4G-DTU-100',
  '防雷器': 'SPD-24V',
  '电缆接头': 'M12-IP68',
  '密封圈': 'OR-80',
  '电池盒': 'BK-12A',
  '雨量传感器': 'SL3-SENSOR',
  '土壤水分探头': 'TDR-100-P',
  '百叶箱配件': 'PHZ-KIT',
};

// 实际备件名称→规格型号映射（匹配数据库中的备件名称）
const partSpecMap = {
  '数据采集终端RTU': 'RTU-600',
  '风速风向仪': 'WA-200',
  '不锈钢水位计支架': 'SS-WL-BRACKET',
  '太阳能板(20W)': 'SP-20W',
  'GPRS通信模块': '4G-DTU-100',
  '温湿度传感器': 'TH-100',
  '蓄电池(12V)': 'BAT-12V38AH',
  '雨量筒翻斗': 'SL3-BUCKET',
  '防雷模块': 'SPD-24V',
  '信号电缆(10m)': 'CABLE-10M',
  '水位计传感器': 'PWL-200A',
  '水位计密封圈': 'OR-80',
};

// 实际备件名称→适用设备类型映射
const partDeviceMap = {
  '数据采集终端RTU': ['hydro_collector'],
  '风速风向仪': ['anemometer', 'weather_screen'],
  '不锈钢水位计支架': ['water_level_meter', 'radar_water_level'],
  '太阳能板(20W)': ['hydro_collector', 'rainfall_gauge'],
  'GPRS通信模块': ['hydro_collector'],
  '温湿度传感器': ['weather_screen'],
  '蓄电池(12V)': ['hydro_collector', 'rainfall_gauge', 'water_level_meter'],
  '雨量筒翻斗': ['rainfall_meter', 'rainfall_gauge'],
  '防雷模块': ['hydro_collector', 'rainfall_gauge', 'water_level_meter'],
  '信号电缆(10m)': ['hydro_collector', 'water_level_meter', 'rainfall_gauge'],
  '水位计传感器': ['water_level_meter', 'pressure_water_level'],
  '水位计密封圈': ['water_level_meter', 'pressure_water_level'],
};

// 实际备件名称→存放位置映射
const partLocationMap = {
  '数据采集终端RTU': 'A区-柜1-层2',
  '风速风向仪': 'B区-柜3-层1',
  '不锈钢水位计支架': 'C区-架2-层1',
  '太阳能板(20W)': 'D区-架1-层3',
  'GPRS通信模块': 'A区-柜2-层1',
  '温湿度传感器': 'B区-柜1-层2',
  '蓄电池(12V)': 'D区-架2-层1',
  '雨量筒翻斗': 'C区-柜1-层1',
  '防雷模块': 'A区-柜3-层3',
  '信号电缆(10m)': 'D区-架3-层2',
  '水位计传感器': 'B区-柜2-层1',
  '水位计密封圈': 'C区-柜2-层2',
};

const spareMfrMap = {
  '翻斗雨量计核心组件': { name: '南京水文仪器有限公司', tel: '025-84312567' },
  '雷达水位计探头': { name: '成都测测科技有限公司', tel: '028-85193456' },
  '压力传感器': { name: '南京水文仪器有限公司', tel: '025-84312567' },
  '流速仪转子': { name: '重庆水文仪器厂', tel: '023-65120123' },
  '数据采集模块': { name: '北京华水科技有限公司', tel: '010-62351234' },
  '太阳能板': { name: '杭州水文智能设备有限公司', tel: '0571-88256789' },
  '蓄电池': { name: '杭州水文智能设备有限公司', tel: '0571-88256789' },
  '通信模块': { name: '武汉长江水文科技有限公司', tel: '027-86771234' },
  '防雷器': { name: '北京华水科技有限公司', tel: '010-62351234' },
  '电缆接头': { name: '南京水文仪器有限公司', tel: '025-84312567' },
  '密封圈': { name: '重庆水文仪器厂', tel: '023-65120123' },
  '电池盒': { name: '杭州水文智能设备有限公司', tel: '0571-88256789' },
  '雨量传感器': { name: '武汉长江水文科技有限公司', tel: '027-86771234' },
  '土壤水分探头': { name: '托普云农科技股份有限公司', tel: '0571-86823567' },
  '百叶箱配件': { name: '杭州水文智能设备有限公司', tel: '0571-88256789' },
};

// ---------- Device Ledger Tab ----------
function DeviceLedgerTab() {
  const { tokens } = useTheme();
  const [searchParams] = useSearchParams();
  const [devices, setDevices] = useState([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState('');
  const [typeFilter, setTypeFilter] = useState(undefined);
  const [statusFilter, setStatusFilter] = useState(searchParams.get('status') || undefined);

  // View / Create / Edit state
  const [viewOpen, setViewOpen] = useState(false);
  const [viewingDevice, setViewingDevice] = useState(null);
  const [viewLoading, setViewLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingDevice, setEditingDevice] = useState(null);
  const [modalLoading, setModalLoading] = useState(false);
  const [sites, setSites] = useState([]);
  const [form] = Form.useForm();

  const fetchDevices = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (search) params.set('search', search);
      if (typeFilter) params.set('type', typeFilter);
      if (statusFilter) params.set('status', statusFilter);
      const data = await api.get(`/devices?${params.toString()}`);
      setDevices(Array.isArray(data) ? data : (data?.devices || []));
    } catch {
      message.error('加载设备列表失败');
      setDevices([]);
    } finally {
      setLoading(false);
    }
  }, [search, typeFilter, statusFilter]);

  useEffect(() => { fetchDevices(); }, [fetchDevices]);

  // Sync status filter from URL params (for cockpit drill-down)
  useEffect(() => {
    const urlStatus = searchParams.get('status') || undefined;
    setStatusFilter(urlStatus);
  }, [searchParams]);

  // Fetch sites for form dropdown
  useEffect(() => {
    api.get('/sites').then(data => {
      const list = Array.isArray(data) ? data : (data?.sites || []);
      setSites(list);
    }).catch(() => {});
  }, []);

  const handleReset = () => {
    setSearch('');
    setTypeFilter(undefined);
    setStatusFilter(undefined);
  };

  // ---- View detail ----
  const handleView = useCallback(async (record) => {
    setViewingDevice(record);
    setViewOpen(true);
    setViewLoading(true);
    try {
      const data = await api.get(`/devices/${record.id}`);
      if (data && data.device) {
        setViewingDevice(data.device);
        setViewingDevice(prev => ({ ...data.device, _logs: data.logs || [] }));
      }
    } catch { /* ignore, use basic info */ }
    setViewLoading(false);
  }, []);

  // ---- Create ----
  const handleCreate = useCallback(() => {
    setEditingDevice(null);
    form.resetFields();
    form.setFieldsValue({ status: 'online' });
    setModalOpen(true);
  }, [form]);

  // ---- Edit (relocation only) ----
  const handleEdit = useCallback((record) => {
    setEditingDevice(record);
    form.setFieldsValue({
      device_code: record.device_code,
      device_name: record.device_name,
      device_type: record.device_type,
      site_id: record.site_id,
    });
    setModalOpen(true);
  }, [form]);

  // ---- Modal submit ----
  const handleModalOk = useCallback(async () => {
    try {
      const values = await form.validateFields();
      setModalLoading(true);
      if (editingDevice) {
        // Only submit site_id for relocation
        const result = await api.put(`/devices/${editingDevice.id}`, { site_id: values.site_id });
        if (result && !result.error) {
          message.success('设备移站成功');
          setModalOpen(false);
          fetchDevices();
        } else {
          message.error(result?.error || '移站失败');
        }
      } else {
        const result = await api.post('/devices', values);
        if (result && !result.error) {
          message.success('设备注册成功');
          setModalOpen(false);
          fetchDevices();
        } else {
          message.error(result?.error || '注册失败');
        }
      }
    } catch { /* validation error */ }
    setModalLoading(false);
  }, [form, editingDevice, fetchDevices]);

  const statusConfig = {
    online: { color: 'success', icon: <CheckCircleOutlined />, label: '在线' },
    offline: { color: 'error', icon: <StopOutlined />, label: '离线' },
    warning: { color: 'warning', icon: <WarningOutlined />, label: '告警' },
    maintenance: { color: 'processing', icon: <ToolOutlined />, label: '维护中' },
    scrapped: { color: 'error', icon: <DeleteOutlined />, label: '已报废' },
  };

  const columns = [
    {
      title: '设备编码',
      dataIndex: 'code',
      key: 'code',
      width: 130,
      fixed: 'left',
      render: (text, record) => (
        <Text strong style={{ color: tokens.colorPrimary }}>{text || record.device_code || `#${record.id}`}</Text>
      ),
    },
    {
      title: '设备名称',
      dataIndex: 'device_name',
      key: 'device_name',
      width: 160,
      ellipsis: true,
    },
    {
      title: '所属站点',
      dataIndex: 'site_name',
      key: 'site_name',
      width: 150,
      ellipsis: true,
      render: (text) => text || '-',
    },
    {
      title: '设备型号',
      dataIndex: 'device_model',
      key: 'device_model',
      width: 120,
      ellipsis: true,
      render: (val, record) => {
        const model = val || deviceModelMap[record.device_type] || '';
        return <Text style={{ fontSize: 13 }}>{model || '-'}</Text>;
      },
    },
    {
      title: '厂商',
      dataIndex: 'manufacturer',
      key: 'manufacturer',
      width: 150,
      ellipsis: true,
      render: (val, record) => {
        const mfrObj = deviceMfrMap[record.device_type];
        const mfr = val || (mfrObj ? mfrObj.name : '') || '';
        return <Text style={{ fontSize: 13 }}>{mfr || '-'}</Text>;
      },
    },
    {
      title: '安装日期',
      dataIndex: 'install_date',
      key: 'install_date',
      width: 110,
      render: (val) => <Text style={{ fontSize: 13 }}>{val || '-'}</Text>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (val) => {
        const cfg = statusConfig[val] || { color: 'default', label: val || '-' };
        return <Badge status={cfg.color} text={cfg.label} />;
      },
    },
    {
      title: '电压(V)',
      dataIndex: 'voltage',
      key: 'voltage',
      width: 90,
      align: 'center',
      render: (val) => {
        if (val == null) return '-';
        const isLow = val < 11.5;
        return <Text strong style={{ color: isLow ? tokens.colorError : tokens.colorText, fontSize: 13 }}>{val}</Text>;
      },
    },
    {
      title: '最后数据',
      dataIndex: 'last_data_time',
      key: 'last_data_time',
      width: 160,
      render: (text) => text ? (
        <Text style={{ color: tokens.colorTextSecondary, fontSize: 13 }}>{text}</Text>
      ) : '-',
    },
    {
      title: '操作',
      key: 'actions',
      width: 140,
      fixed: 'right',
      render: (_, record) => (
        <Space size={4}>
          <Button type="link" size="small" icon={<EyeOutlined />} onClick={() => handleView(record)}>
            详情
          </Button>
          <Button type="link" size="small" icon={<EditOutlined />} onClick={() => handleEdit(record)}>
            编辑
          </Button>
          <Button type="link" size="small" danger icon={<DeleteOutlined />}
            onClick={() => {
              Modal.confirm({
                title: '确认删除',
                icon: <ExclamationCircleOutlined />,
                content: `确认删除设备 ${record.device_name || record.device_code}？`,
                okText: '删除',
                okType: 'danger',
                cancelText: '取消',
                onOk: async () => {
                  const result = await api.delete(`/devices/${record.id}`);
                  if (result && !result.error) {
                    message.success('设备已删除');
                    fetchDevices();
                  } else {
                    message.error('删除失败');
                  }
                },
              });
            }}>
            删除
          </Button>
        </Space>
      ),
    },
  ];

  const typeOptions = Object.entries(deviceTypeMap).map(([value, label]) => ({ value, label }));
  const statusOptions = Object.entries(statusConfig).map(([value, cfg]) => ({ value, label: cfg.label }));
  const siteOptions = sites.map(s => ({ value: s.id, label: s.name || s.code }));
  const logs = viewingDevice?._logs || [];

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
        <Space wrap size={12}>
          <Input
            placeholder="搜索设备编码、名称..."
            prefix={<SearchOutlined style={{ color: tokens.colorTextTertiary }} />}
            allowClear
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{ width: 250, borderRadius: 8 }}
          />
          <Select placeholder="设备类型" allowClear value={typeFilter} onChange={setTypeFilter}
            style={{ width: 160 }} options={typeOptions} showSearch
            filterOption={(input, option) => option.label.toLowerCase().includes(input.toLowerCase())} />
          <Select placeholder="状态" allowClear value={statusFilter} onChange={setStatusFilter}
            style={{ width: 120 }} options={statusOptions} />
          <Button icon={<ReloadOutlined />} onClick={handleReset}>重置</Button>
        </Space>
        <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}
          style={{ background: `linear-gradient(135deg, ${tokens.colorPrimary}, ${tokens.colorPrimaryHover})`, border: 'none' }}>
          注册设备
        </Button>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 280px)', minHeight: 400 }}>
        <style>{`.hide-scrollbar::-webkit-scrollbar{display:none}.hide-scrollbar{-ms-overflow-style:none;scrollbar-width:none}`}</style>
        <div className="hide-scrollbar" style={{ flex: 1, overflow: 'auto' }}>
          <Table
            columns={columns}
            dataSource={devices}
            rowKey={(r) => r.id || r.code || r.device_code}
            loading={loading}
            pagination={false}
            locale={{ emptyText: <Empty description="暂无设备数据" /> }}
            size="middle"
          />
        </div>
      </div>

      {/* ===== View Drawer ===== */}
      <Drawer
        title="设备详情"
        open={viewOpen}
        onClose={() => { setViewOpen(false); setViewingDevice(null); }}
        width={520}
        destroyOnClose
      >
        {viewLoading ? (
          <div style={{ textAlign: 'center', padding: 60 }}><Spin /></div>
        ) : viewingDevice ? (
          <div>
            <Descriptions column={1} bordered size="small" labelStyle={{ width: 100 }}>
              <Descriptions.Item label="设备编码">{viewingDevice.device_code || viewingDevice.code || '-'}</Descriptions.Item>
              <Descriptions.Item label="设备名称">{viewingDevice.device_name || '-'}</Descriptions.Item>
              <Descriptions.Item label="设备类型">{deviceTypeMap[viewingDevice.device_type] || viewingDevice.device_type || '-'}</Descriptions.Item>
              <Descriptions.Item label="设备型号">{viewingDevice.device_model || deviceModelMap[viewingDevice.device_type] || '-'}</Descriptions.Item>
              <Descriptions.Item label="生产厂家">{viewingDevice.manufacturer || deviceMfrMap[viewingDevice.device_type]?.name || '-'}</Descriptions.Item>
              <Descriptions.Item label="安装日期">{viewingDevice.install_date || '-'}</Descriptions.Item>
              <Descriptions.Item label="所属站点">{viewingDevice.site_name || '-'}</Descriptions.Item>
              <Descriptions.Item label="状态">
                {(() => {
                  const cfg = statusConfig[viewingDevice.status] || { color: 'default', label: viewingDevice.status || '-' };
                  return <Badge status={cfg.color} text={cfg.label} />;
                })()}
              </Descriptions.Item>
              <Descriptions.Item label="电压(V)">
                {viewingDevice.voltage != null ? (
                  <Text strong style={{ color: viewingDevice.voltage < 11.5 ? tokens.colorError : tokens.colorText }}>
                    {viewingDevice.voltage}
                  </Text>
                ) : '-'}
              </Descriptions.Item>
              <Descriptions.Item label="电池(%)">{viewingDevice.battery != null ? `${viewingDevice.battery}%` : '-'}</Descriptions.Item>
              <Descriptions.Item label="最后数据时间">{viewingDevice.last_data_time || '-'}</Descriptions.Item>
              {viewingDevice.district && <Descriptions.Item label="所属区域">{viewingDevice.district}</Descriptions.Item>}
              {viewingDevice.manager && <Descriptions.Item label="负责人">{viewingDevice.manager}</Descriptions.Item>}
            </Descriptions>

            <Title level={5} style={{ marginTop: 24, marginBottom: 12 }}>维护记录</Title>
            {logs.length > 0 ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {logs.map((log, i) => (
                  <div key={log.id || i} style={{ padding: '8px 12px', borderRadius: 8, background: tokens.colorBgTextHover, fontSize: 13 }}>
                    <div style={{ fontWeight: 500 }}>{log.action || log.description || '操作记录'}</div>
                    <div style={{ color: tokens.colorTextSecondary, marginTop: 2 }}>
                      {log.created_at || log.timestamp || ''}
                      {log.operator ? ` · ${log.operator}` : ''}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <Empty description="暂无维护记录" style={{ margin: '16px 0' }} />
            )}
          </div>
        ) : null}
      </Drawer>

      {/* ===== Create / Edit Modal ===== */}
      <Modal
        title={editingDevice ? '设备移站' : '注册设备'}
        open={modalOpen}
        onOk={handleModalOk}
        onCancel={() => { setModalOpen(false); setEditingDevice(null); form.resetFields(); }}
        confirmLoading={modalLoading}
        okText={editingDevice ? '确认移站' : '注册'}
        cancelText="取消"
        destroyOnClose
      >
        {editingDevice && (
          <div style={{ marginBottom: 16, padding: '10px 14px', borderRadius: 8, background: 'rgba(24,144,255,0.06)', border: '1px solid rgba(24,144,255,0.15)' }}>
            <Text style={{ fontSize: 13, color: tokens.colorTextSecondary }}>
              设备基础信息不可直接修改。如需变更设备类型、名称等，请通过设备回收后重新注册。
            </Text>
          </div>
        )}
        <Form form={form} layout="vertical" style={{ marginTop: editingDevice ? 0 : 16 }}>
          <Form.Item name="device_code" label="设备编码" rules={[{ required: true, message: '请输入设备编码' }]}>
            <Input placeholder="如: 62313350-01HYDR" disabled={!!editingDevice} />
          </Form.Item>
          <Form.Item name="device_name" label="设备名称" rules={[{ required: true, message: '请输入设备名称' }]}>
            <Input placeholder="请输入设备名称" disabled={!!editingDevice} />
          </Form.Item>
          <Form.Item name="device_type" label="设备类型" rules={[{ required: true, message: '请选择设备类型' }]}>
            <Select placeholder="请选择设备类型" options={typeOptions} showSearch disabled={!!editingDevice}
              filterOption={(input, option) => option.label.toLowerCase().includes(input.toLowerCase())} />
          </Form.Item>
          <Form.Item name="site_id" label="所属站点" rules={[{ required: true, message: '请选择所属站点' }]}
            tooltip={editingDevice ? '可调整设备所属站点' : undefined}>
            <Select placeholder="请选择站点" options={siteOptions} showSearch
              filterOption={(input, option) => option.label.toLowerCase().includes(input.toLowerCase())} />
          </Form.Item>
          {editingDevice ? (
            <div style={{ padding: '8px 0' }}>
              <Text style={{ fontSize: 12, color: tokens.colorTextTertiary }}>
                状态、电压、电池由设备自动上报，不可手动修改
              </Text>
            </div>
          ) : (
            <>
              <Form.Item name="status" label="状态">
                <Select placeholder="请选择状态" options={statusOptions} />
              </Form.Item>
              <Row gutter={16}>
                <Col span={12}>
                  <Form.Item name="voltage" label="电压(V)">
                    <Input type="number" step="0.1" placeholder="12.0" />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item name="battery" label="电池(%)">
                    <Input type="number" step="1" placeholder="85" />
                  </Form.Item>
                </Col>
              </Row>
            </>
          )}
        </Form>
      </Modal>
    </div>
  );
}

// ---------- Spare Parts Inventory Tab ----------
function SparePartsTab() {
  const { tokens } = useTheme();
  const [parts, setParts] = useState([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState('');

  // View / Create / Edit state
  const [viewOpen, setViewOpen] = useState(false);
  const [viewingPart, setViewingPart] = useState(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingPart, setEditingPart] = useState(null);
  const [modalLoading, setModalLoading] = useState(false);
  const [sites, setSites] = useState([]);
  const [form] = Form.useForm();

  // In/Out stock modal state
  const [stockModalOpen, setStockModalOpen] = useState(false);
  const [stockType, setStockType] = useState('in'); // 'in' or 'out'
  const [stockPart, setStockPart] = useState(null);
  const [stockLoading, setStockLoading] = useState(false);
  const [stockForm] = Form.useForm();

  const fetchParts = useCallback(async () => {
    setLoading(true);
    try {
      const params = search ? `?search=${encodeURIComponent(search)}` : '';
      const data = await api.get(`/parts/inventory${params}`);
      setParts(Array.isArray(data) ? data : (data?.parts || []));
    } catch {
      message.error('加载备件数据失败');
      setParts([]);
    } finally {
      setLoading(false);
    }
  }, [search]);

  useEffect(() => { fetchParts(); }, [fetchParts]);

  useEffect(() => {
    api.get('/sites').then(data => {
      const list = Array.isArray(data) ? data : (data?.sites || []);
      setSites(list);
    }).catch(() => {});
  }, []);

  const handleView = useCallback(async (record) => {
    setViewingPart(record);
    setViewOpen(true);
    // Fetch inventory logs for this part
    try {
      const logs = await api.get(`/parts/inventory/${record.id}/logs`);
      setViewingPart(prev => ({ ...prev, _logs: Array.isArray(logs) ? logs : [] }));
    } catch {
      setViewingPart(prev => ({ ...prev, _logs: [] }));
    }
  }, []);

  const handleCreate = useCallback(() => {
    setEditingPart(null);
    form.resetFields();
    form.setFieldsValue({ quantity: 0, min_quantity: 5, unit: '个' });
    setModalOpen(true);
  }, [form]);

  // Edit only basic info (no quantity, no location)
  const handleEdit = useCallback((record) => {
    setEditingPart(record);
    form.setFieldsValue({
      part_code: record.part_code,
      part_name: record.part_name,
      category: record.category,
      unit: record.unit,
      min_quantity: record.min_quantity,
      remark: record.remark,
    });
    setModalOpen(true);
  }, [form]);

  const handleModalOk = useCallback(async () => {
    try {
      const values = await form.validateFields();
      setModalLoading(true);
      if (editingPart) {
        // Only submit editable fields
        const result = await api.put(`/parts/inventory/${editingPart.id}`, {
          part_name: values.part_name,
          category: values.category,
          unit: values.unit,
          min_quantity: values.min_quantity,
          remark: values.remark,
        });
        if (result && !result.error) {
          message.success('备件信息已更新');
          setModalOpen(false);
          fetchParts();
        } else {
          message.error(result?.error || '更新失败');
        }
      } else {
        const result = await api.post('/parts/inventory', values);
        if (result && !result.error) {
          message.success('备件新增成功');
          setModalOpen(false);
          fetchParts();
        } else {
          message.error(result?.error || '新增失败');
        }
      }
    } catch { /* validation error */ }
    setModalLoading(false);
  }, [form, editingPart, fetchParts]);

  // In/Out stock handlers
  const handleStockOpen = useCallback((record, type) => {
    setStockPart(record);
    setStockType(type);
    stockForm.resetFields();
    stockForm.setFieldsValue({ quantity: 1 });
    setStockModalOpen(true);
  }, [stockForm]);

  const handleStockOk = useCallback(async () => {
    try {
      const values = await stockForm.validateFields();
      setStockLoading(true);
      const result = await api.post(`/parts/inventory/${stockPart.id}/stock`, {
        type: stockType,
        quantity: values.quantity,
        reason: values.reason || '',
        operator: values.operator || '',
        work_order_no: values.work_order_no || '',
      });
      if (result && !result.error) {
        message.success(stockType === 'in' ? '入库成功' : '出库成功');
        setStockModalOpen(false);
        fetchParts();
      } else {
        message.error(result?.error || (stockType === 'in' ? '入库失败' : '出库失败'));
      }
    } catch { /* validation error */ }
    setStockLoading(false);
  }, [stockForm, stockPart, stockType, fetchParts]);

  const siteOptions = sites.map(s => ({ value: s.id, label: s.name || s.code }));

  const columns = [
    { title: '备件编号', dataIndex: 'part_code', key: 'part_code', width: 110,
      render: (text, r) => <Text strong style={{ color: tokens.colorPrimary }}>{text || `#${r.id}`}</Text> },
    { title: '备件名称', dataIndex: 'part_name', key: 'part_name', width: 140, ellipsis: true },
    { title: '规格型号', dataIndex: 'spec', key: 'spec', width: 130, ellipsis: true,
      render: (v, r) => v || partSpecMap[r.part_name] || spareSpecMap[r.part_name] || '-' },
    { title: '库存数量', dataIndex: 'quantity', key: 'quantity', width: 110, align: 'center',
      render: (val, r) => {
        const min = r.min_quantity || 5;
        const isLow = val != null && val < min;
        return <Text style={{ color: isLow ? tokens.colorError : tokens.colorText, fontWeight: isLow ? 600 : 400 }}>{val ?? '-'} {isLow && <Tag color="red" style={{ marginLeft: 4, fontSize: 11 }}>低库存</Tag>}</Text>;
      }},
    { title: '存放位置', dataIndex: 'location', key: 'location', width: 120,
      render: (v, r) => v || partLocationMap[r.part_name] || '-' },
    { title: '适用设备', dataIndex: 'device_types', key: 'device_types', width: 160,
      render: (val, r) => {
        const devices = Array.isArray(val) ? val : (partDeviceMap[r.part_name] || []);
        return devices.length > 0
          ? <Space size={4} wrap>{devices.map(t => <Tag key={t} style={{ fontSize: 11 }}>{deviceTypeMap[t] || t}</Tag>)}</Space>
          : '-';
      }},
    { title: '更新时间', dataIndex: 'updated_at', key: 'updated_at', width: 150, render: (v) => v || '-' },
    { title: '操作', key: 'actions', width: 220,
      render: (_, r) => (
        <Space size={0} wrap>
          <Button type="link" size="small" icon={<EyeOutlined />} onClick={() => handleView(r)}>详情</Button>
          <Button type="link" size="small" icon={<EditOutlined />} onClick={() => handleEdit(r)}>编辑</Button>
          <Button type="link" size="small" style={{ color: '#52c41a' }} icon={<ArrowUpOutlined />} onClick={() => handleStockOpen(r, 'in')}>入库</Button>
          <Button type="link" size="small" style={{ color: '#fa8c16' }} icon={<ArrowDownOutlined />} onClick={() => handleStockOpen(r, 'out')}>出库</Button>
        </Space>
      )},
  ];

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
        <Input
          placeholder="搜索备件名称、编号..."
          prefix={<SearchOutlined style={{ color: tokens.colorTextTertiary }} />}
          allowClear
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{ width: 260, borderRadius: 8 }}
        />
        <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}
          style={{ background: `linear-gradient(135deg, ${tokens.colorPrimary}, ${tokens.colorPrimaryHover})`, border: 'none' }}>
          新增备件
        </Button>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 280px)', minHeight: 400 }}>
        <style>{`.hide-scrollbar::-webkit-scrollbar{display:none}.hide-scrollbar{-ms-overflow-style:none;scrollbar-width:none}`}</style>
        <div className="hide-scrollbar" style={{ flex: 1, overflow: 'auto' }}>
          <Table
            columns={columns}
            dataSource={parts}
            rowKey={(r) => r.id || r.part_code}
            loading={loading}
            pagination={false}
            locale={{ emptyText: <Empty description="暂无备件数据" /> }}
            size="middle"
          />
        </div>
      </div>

      {/* ===== View Drawer ===== */}
      <Drawer
        title="备件详情"
        open={viewOpen}
        onClose={() => { setViewOpen(false); setViewingPart(null); }}
        width={520}
        destroyOnClose
      >
        {viewingPart && (
          <div>
            <Descriptions column={1} bordered size="small" labelStyle={{ width: 90 }}>
              <Descriptions.Item label="备件编号">{viewingPart.part_code || '-'}</Descriptions.Item>
              <Descriptions.Item label="备件名称">{viewingPart.part_name || '-'}</Descriptions.Item>
              <Descriptions.Item label="规格型号">{viewingPart.spec || spareSpecMap[viewingPart.part_name] || viewingPart.category || '-'}</Descriptions.Item>
              {(() => {
                const mfr = spareMfrMap[viewingPart.part_name];
                return mfr ? (
                  <>
                    <Descriptions.Item label="厂家名称">{mfr.name}</Descriptions.Item>
                    <Descriptions.Item label="厂家电话">{mfr.tel}</Descriptions.Item>
                  </>
                ) : null;
              })()}
              <Descriptions.Item label="库存数量">
                {viewingPart.quantity ?? '-'}
                {(viewingPart.quantity != null && viewingPart.min_quantity != null && viewingPart.quantity < viewingPart.min_quantity) && (
                  <Tag color="red" style={{ marginLeft: 6 }}>低库存</Tag>
                )}
              </Descriptions.Item>
              <Descriptions.Item label="最低库存">{viewingPart.min_quantity ?? '-'}</Descriptions.Item>
              <Descriptions.Item label="单位">{viewingPart.unit || '-'}</Descriptions.Item>
              <Descriptions.Item label="存放位置">{viewingPart.location || '-'}</Descriptions.Item>
              <Descriptions.Item label="所属站点">{viewingPart.site_name || '-'}</Descriptions.Item>
              <Descriptions.Item label="备注">{viewingPart.remark || '-'}</Descriptions.Item>
              <Descriptions.Item label="更新时间">{viewingPart.updated_at || '-'}</Descriptions.Item>
            </Descriptions>

            {/* Inventory Logs */}
            <div style={{ marginTop: 24 }}>
              <Text strong style={{ fontSize: 14, display: 'flex', alignItems: 'center', gap: 6, marginBottom: 12 }}>
                <SwapOutlined /> 出入库记录
              </Text>
              {viewingPart._logs && viewingPart._logs.length > 0 ? (
                <Table
                  dataSource={viewingPart._logs}
                  columns={[
                    { title: '类型', dataIndex: 'type', key: 'type', width: 70,
                      render: (v) => <Tag color={v === 'in' ? 'green' : 'orange'}>{v === 'in' ? '入库' : '出库'}</Tag> },
                    { title: '数量', dataIndex: 'quantity', key: 'quantity', width: 60, align: 'center' },
                    { title: '事由', dataIndex: 'reason', key: 'reason', ellipsis: true, render: (v) => v || '-' },
                    { title: '关联工单', dataIndex: 'work_order_no', key: 'work_order_no', width: 110,
                      render: (v) => v || '-' },
                    { title: '操作人', dataIndex: 'operator', key: 'operator', width: 80, render: (v) => v || '-' },
                    { title: '时间', dataIndex: 'created_at', key: 'created_at', width: 140, render: (v) => v || '-' },
                  ]}
                  rowKey={(r) => r.id || `${r.created_at}-${r.type}`}
                  pagination={false}
                  size="small"
                  scroll={{ y: 200 }}
                />
              ) : (
                <Empty description="暂无出入库记录" style={{ padding: '16px 0' }} />
              )}
            </div>
          </div>
        )}
      </Drawer>

      {/* ===== Create / Edit Modal (basic info only) ===== */}
      <Modal
        title={editingPart ? '编辑备件信息' : '新增备件'}
        open={modalOpen}
        onOk={handleModalOk}
        onCancel={() => { setModalOpen(false); setEditingPart(null); form.resetFields(); }}
        confirmLoading={modalLoading}
        okText={editingPart ? '保存' : '新增'}
        cancelText="取消"
        destroyOnClose
      >
        {editingPart && (
          <div style={{ marginBottom: 12, padding: '8px 12px', borderRadius: 8, background: 'rgba(250,140,22,0.06)', border: '1px solid rgba(250,140,22,0.15)' }}>
            <Text style={{ fontSize: 12, color: tokens.colorTextSecondary }}>
              数量和存放位置不可直接修改，请通过入库/出库操作调整库存。
            </Text>
          </div>
        )}
        <Form form={form} layout="vertical" style={{ marginTop: editingPart ? 0 : 16 }}>
          <Form.Item name="part_name" label="备件名称" rules={[{ required: true, message: '请输入备件名称' }]}>
            <Input placeholder="请输入备件名称" />
          </Form.Item>
          <Form.Item name="part_code" label="备件编号">
            <Input placeholder="留空自动生成" disabled={!!editingPart} />
          </Form.Item>
          <Form.Item name="category" label="分类">
            <Input placeholder="如: 传感器、电源、通信模块" />
          </Form.Item>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="min_quantity" label="最低库存">
                <Input type="number" min={0} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="unit" label="单位">
                <Input placeholder="个/套/台" />
              </Form.Item>
            </Col>
          </Row>
          {!editingPart && (
            <Form.Item name="quantity" label="初始数量" rules={[{ required: true, message: '请输入初始数量' }]}>
              <Input type="number" min={0} />
            </Form.Item>
          )}
          <Form.Item name="site_id" label="存放站点">
            <Select placeholder="请选择站点" options={siteOptions} showSearch allowClear
              filterOption={(input, option) => option.label.toLowerCase().includes(input.toLowerCase())} />
          </Form.Item>
          <Form.Item name="remark" label="备注">
            <Input.TextArea rows={2} placeholder="备注信息" />
          </Form.Item>
        </Form>
      </Modal>

      {/* ===== In/Out Stock Modal ===== */}
      <Modal
        title={stockType === 'in' ? '备件入库' : '备件出库'}
        open={stockModalOpen}
        onOk={handleStockOk}
        onCancel={() => { setStockModalOpen(false); setStockPart(null); stockForm.resetFields(); }}
        confirmLoading={stockLoading}
        okText="确认"
        cancelText="取消"
        destroyOnClose
      >
        {stockPart && (
          <div style={{ marginBottom: 12, padding: '8px 12px', borderRadius: 8, background: stockType === 'in' ? 'rgba(82,196,26,0.06)' : 'rgba(250,140,22,0.06)', border: `1px solid ${stockType === 'in' ? 'rgba(82,196,26,0.15)' : 'rgba(250,140,22,0.15)'}` }}>
            <Text style={{ fontSize: 13 }}>
              <Text strong>{stockPart.part_name}</Text>
              <Text type="secondary" style={{ marginLeft: 12 }}>当前库存: {stockPart.quantity ?? 0} {stockPart.unit || '个'}</Text>
            </Text>
          </div>
        )}
        <Form form={stockForm} layout="vertical" style={{ marginTop: 12 }}>
          <Form.Item name="quantity" label={stockType === 'in' ? '入库数量' : '出库数量'} rules={[{ required: true, message: '请输入数量' }]}>
            <Input type="number" min={1} placeholder="请输入数量" />
          </Form.Item>
          <Form.Item name="reason" label="事由">
            <Input.TextArea rows={2} placeholder={stockType === 'in' ? '如: 采购入库、退库' : '如: 工单维修领用、更换'} />
          </Form.Item>
          <Form.Item name="work_order_no" label="关联工单号">
            <Input placeholder="可选，关联工单号" />
          </Form.Item>
          <Form.Item name="operator" label="操作人">
            <Input placeholder="操作人姓名" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

// ---------- Spare Parts Approval Tab ----------
function SparePartsApprovalTab() {
  const { tokens } = useTheme();
  const { user } = useAuth();
  const [approvals, setApprovals] = useState([]);
  const [loading, setLoading] = useState(false);
  const [statusFilter, setStatusFilter] = useState(undefined);
  const [actionLoading, setActionLoading] = useState({});
  const [confirmModal, setConfirmModal] = useState({ open: false, type: null, record: null });
  const [rejectComment, setRejectComment] = useState('');
  const isAdmin = user?.role === 'admin';

  const fetchApprovals = useCallback(async () => {
    setLoading(true);
    try {
      const params = statusFilter ? `?status=${statusFilter}` : '';
      const data = await api.get(`/parts/requests${params}`);
      setApprovals(Array.isArray(data) ? data : (data?.approvals || []));
    } catch {
      message.error('加载审批数据失败');
      setApprovals([]);
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => { fetchApprovals(); }, [fetchApprovals]);

  const showApproveConfirm = (record) => {
    setConfirmModal({ open: true, type: 'approve', record });
  };

  const showRejectConfirm = (record) => {
    setConfirmModal({ open: true, type: 'reject', record });
    setRejectComment('');
  };

  const handleConfirmOk = async () => {
    const { type, record } = confirmModal;
    if (!record) return;

    if (type === 'reject' && !rejectComment.trim()) {
      message.warning('请填写驳回说明');
      return;
    }

    setActionLoading(prev => ({ ...prev, [record.id]: type }));
    try {
      const url = `/parts/requests/${record.id}/${type}`;
      const body = type === 'reject' ? { comment: rejectComment.trim() } : {};
      const result = await api.put(url, body);
      if (result && !result.error) {
        message.success(type === 'approve' ? '已批准' : '已驳回');
        fetchApprovals();
      } else {
        message.error(result?.error || (type === 'approve' ? '审批失败' : '驳回失败'));
      }
    } catch (err) {
      message.error(type === 'approve' ? '审批请求失败' : '驳回请求失败');
    } finally {
      setActionLoading(prev => ({ ...prev, [record.id]: null }));
      setConfirmModal({ open: false, type: null, record: null });
      setRejectComment('');
    }
  };

  const handleConfirmCancel = () => {
    setConfirmModal({ open: false, type: null, record: null });
    setRejectComment('');
  };

  const columns = [
    { title: '申请编号', dataIndex: 'request_no', key: 'request_no', width: 130,
      render: (text, r) => <Text strong style={{ color: tokens.colorPrimary }}>{text || `#${r.id}`}</Text> },
    { title: '备件名称', dataIndex: 'part_name', key: 'part_name', width: 120, ellipsis: true },
    { title: '申请人', dataIndex: 'applicant', key: 'applicant', width: 100, render: (v) => v || '-' },
    { title: '数量', dataIndex: 'quantity', key: 'quantity', width: 80, align: 'center' },
    { title: '用途', dataIndex: 'reason', key: 'reason', width: 200, ellipsis: true, render: (v) => v || '-' },
    { title: '状态', dataIndex: 'status', key: 'status', width: 100,
      render: (val) => {
        const map = {
          pending: { color: 'warning', label: '待审批' },
          approved: { color: 'success', label: '已批准' },
          rejected: { color: 'error', label: '已驳回' },
        };
        const cfg = map[val] || { color: 'default', label: val || '-' };
        return <Badge status={cfg.color} text={cfg.label} />;
      }},
    { title: '申请时间', dataIndex: 'created_at', key: 'created_at', width: 160, render: (v) => v || '-' },
    { title: '操作', key: 'actions', width: 140,
      render: (_, record) => {
        if (record.status !== 'pending') return <Text style={{ color: tokens.colorTextTertiary }}>-</Text>;
        if (!isAdmin) return <Text style={{ color: tokens.colorTextTertiary }}>无权限</Text>;
        const isLoading = actionLoading[record.id];
        return (
          <Space size={4}>
            <Button
              type="link"
              size="small"
              style={{ color: tokens.colorSuccess }}
              loading={isLoading === 'approve'}
              disabled={!!isLoading}
              onClick={() => showApproveConfirm(record)}
            >
              批准
            </Button>
            <Button
              type="link"
              size="small"
              danger
              loading={isLoading === 'reject'}
              disabled={!!isLoading}
              onClick={() => showRejectConfirm(record)}
            >
              驳回
            </Button>
          </Space>
        );
      }},
  ];

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <Select
          placeholder="审批状态"
          allowClear
          value={statusFilter}
          onChange={setStatusFilter}
          style={{ width: 140 }}
          options={[
            { value: 'pending', label: '待审批' },
            { value: 'approved', label: '已批准' },
            { value: 'rejected', label: '已驳回' },
          ]}
        />
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 280px)', minHeight: 400 }}>
        <style>{`.hide-scrollbar::-webkit-scrollbar{display:none}.hide-scrollbar{-ms-overflow-style:none;scrollbar-width:none}`}</style>
        <div className="hide-scrollbar" style={{ flex: 1, overflow: 'auto' }}>
          <Table
            columns={columns}
            dataSource={approvals}
            rowKey={(r) => r.id || r.request_no}
            loading={loading}
            pagination={false}
            locale={{ emptyText: <Empty description="暂无审批记录" /> }}
            size="middle"
          />
        </div>
      </div>
      <Modal
        title={confirmModal.type === 'approve' ? '确认批准' : '确认驳回'}
        open={confirmModal.open}
        onOk={handleConfirmOk}
        onCancel={handleConfirmCancel}
        okText="确认"
        cancelText="取消"
        okButtonProps={{ danger: confirmModal.type === 'reject' }}
      >
        {confirmModal.record && (
          <div style={{ marginBottom: 16 }}>
            <p><Text strong>申请编号：</Text>{confirmModal.record.request_no}</p>
            <p><Text strong>备件名称：</Text>{confirmModal.record.part_name}</p>
            <p><Text strong>申请人：</Text>{confirmModal.record.applicant}</p>
            <p><Text strong>数量：</Text>{confirmModal.record.quantity}</p>
          </div>
        )}
        {confirmModal.type === 'reject' && (
          <div>
            <Text strong style={{ display: 'block', marginBottom: 8 }}>
              驳回说明 <Text type="danger">*</Text>
            </Text>
            <textarea
              value={rejectComment}
              onChange={(e) => setRejectComment(e.target.value)}
              placeholder="请输入驳回原因..."
              style={{
                width: '100%',
                minHeight: 80,
                padding: '8px 12px',
                border: `1px solid ${tokens.colorBorder}`,
                borderRadius: tokens.borderRadius,
                resize: 'vertical',
                fontFamily: 'inherit',
                fontSize: 14,
              }}
            />
          </div>
        )}
        {confirmModal.type === 'approve' && (
          <p>确认批准该备件申请？批准后将自动扣减库存。</p>
        )}
      </Modal>
    </div>
  );
}

// ---------- Device Recycling Tab ----------
function DeviceRecyclingTab() {
  const { tokens } = useTheme();
  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(false);

  const fetchRecords = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.get('/device-recycle');
      setRecords(Array.isArray(data) ? data : (data?.records || []));
    } catch {
      message.error('加载回收记录失败');
      setRecords([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchRecords(); }, [fetchRecords]);

  const columns = [
    { title: '设备编码', dataIndex: 'device_code', key: 'device_code', width: 130,
      render: (text, r) => <Text strong style={{ color: tokens.colorPrimary }}>{text || `#${r.id}`}</Text> },
    { title: '设备名称', dataIndex: 'device_name', key: 'device_name', ellipsis: true },
    { title: '设备类型', dataIndex: 'device_type', key: 'device_type', width: 150,
      render: (val) => val ? <Tag>{deviceTypeMap[val] || val}</Tag> : '-' },
    { title: '原属站点', dataIndex: 'site_name', key: 'site_name', width: 150, render: (v) => v || '-' },
    { title: '回收原因', dataIndex: 'reason', key: 'reason', width: 140, ellipsis: true, render: (v) => v || '-' },
    { title: '回收方式', dataIndex: 'destination', key: 'destination', width: 100,
      render: (val) => {
        const map = { repair: '维修', replace: '更换', scrap: '报废', return: '退回' };
        return <Tag color={val === 'scrap' ? 'red' : 'blue'}>{map[val] || val || '-'}</Tag>;
      }},
    { title: '回收时间', dataIndex: 'recycle_date', key: 'recycle_date', width: 160, render: (v) => v || '-' },
    { title: '操作人', dataIndex: 'operator', key: 'operator', width: 100, render: (v) => v || '-' },
  ];

  return (
    <div>
      <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 280px)', minHeight: 400 }}>
        <style>{`.hide-scrollbar::-webkit-scrollbar{display:none}.hide-scrollbar{-ms-overflow-style:none;scrollbar-width:none}`}</style>
        <div className="hide-scrollbar" style={{ flex: 1, overflow: 'auto' }}>
          <Table
            columns={columns}
            dataSource={records}
            rowKey={(r) => r.id || r.device_code}
            loading={loading}
            pagination={false}
            locale={{ emptyText: <Empty description="暂无回收记录" /> }}
            size="middle"
          />
        </div>
      </div>
    </div>
  );
}

// ---------- Main Page ----------
export default function EquipmentPage() {
  const { tokens } = useTheme();

  const tabItems = [
    {
      key: 'ledger',
      label: <span><DatabaseOutlined /> 设备台账</span>,
      children: <DeviceLedgerTab />,
    },
    {
      key: 'spare-parts',
      label: <span><InboxOutlined /> 备件库存</span>,
      children: <SparePartsTab />,
    },
    {
      key: 'approvals',
      label: <span><CheckCircleOutlined /> 备件审批</span>,
      children: <SparePartsApprovalTab />,
    },
    {
      key: 'recycling',
      label: <span><SwapOutlined /> 设备回收</span>,
      children: <DeviceRecyclingTab />,
    },
  ];

  return (
    <div style={{ padding: 24 }}>
      <Title level={4} style={{ margin: '0 0 20px', color: tokens.colorText }}>设备管理</Title>
      <Card style={{ borderRadius: 10 }} bodyStyle={{ padding: '0 20px 20px' }}>
        <Tabs items={tabItems} style={{ marginTop: -8 }} />
      </Card>
    </div>
  );
}
