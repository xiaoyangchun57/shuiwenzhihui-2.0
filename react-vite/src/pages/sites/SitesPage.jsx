import { useState, useEffect, useMemo, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  Table, Card, Input, Select, Button, Space, Tag, Badge,
  Modal, Descriptions, Tabs, Typography, message, Spin, Empty, Row, Col,
  Upload, Timeline, Divider, Form, InputNumber, Popconfirm,
} from 'antd';
import {
  SearchOutlined, FileSearchOutlined, EnvironmentOutlined,
  ReloadOutlined, FilterOutlined, DownloadOutlined, UploadOutlined,
  FileTextOutlined, CloudServerOutlined, ApiOutlined, InboxOutlined,
  PlusOutlined, DeleteOutlined, ExperimentOutlined, CheckCircleOutlined,
  CloseCircleOutlined,
} from '@ant-design/icons';
import { api } from '../../services/api';
import { stationTypeMap } from '../../services/constants';
import { useTheme } from '../../hooks/useTheme';

const { Text, Title } = Typography;

// ---------------------------------------------------------------------------
// Station type → Tag color mapping
// ---------------------------------------------------------------------------
const typeColorMap = {
  rainfall: 'blue',
  water_level: 'cyan',
  hydrology: 'geekblue',
  soil_moisture: 'green',
  evaporation: 'orange',
  groundwater: 'purple',
  station_yard: 'gold',
};

// ---------------------------------------------------------------------------
// Status helpers
// ---------------------------------------------------------------------------
const statusConfig = {
  normal: { color: 'green', text: '在线' },
  online: { color: 'green', text: '在线' },
  offline: { color: 'red', text: '离线' },
  maintenance: { color: 'orange', text: '维护中' },
};

function getStatusCfg(status) {
  return statusConfig[status] || { color: 'default', text: status || '未知' };
}

// ---------------------------------------------------------------------------
// Data trend chart helpers (pure functions, no hooks)
// ---------------------------------------------------------------------------
function generateMockDataTrend(code) {
  const seed = (code || 'DEFAULT').split('').reduce((a, c) => a + c.charCodeAt(0), 0);
  const points = [];
  for (let i = 0; i < 24; i++) {
    const base = 50 + 20 * Math.sin((seed + i * 15) * Math.PI / 180);
    const noise = 5 * Math.sin((seed * 3 + i * 37) * Math.PI / 180);
    points.push({
      hour: `${String(i).padStart(2, '0')}:00`,
      value: Math.round((base + noise) * 100) / 100,
    });
  }
  return points;
}

function renderArchiveTrendChart(dataPoints, primaryColor, textColor, gridColor) {
  if (!dataPoints || dataPoints.length === 0) return null;
  const W = 640, H = 180, padL = 40, padR = 16, padT = 16, padB = 28;
  const chartW = W - padL - padR;
  const chartH = H - padT - padB;
  const vals = dataPoints.map((d) => d.value);
  const minV = Math.floor(Math.min(...vals) - 2);
  const maxV = Math.ceil(Math.max(...vals) + 2);
  const range = maxV - minV || 1;
  const xStep = chartW / (dataPoints.length - 1);
  const toY = (v) => padT + chartH - ((v - minV) / range) * chartH;
  const toX = (i) => padL + i * xStep;
  const linePath = dataPoints.map((d, i) => `${i === 0 ? 'M' : 'L'}${toX(i).toFixed(1)},${toY(d.value).toFixed(1)}`).join(' ');
  const areaPath = `${linePath} L${toX(dataPoints.length - 1).toFixed(1)},${(padT + chartH).toFixed(1)} L${toX(0).toFixed(1)},${(padT + chartH).toFixed(1)} Z`;
  const color = primaryColor || '#1677ff';
  const txtColor = textColor || '#999';
  const grdColor = gridColor || '#e8e8e8';

  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', height: 'auto' }}>
      {[0, 0.25, 0.5, 0.75, 1].map((f) => {
        const y = padT + chartH * f;
        const v = (maxV - range * f).toFixed(1);
        return (
          <g key={f}>
            <line x1={padL} y1={y} x2={W - padR} y2={y} stroke={grdColor} strokeWidth={0.5} />
            <text x={padL - 4} y={y + 3} textAnchor="end" fontSize={9} fill={txtColor}>{v}</text>
          </g>
        );
      })}
      <defs>
        <linearGradient id="archiveTrendFill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity={0.15} />
          <stop offset="100%" stopColor={color} stopOpacity={0.01} />
        </linearGradient>
      </defs>
      <path d={areaPath} fill="url(#archiveTrendFill)" />
      <path d={linePath} fill="none" stroke={color} strokeWidth={1.8} strokeLinejoin="round" />
      {dataPoints.map((d, i) => (
        <circle key={i} cx={toX(i).toFixed(1)} cy={toY(d.value).toFixed(1)} r={2.2} fill="#fff" stroke={color} strokeWidth={1.2} />
      ))}
      {dataPoints.filter((_, i) => i % 4 === 0).map((d, idx) => {
        const i = idx * 4;
        return (
          <text key={i} x={toX(i).toFixed(1)} y={H - 6} textAnchor="middle" fontSize={9} fill={txtColor}>{d.hour}</text>
        );
      })}
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------
export default function SitesPage() {
  const { tokens } = useTheme();
  const [searchParams, setSearchParams] = useSearchParams();

  // ---- data state ----
  const [sites, setSites] = useState([]);
  const [loading, setLoading] = useState(false);
  const [fetchError, setFetchError] = useState(null);

  // ---- filter state ----
  const [searchText, setSearchText] = useState('');
  const [typeFilter, setTypeFilter] = useState(undefined);
  const [districtFilter, setDistrictFilter] = useState(undefined);
  const [managerFilter, setManagerFilter] = useState(undefined);

  // ---- archive modal ----
  const [archiveModalOpen, setArchiveModalOpen] = useState(false);
  const [archiveData, setArchiveData] = useState(null);
  const [archiveLoading, setArchiveLoading] = useState(false);

  // ---- data import modal ----
  const [importModalOpen, setImportModalOpen] = useState(false);
  const [importTab, setImportTab] = useState('file');
  const [importLoading, setImportLoading] = useState(false);
  const [importResult, setImportResult] = useState(null);
  const [dataSources, setDataSources] = useState([]);
  const [dsForm] = Form.useForm();
  const [dsModalOpen, setDsModalOpen] = useState(false);
  const [dsLoading, setDsLoading] = useState(false);
  const [testingDs, setTestingDs] = useState(null);

  // ========================================================================
  // Fetch all sites
  // ========================================================================
  const fetchSites = useCallback(async () => {
    setLoading(true);
    setFetchError(null);
    try {
      const data = await api.get('/sites');
      if (data && Array.isArray(data)) {
        setSites(data);
      } else if (data && Array.isArray(data.data)) {
        // handle { data: [...] } wrapper
        setSites(data.data);
      } else {
        setSites([]);
        setFetchError('无法获取站点数据，请稍后重试');
      }
    } catch (err) {
      console.error('Failed to fetch sites:', err);
      setFetchError('网络异常，无法加载站点列表');
      message.error('加载站点列表失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSites();
  }, [fetchSites]);

  // ========================================================================
  // Derived option lists for filter dropdowns
  // ========================================================================
  // Normalize district names: strip "江西" prefix, merge county/district variants
  const normalizeDistrict = (addr) => {
    if (!addr) return '';
    let d = addr.replace(/^江西/, '');
    // Merge known variants
    const mergeMap = { '新建县': '新建区', '红谷滩新区': '红谷滩区' };
    if (mergeMap[d]) d = mergeMap[d];
    return d;
  };

  // Extract district-level prefix from full address (e.g. "新建区某某村" → "新建区")
  const extractDistrict = (addr) => {
    if (!addr) return '';
    for (let i = 0; i < addr.length; i++) {
      if ('区县市'.includes(addr[i]) && i > 0 && i < addr.length - 1) {
        return normalizeDistrict(addr.slice(0, i + 1));
      }
    }
    return normalizeDistrict(addr);
  };

  const districtOptions = useMemo(() => {
    const set = new Set(sites.map((s) => extractDistrict(s.district)).filter(Boolean));
    return [...set].sort().map((d) => ({ label: d, value: d }));
  }, [sites]);

  const managerOptions = useMemo(() => {
    const set = new Set(sites.map((s) => s.manager).filter(Boolean));
    return [...set].sort().map((m) => ({ label: m, value: m }));
  }, [sites]);

  const typeOptions = useMemo(
    () =>
      Object.entries(stationTypeMap).map(([value, label]) => ({
        label,
        value,
      })),
    [],
  );

  // ========================================================================
  // Client-side filtering
  // ========================================================================
  const filteredSites = useMemo(() => {
    const keyword = searchText.trim().toLowerCase();
    return sites.filter((site) => {
      if (keyword) {
        const nameMatch = (site.name || '').toLowerCase().includes(keyword);
        const codeMatch = (site.code || '').toLowerCase().includes(keyword);
        if (!nameMatch && !codeMatch) return false;
      }
      if (typeFilter && site.type !== typeFilter) return false;
      if (districtFilter && extractDistrict(site.district) !== districtFilter) return false;
      if (managerFilter && site.manager !== managerFilter) return false;
      return true;
    });
  }, [sites, searchText, typeFilter, districtFilter, managerFilter]);

  // ========================================================================
  // Archive modal handler
  // ========================================================================
  const openArchive = useCallback(async (siteId) => {
    setArchiveModalOpen(true);
    setArchiveLoading(true);
    setArchiveData(null);
    try {
      const data = await api.get(`/sites/${siteId}/archive`);
      if (data) {
        setArchiveData(data);
      } else {
        message.warning('未获取到该站点的档案信息');
      }
    } catch (err) {
      console.error('Failed to fetch archive:', err);
      message.error('加载站点档案失败');
    } finally {
      setArchiveLoading(false);
    }
  }, []);

  const closeArchive = useCallback(() => {
    setArchiveModalOpen(false);
    setArchiveData(null);
  }, []);

  // Auto-open archive modal when navigated from cockpit with ?archive=siteId
  useEffect(() => {
    const archiveId = searchParams.get('archive');
    if (archiveId) {
      const timer = setTimeout(() => {
        openArchive(archiveId);
        setSearchParams({}, { replace: true });
      }, 500);
      return () => clearTimeout(timer);
    }
  }, [searchParams, openArchive, setSearchParams]);

  // ========================================================================
  // Reset filters
  // ========================================================================
  const resetFilters = useCallback(() => {
    setSearchText('');
    setTypeFilter(undefined);
    setDistrictFilter(undefined);
    setManagerFilter(undefined);
  }, []);

  // ========================================================================
  // Table columns
  // ========================================================================
  const columns = useMemo(
    () => [
      {
        title: '站点编码',
        dataIndex: 'code',
        key: 'code',
        width: 140,
        ellipsis: true,
        sorter: (a, b) => (a.code || '').localeCompare(b.code || ''),
        render: (text) => text || '-',
      },
      {
        title: '站点名称',
        dataIndex: 'name',
        key: 'name',
        width: 180,
        ellipsis: true,
        sorter: (a, b) => (a.name || '').localeCompare(b.name || ''),
        render: (text) => <Text strong>{text}</Text>,
      },
      {
        title: '区县/地址',
        key: 'location',
        width: 240,
        ellipsis: true,
        render: (_, record) => (
          <Space size={4} align="start">
            <EnvironmentOutlined style={{ color: tokens.colorTextTertiary, marginTop: 4 }} />
            <span>
              <Text type="secondary">{record.district}</Text>
              {record.address && (
                <>
                  <Text type="secondary"> · </Text>
                  <Text>{record.address}</Text>
                </>
              )}
            </span>
          </Space>
        ),
      },
      {
        title: '站点类型',
        dataIndex: 'type',
        key: 'type',
        width: 120,
        filters: Object.entries(stationTypeMap).map(([value, text]) => ({
          text,
          value,
        })),
        onFilter: (value, record) => record.type === value,
        render: (type) => {
          const label = stationTypeMap[type] || type;
          const color = typeColorMap[type] || 'default';
          return <Tag color={color}>{label}</Tag>;
        },
      },
      {
        title: '状态',
        dataIndex: 'status',
        key: 'status',
        width: 100,
        render: (status) => {
          const cfg = getStatusCfg(status);
          return <Badge color={cfg.color} text={cfg.text} />;
        },
      },
      {
        title: '负责人',
        dataIndex: 'manager',
        key: 'manager',
        width: 110,
        ellipsis: true,
      },
      {
        title: '操作',
        key: 'actions',
        width: 100,
        fixed: 'right',
        render: (_, record) => (
          <Button
            type="link"
            size="small"
            icon={<FileSearchOutlined />}
            onClick={() => openArchive(record.id)}
          >
            档案
          </Button>
        ),
      },
    ],
    [tokens, openArchive],
  );

  // ========================================================================
  // Active filter count (for badge on reset button)
  // ========================================================================
  const activeFilterCount = useMemo(
    () => [typeFilter, districtFilter, managerFilter].filter(Boolean).length + (searchText ? 1 : 0),
    [typeFilter, districtFilter, managerFilter, searchText],
  );

  // ========================================================================
  // Archive modal content
  // ========================================================================
  const renderArchiveContent = () => {
    if (archiveLoading) {
      return (
        <div style={{ textAlign: 'center', padding: '48px 0' }}>
          <Spin size="large" tip="加载档案数据..." />
        </div>
      );
    }
    if (!archiveData) {
      return <Empty description="暂无档案数据" />;
    }

    const {
      name, code, type, district, address, manager, status,
      lat, lng, build_date, equipment, history_records,
      description: siteDesc, contact, area, basin,
      fault_records, replacement_records, inspection_records, calibration_reports,
    } = archiveData;

    const basicItems = [
      { key: 'code', label: '站点编码', children: code },
      { key: 'name', label: '站点名称', children: name },
      {
        key: 'type',
        label: '站点类型',
        children: <Tag color={typeColorMap[type] || 'default'}>{stationTypeMap[type] || type}</Tag>,
      },
      {
        key: 'status',
        label: '运行状态',
        children: <Badge {...getStatusCfg(status)} />,
      },
      { key: 'district', label: '所属区县', children: extractDistrict(district) || '-' },
      { key: 'address', label: '详细地址', children: address || '-', span: 2 },
      { key: 'basin', label: '所属流域', children: basin || '-' },
      {
        key: 'coordinates',
        label: '经纬度',
        children: lat && lng ? `${Number(lat).toFixed(6)}, ${Number(lng).toFixed(6)}` : '-',
      },
      { key: 'build_date', label: '建站日期', children: build_date || '-' },
      { key: 'manager', label: '负责人', children: manager || '-' },
    ];

    // Generate mock data trend for this site
    const dataTrend = generateMockDataTrend(code);

    const tabItems = [
      {
        key: 'basic',
        label: '基本信息',
        children: (
          <div>
            <Descriptions bordered size="small" column={2} items={basicItems} labelStyle={{ width: 90, minWidth: 90 }} contentStyle={{ width: 'auto' }} />
            <Divider style={{ margin: '20px 0 16px' }} />
            <div style={{ marginBottom: 12, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <Text strong style={{ fontSize: 14 }}>数据采集趋势（24小时）</Text>
              <Text type="secondary" style={{ fontSize: 12 }}>基于最近采集数据</Text>
            </div>
            <div style={{ background: tokens.colorBgLayout || '#fafafa', borderRadius: 8, padding: '12px 8px 8px' }}>
              {renderArchiveTrendChart(dataTrend, tokens.colorPrimary, tokens.colorTextTertiary, tokens.colorBorderSecondary)}
            </div>
            <div style={{ marginTop: 12 }}>
              <Table
                dataSource={dataTrend}
                columns={[
                  { title: '时间', dataIndex: 'hour', key: 'hour', width: 80 },
                  {
                    title: '采集值',
                    dataIndex: 'value',
                    key: 'value',
                    width: 100,
                    render: (v) => <Text strong style={{ color: tokens.colorPrimary }}>{v}</Text>,
                  },
                  {
                    title: '状态',
                    key: 'status',
                    width: 80,
                    render: (_, record) => {
                      const avg = dataTrend.reduce((s, d) => s + d.value, 0) / dataTrend.length;
                      const deviation = Math.abs(record.value - avg);
                      if (deviation > avg * 0.3) return <Tag color="warning">异常</Tag>;
                      return <Tag color="success">正常</Tag>;
                    },
                  },
                ]}
                rowKey="hour"
                pagination={false}
                size="small"
                scroll={{ y: 240 }}
              />
            </div>
          </div>
        ),
      },
    ];

    // Equipment list - always show tab
    const equipmentList = equipment || [];
    const eqColumns = [
      { title: '设备名称', dataIndex: 'name', key: 'name' },
      { title: '设备型号', dataIndex: 'model', key: 'model' },
      { title: '安装日期', dataIndex: 'install_date', key: 'install_date' },
      {
        title: '状态',
        dataIndex: 'status',
        key: 'status',
        render: (s) => {
          const cfg = getStatusCfg(s);
          return <Badge color={cfg.color} text={cfg.text} />;
        },
      },
    ];
    tabItems.push({
      key: 'equipment',
      label: `设备清单${equipmentList.length > 0 ? ` (${equipmentList.length})` : ''}`,
      children: equipmentList.length > 0 ? (
        <Table dataSource={equipmentList} columns={eqColumns} rowKey={(r) => r.id || r.name} pagination={false} size="small" />
      ) : (
        <Empty description="暂无设备信息" style={{ padding: '32px 0' }} />
      ),
    });

    // Fault records - always show tab
    const faultRecords = fault_records || [];
    tabItems.push({
      key: 'faults',
      label: `故障记录${faultRecords.length > 0 ? ` (${faultRecords.length})` : ''}`,
      children: faultRecords.length > 0 ? (
        <Timeline
          items={faultRecords.map((r) => ({
            color: r.severity === 'high' ? 'red' : r.severity === 'medium' ? 'orange' : 'blue',
            children: (
              <div>
                <div style={{ fontWeight: 500 }}>{r.title || r.event}</div>
                <div style={{ fontSize: 12, color: tokens.colorTextSecondary, marginTop: 4 }}>{r.description || r.detail}</div>
                <div style={{ fontSize: 11, color: tokens.colorTextTertiary, marginTop: 4 }}>
                  {r.date} · {r.operator || '未知'}
                </div>
              </div>
            ),
          }))}
        />
      ) : (
        <Empty description="暂无故障记录" style={{ padding: '32px 0' }} />
      ),
    });

    // Equipment replacement records - always show tab
    const replacementRecords = replacement_records || [];
    tabItems.push({
      key: 'replacement',
      label: `设备更换${replacementRecords.length > 0 ? ` (${replacementRecords.length})` : ''}`,
      children: replacementRecords.length > 0 ? (
        <Table
          dataSource={replacementRecords}
          columns={[
            { title: '日期', dataIndex: 'date', key: 'date', width: 120 },
            { title: '旧设备', dataIndex: 'old_equipment', key: 'old_equipment' },
            { title: '新设备', dataIndex: 'new_equipment', key: 'new_equipment' },
            { title: '原因', dataIndex: 'reason', key: 'reason' },
            { title: '操作人', dataIndex: 'operator', key: 'operator', width: 100 },
          ]}
          rowKey={(r, i) => r.id || `${r.date}-${i}`}
          pagination={{ pageSize: 5, size: 'small' }}
          size="small"
        />
      ) : (
        <Empty description="暂无设备更换记录" style={{ padding: '32px 0' }} />
      ),
    });

    // Inspection records - always show tab
    const inspectionRecords = inspection_records || [];
    tabItems.push({
      key: 'inspection',
      label: `巡检记录${inspectionRecords.length > 0 ? ` (${inspectionRecords.length})` : ''}`,
      children: inspectionRecords.length > 0 ? (
        <Table
          dataSource={inspectionRecords}
          columns={[
            { title: '巡检日期', dataIndex: 'date', key: 'date', width: 120 },
            { title: '巡检类型', dataIndex: 'type', key: 'type', width: 100 },
            { title: '巡检结果', dataIndex: 'result', key: 'result' },
            { title: '发现问题', dataIndex: 'issues', key: 'issues' },
            { title: '巡检人', dataIndex: 'inspector', key: 'inspector', width: 100 },
          ]}
          rowKey={(r, i) => r.id || `${r.date}-${i}`}
          pagination={{ pageSize: 5, size: 'small' }}
          size="small"
        />
      ) : (
        <Empty description="暂无巡检记录" style={{ padding: '32px 0' }} />
      ),
    });

    // Calibration reports with file upload
    tabItems.push({
      key: 'calibration',
      label: '校准报告',
      children: (
        <div>
          {calibration_reports && Array.isArray(calibration_reports) && calibration_reports.length > 0 ? (
            <Table
              dataSource={calibration_reports}
              columns={[
                { title: '报告日期', dataIndex: 'date', key: 'date', width: 120 },
                { title: '校准类型', dataIndex: 'type', key: 'type', width: 120 },
                { title: '校准结果', dataIndex: 'result', key: 'result' },
                { title: '有效期', dataIndex: 'valid_until', key: 'valid_until', width: 120 },
                {
                  title: '附件',
                  dataIndex: 'file',
                  key: 'file',
                  render: (file) => file ? (
                    <a href={file.url || '#'} target="_blank" rel="noopener noreferrer">
                      <FileTextOutlined style={{ marginRight: 4 }} />{file.name || '下载'}
                    </a>
                  ) : '-',
                },
              ]}
              rowKey={(r, i) => r.id || `${r.date}-${i}`}
              pagination={{ pageSize: 5, size: 'small' }}
              size="small"
            />
          ) : (
            <Empty description="暂无校准报告" style={{ padding: '20px 0' }} />
          )}
          <Divider style={{ margin: '16px 0' }} />
          <div style={{ textAlign: 'center' }}>
            <Upload
              action="/api/sites/archive/upload-calibration"
              listType="text"
              accept=".pdf,.doc,.docx,.xls,.xlsx"
              onChange={(info) => {
                if (info.file.status === 'done') {
                  message.success('校准报告上传成功');
                } else if (info.file.status === 'error') {
                  message.error('上传失败，请重试');
                }
              }}
            >
              <Button icon={<UploadOutlined />}>上传校准报告</Button>
            </Upload>
          </div>
        </div>
      ),
    });

    return <Tabs items={tabItems} defaultActiveKey="basic" size="small" />;
  };

  // ---- Data import handlers ----
  const fetchDataSources = useCallback(async () => {
    try {
      const data = await api.get('/sites/data-sources');
      setDataSources(Array.isArray(data) ? data : []);
    } catch { setDataSources([]); }
  }, []);

  const handleImportFile = async (file) => {
    setImportLoading(true);
    setImportResult(null);
    const formData = new FormData();
    formData.append('file', file);
    try {
      const res = await fetch('/api/sites/import', {
        method: 'POST',
        headers: { Authorization: `Bearer ${localStorage.getItem('water_ops_token') || ''}` },
        body: formData,
      });
      const data = await res.json();
      setImportResult(data);
      if (data.imported > 0) {
        message.success(`成功导入 ${data.imported} 个站点`);
        fetchSites();
      }
      if (data.failed > 0) {
        message.warning(`${data.failed} 条记录导入失败`);
      }
    } catch (e) {
      message.error('导入失败');
      setImportResult({ error: String(e) });
    } finally {
      setImportLoading(false);
    }
    return false; // prevent auto upload
  };

  const handleAddDataSource = async () => {
    try {
      const values = await dsForm.validateFields();
      setDsLoading(true);
      const result = await api.post('/sites/data-sources', values);
      if (result && !result.error) {
        message.success('数据源已添加');
        setDsModalOpen(false);
        dsForm.resetFields();
        fetchDataSources();
      } else {
        message.error(result?.error || '添加失败');
      }
    } catch { /* validation error */ }
    setDsLoading(false);
  };

  const handleTestDs = async (ds) => {
    setTestingDs(ds.id);
    try {
      const result = await api.post(`/sites/data-sources/${ds.id}/test`, {});
      if (result?.success) {
        message.success(result.message || '连接成功');
      } else {
        message.error(result?.error || '连接失败');
      }
    } catch { message.error('测试失败'); }
    setTestingDs(null);
  };

  const handleDeleteDs = async (id) => {
    const result = await api.delete(`/sites/data-sources/${id}`);
    if (result && !result.error) {
      message.success('数据源已删除');
      fetchDataSources();
    } else {
      message.error('删除失败');
    }
  };

  // ========================================================================
  // Render
  // ========================================================================
  return (
    <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', padding: 24 }}>
      {/* ---- Page Header ---- */}
      <div style={{ marginBottom: 20, display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12, flexShrink: 0 }}>
        <Title level={4} style={{ margin: 0, color: tokens.colorText }}>站点管理</Title>
        <Button
          icon={<CloudServerOutlined />}
          onClick={() => { setImportModalOpen(true); setImportResult(null); fetchDataSources(); }}
          style={{
            background: 'linear-gradient(135deg, #1890ff, #00c9a7)',
            border: 'none', color: '#fff', fontWeight: 500,
          }}
        >
          数据接入
        </Button>
      </div>

      {/* ---- Filter Bar ---- */}
      <Card size="small" style={{ flexShrink: 0 }}>
        <Row gutter={[12, 12]} align="middle">
          <Col flex="auto">
            <Space wrap size={12}>
              <Input
                placeholder="搜索站点名称 / 编码"
                prefix={<SearchOutlined style={{ color: tokens.colorTextQuaternary }} />}
                allowClear
                value={searchText}
                onChange={(e) => setSearchText(e.target.value)}
                style={{ width: 260 }}
              />

              <Select
                placeholder="站点类型"
                allowClear
                value={typeFilter}
                onChange={setTypeFilter}
                options={typeOptions}
                style={{ width: 140 }}
              />

              <Select
                placeholder="所属区县"
                allowClear
                showSearch
                optionFilterProp="label"
                value={districtFilter}
                onChange={setDistrictFilter}
                options={districtOptions}
                style={{ width: 150 }}
              />

              <Select
                placeholder="负责人"
                allowClear
                showSearch
                optionFilterProp="label"
                value={managerFilter}
                onChange={setManagerFilter}
                options={managerOptions}
                style={{ width: 140 }}
              />
            </Space>
          </Col>

          <Col>
            <Space>
              <Button icon={<ReloadOutlined />} onClick={resetFilters}>
                重置
              </Button>
              <Button
                icon={<ReloadOutlined />}
                onClick={fetchSites}
                loading={loading}
              >
                刷新
              </Button>
            </Space>
          </Col>
        </Row>
      </Card>

      {/* ---- Data Table ---- */}
      <Card
        size="small"
        style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}
        styles={{ body: { flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', padding: 0 } }}
      >
        {fetchError && !loading ? (
          <Empty
            description={fetchError}
            image={Empty.PRESENTED_IMAGE_SIMPLE}
          >
            <Button type="primary" onClick={fetchSites}>
              重新加载
            </Button>
          </Empty>
        ) : (
          <>
            <style>{`.hide-scrollbar::-webkit-scrollbar{display:none}.hide-scrollbar{-ms-overflow-style:none;scrollbar-width:none}`}</style>
            <div className="hide-scrollbar" style={{ flex: 1, overflow: 'auto' }}>
              <Table
                dataSource={filteredSites}
                columns={columns}
                rowKey="id"
                size="small"
                loading={loading}
                pagination={false}
                locale={{
                  emptyText: (
                    <Empty
                      image={Empty.PRESENTED_IMAGE_SIMPLE}
                      description={
                        activeFilterCount > 0
                          ? '没有符合条件的站点'
                          : '暂无站点数据'
                      }
                    />
                  ),
                }}
              />
            </div>
          </>
        )}
      </Card>

      {/* ---- Archive Modal ---- */}
      <Modal
        title={
          <Space>
            <FileSearchOutlined />
            <span>站点档案</span>
            {archiveData?.name && (
              <Tag color="processing">{archiveData.name}</Tag>
            )}
          </Space>
        }
        open={archiveModalOpen}
        onCancel={closeArchive}
        footer={[
          <Button key="export" icon={<DownloadOutlined />} onClick={() => {
            if (!archiveData) return;
            const exportData = {
              站点名称: archiveData.name,
              站点编码: archiveData.code,
              站点类型: stationTypeMap[archiveData.type] || archiveData.type,
              所属区县: archiveData.district,
              详细地址: archiveData.address,
              负责人: archiveData.manager,
              运行状态: archiveData.status,
              经纬度: archiveData.lat && archiveData.lng ? `${archiveData.lat}, ${archiveData.lng}` : '',
              建站日期: archiveData.build_date,
              设备清单: (archiveData.equipment || []).map(e => ({
                设备编码: e.device_code, 设备名称: e.device_name, 设备类型: e.device_type, 状态: e.status
              })),
              故障记录: (archiveData.fault_records || []).map(r => ({
                时间: r.time || r.created_at, 描述: r.description || r.event_type, 状态: r.status
              })),
              更换记录: (archiveData.replacement_records || []).map(r => ({
                时间: r.time || r.created_at, 设备: r.device_name, 描述: r.description
              })),
              巡检记录: (archiveData.inspection_records || []).map(r => ({
                计划: r.plan_name, 频次: r.frequency, 状态: r.status
              })),
            };
            const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `站点档案_${archiveData.name || archiveData.code || 'export'}.json`;
            a.click();
            URL.revokeObjectURL(url);
            message.success('档案已导出');
          }}>
            导出档案
          </Button>,
          <Button key="close" onClick={closeArchive}>
            关闭
          </Button>,
        ]}
        width={880}
        destroyOnClose
      >
        {renderArchiveContent()}
      </Modal>

      {/* ===== Data Import Modal ===== */}
      <Modal
        title={<span><CloudServerOutlined style={{ marginRight: 8, color: '#1890ff' }} />数据接入</span>}
        open={importModalOpen}
        onCancel={() => setImportModalOpen(false)}
        footer={[<Button key="close" onClick={() => setImportModalOpen(false)}>关闭</Button>]}
        width={720}
        destroyOnClose
      >
        <Tabs
          activeKey={importTab}
          onChange={setImportTab}
          items={[
            {
              key: 'file',
              label: <span><UploadOutlined /> 文件导入</span>,
              children: (
                <div style={{ padding: '16px 0' }}>
                  <div style={{ marginBottom: 16, padding: '10px 14px', borderRadius: 8, background: tokens.colorBgTextHover }}>
                    <Text style={{ fontSize: 13 }}>
                      支持 CSV 格式批量导入站点，必填字段：code（编码）、name（名称）、type（类型）。
                      <a onClick={() => window.open('/api/sites/template')} style={{ marginLeft: 8 }}>下载导入模板</a>
                    </Text>
                  </div>
                  <Upload.Dragger
                    accept=".csv"
                    showUploadList={false}
                    beforeUpload={handleImportFile}
                    disabled={importLoading}
                    style={{ borderRadius: 10 }}
                  >
                    <p style={{ fontSize: 36, color: tokens.colorPrimary, marginBottom: 8 }}><InboxOutlined /></p>
                    <p style={{ fontSize: 15, fontWeight: 500 }}>点击或拖拽 CSV 文件到此区域</p>
                    <p style={{ fontSize: 13, color: tokens.colorTextSecondary }}>支持 .csv 格式，UTF-8 编码</p>
                  </Upload.Dragger>
                  {importLoading && <div style={{ textAlign: 'center', padding: 16 }}><Spin /> <Text style={{ marginLeft: 8 }}>正在导入...</Text></div>}
                  {importResult && !importResult.error && (
                    <div style={{ marginTop: 16, padding: '12px 16px', borderRadius: 8, background: importResult.imported > 0 ? 'rgba(82,196,26,0.08)' : 'rgba(250,173,20,0.08)', border: `1px solid ${importResult.imported > 0 ? '#b7eb8f' : '#ffe58f'}` }}>
                      <div style={{ fontWeight: 500, marginBottom: 4 }}>
                        <CheckCircleOutlined style={{ color: '#52c41a', marginRight: 6 }} />
                        导入完成：成功 {importResult.imported} 条，失败 {importResult.failed} 条
                      </div>
                      {importResult.errors?.length > 0 && (
                        <div style={{ fontSize: 12, color: tokens.colorTextSecondary, marginTop: 4 }}>
                          {importResult.errors.map((e, i) => <div key={i}>{e}</div>)}
                        </div>
                      )}
                    </div>
                  )}
                  {importResult?.error && (
                    <div style={{ marginTop: 16, padding: '12px 16px', borderRadius: 8, background: 'rgba(255,77,79,0.08)', border: '1px solid #ffa39e' }}>
                      <CloseCircleOutlined style={{ color: '#ff4d4f', marginRight: 6 }} />
                      <Text type="danger">{importResult.error}</Text>
                    </div>
                  )}
                </div>
              ),
            },
            {
              key: 'api',
              label: <span><ApiOutlined /> 数据源配置</span>,
              children: (
                <div style={{ padding: '16px 0' }}>
                  <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <Text style={{ fontSize: 13, color: tokens.colorTextSecondary }}>配置外部数据源，实现站点数据自动接入</Text>
                    <Button type="primary" size="small" icon={<PlusOutlined />} onClick={() => { dsForm.resetFields(); setDsModalOpen(true); }}>
                      添加数据源
                    </Button>
                  </div>
                  {dataSources.length === 0 ? (
                    <Empty description="暂无数据源配置" style={{ padding: '24px 0' }} />
                  ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                      {dataSources.map((ds) => (
                        <div key={ds.id} style={{
                          padding: '12px 16px', borderRadius: 10,
                          border: `1px solid ${tokens.colorBorder}`,
                          background: tokens.colorBgContainer,
                        }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <div>
                              <Text strong style={{ fontSize: 14 }}>{ds.name}</Text>
                              <Tag color="blue" style={{ marginLeft: 8, fontSize: 11 }}>{ds.protocol || 'HTTP'}</Tag>
                              <Tag color={ds.status === 'active' ? 'green' : 'default'} style={{ fontSize: 11 }}>
                                {ds.status === 'active' ? '运行中' : '未启用'}
                              </Tag>
                            </div>
                            <Space size={4}>
                              <Button type="link" size="small" icon={<ExperimentOutlined />}
                                loading={testingDs === ds.id} onClick={() => handleTestDs(ds)}>测试</Button>
                              <Popconfirm title="确认删除此数据源？" onConfirm={() => handleDeleteDs(ds.id)} okText="删除" cancelText="取消">
                                <Button type="link" size="small" danger icon={<DeleteOutlined />}>删除</Button>
                              </Popconfirm>
                            </Space>
                          </div>
                          <div style={{ marginTop: 6, fontSize: 12, color: tokens.colorTextSecondary }}>
                            <Text copyable style={{ fontSize: 12 }}>{ds.url}</Text>
                            {ds.last_sync && <Text style={{ marginLeft: 12, fontSize: 12 }}>上次同步: {ds.last_sync}</Text>}
                            {ds.sync_interval && <Text style={{ marginLeft: 12, fontSize: 12 }}>间隔: {ds.sync_interval}分钟</Text>}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ),
            },
          ]}
        />
      </Modal>

      {/* ===== Add Data Source Modal ===== */}
      <Modal
        title="添加数据源"
        open={dsModalOpen}
        onOk={handleAddDataSource}
        onCancel={() => { setDsModalOpen(false); dsForm.resetFields(); }}
        confirmLoading={dsLoading}
        okText="保存"
        cancelText="取消"
        destroyOnClose
      >
        <Form form={dsForm} layout="vertical" style={{ marginTop: 16 }} initialValues={{ source_type: 'api', protocol: 'HTTP', auth_type: 'none', sync_interval: 60 }}>
          <Form.Item name="name" label="数据源名称" rules={[{ required: true, message: '请输入名称' }]}>
            <Input placeholder="如: 省水文局数据接口" />
          </Form.Item>
          <Row gutter={12}>
            <Col span={12}>
              <Form.Item name="source_type" label="接入类型">
                <Select options={[
                  { value: 'api', label: 'REST API' },
                  { value: 'mqtt', label: 'MQTT' },
                  { value: 'ftp', label: 'FTP/SFTP' },
                  { value: 'database', label: '数据库直连' },
                ]} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="protocol" label="协议">
                <Select options={[
                  { value: 'HTTP', label: 'HTTP/HTTPS' },
                  { value: 'TCP', label: 'TCP' },
                  { value: 'UDP', label: 'UDP' },
                  { value: 'MQTT', label: 'MQTT' },
                ]} />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="url" label="接口地址" rules={[{ required: true, message: '请输入URL' }]}>
            <Input placeholder="https://api.example.com/water/data" />
          </Form.Item>
          <Row gutter={12}>
            <Col span={12}>
              <Form.Item name="auth_type" label="认证方式">
                <Select options={[
                  { value: 'none', label: '无认证' },
                  { value: 'token', label: 'Token' },
                  { value: 'basic', label: 'Basic Auth' },
                  { value: 'apikey', label: 'API Key' },
                ]} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="sync_interval" label="同步间隔(分钟)">
                <InputNumber min={1} max={1440} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="remark" label="备注">
            <Input.TextArea rows={2} placeholder="可选备注信息" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
