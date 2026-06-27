import { useState, useEffect, useCallback, createContext, useContext } from 'react';
import { getThemeConfig, getTokens } from '../theme/themeConfig';

const ThemeContext = createContext(null);

export function ThemeProvider({ children }) {
  const [isDark, setIsDark] = useState(() => {
    try {
      const saved = localStorage.getItem('water_ops_theme');
      return saved !== 'light'; // default dark
    } catch { return true; }
  });

  const toggleTheme = useCallback(() => {
    setIsDark(prev => {
      const next = !prev;
      localStorage.setItem('water_ops_theme', next ? 'dark' : 'light');
      return next;
    });
  }, []);

  const themeConfig = getThemeConfig(isDark);
  const tokens = getTokens(isDark);

  // Apply data-theme attribute for any custom CSS
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', isDark ? 'dark' : 'light');
  }, [isDark]);

  return (
    <ThemeContext.Provider value={{ isDark, toggleTheme, themeConfig, tokens }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error('useTheme must be used within ThemeProvider');
  return ctx;
}
