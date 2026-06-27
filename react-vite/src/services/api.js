const API_BASE = '/api';

function getToken() {
  try { return localStorage.getItem('water_ops_token') || ''; } catch { return ''; }
}

function authHeaders() {
  const h = {};
  const t = getToken();
  if (t) h['Authorization'] = `Bearer ${t}`;
  return h;
}

function handle401() {
  try { localStorage.removeItem('water_ops_token'); } catch { /* ignore */ }
  window.location.hash = '#/login';
}

async function request(url, options = {}) {
  const { method = 'GET', body, timeout = 30000 } = options;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);

  try {
    const headers = { ...authHeaders() };
    if (body && typeof body === 'object') {
      headers['Content-Type'] = 'application/json';
    }
    const res = await fetch(`${API_BASE}${url}`, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    });

    if (res.status === 401) {
      handle401();
      return null;
    }

    const ct = (res.headers.get('content-type') || '').toLowerCase();
    if (ct.includes('application/json')) {
      return await res.json();
    }
    const text = await res.text();
    return res.ok ? { success: true } : { error: text.substring(0, 100) };
  } catch (e) {
    console.error(`API ${method} ${url}:`, e);
    return method === 'GET' ? null : { error: String(e) };
  } finally {
    clearTimeout(timer);
  }
}

export const api = {
  get: (url, timeout) => request(url, { timeout }),
  post: (url, data, timeout) => request(url, { method: 'POST', body: data, timeout }),
  put: (url, data, timeout) => request(url, { method: 'PUT', body: data, timeout }),
  delete: (url, timeout) => request(url, { method: 'DELETE', timeout }),
};
