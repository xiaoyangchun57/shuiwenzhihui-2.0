// Station type mappings
export const stationTypeMap = {
  rainfall: '雨量站',
  water_level: '水位站',
  hydrology: '水文站',
  soil_moisture: '墒情站',
  evaporation: '蒸发站',
  groundwater: '地下水站',
  station_yard: '站院',
};

// Work order status mappings
export const orderStatusMap = {
  pending: '待受理',
  accepted: '已受理',
  generated: '已生成',
  dispatched: '已派发',
  in_progress: '处置中',
  reviewing: '审核中',
  acceptance: '验收中',
  closed: '已完成',
};

// Work order level mappings
export const orderLevelMap = {
  normal: '一般',
  urgent: '紧急',
  critical: '重大',
  red: '重大',
  orange: '紧急',
  yellow: '一般',
  blue: '一般',
};

// Work order source mappings
export const orderSourceMap = {
  auto: '自动',
  patrol: '巡查',
  manual: '人工',
  superior: '上级',
  hotline: '热线',
  alert_convert: '告警转工单',
  alert_auto: '告警自动生成',
};

// Metric name mappings
export const metricMap = {
  water_level: '水位',
  rainfall: '降雨',
  precipitation: '降雨量',
  cumulative_rainfall: '累计雨量',
  flow: '流量',
  velocity: '流速',
  soil_moisture: '土壤含水量',
  soil_temperature: '土壤温度',
  evaporation: '蒸发量',
  temperature: '气温',
  wind_speed: '风速',
  device_status: '设备状态',
  groundwater_level: '地下水位',
  water_quality: '水质',
  noise: '噪声',
  data_spike: '数据突变',
  data_freeze: '数据冻结',
  data_gap: '数据缺失',
};

// Device type mappings
export const deviceTypeMap = {
  rainfall_gauge: '翻斗式雨量计',
  electronic_rainfall: '电子雨量计',
  radar_water_level: '雷达水位计',
  pressure_water_level: '压力式水位计',
  flow_meter: '流速计',
  hydro_collector: '水文采集仪',
  current_meter: '流速仪',
  rainfall_meter: '雨量计',
  water_level_meter: '水位计',
  soil_moisture_sensor: '土壤水分传感器',
  soil_temperature: '土壤温度计',
  evaporation_pan: '蒸发皿',
  weather_screen: '气象百叶箱',
  anemometer: '风速仪',
};

// Inspection type mappings
export const inspectionTypeMap = {
  daily: '日常',
  weekly: '定期',
  monthly: '月度',
  special: '专项',
};

// Alert level colors
export const alertLevelColor = {
  blue: '#38bdf8',
  yellow: '#facc15',
  orange: '#fb923c',
  red: '#ef4444',
};

export const alertLevelLabel = {
  blue: '蓝色关注',
  yellow: '黄色警示',
  orange: '橙色预警',
  red: '红色警报',
};

// Work order status badge color mapping
export const orderStatusBadge = {
  pending: 'default',
  accepted: 'processing',
  generated: 'cyan',
  dispatched: 'warning',
  in_progress: 'success',
  reviewing: 'purple',
  acceptance: 'gold',
  closed: 'green',
};

// Alert status mappings
export const alertStatusMap = {
  pending: '待处理',
  acknowledged: '处理中',
  resolved: '已办结',
};

// Timeline event type mappings
export const timelineEventMap = {
  alert: '告警',
  order: '工单',
  inspection: '巡检',
  maintenance: '运维',
  water_level: '水位校验',
  acknowledged: '确认',
  urged: '督办',
  converted: '转工单',
  created: '创建',
  completed: '完成',
  checked: '校验',
  auto_checked: '自动校验',
  alert_generated: '触发告警',
  acceptance: '验收中',
  closed: '已关闭',
};
