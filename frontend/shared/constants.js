/** ══════════════════════════════════
 *  水文监测智慧运营平台 - 共享常量层
 *  ⚠️ 旧版（dashboard/mobile 用）
 *  新版开发请用 react-vite/src/services/constants.js
 * ══════════════════════════════════ */
/* Dashboard用 const；Mobile用 var（函数作用域） */

// 站点类型映射
var TM={rainfall:'雨量站',water_level:'水位站',hydrology:'水文站',soil_moisture:'墒情站',evaporation:'蒸发站',groundwater:'地下水站',station_yard:'站院'};

// 工单状态映射（同事版本：待受理→已受理→已派发→处置中→审核中→已完成）
var SM={pending:'待受理',accepted:'已受理',generated:'已生成',dispatched:'已派发',in_progress:'处置中',reviewing:'审核中',acceptance:'验收中',closed:'已完成'};

// 工单级别映射（支持告警颜色映射到工单级别，兼容历史数据）
var LM={normal:'一般',urgent:'紧急',critical:'重大', red:'重大', orange:'紧急', yellow:'一般', blue:'一般'};

// 工单来源映射
var SL={auto:'自动',patrol:'巡查',manual:'人工',superior:'上级',hotline:'热线'};

// 指标名称映射（通用传感器指标）
var MT={water_level:'水位',rainfall:'降雨',precipitation:'降雨量',cumulative_rainfall:'累计雨量',flow:'流量',velocity:'流速',soil_moisture:'土壤含水量',soil_temperature:'土壤温度',evaporation:'蒸发量',temperature:'气温',wind_speed:'风速',device_status:'设备状态'};

// 指标名称映射（带单位，移动端使用）
var MCN={precipitation:'降雨量(mm/h)',cumulative_rainfall:'累计降雨量(mm)',water_level:'水位(m)',flow_rate:'流量(m³/s)',temperature:'温度(°C)',humidity:'湿度(%)',soil_moisture:'土壤含水量(%)',evaporation:'蒸发量(mm)',pressure:'压力(MPa)',vibration:'振动(mm/s)',battery:'电池电量(V)',signal_strength:'信号强度(dBm)'};

// 设备类型映射
var DT={rainfall_gauge:'翻斗式雨量计',electronic_rainfall:'电子雨量计',radar_water_level:'雷达水位计',pressure_water_level:'压力式水位计',flow_meter:'流速计',hydro_collector:'水文采集仪',current_meter:'流速仪',rainfall_meter:'雨量计',water_level_meter:'水位计',soil_moisture_sensor:'土壤水分传感器',soil_temperature:'土壤温度计',evaporation_pan:'蒸发皿',weather_screen:'气象百叶箱',anemometer:'风速仪'};

// 巡检类型映射
var ITM={daily:'日常',weekly:'定期',monthly:'月度',special:'专项'};

// 设备类型中文映射（用于设备台账筛选）
var DEVICE_TYPE_CN={'rainfall_gauge':'雨量计','electronic_rainfall':'电子雨量计','radar_water_level':'雷达水位计','pressure_water_level':'压力式水位计','flow_meter':'流速计','hydro_collector':'采集仪','current_meter':'流速仪','rainfall_meter':'雨量计','water_level_meter':'水位计','soil_moisture_sensor':'土壤水分传感器','soil_temperature':'土壤温度计','evaporation_pan':'蒸发皿','weather_screen':'百叶箱','anemometer':'风速仪','arrow':'箭头'};

// 指标中文映射（用于告警等）
var METRIC_CN={'precipitation':'雨量','water_level':'水位','flow':'流量','vibration':'振动','seepage':'渗流','temperature':'温度','humidity':'湿度','rainfall':'雨量','water_level_upstream':'上游水位','device_status':'设备状态','water_level_diff':'水位差值'};

// 站点类型在地图上的颜色
var CLR={rainfall:'#FF0000',water_level:'#FF0000',hydrology:'#FF0000',soil_moisture:'#FFA600',evaporation:'#1890FF',groundwater:'#00CCFF',station_yard:'#1890FF'};

// 告警级别颜色映射（dashboard用四级：蓝黄橙红）
var ALERT_LEVEL_COLOR={blue:'#1890ff',yellow:'#faad14',orange:'#fa8c16',red:'#f5222d'};
var ALERT_LEVEL_LABEL={blue:'蓝色关注',yellow:'黄色警示',orange:'橙色预警',red:'红色警报'};

// 工单流转状态颜色映射（dashboard用）
var OB={'pending':'gray','accepted':'blue','generated':'cyan','dispatched':'org','in_progress':'grn','reviewing':'purple','acceptance':'yellow','closed':'darkgrn'};

// 工单流转进度百分比（移动端用）
var WO_PCT={pending:0,accepted:15,generated:0,dispatched:0,in_progress:40,reviewing:70,acceptance:90,closed:100};

// 工单流转状态条CSS类名（移动端用）
var SB_CLASS={pending:'sb-pending',accepted:'sb-accepted',generated:'sb-generated',dispatched:'sb-dispatched',in_progress:'sb-inprogress',reviewing:'sb-reviewing',acceptance:'sb-acceptance',closed:'sb-closed'};

// 事件类型中文映射（时间线用）
var TL_CN={alert:'告警',order:'工单',inspection:'巡检',maintenance:'运维',water_level:'水位校验',acknowledged:'确认',urged:'督办',converted:'转工单',created:'创建',completed:'完成',checked:'校验',auto_checked:'自动校验',alert_generated:'触发告警',acceptance:'验收中',closed:'已关闭'};

// 告警状态颜色映射（dashboard用）
var ALERT_STATUS_COLOR={pending:'#ffa040',acknowledged:'#5ea8c8',resolved:'#2ea080'};
var ALERT_STATUS_LABEL={pending:'待处理',acknowledged:'处理中',resolved:'已办结'};

// 指标名称映射（移动端用辅助函数）
var _mcn=function(key){return MCN[key]||key};
