import { useState, useEffect, useCallback, createContext, useContext } from 'react';
import { api } from '../services/api';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(() => {
    try { return localStorage.getItem('water_ops_token') || ''; } catch { return ''; }
  });
  const [loading, setLoading] = useState(false);

  const login = useCallback(async (username, password) => {
    setLoading(true);
    try {
      const res = await api.post('/auth/login', { username, password });
      if (res && res.token) {
        localStorage.setItem('water_ops_token', res.token);
        setToken(res.token);
        setUser(res.user || { username, role: res.role || 'user' });
        return { success: true };
      }
      return { success: false, error: res?.error || '登录失败' };
    } catch (e) {
      return { success: false, error: '网络错误' };
    } finally {
      setLoading(false);
    }
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem('water_ops_token');
    setToken('');
    setUser(null);
  }, []);

  // Restore user on mount
  useEffect(() => {
    if (token && !user) {
      api.get('/auth/me').then(res => {
        if (res && res.user) setUser(res.user);
        else if (res && res.username) setUser(res);
      });
    }
  }, [token]);

  return (
    <AuthContext.Provider value={{ user, token, loading, login, logout, isAuthenticated: !!token }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
