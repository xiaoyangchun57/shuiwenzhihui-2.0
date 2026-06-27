import { theme } from 'antd';
import { darkTokens, lightTokens } from './tokens';

const { darkAlgorithm, defaultAlgorithm } = theme;

function buildAntdTheme(tokens) {
  return {
    token: {
      colorPrimary: tokens.colorPrimary,
      colorBgBase: tokens.colorBgBase,
      colorBgContainer: tokens.colorBgContainer,
      colorBgElevated: tokens.colorBgElevated,
      colorBgLayout: tokens.colorBgLayout,
      colorText: tokens.colorText,
      colorTextSecondary: tokens.colorTextSecondary,
      colorTextTertiary: tokens.colorTextTertiary,
      colorTextQuaternary: tokens.colorTextQuaternary,
      colorBorder: tokens.colorBorder,
      colorBorderSecondary: tokens.colorBorderSecondary,
      colorSuccess: tokens.colorSuccess,
      colorWarning: tokens.colorWarning,
      colorError: tokens.colorError,
      colorInfo: tokens.colorInfo,
      borderRadius: tokens.borderRadius,
      borderRadiusLG: tokens.borderRadiusLG,
      borderRadiusSM: tokens.borderRadiusSM,
      fontFamily: '"Inter", "PingFang SC", "Microsoft YaHei", -apple-system, sans-serif',
      fontSize: 14,
    },
    components: {
      Layout: {
        headerBg: tokens.navBg,
        headerPadding: '0 24px',
        headerHeight: 56,
        bodyBg: tokens.colorBgLayout,
      },
      Menu: {
        darkItemBg: 'transparent',
        darkItemColor: tokens.colorTextSecondary,
        darkItemSelectedColor: tokens.colorPrimary,
        darkItemHoverColor: tokens.colorText,
        darkItemSelectedBg: tokens.colorPrimaryBg,
        itemBg: 'transparent',
        itemColor: tokens.colorTextSecondary,
        itemSelectedColor: tokens.colorPrimary,
        itemHoverColor: tokens.colorText,
        itemSelectedBg: tokens.colorPrimaryBg,
      },
      Table: {
        headerBg: tokens.colorPrimaryBg,
        headerColor: tokens.colorTextSecondary,
        rowHoverBg: tokens.colorPrimaryBg,
        borderColor: tokens.colorBorderSecondary,
      },
      Card: {
        headerBg: tokens.colorPrimaryBg,
      },
      Button: {
        primaryShadow: 'none',
        defaultShadow: 'none',
        dangerShadow: 'none',
      },
      Modal: {
        headerBg: 'transparent',
      },
    },
  };
}

export const darkTheme = {
  algorithm: darkAlgorithm,
  ...buildAntdTheme(darkTokens),
};

export const lightTheme = {
  algorithm: defaultAlgorithm,
  ...buildAntdTheme(lightTokens),
};

export function getThemeConfig(isDark) {
  return isDark ? darkTheme : lightTheme;
}

export function getTokens(isDark) {
  return isDark ? darkTokens : lightTokens;
}
