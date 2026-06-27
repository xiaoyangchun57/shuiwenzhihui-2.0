import dayjs from 'dayjs';
import relativeTime from 'dayjs/plugin/relativeTime';
import 'dayjs/locale/zh-cn';

dayjs.extend(relativeTime);
dayjs.locale('zh-cn');

// HTML escape to prevent XSS
export function esc(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

// Format date to YYYY-MM-DD HH:mm
export function formatDate(dateStr) {
  if (!dateStr) return '-';
  const d = dayjs(dateStr);
  return d.isValid() ? d.format('YYYY-MM-DD HH:mm') : dateStr.substring(0, 16);
}

// Relative time (e.g., 5分钟前)
export function relativeTimeStr(dateStr) {
  if (!dateStr) return '';
  return dayjs(dateStr).fromNow();
}

// Truncate string
export function truncate(str, len = 30) {
  if (!str || str.length <= len) return str || '';
  return str.substring(0, len) + '...';
}

// Format number with commas
export function formatNum(n) {
  if (n === null || n === undefined) return '-';
  return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

// Debounce
export function debounce(fn, delay = 300) {
  let timer = null;
  return function (...args) {
    clearTimeout(timer);
    timer = setTimeout(() => fn.apply(this, args), delay);
  };
}
