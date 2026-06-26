const fs = require('fs');
const col = fs.readFileSync('E:/杂七杂八/workbuddy/辅助/shuiwenzhihui/frontend/dashboard.html', 'utf-8');
const m = col.match(/<script>([\s\S]*?)<\/script>/);
const js = m[1];
const start = js.indexOf('async function ldMp');
// Find next top-level function or section
let end = js.indexOf('\nfunction ', start + 20);
if (end < 0) end = js.indexOf('\n// =====', start + 20);
if (end < 0) end = js.length;
const ldmp = js.substring(start, end);
fs.writeFileSync('colleague_ldmp.js', ldmp);
console.log('Extracted: ' + ldmp.length + ' chars');
// Also show key parts
console.log('First 100:', ldmp.substring(0, 100));
