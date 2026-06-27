// Design Tokens for the hydrological monitoring platform
// Dual theme: dark (default) and light

export const darkTokens = {
  // Brand
  colorPrimary: '#00c9a7',
  colorPrimaryHover: '#00e0c0',
  colorPrimaryBg: 'rgba(0,201,167,0.08)',

  // Backgrounds
  colorBgBase: '#0a1628',
  colorBgContainer: 'rgba(12,28,52,0.85)',
  colorBgElevated: '#0e1f38',
  colorBgLayout: '#0a1628',

  // Text
  colorText: '#d0e8ff',
  colorTextSecondary: '#6db8d8',
  colorTextTertiary: '#4a8aaa',
  colorTextQuaternary: '#3a7090',

  // Border
  colorBorder: 'rgba(0,200,180,0.15)',
  colorBorderSecondary: 'rgba(0,200,180,0.08)',

  // Status
  colorSuccess: '#10b981',
  colorWarning: '#f59e0b',
  colorError: '#ef4444',
  colorInfo: '#38bdf8',

  // Component
  borderRadius: 8,
  borderRadiusLG: 12,
  borderRadiusSM: 4,

  // Custom tokens (not part of Ant Design)
  navBg: 'rgba(8,20,42,0.98)',
  panelBg: 'rgba(12,28,52,0.68)',
  panelGlass: true,
  glowAccent: 'rgba(0,200,180,0.15)',
  shadowCard: '0 2px 12px rgba(0,0,0,0.35)',
  shadowNav: '0 2px 8px rgba(0,0,0,0.5)',
};

export const lightTokens = {
  colorPrimary: '#0d9488',
  colorPrimaryHover: '#14b8a6',
  colorPrimaryBg: 'rgba(13,148,136,0.06)',

  colorBgBase: '#f5f7fa',
  colorBgContainer: '#ffffff',
  colorBgElevated: '#ffffff',
  colorBgLayout: '#f5f7fa',

  colorText: '#0f172a',
  colorTextSecondary: '#475569',
  colorTextTertiary: '#64748b',
  colorTextQuaternary: '#94a3b8',

  colorBorder: '#e2e8f0',
  colorBorderSecondary: '#f1f5f9',

  colorSuccess: '#059669',
  colorWarning: '#d97706',
  colorError: '#dc2626',
  colorInfo: '#0284c7',

  borderRadius: 8,
  borderRadiusLG: 12,
  borderRadiusSM: 4,

  navBg: '#ffffff',
  panelBg: 'rgba(255,255,255,0.92)',
  panelGlass: true,
  glowAccent: 'rgba(13,148,136,0.08)',
  shadowCard: '0 1px 3px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04)',
  shadowNav: '0 1px 3px rgba(0,0,0,0.08)',
};

// Semantic color helpers for status indicators (theme-agnostic)
export const statusColors = {
  danger: { dark: '#ef4444', light: '#dc2626' },
  warning: { dark: '#f59e0b', light: '#d97706' },
  success: { dark: '#10b981', light: '#059669' },
  info: { dark: '#38bdf8', light: '#0284c7' },
  accent: { dark: '#00c9a7', light: '#0d9488' },
  purple: { dark: '#a855f7', light: '#7c3aed' },
};

// Chart color palette
export const chartPalette = [
  '#00c9a7', // teal
  '#38bdf8', // sky
  '#f59e0b', // amber
  '#ef4444', // red
  '#a855f7', // purple
  '#ec4899', // pink
];

// Station type colors (for map markers and legends)
export const stationTypeColors = {
  rainfall: '#ef4444',
  water_level: '#ef4444',
  hydrology: '#ef4444',
  soil_moisture: '#f59e0b',
  evaporation: '#38bdf8',
  groundwater: '#06b6d4',
  station_yard: '#38bdf8',
};
