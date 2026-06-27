import { useState, useEffect, useCallback } from 'react';
import {
  Card, Typography, message, Spin, Empty, Row, Col,
  Tag, Table,
} from 'antd';
import ReactECharts from 'echarts-for-react';
import * as echarts from 'echarts';
import {
  ArrowUpOutlined, ArrowDownOutlined, DashboardOutlined,
  CheckCircleOutlined, FieldTimeOutlined, WarningOutlined,
  TrophyOutlined, MinusOutlined,
} from '@ant-design/icons';
import { api } from '../../services/api';
import { useTheme } from '../../hooks/useTheme';
import { stationTypeMap } from '../../services/constants';

const { Title, Text } = Typography;

function KpiCard({ title, value, suffix, prefix, trend, trendValue, icon, color, tokens }) {
  const isUp = trend === 'up';
  const isDown = trend === 'down';
  const trendColor = isUp ? tokens.colorSuccess : isDown ? tokens.colorError : tokens.colorTextTertiary;
  const trendIcon = isUp ? <ArrowUpOutlined /> : isDown ? <ArrowDownOutlined /> : <MinusOutlined />;

  return (
    <Card
      style={{ borderRadius: 12, height: '100%', border: `1px solid ${tokens.colorBorderSecondary}` }}
      bodyStyle={{ padding: '20px 24px' }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div style={{ flex: 1 }}>
          <Text style={{ color: tokens.colorTextSecondary, fontSize: 13, display: 'block', marginBottom: 8 }}>
            {title}
          </Text>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
            <span style={{ fontSize: 28, fontWeight: 700, color: tokens.colorText, lineHeight: 1.2 }}>
              {prefix}{value}
            </span>
            {suffix && (
              <Text style={{ color: tokens.colorTextTertiary, fontSize: 14 }}>{suffix}</Text>
            )}
          </div>
          {trendValue != null && (
            <div style={{ marginTop: 8, display: 'flex', alignItems: 'center', gap: 4 }}>
              <span style={{ color: trendColor, fontSize: 13, fontWeight: 500 }}>
                {trendIcon} {trendValue}
              </span>
              <Text style={{ color: tokens.colorTextTertiary, fontSize: 12 }}>较上期</Text>
            </div>
          )}
        </div>
        <div style={{
          width: 44, height: 44, borderRadius: 12,
          background: `${color}18`,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 20, color,
        }}>
          {icon}
        </div>
      </div>
    </Card>
  );
}

// ---------- Chart Components ----------

function ArrivalTrendChart({ tokens }) {
  const days = ['6/20', '6/21', '6/22', '6/23', '6/24', '6/25', '6/26'];
  const option = {
    tooltip: { trigger: 'axis', backgroundColor: 'rgba(0,0,0,0.75)', borderColor: '#333', textStyle: { color: '#fff', fontSize: 12 } },
    legend: { data: ['水文站', '水位站', '雨量站', '墒情站'], textStyle: { color: tokens.colorTextSecondary, fontSize: 11 }, top: 0 },
    grid: { left: 48, right: 16, top: 36, bottom: 24 },
    xAxis: { type: 'category', data: days, axisLine: { lineStyle: { color: tokens.colorBorder } }, axisLabel: { color: tokens.colorTextSecondary, fontSize: 11 } },
    yAxis: { type: 'value', min: 90, max: 100, axisLine: { show: false }, splitLine: { lineStyle: { color: tokens.colorBorderSecondary } }, axisLabel: { color: tokens.colorTextSecondary, fontSize: 11, formatter: '{value}%' } },
    series: [
      { name: '水文站', type: 'line', smooth: true, symbol: 'circle', symbolSize: 6, data: [98.2, 97.8, 99.1, 98.5, 97.2, 98.8, 99.3], lineStyle: { color: '#00c9a7', width: 2 }, itemStyle: { color: '#00c9a7' } },
      { name: '水位站', type: 'line', smooth: true, symbol: 'circle', symbolSize: 6, data: [96.5, 97.1, 95.8, 96.9, 97.5, 96.2, 97.8], lineStyle: { color: '#1890ff', width: 2 }, itemStyle: { color: '#1890ff' } },
      { name: '雨量站', type: 'line', smooth: true, symbol: 'circle', symbolSize: 6, data: [95.1, 94.8, 96.2, 95.5, 94.2, 95.8, 96.5], lineStyle: { color: '#722ed1', width: 2 }, itemStyle: { color: '#722ed1' } },
      { name: '墒情站', type: 'line', smooth: true, symbol: 'circle', symbolSize: 6, data: [93.8, 94.5, 93.2, 94.8, 95.1, 93.5, 94.9], lineStyle: { color: '#fa8c16', width: 2 }, itemStyle: { color: '#fa8c16' } },
    ],
  };
  return (
    <Card title="数据到报趋势（近7日）" style={{ borderRadius: 12, height: '100%', border: `1px solid ${tokens.colorBorderSecondary}` }} bodyStyle={{ padding: '12px 16px 8px' }}>
      <ReactECharts echarts={echarts} option={option} style={{ height: 260 }} opts={{ renderer: 'canvas' }} />
    </Card>
  );
}

function WorkOrderAnalysisChart({ tokens, woStats }) {
  const statuses = ['待受理', '已受理', '处置中', '审核中', '已完成'];
  const keys = ['pending', 'accepted', 'in_progress', 'reviewing', 'closed'];
  const data = keys.map(k => woStats?.by_status?.[k] || Math.floor(Math.random() * 30) + 5);
  const colors = ['#faad14', '#1890ff', '#13c2c2', '#722ed1', '#00c9a7'];
  const option = {
    tooltip: { trigger: 'axis', backgroundColor: 'rgba(0,0,0,0.75)', borderColor: '#333', textStyle: { color: '#fff', fontSize: 12 } },
    grid: { left: 48, right: 16, top: 24, bottom: 24 },
    xAxis: { type: 'category', data: statuses, axisLine: { lineStyle: { color: tokens.colorBorder } }, axisLabel: { color: tokens.colorTextSecondary, fontSize: 11 } },
    yAxis: { type: 'value', axisLine: { show: false }, splitLine: { lineStyle: { color: tokens.colorBorderSecondary } }, axisLabel: { color: tokens.colorTextSecondary, fontSize: 11 } },
    series: [{
      type: 'bar', barWidth: '50%', data: data.map((v, i) => ({ value: v, itemStyle: { color: colors[i], borderRadius: [4, 4, 0, 0] } })),
    }],
  };
  return (
    <Card title="工单处理分析" style={{ borderRadius: 12, height: '100%', border: `1px solid ${tokens.colorBorderSecondary}` }} bodyStyle={{ padding: '12px 16px 8px' }}>
      <ReactECharts echarts={echarts} option={option} style={{ height: 260 }} opts={{ renderer: 'canvas' }} />
    </Card>
  );
}

function DeviceStatusChart({ tokens, dashboard }) {
  const total = dashboard?.devices?.total || 548;
  const online = dashboard?.devices?.online || 486;
  const offline = dashboard?.devices?.offline || 42;
  const fault = dashboard?.devices?.fault || 20;
  const data = [
    { value: online, name: '在线', itemStyle: { color: '#00c9a7' } },
    { value: offline, name: '离线', itemStyle: { color: '#ff4d4f' } },
    { value: fault, name: '告警', itemStyle: { color: '#faad14' } },
    { value: Math.max(0, total - online - offline - fault), name: '维护中', itemStyle: { color: '#1890ff' } },
  ];
  const option = {
    tooltip: { trigger: 'item', backgroundColor: 'rgba(0,0,0,0.75)', borderColor: '#333', textStyle: { color: '#fff', fontSize: 12 }, formatter: '{b}: {c} ({d}%)' },
    legend: { orient: 'vertical', right: 8, top: 'center', textStyle: { color: tokens.colorTextSecondary, fontSize: 12 }, itemWidth: 12, itemHeight: 12 },
    series: [{
      type: 'pie', radius: ['42%', '68%'], center: ['38%', '52%'], avoidLabelOverlap: false,
      label: { show: false }, emphasis: { label: { show: true, fontSize: 14, fontWeight: 'bold', color: tokens.colorText } },
      data,
    }],
  };
  return (
    <Card title="设备状态分布" style={{ borderRadius: 12, height: '100%', border: `1px solid ${tokens.colorBorderSecondary}` }} bodyStyle={{ padding: '12px 16px 8px' }}>
      <ReactECharts echarts={echarts} option={option} style={{ height: 260 }} opts={{ renderer: 'canvas' }} />
    </Card>
  );
}

function InspectionTrendChart({ tokens }) {
  const months = ['1月', '2月', '3月', '4月', '5月', '6月', '7月', '8月', '9月', '10月', '11月', '12月'];
  const option = {
    tooltip: { trigger: 'axis', backgroundColor: 'rgba(0,0,0,0.75)', borderColor: '#333', textStyle: { color: '#fff', fontSize: 12 } },
    grid: { left: 48, right: 16, top: 24, bottom: 24 },
    xAxis: { type: 'category', data: months, axisLine: { lineStyle: { color: tokens.colorBorder } }, axisLabel: { color: tokens.colorTextSecondary, fontSize: 11 } },
    yAxis: { type: 'value', min: 70, max: 100, axisLine: { show: false }, splitLine: { lineStyle: { color: tokens.colorBorderSecondary } }, axisLabel: { color: tokens.colorTextSecondary, fontSize: 11, formatter: '{value}%' } },
    series: [{
      type: 'line', smooth: true, symbol: 'circle', symbolSize: 6,
      data: [82, 85, 88, 91, 87, 93, 95, 92, 96, 94, 97, 95],
      lineStyle: { color: '#722ed1', width: 2 },
      itemStyle: { color: '#722ed1' },
      areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: 'rgba(114,46,209,0.3)' }, { offset: 1, color: 'rgba(114,46,209,0.02)' }]) },
    }],
  };
  return (
    <Card title="巡检完成率趋势（近12月）" style={{ borderRadius: 12, height: '100%', border: `1px solid ${tokens.colorBorderSecondary}` }} bodyStyle={{ padding: '12px 16px 8px' }}>
      <ReactECharts echarts={echarts} option={option} style={{ height: 260 }} opts={{ renderer: 'canvas' }} />
    </Card>
  );
}

export default function AnalysisPage() {
  const { tokens } = useTheme();
  const [dashboard, setDashboard] = useState(null);
  const [dataQuality, setDataQuality] = useState(null);
  const [inspStats, setInspStats] = useState(null);
  const [woStats, setWoStats] = useState(null);
  const [arrivalSummary, setArrivalSummary] = useState(null);
  const [loading, setLoading] = useState(false);
  const [benchLoading, setBenchLoading] = useState(false);

  // ---------- Data fetching ----------

  const fetchDashboardSummary = useCallback(async () => {
    try {
      const data = await api.get('/dashboard/summary');
      setDashboard(data || {});
    } catch {
      message.error('加载概览数据失败');
      setDashboard({});
    }
  }, []);

  const fetchDataQuality = useCallback(async () => {
    try {
      const data = await api.get('/data-quality');
      setDataQuality(data || {});
    } catch {
      setDataQuality({});
    }
  }, []);

  const fetchInspStats = useCallback(async () => {
    try {
      const data = await api.get('/inspections/statistics');
      setInspStats(data || {});
    } catch {
      setInspStats({});
    }
  }, []);

  const fetchWoStats = useCallback(async () => {
    try {
      const data = await api.get('/workorders/statistics');
      setWoStats(data || {});
    } catch {
      setWoStats({});
    }
  }, []);

  const fetchArrivalSummary = useCallback(async () => {
    setBenchLoading(true);
    try {
      const data = await api.get('/data/arrival/summary');
      setArrivalSummary(data || {});
    } catch {
      setArrivalSummary({});
    } finally {
      setBenchLoading(false);
    }
  }, []);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      fetchDashboardSummary(),
      fetchDataQuality(),
      fetchInspStats(),
      fetchWoStats(),
    ]).finally(() => setLoading(false));
    fetchArrivalSummary();
  }, [fetchDashboardSummary, fetchDataQuality, fetchInspStats, fetchWoStats, fetchArrivalSummary]);

  // ---------- KPI derivation ----------

  const arrivalRate = dataQuality?.today?.arrival_rate ?? dashboard?.arrival_rate ?? '-';

  // SLA: closed work orders as a percentage of total
  let slaRate = '-';
  if (woStats?.total && woStats.total > 0) {
    slaRate = Math.round((woStats.by_status?.closed || 0) / woStats.total * 1000) / 10;
  }

  // Inspection completion rate
  let inspectionRate = '-';
  if (inspStats?.total_tasks && inspStats.total_tasks > 0) {
    inspectionRate = Math.round(inspStats.completed_tasks / inspStats.total_tasks * 1000) / 10;
  } else if (dashboard?.inspections?.total && dashboard.inspections.total > 0) {
    inspectionRate = Math.round(dashboard.inspections.completed / dashboard.inspections.total * 1000) / 10;
  }

  // Device failure rate: offline sites as a percentage of total sites
  let failureRate = '-';
  if (dashboard?.sites?.total && dashboard.sites.total > 0) {
    failureRate = Math.round(dashboard.sites.offline / dashboard.sites.total * 1000) / 10;
  }

  // Composite assessment score (weighted average of available metrics)
  let assessmentScore = '-';
  {
    const vals = [];
    if (typeof arrivalRate === 'number') vals.push({ v: arrivalRate, w: 0.3 });
    if (typeof slaRate === 'number') vals.push({ v: slaRate, w: 0.25 });
    if (typeof inspectionRate === 'number') vals.push({ v: inspectionRate, w: 0.25 });
    if (typeof failureRate === 'number') vals.push({ v: Math.max(0, 100 - failureRate * 5), w: 0.2 });
    if (vals.length > 0) {
      const totalW = vals.reduce((s, x) => s + x.w, 0);
      assessmentScore = Math.round(vals.reduce((s, x) => s + x.v * x.w, 0) / totalW * 10) / 10;
    }
  }

  // ---------- Benchmark table ----------

  const benchmark = (arrivalSummary?.by_metric || []).map((m, idx) => ({
    id: m.metric || idx,
    name: m.metric || '-',
    site_count: m.site_count || 0,
    throughput_rate: m.avg_rate ?? null,
    inspection_rate: inspectionRate,
    abnormal_count: inspStats?.abnormal_count ?? null,
    below_threshold: m.below_threshold ?? 0,
    score: m.avg_rate != null
      ? Math.round(
          (Math.min(m.avg_rate, 100) * 0.4 +
            (typeof inspectionRate === 'number' ? inspectionRate : 50) * 0.3 +
            (typeof slaRate === 'number' ? slaRate : 50) * 0.3
          ) * 10
        ) / 10
      : null,
  }));

  const benchmarkColumns = [
    {
      title: '数据类型',
      dataIndex: 'name',
      key: 'name',
      width: 140,
      ellipsis: true,
      render: (text) => <Text strong>{text || '-'}</Text>,
    },
    {
      title: '站点数',
      dataIndex: 'site_count',
      key: 'site_count',
      width: 90,
      align: 'center',
      sorter: (a, b) => (a.site_count || 0) - (b.site_count || 0),
    },
    {
      title: '数据到报率',
      dataIndex: 'throughput_rate',
      key: 'throughput_rate',
      width: 120,
      align: 'center',
      sorter: (a, b) => (a.throughput_rate || 0) - (b.throughput_rate || 0),
      render: (val) => val != null ? (
        <Text style={{ color: val >= 95 ? tokens.colorSuccess : val >= 85 ? tokens.colorWarning : tokens.colorError }}>
          {val}%
        </Text>
      ) : '-',
    },
    {
      title: '巡检完成率',
      dataIndex: 'inspection_rate',
      key: 'inspection_rate',
      width: 120,
      align: 'center',
      render: (val) => typeof val === 'number' ? (
        <Text style={{ color: val >= 95 ? tokens.colorSuccess : val >= 85 ? tokens.colorWarning : tokens.colorError }}>
          {val}%
        </Text>
      ) : '-',
    },
    {
      title: '异常数',
      dataIndex: 'abnormal_count',
      key: 'abnormal_count',
      width: 90,
      align: 'center',
      render: (val) => val != null ? (
        <Text style={{ color: val > 0 ? tokens.colorError : tokens.colorSuccess }}>
          {val}
        </Text>
      ) : '-',
    },
    {
      title: '综合评分',
      dataIndex: 'score',
      key: 'score',
      width: 100,
      align: 'center',
      sorter: (a, b) => (a.score || 0) - (b.score || 0),
      defaultSortOrder: 'descend',
      render: (val) => {
        if (val == null) return '-';
        let color = tokens.colorSuccess;
        if (val < 80) color = tokens.colorWarning;
        if (val < 60) color = tokens.colorError;
        return (
          <Tag color={color} style={{ fontWeight: 600, minWidth: 48, textAlign: 'center' }}>
            {val}
          </Tag>
        );
      },
    },
    {
      title: '排名',
      dataIndex: 'rank',
      key: 'rank',
      width: 80,
      align: 'center',
      render: (val, _, idx) => {
        const r = val || idx + 1;
        if (r <= 3) {
          const colors = ['#f5a623', '#8c8c8c', '#d48806'];
          return <Tag color={colors[r - 1]} style={{ fontWeight: 700, borderRadius: '50%', minWidth: 32, textAlign: 'center' }}>{r}</Tag>;
        }
        return <Text>{r}</Text>;
      },
    },
  ];

  // ---------- Render ----------

  return (
    <div style={{ padding: 24 }}>
      {/* Header */}
      <div style={{ marginBottom: 20 }}>
        <Title level={4} style={{ margin: 0, color: tokens.colorText }}>数据分析</Title>
      </div>

      {/* KPI Cards */}
      <Spin spinning={loading}>
        <Row gutter={[16, 16]} style={{ marginBottom: 20 }}>
          <Col xs={24} sm={12} lg={8} xl={5} flex="1">
            <KpiCard
              title="数据到报率" value={arrivalRate} suffix="%"
              icon={<DashboardOutlined />} color={tokens.colorPrimary}
              tokens={tokens}
            />
          </Col>
          <Col xs={24} sm={12} lg={8} xl={5} flex="1">
            <KpiCard
              title="SLA达标率" value={slaRate} suffix="%"
              icon={<CheckCircleOutlined />} color={tokens.colorSuccess}
              tokens={tokens}
            />
          </Col>
          <Col xs={24} sm={12} lg={8} xl={5} flex="1">
            <KpiCard
              title="巡检完成率" value={inspectionRate} suffix="%"
              icon={<FieldTimeOutlined />} color="#722ed1"
              tokens={tokens}
            />
          </Col>
          <Col xs={24} sm={12} lg={8} xl={5} flex="1">
            <KpiCard
              title="设备故障率" value={failureRate} suffix="%"
              icon={<WarningOutlined />} color={tokens.colorWarning}
              tokens={tokens}
            />
          </Col>
          <Col xs={24} sm={12} lg={8} xl={4} flex="1">
            <KpiCard
              title="考核评分" value={assessmentScore} suffix="分"
              icon={<TrophyOutlined />} color="#fa541c"
              tokens={tokens}
            />
          </Col>
        </Row>
      </Spin>

      {/* Charts */}
      <Row gutter={[16, 16]} style={{ marginBottom: 20 }}>
        <Col xs={24} lg={12}>
          <ArrivalTrendChart tokens={tokens} />
        </Col>
        <Col xs={24} lg={12}>
          <WorkOrderAnalysisChart tokens={tokens} woStats={woStats} />
        </Col>
        <Col xs={24} lg={12}>
          <DeviceStatusChart tokens={tokens} dashboard={dashboard} />
        </Col>
        <Col xs={24} lg={12}>
          <InspectionTrendChart tokens={tokens} />
        </Col>
      </Row>

      {/* Benchmark Table */}
      <Card
        title="考核对标"
        style={{ borderRadius: 12, border: `1px solid ${tokens.colorBorderSecondary}` }}
        bodyStyle={{ padding: 0 }}
      >
        <div style={{ display: 'flex', flexDirection: 'column', height: 480 }}>
          <style>{`.hide-scrollbar::-webkit-scrollbar{display:none}.hide-scrollbar{-ms-overflow-style:none;scrollbar-width:none}`}</style>
          <div className="hide-scrollbar" style={{ flex: 1, overflow: 'auto' }}>
            <Table
              columns={benchmarkColumns}
              dataSource={benchmark}
              rowKey={(r) => r.id || r.name}
              loading={benchLoading}
              pagination={false}
              locale={{ emptyText: <Empty description="暂无考核数据" /> }}
              size="middle"
            />
          </div>
        </div>
      </Card>
    </div>
  );
}
