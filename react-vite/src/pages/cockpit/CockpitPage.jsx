import { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Card,
  List,
  Tag,
  Badge,
  Typography,
  Button,
  Segmented,
  Input,
  Space,
  Statistic,
  Spin,
  Empty,
  Tooltip,
} from 'antd';
import {
  EnvironmentOutlined,
  AlertOutlined,
  ThunderboltOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  ExclamationCircleOutlined,
  SearchOutlined,
  LeftOutlined,
  RightOutlined,
  ReloadOutlined,
  DashboardOutlined,
  ToolOutlined,
  CloudServerOutlined,
  EyeOutlined,
  SoundOutlined,
  ClockCircleOutlined,
  ApiOutlined,
  FilterOutlined,
  FileSearchOutlined,
  AimOutlined,
  WarningOutlined,
  FullscreenOutlined,
  ShrinkOutlined,
  BarChartOutlined,
  PushpinOutlined,
  PushpinFilled,
} from '@ant-design/icons';
import { MapContainer, TileLayer, Marker, Popup, useMap } from 'react-leaflet';
import L, { divIcon } from 'leaflet';
import { useTheme } from '../../hooks/useTheme';
import { api } from '../../services/api';
import { stationTypeMap, metricMap, alertLevelColor, alertLevelLabel } from '../../services/constants';
import { stationTypeColors, statusColors } from '../../theme/tokens';
import { formatDate, relativeTimeStr, truncate } from '../../utils/helpers';

const { Text, Title } = Typography;
const { Search } = Input;

const stationIconMap = {
  rainfall: '/icons/stations/雨量站.svg',
  water_level: '/icons/stations/水位站.svg',
  hydrology: '/icons/stations/水文站.svg',
  soil_moisture: '/icons/stations/墒情站.svg',
  evaporation: '/icons/stations/蒸发站.svg',
  groundwater: '/icons/stations/地下水.svg',
  station_yard: '/icons/stations/站院.svg',
};

// ---------------------------------------------------------------------------
// CSS-in-JS style tag for map-specific styles
// ---------------------------------------------------------------------------
const cockpitStyles = `
  /* Leaflet container reset */
  .cockpit-map .leaflet-container {
    width: 100%;
    height: 100%;
    background: #0a1628;
    font-family: inherit;
  }
  .cockpit-map .leaflet-control-zoom {
    border: none !important;
    box-shadow: 0 2px 8px rgba(0,0,0,0.3) !important;
  }
  .cockpit-map .leaflet-control-zoom a {
    background: rgba(12,28,52,0.85) !important;
    color: #d0e8ff !important;
    border: 1px solid rgba(0,200,180,0.15) !important;
    backdrop-filter: blur(8px);
    width: 32px !important;
    height: 32px !important;
    line-height: 32px !important;
    font-size: 16px !important;
  }
  .cockpit-map .leaflet-control-zoom a:hover {
    background: rgba(0,201,167,0.2) !important;
  }

  /* Marker breathing animation - soft glow, multi-color support */
  @keyframes markerBreathe {
    0%, 100% {
      box-shadow: 0 0 3px 1px var(--glow-color, rgba(239, 68, 68, 0.25));
      transform: scale(1);
    }
    50% {
      box-shadow: 0 0 8px 3px var(--glow-color, rgba(239, 68, 68, 0.12));
      transform: scale(1.08);
    }
  }
  /* Tighter breathing for smaller markers - minimal scale change */
  @keyframes markerBreatheTight {
    0%, 100% {
      box-shadow: 0 0 2px 1px var(--glow-color, rgba(239, 68, 68, 0.2));
      transform: scale(1);
    }
    50% {
      box-shadow: 0 0 5px 2px var(--glow-color, rgba(239, 68, 68, 0.08));
      transform: scale(1.04);
    }
  }
  /* Prominent breathing for alert markers - larger scale, stronger glow */
  @keyframes markerBreatheBig {
    0%, 100% {
      box-shadow: 0 0 4px 2px var(--glow-color, rgba(239, 68, 68, 0.35));
      transform: scale(1);
    }
    50% {
      box-shadow: 0 0 12px 5px var(--glow-color, rgba(239, 68, 68, 0.1));
      transform: scale(1.12);
    }
  }
  @keyframes markerPulse {
    0% { box-shadow: 0 0 3px 1px var(--glow-color, rgba(239, 68, 68, 0.3)); }
    50% { box-shadow: 0 0 10px 4px var(--glow-color, rgba(239, 68, 68, 0.08)); }
    100% { box-shadow: 0 0 3px 1px var(--glow-color, rgba(239, 68, 68, 0.3)); }
  }
  @keyframes ripple {
    0% { width: 20px; height: 20px; opacity: 0.5; }
    100% { width: 44px; height: 44px; opacity: 0; }
  }

  .marker-normal {
    border-radius: 50%;
    border: 2px solid rgba(255,255,255,0.8);
    box-shadow: 0 2px 8px rgba(0,0,0,0.3);
    transition: transform 0.2s, box-shadow 0.2s;
  }
  .marker-normal:hover {
    transform: scale(1.25);
    box-shadow: 0 2px 12px rgba(0,0,0,0.5);
  }

  .marker-alert {
    border-radius: 50%;
    border: 2px solid var(--alert-border, #ef4444);
    animation: markerBreathe 2.5s ease-in-out infinite;
    position: relative;
  }
  .marker-alert::after {
    content: '';
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    border-radius: 50%;
    border: 1.5px solid var(--alert-ripple, rgba(239, 68, 68, 0.4));
    animation: ripple 2.5s ease-out infinite;
    pointer-events: none;
  }

  .marker-normal-svg {
    transition: transform 0.2s;
    filter: drop-shadow(0 2px 4px rgba(0,0,0,0.4));
  }
  .marker-normal-svg:hover {
    transform: scale(1.3);
  }
  .marker-alert-svg {
    border-radius: 50%;
    overflow: hidden;
    animation: markerBreatheRing 2.5s ease-in-out infinite;
  }
  @keyframes markerBreatheRing {
    0%, 100% { box-shadow: 0 0 0 0 var(--glow-color, rgba(239, 68, 68, 0.3)); }
    50% { box-shadow: 0 0 0 4px var(--glow-color, rgba(239, 68, 68, 0)); }
  }

  /* Site dot breathing animation for alert sites */
  @keyframes dotBreathe {
    0%, 100% { box-shadow: 0 0 3px 1px var(--glow-color, rgba(239, 68, 68, 0.25)); transform: scale(1); }
    50% { box-shadow: 0 0 7px 2px var(--glow-color, rgba(239, 68, 68, 0.12)); transform: scale(1.15); }
  }
  .site-dot-alert {
    animation: dotBreathe 2.5s ease-in-out infinite;
  }

  /* Floating panel base */
  .cockpit-panel {
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
    border-radius: 12px;
    transition: all 0.35s cubic-bezier(0.4, 0, 0.2, 1);
    overflow: hidden;
  }

  /* Alert ticker animation */
  @keyframes tickerScroll {
    0% { transform: translateX(100%); }
    100% { transform: translateX(-100%); }
  }
  .alert-ticker-content {
    animation: tickerScroll 30s linear infinite;
    white-space: nowrap;
  }
  .alert-ticker-content:hover {
    animation-play-state: paused;
  }

  /* Scrollbar styling for panels */
  .cockpit-scroll::-webkit-scrollbar {
    width: 4px;
  }
  .cockpit-scroll::-webkit-scrollbar-track {
    background: transparent;
  }
  .cockpit-scroll::-webkit-scrollbar-thumb {
    background: rgba(0,200,180,0.2);
    border-radius: 4px;
  }
  .cockpit-scroll::-webkit-scrollbar-thumb:hover {
    background: rgba(0,200,180,0.4);
  }

  /* Override antd Card styles inside cockpit */
  .cockpit-panel .ant-card {
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
  }
  .cockpit-panel .ant-card-head {
    border-bottom: 1px solid rgba(0,200,180,0.1) !important;
    min-height: 40px !important;
    padding: 0 16px !important;
  }
  .cockpit-panel .ant-card-head-title {
    font-size: 13px !important;
    padding: 10px 0 !important;
  }
  .cockpit-panel .ant-card-body {
    padding: 12px 16px !important;
  }
  .cockpit-panel .ant-list-item {
    padding: 8px 0 !important;
    border-bottom: 1px solid rgba(0,200,180,0.06) !important;
  }
  .cockpit-panel .ant-list-item:last-child {
    border-bottom: none !important;
  }
  .cockpit-panel .ant-statistic-title {
    font-size: 11px !important;
  }
  .cockpit-panel .ant-statistic-content-value {
    font-size: 20px !important;
  }
`;

// ---------------------------------------------------------------------------
// Inject styles once
// ---------------------------------------------------------------------------
let styleInjected = false;
function injectStyles() {
  if (styleInjected) return;
  if (typeof document === 'undefined') return;
  const tag = document.createElement('style');
  tag.setAttribute('data-cockpit', 'true');
  tag.textContent = cockpitStyles;
  document.head.appendChild(tag);
  styleInjected = true;
}

// ---------------------------------------------------------------------------
// Helper: create marker icon
// Breathing light color indicates site status:
//   online = no breathing (static green ring)
//   offline = red breathing
//   data anomaly = yellow breathing
//   pending inspection = gray breathing
// ---------------------------------------------------------------------------
function createMarkerIcon(type, markerStatus) {
  const iconSize = 24;
  const svgUrl = stationIconMap[type] || stationIconMap.hydrology;

  // Status-based glow colors
  const glowColors = {
    anomaly: 'rgba(250, 204, 21, 0.6)',
    offline: 'rgba(239,68,68,0.6)',
    pending: 'rgba(140,140,140,0.5)',
  };

  if (markerStatus !== 'normal') {
    // Alert/offline/pending: prominent breathing ring
    const glowColor = glowColors[markerStatus] || glowColors.offline;
    const containerSize = 36;
    return divIcon({
      className: '',
      iconSize: [containerSize, containerSize],
      iconAnchor: [containerSize / 2, containerSize / 2],
      popupAnchor: [0, -containerSize / 2 - 4],
      html: `<div style="position:relative;width:${containerSize}px;height:${containerSize}px;display:flex;align-items:center;justify-content:center;">
        <div style="position:absolute;inset:0;border-radius:50%;background:${glowColor};animation:markerBreatheBig 2s ease-in-out infinite;--glow-color:${glowColor};pointer-events:none;"></div>
        <img src="${svgUrl}" style="width:${iconSize}px;height:${iconSize}px;object-fit:contain;position:relative;z-index:1;filter:drop-shadow(0 2px 4px rgba(0,0,0,0.6));" />
      </div>`,
    });
  }

  // Normal (online): just the icon, no ring, minimal footprint
  return divIcon({
    className: '',
    iconSize: [iconSize, iconSize],
    iconAnchor: [iconSize / 2, iconSize / 2],
    popupAnchor: [0, -iconSize / 2 - 4],
    html: `<div style="width:${iconSize}px;height:${iconSize}px;">
      <img src="${svgUrl}" style="width:100%;height:100%;object-fit:contain;filter:drop-shadow(0 1px 2px rgba(0,0,0,0.4));" />
    </div>`,
  });
}

// ---------------------------------------------------------------------------
// Sub-component: fit map to markers
// ---------------------------------------------------------------------------
function MapAutoFitter({ sites }) {
  const map = useMap();
  const fitted = useRef(false);

  useEffect(() => {
    if (fitted.current || !sites || sites.length === 0) return;
    const validSites = sites.filter((s) => s.lat && s.lng);
    if (validSites.length === 0) return;

    const bounds = L.latLngBounds(validSites.map((s) => [s.lat, s.lng]));
    map.fitBounds(bounds, { padding: [60, 60], maxZoom: 14 });
    fitted.current = true;
  }, [map, sites]);

  return null;
}

// ---------------------------------------------------------------------------
// Sub-component: fly to a specific position
// ---------------------------------------------------------------------------
function MapFlyTo({ position, zoom }) {
  const map = useMap();
  useEffect(() => {
    if (position) {
      map.flyTo(position, zoom || 15, { duration: 1.2 });
    }
  }, [map, position, zoom]);
  return null;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------
const AMAP_SATELLITE_URL =
  'https://webst0{s}.is.autonavi.com/appmaptile?style=6&x={x}&y={y}&z={z}';
const AMAP_SUBDOMAINS = ['1', '2', '3', '4'];

const DEFAULT_CENTER = [30.27, 120.15]; // Hangzhou area default
const DEFAULT_ZOOM = 10;

const FILTER_ALL = 'all';

// ---------------------------------------------------------------------------
// Main Component
// ---------------------------------------------------------------------------
export default function CockpitPage() {
  const { isDark, tokens } = useTheme();
  const navigate = useNavigate();

  // ---- State ----
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [sites, setSites] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [devices, setDevices] = useState([]);
  const [workOrders, setWorkOrders] = useState({});

  const [typeFilter, setTypeFilter] = useState(FILTER_ALL);
  const [searchText, setSearchText] = useState('');
  const [showSearch, setShowSearch] = useState(false);
  const [flyTarget, setFlyTarget] = useState(null);

  const [leftCollapsed, setLeftCollapsed] = useState(false);
  const [rightCollapsed, setRightCollapsed] = useState(false);
  const [legendCollapsed, setLegendCollapsed] = useState(false);

  const [lastRefresh, setLastRefresh] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  const [pinnedSites, setPinnedSites] = useState(new Set());

  // Map reference and popup control
  const mapRef = useRef(null);
  const markersRef = useRef(new Map()); // Store marker instances by site ID
  const [popupOpenSiteId, setPopupOpenSiteId] = useState(null);

  // After fly-to completes, programmatically open the popup for the target site
  useEffect(() => {
    if (!flyTarget || !popupOpenSiteId || !mapRef.current) return;
    const map = mapRef.current;
    const onMoveEnd = () => {
      setTimeout(() => {
        // Open the popup for the target site (don't close others - user may have opened them manually)
        const marker = markersRef.current.get(popupOpenSiteId);
        if (marker) {
          marker.openPopup();
        }
      }, 500);
    };
    map.on('moveend', onMoveEnd);
    return () => map.off('moveend', onMoveEnd);
  }, [flyTarget, popupOpenSiteId]);

  // ---- Inject CSS ----
  useEffect(() => {
    injectStyles();
  }, []);

  // Apply theme styles to Leaflet popup wrappers via MutationObserver
  // (Leaflet renders popups in separate panes, CSS vars don't propagate)
  useEffect(() => {
    const applyPopupTheme = () => {
      const bg = isDark ? 'rgba(12,28,52,0.92)' : 'rgba(255,255,255,0.96)';
      const color = isDark ? '#d0e8ff' : tokens.colorText;
      const border = isDark ? 'rgba(0,200,180,0.2)' : 'rgba(0,0,0,0.1)';
      const shadow = isDark ? '0 4px 20px rgba(0,0,0,0.4)' : '0 4px 20px rgba(0,0,0,0.12)';
      const closeColor = isDark ? '#6db8d8' : tokens.colorTextTertiary;

      document.querySelectorAll('.leaflet-popup-content-wrapper').forEach((el) => {
        el.style.background = bg;
        el.style.color = color;
        el.style.borderRadius = '10px';
        el.style.border = `1px solid ${border}`;
        el.style.backdropFilter = 'blur(12px)';
        el.style.boxShadow = shadow;
      });
      document.querySelectorAll('.leaflet-popup-tip').forEach((el) => {
        el.style.background = bg;
        el.style.border = `1px solid ${border}`;
      });
      document.querySelectorAll('.leaflet-popup-close-button').forEach((el) => {
        el.style.color = closeColor;
      });
    };

    // Apply immediately
    applyPopupTheme();

    // Watch for new popup elements being added to DOM
    const observer = new MutationObserver((mutations) => {
      for (const mutation of mutations) {
        if (mutation.addedNodes.length > 0) {
          applyPopupTheme();
          break;
        }
      }
    });
    observer.observe(document.body, { childList: true, subtree: true });

    return () => observer.disconnect();
  }, [isDark, tokens]);

  // ---- Data Loading ----
  const fetchData = useCallback(async () => {
    setRefreshing(true);
    setError(null);
    try {
      // Fetch all data sources in parallel
      const [summary, sitesData, devicesData] = await Promise.all([
        api.get('/dashboard/summary'),
        api.get('/sites'),
        api.get('/devices'),
      ]);

      // Sites: /api/sites returns a plain array of site objects
      const sitesList = Array.isArray(sitesData) ? sitesData : [];
      setSites(sitesList);

      // Alerts: summary.latest_alerts is the array
      if (summary) {
        setAlerts(Array.isArray(summary.latest_alerts) ? summary.latest_alerts : []);
        // Work orders: summary.workorders.by_status has the status counts
        const wo = summary.workorders || {};
        setWorkOrders(wo.by_status || wo);
      }

      // Devices: /api/devices returns a plain array
      setDevices(Array.isArray(devicesData) ? devicesData : []);

      setLastRefresh(new Date());
    } catch (err) {
      console.error('CockpitPage data load error:', err);
      setError(err.message || '数据加载失败');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 60000);
    return () => clearInterval(interval);
  }, [fetchData]);

  // ---- Derived data ----
  const alertSiteIds = useMemo(() => {
    const ids = new Set();
    alerts
      .filter((a) => a.status !== 'resolved')
      .forEach((a) => ids.add(a.site_id));
    return ids;
  }, [alerts]);

  const filteredSites = useMemo(() => {
    let result = sites;
    if (typeFilter !== FILTER_ALL) {
      result = result.filter((s) => s.type === typeFilter);
    }
    if (searchText.trim()) {
      const q = searchText.trim().toLowerCase();
      result = result.filter(
        (s) =>
          (s.name && s.name.toLowerCase().includes(q)) ||
          (s.code && s.code.toLowerCase().includes(q)) ||
          (s.district && s.district.toLowerCase().includes(q))
      );
    }
    // Sort by priority: offline > anomaly (has alerts) > pinned > pending > normal
    const sorted = [...result].sort((a, b) => {
      const getPriority = (site) => {
        if (site.status === 'offline') return 0;
        if (alertSiteIds.has(site.id)) return 1;
        if (pinnedSites.has(site.id)) return 2;
        if (site.status === 'pending' || site.status === 'inspection_pending') return 3;
        return 4;
      };
      return getPriority(a) - getPriority(b);
    });
    return sorted;
  }, [sites, typeFilter, searchText, alertSiteIds, pinnedSites]);

  const healthByType = useMemo(() => {
    const typeGroups = {};
    sites.forEach((s) => {
      const t = s.type || 'other';
      if (!typeGroups[t]) typeGroups[t] = { total: 0, online: 0 };
      typeGroups[t].total++;
      if (s.status === 'online' || s.status === 'normal') typeGroups[t].online++;
    });
    return Object.entries(stationTypeMap)
      .map(([type, label]) => {
        const g = typeGroups[type];
        if (!g || g.total === 0) return null;
        return {
          type,
          label,
          total: g.total,
          online: g.online,
          rate: Math.round((g.online / g.total) * 100),
        };
      })
      .filter(Boolean);
  }, [sites]);

  const deviceStats = useMemo(() => {
    const total = devices.length;
    const online = devices.filter((d) => d.status === 'online' || d.status === 'normal').length;
    const offline = devices.filter((d) => d.status === 'offline').length;
    const fault = devices.filter((d) => d.status === 'fault' || d.status === 'error').length;
    const lowBattery = devices.filter((d) => typeof d.voltage === 'number' && d.voltage < 3.3).length;
    return { total, online, offline, fault, lowBattery };
  }, [devices]);

  const workOrderTotal = useMemo(() => {
    return Object.values(workOrders).reduce((sum, v) => sum + (typeof v === 'number' ? v : 0), 0);
  }, [workOrders]);

  const activeAlerts = useMemo(() => {
    return alerts.filter((a) => a.status !== 'resolved');
  }, [alerts]);

  // Filter alerts by station type for the right panel
  const filteredAlerts = useMemo(() => {
    if (typeFilter === FILTER_ALL) return activeAlerts;
    // Get site IDs that match the current type filter
    const matchingSiteIds = new Set(
      sites.filter((s) => s.type === typeFilter).map((s) => s.id)
    );
    return activeAlerts.filter((a) => matchingSiteIds.has(a.site_id));
  }, [activeAlerts, typeFilter, sites]);

  // Pre-compute data trends for all sites (top-level, not inside map)
  const siteDataTrends = useMemo(() => {
    const trends = {};
    sites.forEach((site) => {
      if (site.latest_value != null) {
        const base = parseFloat(site.latest_value);
        if (!isNaN(base)) {
          // Use site code as seed for deterministic mock data
          const seed = (site.code || site.id || '').split('').reduce((a, c) => a + c.charCodeAt(0), 0);
          trends[site.id] = Array.from({ length: 24 }, (_, i) => {
            const variation = Math.sin(seed + i) * base * 0.08;
            return { time: `${String(i).padStart(2, '0')}:00`, value: base + variation };
          });
        }
      }
    });
    return trends;
  }, [sites]);

  // Pure function to render SVG trend chart (no hooks)
  const renderTrendChart = (dataTrend) => {
    if (!dataTrend || dataTrend.length === 0) return null;
    const width = 280;
    const height = 80;
    const padding = 20;
    const values = dataTrend.map((d) => d.value);
    const min = Math.min(...values);
    const max = Math.max(...values);
    const range = max - min || 1;

    const points = dataTrend.map((d, i) => {
      const x = padding + (i / (dataTrend.length - 1)) * (width - padding * 2);
      const y = height - padding - ((d.value - min) / range) * (height - padding * 2);
      return `${x},${y}`;
    }).join(' ');

    return (
      <svg width={width} height={height} style={{ display: 'block', margin: '8px auto' }}>
        <line x1={padding} y1={padding} x2={width - padding} y2={padding} stroke={isDark ? 'rgba(0,200,180,0.1)' : 'rgba(0,0,0,0.06)'} strokeDasharray="2,2" />
        <line x1={padding} y1={height / 2} x2={width - padding} y2={height / 2} stroke={isDark ? 'rgba(0,200,180,0.1)' : 'rgba(0,0,0,0.06)'} strokeDasharray="2,2" />
        <line x1={padding} y1={height - padding} x2={width - padding} y2={height - padding} stroke={isDark ? 'rgba(0,200,180,0.1)' : 'rgba(0,0,0,0.06)'} strokeDasharray="2,2" />
        <text x={4} y={padding + 4} fill={isDark ? '#4a8aaa' : tokens.colorTextTertiary} fontSize="9">{max.toFixed(1)}</text>
        <text x={4} y={height / 2 + 4} fill={isDark ? '#4a8aaa' : tokens.colorTextTertiary} fontSize="9">{((max + min) / 2).toFixed(1)}</text>
        <text x={4} y={height - padding + 4} fill={isDark ? '#4a8aaa' : tokens.colorTextTertiary} fontSize="9">{min.toFixed(1)}</text>
        <polyline points={points} fill="none" stroke={isDark ? '#00c9a7' : tokens.colorPrimary} strokeWidth="2" />
        {dataTrend.map((d, i) => {
          const x = padding + (i / (dataTrend.length - 1)) * (width - padding * 2);
          const y = height - padding - ((d.value - min) / range) * (height - padding * 2);
          return <circle key={i} cx={x} cy={y} r="2" fill={isDark ? '#00c9a7' : tokens.colorPrimary} />;
        })}
        <text x={padding} y={height - 4} fill={isDark ? '#4a8aaa' : tokens.colorTextTertiary} fontSize="9">00:00</text>
        <text x={width / 2 - 10} y={height - 4} fill={isDark ? '#4a8aaa' : tokens.colorTextTertiary} fontSize="9">12:00</text>
        <text x={width - padding - 20} y={height - 4} fill={isDark ? '#4a8aaa' : tokens.colorTextTertiary} fontSize="9">23:00</text>
      </svg>
    );
  };

  // ---- Station type filter options ----
  const typeFilterOptions = useMemo(() => {
    const opts = [{ label: '全部', value: FILTER_ALL }];
    Object.entries(stationTypeMap).forEach(([key, label]) => {
      const count = sites.filter((s) => s.type === key).length;
      opts.push({
        label: `${label}(${count})`,
        value: key,
      });
    });
    return opts;
  }, [sites]);

  // ---- Event handlers ----
  const handleSiteClick = useCallback((site) => {
    if (site.lat && site.lng) {
      setFlyTarget([site.lat, site.lng]);
      setPopupOpenSiteId(site.id);
    }
  }, []);

  const togglePinSite = useCallback((siteId) => {
    setPinnedSites((prev) => {
      const next = new Set(prev);
      if (next.has(siteId)) {
        next.delete(siteId);
      } else {
        next.add(siteId);
      }
      return next;
    });
  }, []);

  const handleSearch = useCallback((value) => {
    setSearchText(value);
  }, []);

  const handleLocateAll = useCallback(() => {
    setFlyTarget(null);
    // Reset the fitter by briefly modifying sites reference (force re-render)
    setTypeFilter(FILTER_ALL);
    setSearchText('');
  }, []);

  // ---- Panel background styles ----
  const panelBg = isDark
    ? 'rgba(8, 22, 48, 0.78)'
    : 'rgba(255, 255, 255, 0.82)';
  const panelBorder = isDark
    ? '1px solid rgba(0, 200, 180, 0.12)'
    : '1px solid rgba(0, 0, 0, 0.06)';
  const panelShadow = isDark
    ? '0 4px 24px rgba(0,0,0,0.4), 0 0 1px rgba(0,200,180,0.15)'
    : '0 4px 24px rgba(0,0,0,0.08), 0 0 1px rgba(0,0,0,0.1)';

  const panelStyle = {
    background: panelBg,
    border: panelBorder,
    boxShadow: panelShadow,
    backdropFilter: 'blur(12px)',
    WebkitBackdropFilter: 'blur(12px)',
  };

  // ---- Marker rendering ----
  // Status priority for deduplication: offline > anomaly > pending > normal
  const statusPriority = { offline: 4, anomaly: 3, pending: 2, normal: 1 };

  const markers = useMemo(() => {
    const sitesWithCoords = filteredSites.filter((s) => s.lat && s.lng);

    // Group sites by location (rounded to 5 decimal places ~1m precision)
    const locationGroups = new Map();
    sitesWithCoords.forEach((site) => {
      const locKey = `${site.lat.toFixed(5)},${site.lng.toFixed(5)}`;
      if (!locationGroups.has(locKey)) {
        locationGroups.set(locKey, []);
      }
      locationGroups.get(locKey).push(site);
    });

    // For each location group, keep only the site with highest priority status
    const deduplicatedSites = [];
    locationGroups.forEach((sites) => {
      if (sites.length === 1) {
        deduplicatedSites.push(sites[0]);
      } else {
        // Sort by status priority (highest first), then by alert status
        const sorted = sites.sort((a, b) => {
          const aStatus = a.status === 'offline' ? 'offline'
            : alertSiteIds.has(a.id) ? 'anomaly'
            : (a.status === 'pending' || a.status === 'inspection_pending') ? 'pending'
            : 'normal';
          const bStatus = b.status === 'offline' ? 'offline'
            : alertSiteIds.has(b.id) ? 'anomaly'
            : (b.status === 'pending' || b.status === 'inspection_pending') ? 'pending'
            : 'normal';
          return statusPriority[bStatus] - statusPriority[aStatus];
        });
        deduplicatedSites.push(sorted[0]);
      }
    });

    return deduplicatedSites.map((site) => {
      let markerStatus = 'normal';
      if (site.status === 'offline') {
        markerStatus = 'offline';
      } else if (alertSiteIds.has(site.id)) {
        markerStatus = 'anomaly';
      } else if (site.status === 'pending' || site.status === 'inspection_pending') {
        markerStatus = 'pending';
      }
      const icon = createMarkerIcon(site.type, markerStatus);
      return { site, icon, markerStatus, key: site.id || site.code };
    });
  }, [filteredSites, alertSiteIds]);

  // ---- Render: loading state ----
  if (loading) {
    return (
      <div
        style={{
          width: '100%',
          height: '100%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          background: tokens.colorBgLayout,
        }}
      >
        <div style={{ textAlign: 'center' }}>
          <Spin size="large" tip="加载监测数据..." />
          <div style={{ marginTop: 16, color: tokens.colorTextSecondary, fontSize: 13 }}>
            正在连接监测网络...
          </div>
        </div>
      </div>
    );
  }

  // ---- Render: error state ----
  if (error && sites.length === 0) {
    return (
      <div
        style={{
          width: '100%',
          height: '100%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          background: tokens.colorBgLayout,
        }}
      >
        <div style={{ textAlign: 'center', maxWidth: 400 }}>
          <ExclamationCircleOutlined
            style={{ fontSize: 48, color: tokens.colorWarning, marginBottom: 16 }}
          />
          <Title level={4} style={{ color: tokens.colorText, margin: '0 0 8px' }}>
            数据加载失败
          </Title>
          <Text style={{ color: tokens.colorTextSecondary, display: 'block', marginBottom: 20 }}>
            {error}
          </Text>
          <Button
            type="primary"
            icon={<ReloadOutlined />}
            onClick={fetchData}
          >
            重新加载
          </Button>
        </div>
      </div>
    );
  }

  // ---- Main render ----
  return (
    <div className="cockpit-map" style={{ position: 'relative', width: '100%', flex: 1, minHeight: 0, overflow: 'hidden' }}>
      {/* ===== Full-screen Leaflet Map ===== */}
      <MapContainer
        center={DEFAULT_CENTER}
        zoom={DEFAULT_ZOOM}
        zoomControl={false}
        attributionControl={false}
        ref={mapRef}
        style={{ width: '100%', height: '100%' }}
      >
        <TileLayer
          url={AMAP_SATELLITE_URL}
          subdomains={AMAP_SUBDOMAINS}
          maxZoom={18}
        />
        <MapAutoFitter sites={filteredSites} />
        {flyTarget && <MapFlyTo position={flyTarget} zoom={15} />}

        {markers.map(({ site, icon, markerStatus, key }) => {
          const siteDevices = devices.filter((d) => d.site_id === site.id || d.site_code === site.code);
          const siteAlerts = alerts.filter((a) => a.site_id === site.id && a.status !== 'resolved');
          const isOnline = site.status === 'online' || site.status === 'normal';
          const dataTrend = siteDataTrends[site.id] || [];

          // Status tag based on markerStatus
          const statusTag = markerStatus === 'offline'
            ? <Tag color="red" style={{ marginLeft: 8, fontSize: 11, lineHeight: '18px' }}>离线</Tag>
            : markerStatus === 'anomaly'
            ? <Tag color="orange" style={{ marginLeft: 8, fontSize: 11, lineHeight: '18px' }}>数据异常</Tag>
            : markerStatus === 'pending'
            ? <Tag color="default" style={{ marginLeft: 8, fontSize: 11, lineHeight: '18px' }}>待巡检</Tag>
            : null;

          return (
            <Marker
              key={key}
              position={[site.lat, site.lng]}
              icon={icon}
              whenCreated={(markerInstance) => {
                markersRef.current.set(site.id, markerInstance);
              }}
            >
              <Popup maxWidth={420} minWidth={400}>
                <div style={{ minWidth: 380, fontSize: 13, lineHeight: 1.6 }}>
                  {/* Header */}
                  <div style={{ fontWeight: 600, fontSize: 16, marginBottom: 10, color: isDark ? '#d0e8ff' : tokens.colorText, borderBottom: `1px solid ${isDark ? 'rgba(0,200,180,0.2)' : 'rgba(0,0,0,0.1)'}`, paddingBottom: 8 }}>
                    {site.name}
                    {statusTag}
                  </div>

                  {/* Basic Info */}
                  <div style={{ color: isDark ? '#6db8d8' : tokens.colorTextSecondary, fontSize: 12, marginBottom: 10 }}>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px 16px' }}>
                      <div><span style={{ color: isDark ? '#4a8aaa' : tokens.colorTextTertiary }}>编号:</span> {site.code || '-'}</div>
                      <div><span style={{ color: isDark ? '#4a8aaa' : tokens.colorTextTertiary }}>类型:</span> {stationTypeMap[site.type] || site.type || '-'}</div>
                      <div><span style={{ color: isDark ? '#4a8aaa' : tokens.colorTextTertiary }}>区域:</span> {site.district || '-'}</div>
                      <div><span style={{ color: isDark ? '#4a8aaa' : tokens.colorTextTertiary }}>负责人:</span> {site.manager || '-'}</div>
                    </div>
                  </div>

                  {/* Status & Latest Value */}
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 0', borderTop: `1px solid ${isDark ? 'rgba(0,200,180,0.1)' : 'rgba(0,0,0,0.06)'}`, borderBottom: `1px solid ${isDark ? 'rgba(0,200,180,0.1)' : 'rgba(0,0,0,0.06)'}`, marginBottom: 10 }}>
                    <div>
                      <span style={{ color: isDark ? '#4a8aaa' : tokens.colorTextTertiary, fontSize: 11 }}>状态:</span>{' '}
                      <span style={{ color: isOnline ? '#10b981' : '#ef4444', fontWeight: 600, fontSize: 14 }}>
                        {isOnline ? '在线' : '离线'}
                      </span>
                    </div>
                    {site.latest_value != null && (
                      <div>
                        <span style={{ color: isDark ? '#4a8aaa' : tokens.colorTextTertiary, fontSize: 11 }}>最新值:</span>{' '}
                        <span style={{ color: isDark ? '#00c9a7' : tokens.colorPrimary, fontWeight: 600, fontFamily: 'monospace', fontSize: 14 }}>
                          {site.latest_value} {site.unit || ''}
                        </span>
                        {site.latest_time && (
                          <div style={{ fontSize: 10, color: isDark ? '#4a8aaa' : tokens.colorTextTertiary, textAlign: 'right' }}>
                            {relativeTimeStr(site.latest_time)}
                          </div>
                        )}
                      </div>
                    )}
                  </div>

                  {/* Device Info List */}
                  {siteDevices.length > 0 && (
                    <div style={{ marginBottom: 10 }}>
                      <div style={{ fontSize: 12, color: isDark ? '#4a8aaa' : tokens.colorTextSecondary, marginBottom: 6, fontWeight: 500 }}>设备信息</div>
                      <div style={{ background: isDark ? 'rgba(0,200,180,0.03)' : 'rgba(0,0,0,0.02)', borderRadius: 6, padding: '8px' }}>
                        {siteDevices.map((dev, idx) => (
                          <div key={idx} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '4px 0', borderBottom: idx < siteDevices.length - 1 ? `1px solid ${isDark ? 'rgba(0,200,180,0.08)' : 'rgba(0,0,0,0.06)'}` : 'none' }}>
                            <div style={{ flex: 1 }}>
                              <div style={{ fontSize: 13, color: isDark ? '#d0e8ff' : tokens.colorText, fontWeight: 500 }}>{dev.device_name || dev.name || '未知设备'}</div>
                              <div style={{ fontSize: 11, color: isDark ? '#4a8aaa' : tokens.colorTextTertiary }}>{dev.model || '未知型号'}</div>
                            </div>
                            <div style={{ textAlign: 'right' }}>
                              <div style={{ fontSize: 12, fontFamily: 'monospace', color: dev.voltage < 11.5 ? '#faad14' : (isDark ? '#d0e8ff' : tokens.colorText) }}>
                                {dev.voltage != null ? `${dev.voltage}V` : '-'}
                              </div>
                              <div style={{ fontSize: 11, color: dev.status === 'online' ? '#10b981' : '#ef4444' }}>
                                {dev.status === 'online' ? '正常' : '离线'}
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Data Trend Chart */}
                  {dataTrend.length > 0 && (
                    <div style={{ marginBottom: 10 }}>
                      <div style={{ fontSize: 12, color: isDark ? '#4a8aaa' : tokens.colorTextSecondary, marginBottom: 6, fontWeight: 500, textAlign: 'center' }}>24小时数据趋势</div>
                      {renderTrendChart(dataTrend)}
                    </div>
                  )}

                  {/* Alert Summary - Clickable, navigates to alerts filtered by site */}
                  {(() => {
                    // For offline sites with no DB alerts, show a synthetic offline alert
                    const displayAlerts = siteAlerts.length > 0
                      ? siteAlerts
                      : (markerStatus === 'offline'
                        ? [{ id: 'offline-synthetic', site_id: site.id, level: 'red', message: '站点离线，设备通信中断', created_at: site.latest_time || null }]
                        : []);
                    return displayAlerts.length > 0 ? (
                      <div
                        style={{
                          background: isDark ? 'rgba(239,68,68,0.08)' : 'rgba(239,68,68,0.04)',
                          padding: '8px',
                          borderRadius: 6,
                          marginBottom: 10,
                          cursor: 'pointer',
                          border: `1px solid ${isDark ? 'rgba(239,68,68,0.2)' : 'rgba(239,68,68,0.15)'}`,
                          transition: 'background 0.2s',
                        }}
                        onClick={() => {
                          navigate(`/alerts?search=${encodeURIComponent(site.name)}`);
                        }}
                        onMouseEnter={(e) => { e.currentTarget.style.background = isDark ? 'rgba(239,68,68,0.14)' : 'rgba(239,68,68,0.08)'; }}
                        onMouseLeave={(e) => { e.currentTarget.style.background = isDark ? 'rgba(239,68,68,0.08)' : 'rgba(239,68,68,0.04)'; }}
                      >
                        <div style={{ fontSize: 12, color: '#ef4444', fontWeight: 500, marginBottom: 6, display: 'flex', alignItems: 'center', gap: 4 }}>
                          <AlertOutlined style={{ fontSize: 12 }} />
                          活跃告警 ({displayAlerts.length}) — 点击跳转到预警中心
                        </div>
                        {displayAlerts.slice(0, 3).map((alert, idx) => {
                          const lColor = alert.level === 'red' ? '#ef4444'
                            : alert.level === 'orange' ? '#fb923c'
                            : alert.level === 'yellow' ? '#facc15'
                            : alert.level === 'blue' ? '#38bdf8'
                            : '#faad14';
                          return (
                            <div key={idx} style={{ fontSize: 11, color: isDark ? '#d0e8ff' : tokens.colorText, marginBottom: 3, paddingLeft: 8, display: 'flex', alignItems: 'flex-start', gap: 4 }}>
                              <span style={{ width: 5, height: 5, borderRadius: '50%', background: lColor, flexShrink: 0, marginTop: 4, boxShadow: `0 0 3px ${lColor}` }} />
                              <span style={{ flex: 1 }}>{alert.message || alert.level || '未知告警'}</span>
                              <span style={{ color: isDark ? '#4a8aaa' : tokens.colorTextTertiary, fontSize: 10, flexShrink: 0 }}>
                                {alert.created_at ? relativeTimeStr(alert.created_at) : ''}
                              </span>
                            </div>
                          );
                        })}
                      </div>
                    ) : null;
                  })()}

                  {/* Footer with Archive Button */}
                  <div style={{ display: 'flex', justifyContent: 'center', padding: '8px 0', borderTop: `1px solid ${isDark ? 'rgba(0,200,180,0.1)' : 'rgba(0,0,0,0.06)'}` }}>
                    <Button
                      type="primary"
                      size="small"
                      icon={<FileSearchOutlined />}
                      onClick={() => {
                        navigate(`/sites?archive=${site.id}`);
                      }}
                      style={{
                        background: 'linear-gradient(135deg, #00c9a7, #00a88a)',
                        border: 'none',
                        borderRadius: 6,
                      }}
                    >
                      查看档案
                    </Button>
                  </div>
                </div>
              </Popup>
            </Marker>
          );
        })}
      </MapContainer>

      {/* ===== Top Toolbar ===== */}
      <div
        style={{
          position: 'absolute',
          top: 12,
          left: '50%',
          transform: 'translateX(-50%)',
          zIndex: 1000,
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          padding: '6px 12px',
          borderRadius: 10,
          ...panelStyle,
        }}
      >
        <FilterOutlined style={{ color: tokens.colorTextSecondary, fontSize: 14 }} />
        <Segmented
          value={typeFilter}
          onChange={setTypeFilter}
          options={typeFilterOptions}
          size="small"
          style={{
            background: isDark ? 'rgba(0,200,180,0.06)' : 'rgba(0,0,0,0.04)',
            borderRadius: 8,
          }}
        />
        <Tooltip title="搜索站点">
          <Button
            type="text"
            size="small"
            icon={<SearchOutlined />}
            onClick={() => setShowSearch((v) => !v)}
            style={{
              color: showSearch ? tokens.colorPrimary : tokens.colorTextSecondary,
              borderRadius: 6,
            }}
          />
        </Tooltip>
        <Tooltip title="复位地图">
          <Button
            type="text"
            size="small"
            icon={<AimOutlined />}
            onClick={handleLocateAll}
            style={{ color: tokens.colorTextSecondary, borderRadius: 6 }}
          />
        </Tooltip>
        <Tooltip title="刷新数据">
          <Button
            type="text"
            size="small"
            icon={<ReloadOutlined spin={refreshing} />}
            onClick={fetchData}
            loading={refreshing}
            style={{ color: tokens.colorTextSecondary, borderRadius: 6 }}
          />
        </Tooltip>
      </div>

      {/* ===== Search Panel ===== */}
      {showSearch && (
        <div
          style={{
            position: 'absolute',
            top: 52,
            left: '50%',
            transform: 'translateX(-50%)',
            zIndex: 1000,
            width: 380,
            padding: 16,
            borderRadius: 12,
            ...panelStyle,
          }}
        >
          <Search
            placeholder="搜索站点名称、编号或区域..."
            allowClear
            onSearch={handleSearch}
            onChange={(e) => handleSearch(e.target.value)}
            value={searchText}
            autoFocus
            style={{ width: '100%' }}
            prefix={<SearchOutlined style={{ color: tokens.colorTextTertiary }} />}
          />
          {searchText && (
            <div
              className="cockpit-scroll"
              style={{
                maxHeight: 200,
                overflowY: 'auto',
                marginTop: 10,
              }}
            >
              {filteredSites.length === 0 ? (
                <Text style={{ color: tokens.colorTextTertiary, fontSize: 12 }}>
                  无匹配结果
                </Text>
              ) : (
                filteredSites.slice(0, 10).map((site) => (
                  <div
                    key={site.id || site.code}
                    onClick={() => {
                      handleSiteClick(site);
                      setShowSearch(false);
                    }}
                    style={{
                      padding: '8px 10px',
                      borderRadius: 6,
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      transition: 'background 0.2s',
                      background: 'transparent',
                    }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.background = tokens.colorPrimaryBg;
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.background = 'transparent';
                    }}
                  >
                    <div>
                      <div style={{ fontSize: 13, color: tokens.colorText, fontWeight: 500 }}>
                        {site.name}
                      </div>
                      <div style={{ fontSize: 11, color: tokens.colorTextTertiary }}>
                        {site.code} · {stationTypeMap[site.type] || site.type} · {site.district || ''}
                      </div>
                    </div>
                    <EnvironmentOutlined style={{ color: tokens.colorPrimary, fontSize: 14 }} />
                  </div>
                ))
              )}
            </div>
          )}
        </div>
      )}

      {/* ===== Left Panel Group ===== */}
      <div
        style={{
          position: 'absolute',
          top: 12,
          left: 12,
          bottom: 56,
          zIndex: 1000,
          display: 'flex',
          flexDirection: 'column',
          gap: 10,
          width: leftCollapsed ? 42 : 340,
          transition: 'width 0.35s cubic-bezier(0.4, 0, 0.2, 1)',
        }}
      >
        {/* Collapse toggle */}
        <Button
          type="primary"
          size="small"
          shape="circle"
          icon={leftCollapsed ? <RightOutlined /> : <LeftOutlined />}
          onClick={() => setLeftCollapsed((v) => !v)}
          style={{
            position: 'absolute',
            top: 0,
            right: -14,
            zIndex: 10,
            width: 28,
            height: 28,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            boxShadow: '0 2px 8px rgba(0,0,0,0.3)',
          }}
        />

        {!leftCollapsed && (
          <>
            {/* Site Real-time Monitoring */}
            <div
              className="cockpit-panel"
              style={{
                ...panelStyle,
                flex: '1 1 50%',
                minHeight: 0,
                display: 'flex',
                flexDirection: 'column',
              }}
            >
              <Card
                title={
                  <Space size={6}>
                    <EnvironmentOutlined style={{ color: tokens.colorPrimary }} />
                    <span>站点实时监测</span>
                    <Badge
                      count={filteredSites.length}
                      style={{
                        backgroundColor: tokens.colorPrimaryBg,
                        color: tokens.colorPrimary,
                        fontSize: 11,
                        boxShadow: 'none',
                      }}
                    />
                  </Space>
                }
                size="small"
                style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 }}
                styles={{ body: { padding: 0, flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' } }}
              >
                <div
                  className="cockpit-scroll"
                  style={{
                    overflowY: 'auto',
                    flex: 1,
                    minHeight: 0,
                    padding: '4px 12px 8px',
                  }}
                >
                  {filteredSites.length === 0 ? (
                    <Empty
                      image={Empty.PRESENTED_IMAGE_SIMPLE}
                      description="暂无站点数据"
                      style={{ padding: '20px 0' }}
                    />
                  ) : (
                    <List
                      dataSource={filteredSites}
                      renderItem={(site) => {
                        // Compute marker status: offline (red) > anomaly (yellow) > pending (gray) > normal (green)
                        let markerStatus = 'normal';
                        if (site.status === 'offline') {
                          markerStatus = 'offline';
                        } else if (alertSiteIds.has(site.id)) {
                          markerStatus = 'anomaly';
                        } else if (site.status === 'pending' || site.status === 'inspection_pending') {
                          markerStatus = 'pending';
                        }
                        const isOnline = site.status === 'online' || site.status === 'normal';
                        return (
                          <List.Item
                            style={{ cursor: 'pointer' }}
                            onClick={() => handleSiteClick(site)}
                          >
                            <div style={{ width: '100%' }}>
                              <div
                                style={{
                                  display: 'flex',
                                  alignItems: 'center',
                                  justifyContent: 'space-between',
                                  marginBottom: 2,
                                }}
                              >
                                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                                  <div
                                    className={markerStatus !== 'normal' ? 'site-dot-alert' : ''}
                                    style={{
                                      width: 8,
                                      height: 8,
                                      borderRadius: '50%',
                                      background: markerStatus === 'offline' ? tokens.colorError
                                        : markerStatus === 'anomaly' ? tokens.colorWarning
                                        : markerStatus === 'pending' ? '#8c8c8c'
                                        : tokens.colorSuccess,
                                      flexShrink: 0,
                                      boxShadow: markerStatus !== 'normal'
                                        ? `0 0 6px 2px ${markerStatus === 'offline' ? tokens.colorError : markerStatus === 'pending' ? 'rgba(140,140,140,0.5)' : tokens.colorWarning}`
                                        : 'none',
                                    }}
                                  />
                                  <Text
                                    style={{
                                      fontSize: 13,
                                      fontWeight: 500,
                                      color: tokens.colorText,
                                      maxWidth: 140,
                                    }}
                                    ellipsis={{ tooltip: site.name }}
                                  >
                                    {site.name}
                                  </Text>
                                </div>
                                <Space size={4}>
                                  {markerStatus === 'offline' && (
                                    <WarningOutlined
                                      style={{ color: tokens.colorError, fontSize: 13 }}
                                    />
                                  )}
                                  {markerStatus === 'anomaly' && (
                                    <WarningOutlined
                                      style={{ color: tokens.colorWarning, fontSize: 13 }}
                                    />
                                  )}
                                  {markerStatus === 'pending' && (
                                    <ClockCircleOutlined
                                      style={{ color: '#8c8c8c', fontSize: 13 }}
                                    />
                                  )}
                                  <Tooltip title={pinnedSites.has(site.id) ? '取消关注' : '重点关注'}>
                                    <Button
                                      type="text"
                                      size="small"
                                      icon={pinnedSites.has(site.id)
                                        ? <PushpinFilled style={{ color: tokens.colorPrimary, fontSize: 13 }} />
                                        : <PushpinOutlined style={{ color: tokens.colorTextQuaternary, fontSize: 13 }} />
                                      }
                                      onClick={(e) => {
                                        e.stopPropagation();
                                        togglePinSite(site.id);
                                      }}
                                      style={{ padding: 0, minWidth: 'auto', height: 'auto' }}
                                    />
                                  </Tooltip>
                                  <Badge
                                    status={isOnline ? 'success' : 'error'}
                                    text={
                                      <span
                                        style={{
                                          fontSize: 11,
                                          color: isOnline
                                            ? tokens.colorSuccess
                                            : tokens.colorError,
                                        }}
                                      >
                                        {isOnline ? '在线' : '离线'}
                                      </span>
                                    }
                                  />
                                </Space>
                              </div>
                              <div
                                style={{
                                  display: 'flex',
                                  justifyContent: 'space-between',
                                  alignItems: 'center',
                                  paddingLeft: 14,
                                }}
                              >
                                <Text style={{ fontSize: 11, color: tokens.colorTextTertiary }}>
                                  {stationTypeMap[site.type] || site.type} · {site.code}
                                </Text>
                                {site.latest_value != null && (
                                  <Text
                                    style={{
                                      fontSize: 13,
                                      fontWeight: 600,
                                      color: tokens.colorPrimary,
                                      fontFamily: 'monospace',
                                    }}
                                  >
                                    {site.latest_value}
                                    <span
                                      style={{
                                        fontSize: 10,
                                        color: tokens.colorTextTertiary,
                                        fontWeight: 400,
                                        marginLeft: 2,
                                      }}
                                    >
                                      {site.unit || ''}
                                    </span>
                                  </Text>
                                )}
                              </div>
                            </div>
                          </List.Item>
                        );
                      }}
                    />
                  )}
                </div>
              </Card>
            </div>

            {/* Data Health Rate */}
            <div
              className="cockpit-panel"
              style={{
                ...panelStyle,
                flex: '0 0 auto',
              }}
            >
              <Card
                title={
                  <Space size={6}>
                    <DashboardOutlined style={{ color: tokens.colorInfo }} />
                    <span>数据健康度</span>
                  </Space>
                }
                size="small"
              >
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {healthByType.map((item) => {
                    const barColor = item.rate >= 80
                      ? tokens.colorSuccess
                      : item.rate >= 50
                      ? tokens.colorWarning
                      : tokens.colorError;
                    return (
                      <div key={item.type}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
                          <Text style={{ fontSize: 11, color: tokens.colorTextSecondary }}>
                            {item.label}
                            <span style={{ color: tokens.colorTextQuaternary, marginLeft: 4 }}>
                              {item.online}/{item.total}
                            </span>
                          </Text>
                          <Text style={{ fontSize: 11, fontWeight: 600, color: barColor, fontFamily: 'monospace' }}>
                            {item.rate}%
                          </Text>
                        </div>
                        <div style={{
                          height: 5,
                          borderRadius: 3,
                          background: isDark ? 'rgba(0,200,180,0.08)' : 'rgba(0,0,0,0.06)',
                          overflow: 'hidden',
                        }}>
                          <div style={{
                            width: `${item.rate}%`,
                            height: '100%',
                            background: barColor,
                            borderRadius: 3,
                            transition: 'width 0.6s ease',
                            minWidth: item.total > 0 ? 4 : 0,
                          }} />
                        </div>
                      </div>
                    );
                  })}
                  {healthByType.length === 0 && (
                    <Text style={{ fontSize: 12, color: tokens.colorTextTertiary, textAlign: 'center', padding: '8px 0' }}>
                      暂无站点数据
                    </Text>
                  )}
                </div>
              </Card>
            </div>
          </>
        )}
      </div>

      {/* ===== Map Legend (right of left panel) ===== */}
      <div
        style={{
          position: 'absolute',
          bottom: 56,
          left: 12 + (leftCollapsed ? 42 : 340) + 8,
          zIndex: 1000,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'flex-start',
          gap: 4,
          transition: 'left 0.35s cubic-bezier(0.4, 0, 0.2, 1)',
        }}
      >
        <Button
          type="primary"
          size="small"
          shape="circle"
          icon={legendCollapsed ? <FullscreenOutlined /> : <ShrinkOutlined />}
          onClick={() => setLegendCollapsed((v) => !v)}
          style={{
            width: 24,
            height: 24,
            fontSize: 11,
            boxShadow: '0 2px 8px rgba(0,0,0,0.3)',
          }}
        />
        {!legendCollapsed && (
          <div
            style={{
              padding: '6px 10px',
              borderRadius: 8,
              ...panelStyle,
              minWidth: 120,
            }}
          >
            <div style={{ fontSize: 10, fontWeight: 600, color: tokens.colorTextSecondary, marginBottom: 6 }}>
              图例
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              {Object.entries(stationTypeMap).map(([key, label]) => (
                <div key={key} style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                  <img
                    src={stationIconMap[key] || stationIconMap.hydrology}
                    alt={label}
                    style={{ width: 14, height: 14, objectFit: 'contain' }}
                  />
                  <Text style={{ fontSize: 10, color: tokens.colorText }}>{label}</Text>
                </div>
              ))}
              {/* Device status colors */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 3, marginTop: 2, paddingTop: 4, borderTop: `1px solid ${tokens.colorBorderSecondary}` }}>
                <div style={{ fontSize: 9, color: tokens.colorTextQuaternary, marginBottom: 1 }}>站点状态</div>
                {[
                  { color: '#00c9a7', label: '在线' },
                  { color: '#ef4444', label: '离线' },
                  { color: '#facc15', label: '数据异常' },
                  { color: '#8c8c8c', label: '待巡检' },
                ].map(({ color, label }) => (
                  <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                    <div
                      style={{
                        width: 8,
                        height: 8,
                        borderRadius: '50%',
                        background: color,
                        boxShadow: `0 0 4px ${color}40`,
                      }}
                    />
                    <Text style={{ fontSize: 10, color: tokens.colorText }}>{label}</Text>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* ===== Right Panel Group ===== */}
      <div
        style={{
          position: 'absolute',
          top: 12,
          right: 12,
          bottom: 56,
          zIndex: 1000,
          display: 'flex',
          flexDirection: 'column',
          gap: 10,
          width: rightCollapsed ? 42 : 340,
          transition: 'width 0.35s cubic-bezier(0.4, 0, 0.2, 1)',
        }}
      >
        {/* Collapse toggle */}
        <Button
          type="primary"
          size="small"
          shape="circle"
          icon={rightCollapsed ? <LeftOutlined /> : <RightOutlined />}
          onClick={() => setRightCollapsed((v) => !v)}
          style={{
            position: 'absolute',
            top: 0,
            left: -14,
            zIndex: 10,
            width: 28,
            height: 28,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            boxShadow: '0 2px 8px rgba(0,0,0,0.3)',
          }}
        />

        {!rightCollapsed && (
          <>
            {/* Real-time Alerts */}
            <div
              className="cockpit-panel"
              style={{
                ...panelStyle,
                flex: '1 1 35%',
                minHeight: 0,
                display: 'flex',
                flexDirection: 'column',
              }}
            >
              <Card
                title={
                  <Space size={6}>
                    <AlertOutlined style={{ color: tokens.colorError }} />
                    <span>实时告警</span>
                    <Badge
                      count={filteredAlerts.length}
                      style={{
                        backgroundColor: filteredAlerts.length > 0 ? 'rgba(239,68,68,0.15)' : tokens.colorPrimaryBg,
                        color: filteredAlerts.length > 0 ? tokens.colorError : tokens.colorPrimary,
                        fontSize: 11,
                        boxShadow: 'none',
                      }}
                    />
                  </Space>
                }
                size="small"
                style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 }}
                styles={{ body: { padding: 0, flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' } }}
              >
                <div
                  className="cockpit-scroll"
                  style={{
                    overflowY: 'auto',
                    flex: 1,
                    minHeight: 0,
                    padding: '4px 12px 8px',
                  }}
                >
                  {filteredAlerts.length === 0 ? (
                    <Empty
                      image={Empty.PRESENTED_IMAGE_SIMPLE}
                      description="暂无告警"
                      style={{ padding: '16px 0' }}
                    />
                  ) : (
                    <List
                      dataSource={filteredAlerts}
                      renderItem={(alert) => {
                        const levelColor = alertLevelColor[alert.level] || tokens.colorWarning;
                        const levelLabel = alertLevelLabel[alert.level] || alert.level;
                        const isResolved = alert.status === 'resolved';
                        return (
                          <List.Item
                            style={{ cursor: 'pointer', transition: 'background 0.2s', borderRadius: 6 }}
                            onClick={() => navigate(`/alerts?search=${encodeURIComponent(alert.site_name || '')}`)}
                            onMouseEnter={(e) => { e.currentTarget.style.background = isDark ? 'rgba(0,200,180,0.06)' : 'rgba(0,0,0,0.03)'; }}
                            onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; }}
                          >
                            <div style={{ width: '100%' }}>
                              <div
                                style={{
                                  display: 'flex',
                                  alignItems: 'center',
                                  justifyContent: 'space-between',
                                  marginBottom: 2,
                                }}
                              >
                                <Space size={6}>
                                  <div
                                    style={{
                                      width: 6,
                                      height: 6,
                                      borderRadius: '50%',
                                      background: levelColor,
                                      boxShadow: `0 0 4px ${levelColor}`,
                                      flexShrink: 0,
                                    }}
                                  />
                                  <Text
                                    style={{
                                      fontSize: 13,
                                      fontWeight: 500,
                                      color: tokens.colorText,
                                      maxWidth: 160,
                                    }}
                                    ellipsis={{ tooltip: alert.site_name }}
                                  >
                                    {alert.site_name}
                                  </Text>
                                </Space>
                                <Tag
                                  color={levelColor}
                                  style={{
                                    fontSize: 10,
                                    lineHeight: '16px',
                                    padding: '0 6px',
                                    margin: 0,
                                    borderRadius: 4,
                                    border: 'none',
                                  }}
                                >
                                  {levelLabel}
                                </Tag>
                              </div>
                              <div style={{ paddingLeft: 12 }}>
                                <Text
                                  style={{
                                    fontSize: 12,
                                    color: tokens.colorTextSecondary,
                                    display: 'block',
                                    lineHeight: 1.5,
                                  }}
                                >
                                  {truncate(alert.message, 40)}
                                </Text>
                                <div
                                  style={{
                                    display: 'flex',
                                    justifyContent: 'space-between',
                                    alignItems: 'center',
                                    marginTop: 2,
                                  }}
                                >
                                  <Text style={{ fontSize: 10, color: tokens.colorTextQuaternary }}>
                                    {alert.created_at ? relativeTimeStr(alert.created_at) : ''}
                                  </Text>
                                  <Tag
                                    style={{
                                      fontSize: 10,
                                      lineHeight: '16px',
                                      padding: '0 4px',
                                      margin: 0,
                                      borderRadius: 3,
                                      background: isResolved
                                        ? 'rgba(16,185,129,0.1)'
                                        : alert.status === 'acknowledged'
                                        ? 'rgba(245,158,11,0.1)'
                                        : 'rgba(239,68,68,0.1)',
                                      color: isResolved
                                        ? tokens.colorSuccess
                                        : alert.status === 'acknowledged'
                                        ? tokens.colorWarning
                                        : tokens.colorError,
                                      border: 'none',
                                    }}
                                  >
                                    {isResolved ? '已办结' : alert.status === 'acknowledged' ? '处理中' : '待处理'}
                                  </Tag>
                                </div>
                              </div>
                            </div>
                          </List.Item>
                        );
                      }}
                    />
                  )}
                </div>
              </Card>
            </div>

            {/* Device Health Dashboard */}
            <div
              className="cockpit-panel"
              style={{
                ...panelStyle,
                flex: '0 0 auto',
              }}
            >
              <Card
                title={
                  <Space size={6}>
                    <CloudServerOutlined style={{ color: tokens.colorInfo }} />
                    <span>设备健康</span>
                  </Space>
                }
                size="small"
              >
                {devices.length === 0 ? (
                  <Empty
                    image={Empty.PRESENTED_IMAGE_SIMPLE}
                    description="暂无设备数据"
                    style={{ padding: '12px 0' }}
                  />
                ) : (
                  <div>
                    <div
                      style={{
                        display: 'grid',
                        gridTemplateColumns: '1fr 1fr',
                        gap: '8px 16px',
                      }}
                    >
                      <div
                        onClick={() => navigate('/equipment')}
                        style={{ cursor: 'pointer' }}
                        onMouseEnter={(e) => { e.currentTarget.style.opacity = '0.8'; }}
                        onMouseLeave={(e) => { e.currentTarget.style.opacity = '1'; }}
                      >
                        <Statistic
                          title="设备总数"
                          value={deviceStats.total}
                          valueStyle={{ fontSize: 20, fontWeight: 700, color: tokens.colorText, fontFamily: 'monospace' }}
                          prefix={<ApiOutlined style={{ fontSize: 14 }} />}
                        />
                      </div>
                      <div
                        onClick={() => navigate('/equipment?status=online')}
                        style={{ cursor: 'pointer' }}
                        onMouseEnter={(e) => { e.currentTarget.style.opacity = '0.8'; }}
                        onMouseLeave={(e) => { e.currentTarget.style.opacity = '1'; }}
                      >
                        <Statistic
                          title="在线运行"
                          value={deviceStats.online}
                          valueStyle={{ fontSize: 20, fontWeight: 700, color: tokens.colorSuccess, fontFamily: 'monospace' }}
                          prefix={<CheckCircleOutlined style={{ fontSize: 14 }} />}
                        />
                      </div>
                      <div
                        onClick={() => navigate('/equipment?status=offline')}
                        style={{ cursor: 'pointer' }}
                        onMouseEnter={(e) => { e.currentTarget.style.opacity = '0.8'; }}
                        onMouseLeave={(e) => { e.currentTarget.style.opacity = '1'; }}
                      >
                        <Statistic
                          title="离线设备"
                          value={deviceStats.offline}
                          valueStyle={{
                            fontSize: 20,
                            fontWeight: 700,
                            color: deviceStats.offline > 0 ? tokens.colorError : tokens.colorTextTertiary,
                            fontFamily: 'monospace',
                          }}
                          prefix={<CloseCircleOutlined style={{ fontSize: 14 }} />}
                        />
                      </div>
                      <div
                        onClick={() => navigate('/equipment?status=warning')}
                        style={{ cursor: 'pointer' }}
                        onMouseEnter={(e) => { e.currentTarget.style.opacity = '0.8'; }}
                        onMouseLeave={(e) => { e.currentTarget.style.opacity = '1'; }}
                      >
                        <Statistic
                          title="故障/低电"
                          value={deviceStats.fault + deviceStats.lowBattery}
                          valueStyle={{
                            fontSize: 20,
                            fontWeight: 700,
                            color:
                              deviceStats.fault + deviceStats.lowBattery > 0
                                ? tokens.colorWarning
                                : tokens.colorTextTertiary,
                            fontFamily: 'monospace',
                          }}
                          prefix={<ExclamationCircleOutlined style={{ fontSize: 14 }} />}
                        />
                      </div>
                    </div>

                    {/* Health bar */}
                    <div style={{ marginTop: 10 }}>
                      <div
                        style={{
                          display: 'flex',
                          justifyContent: 'space-between',
                          marginBottom: 4,
                        }}
                      >
                        <Text style={{ fontSize: 11, color: tokens.colorTextTertiary }}>
                          在线率
                        </Text>
                        <Text
                          style={{
                            fontSize: 11,
                            fontWeight: 600,
                            color:
                              deviceStats.total > 0 && deviceStats.online / deviceStats.total >= 0.8
                                ? tokens.colorSuccess
                                : tokens.colorWarning,
                            fontFamily: 'monospace',
                          }}
                        >
                          {deviceStats.total > 0
                            ? Math.round((deviceStats.online / deviceStats.total) * 100)
                            : 0}
                          %
                        </Text>
                      </div>
                      <div
                        style={{
                          height: 6,
                          borderRadius: 3,
                          background: isDark ? 'rgba(0,200,180,0.08)' : 'rgba(0,0,0,0.06)',
                          overflow: 'hidden',
                          display: 'flex',
                        }}
                      >
                        <div
                          style={{
                            width: `${
                              deviceStats.total > 0
                                ? (deviceStats.online / deviceStats.total) * 100
                                : 0
                            }%`,
                            background: tokens.colorSuccess,
                            borderRadius: '3px 0 0 3px',
                            transition: 'width 0.6s ease',
                          }}
                        />
                        <div
                          style={{
                            width: `${
                              deviceStats.total > 0
                                ? (deviceStats.offline / deviceStats.total) * 100
                                : 0
                            }%`,
                            background: tokens.colorError,
                            transition: 'width 0.6s ease',
                          }}
                        />
                        <div
                          style={{
                            width: `${
                              deviceStats.total > 0
                                ? ((deviceStats.fault + deviceStats.lowBattery) / deviceStats.total) * 100
                                : 0
                            }%`,
                            background: tokens.colorWarning,
                            borderRadius: '0 3px 3px 0',
                            transition: 'width 0.6s ease',
                          }}
                        />
                      </div>
                      <div
                        style={{
                          display: 'flex',
                          gap: 12,
                          marginTop: 4,
                        }}
                      >
                        <span style={{ fontSize: 10, color: tokens.colorTextQuaternary, display: 'flex', alignItems: 'center', gap: 3 }}>
                          <span style={{ width: 6, height: 6, borderRadius: '50%', background: tokens.colorSuccess, display: 'inline-block' }} />
                          在线
                        </span>
                        <span style={{ fontSize: 10, color: tokens.colorTextQuaternary, display: 'flex', alignItems: 'center', gap: 3 }}>
                          <span style={{ width: 6, height: 6, borderRadius: '50%', background: tokens.colorError, display: 'inline-block' }} />
                          离线
                        </span>
                        <span style={{ fontSize: 10, color: tokens.colorTextQuaternary, display: 'flex', alignItems: 'center', gap: 3 }}>
                          <span style={{ width: 6, height: 6, borderRadius: '50%', background: tokens.colorWarning, display: 'inline-block' }} />
                          故障
                        </span>
                      </div>
                    </div>
                  </div>
                )}
              </Card>
            </div>

            {/* Work Order Status */}
            <div
              className="cockpit-panel"
              style={{
                ...panelStyle,
                flex: '1 1 30%',
                minHeight: 0,
                display: 'flex',
                flexDirection: 'column',
              }}
            >
              <Card
                title={
                  <Space
                    size={6}
                    style={{ cursor: 'pointer' }}
                    onClick={() => navigate('/workorders')}
                  >
                    <ToolOutlined style={{ color: tokens.colorWarning }} />
                    <span>工单态势</span>
                  </Space>
                }
                size="small"
                style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 }}
                styles={{ body: { padding: '12px 16px', flex: 1, overflow: 'auto', display: 'flex', flexDirection: 'column' } }}
              >
                {workOrderTotal === 0 ? (
                  <Empty
                    image={Empty.PRESENTED_IMAGE_SIMPLE}
                    description="暂无工单"
                    style={{ padding: '12px 0' }}
                  />
                ) : (
                  <div>
                    {/* Total summary */}
                    <div
                      style={{
                        display: 'flex',
                        alignItems: 'baseline',
                        justifyContent: 'space-between',
                        marginBottom: 10,
                      }}
                    >
                      <Text style={{ fontSize: 12, color: tokens.colorTextSecondary }}>
                        工单总数
                      </Text>
                      <div>
                        <span
                          style={{
                            fontSize: 28,
                            fontWeight: 700,
                            color: tokens.colorPrimary,
                            fontFamily: 'monospace',
                            lineHeight: 1,
                          }}
                        >
                          {workOrderTotal}
                        </span>
                        <span
                          style={{
                            fontSize: 11,
                            color: tokens.colorTextTertiary,
                            marginLeft: 4,
                          }}
                        >
                          件
                        </span>
                      </div>
                    </div>

                    {/* Status bars */}
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                      {Object.entries(workOrders).map(([status, count]) => {
                        if (typeof count !== 'number' || count === 0) return null;
                        const pct = workOrderTotal > 0 ? (count / workOrderTotal) * 100 : 0;
                        const statusLabels = {
                          pending: '待受理',
                          accepted: '已受理',
                          generated: '已生成',
                          dispatched: '已派发',
                          in_progress: '处置中',
                          reviewing: '审核中',
                          acceptance: '验收中',
                          closed: '已完成',
                        };
                        const statusBarColors = {
                          pending: tokens.colorTextTertiary,
                          accepted: tokens.colorInfo,
                          generated: tokens.colorInfo,
                          dispatched: tokens.colorWarning,
                          in_progress: tokens.colorPrimary,
                          reviewing: '#a855f7',
                          acceptance: '#f59e0b',
                          closed: tokens.colorSuccess,
                        };
                        const barColor = statusBarColors[status] || tokens.colorTextTertiary;
                        return (
                          <div
                            key={status}
                            onClick={() => navigate(`/workorders?status=${status}`)}
                            style={{ cursor: 'pointer', transition: 'opacity 0.2s' }}
                            onMouseEnter={(e) => { e.currentTarget.style.opacity = '0.75'; }}
                            onMouseLeave={(e) => { e.currentTarget.style.opacity = '1'; }}
                          >
                            <div
                              style={{
                                display: 'flex',
                                justifyContent: 'space-between',
                                marginBottom: 2,
                              }}
                            >
                              <Text style={{ fontSize: 11, color: tokens.colorTextSecondary }}>
                                {statusLabels[status] || status}
                              </Text>
                              <Text
                                style={{
                                  fontSize: 12,
                                  fontWeight: 600,
                                  color: tokens.colorText,
                                  fontFamily: 'monospace',
                                }}
                              >
                                {count}
                              </Text>
                            </div>
                            <div
                              style={{
                                height: 4,
                                borderRadius: 2,
                                background: isDark ? 'rgba(0,200,180,0.06)' : 'rgba(0,0,0,0.04)',
                                overflow: 'hidden',
                              }}
                            >
                              <div
                                style={{
                                  width: `${pct}%`,
                                  height: '100%',
                                  background: barColor,
                                  borderRadius: 2,
                                  transition: 'width 0.6s ease',
                                  minWidth: count > 0 ? 4 : 0,
                                }}
                              />
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
              </Card>
            </div>
          </>
        )}
      </div>

      {/* ===== Bottom Status Bar ===== */}
      <div
        style={{
          position: 'absolute',
          bottom: 0,
          left: 0,
          right: 0,
          zIndex: 1000,
          height: 40,
          display: 'flex',
          alignItems: 'center',
          padding: '0 16px',
          gap: 16,
          background: isDark
            ? 'rgba(6, 16, 36, 0.88)'
            : 'rgba(255, 255, 255, 0.88)',
          borderTop: `1px solid ${tokens.colorBorder}`,
          backdropFilter: 'blur(12px)',
          WebkitBackdropFilter: 'blur(12px)',
        }}
      >
        {/* System status indicators */}
        <Space size={12} style={{ flexShrink: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <div
              style={{
                width: 6,
                height: 6,
                borderRadius: '50%',
                background: tokens.colorSuccess,
                boxShadow: `0 0 4px ${tokens.colorSuccess}`,
              }}
            />
            <Text style={{ fontSize: 11, color: tokens.colorTextSecondary }}>系统正常</Text>
          </div>

          <Text style={{ fontSize: 11, color: tokens.colorTextQuaternary }}>|</Text>

          <Space size={4}>
            <EnvironmentOutlined style={{ fontSize: 12, color: tokens.colorTextTertiary }} />
            <Text style={{ fontSize: 11, color: tokens.colorTextTertiary }}>
              站点 <Text style={{ fontSize: 11, color: tokens.colorPrimary, fontWeight: 600 }}>{sites.length}</Text>
            </Text>
          </Space>

          <Space size={4}>
            <AlertOutlined style={{ fontSize: 12, color: activeAlerts.length > 0 ? tokens.colorError : tokens.colorTextTertiary }} />
            <Text style={{ fontSize: 11, color: tokens.colorTextTertiary }}>
              告警 <Text style={{ fontSize: 11, color: activeAlerts.length > 0 ? tokens.colorError : tokens.colorTextTertiary, fontWeight: 600 }}>{activeAlerts.length}</Text>
            </Text>
          </Space>

          <Space size={4}>
            <CloudServerOutlined style={{ fontSize: 12, color: tokens.colorTextTertiary }} />
            <Text style={{ fontSize: 11, color: tokens.colorTextTertiary }}>
              设备 <Text style={{ fontSize: 11, color: tokens.colorText, fontWeight: 600 }}>{devices.length}</Text>
            </Text>
          </Space>
        </Space>

        {/* Alert ticker */}
        {activeAlerts.length > 0 && (
          <div
            style={{
              flex: 1,
              overflow: 'hidden',
              position: 'relative',
              maskImage: 'linear-gradient(to right, transparent, black 5%, black 95%, transparent)',
              WebkitMaskImage: 'linear-gradient(to right, transparent, black 5%, black 95%, transparent)',
            }}
          >
            <div className="alert-ticker-content" style={{ display: 'flex', alignItems: 'center' }}>
              <SoundOutlined
                style={{
                  color: tokens.colorError,
                  fontSize: 13,
                  marginRight: 8,
                  flexShrink: 0,
                }}
              />
              {activeAlerts.map((alert, idx) => (
                <span
                  key={alert.id || idx}
                  style={{
                    fontSize: 12,
                    color: tokens.colorTextSecondary,
                    marginRight: 40,
                    flexShrink: 0,
                  }}
                >
                  <span
                    style={{
                      color: alertLevelColor[alert.level] || tokens.colorWarning,
                      fontWeight: 500,
                    }}
                  >
                    [{alertLevelLabel[alert.level] || alert.level}]
                  </span>{' '}
                  {alert.site_name}: {truncate(alert.message, 30)}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Last refresh time */}
        <div style={{ flexShrink: 0, display: 'flex', alignItems: 'center', gap: 4, marginLeft: 'auto' }}>
          <ClockCircleOutlined style={{ fontSize: 11, color: tokens.colorTextQuaternary }} />
          <Text style={{ fontSize: 11, color: tokens.colorTextQuaternary }}>
            {lastRefresh
              ? `更新于 ${String(lastRefresh.getHours()).padStart(2, '0')}:${String(lastRefresh.getMinutes()).padStart(2, '0')}:${String(lastRefresh.getSeconds()).padStart(2, '0')}`
              : '尚未更新'}
          </Text>
        </div>
      </div>
    </div>
  );
}
