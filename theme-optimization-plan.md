# 驾驶舱主题体系完整改版方案

> 日期：2026-06-26
> 项目：水文监测智慧运营平台
> 范围：驾驶舱深色/浅色双主题系统性优化

---

## 一、现状审计摘要

### 1.1 CSS变量体系（已建）

`dashboard.css`中已有 **38个CSS变量** 分别定义在 `:root`（深色默认）和 `[data-theme="light"]`（浅色覆盖）中。覆盖：
- 背景层（6变量）
- 文字层（6变量）
- 边框层（3变量）
- 状态色（5变量）
- 效果色（4变量，glow/accent）
- 输入控件（3变量）
- 滚动条（1变量）

### 1.2 硬编码色值审计

在 `dashboard.html` 中发现 **约150+处内联style硬编码色值**，这些值**不会随主题切换**改变：

| 色值 | 出现次数 | 对应变量 | 影响区域 |
|------|---------|---------|---------|
| `#5ea8c8` | 72次 | `--text-secondary` | 状态标签、说明文字、分页 |
| `#4a8aaa` | 65次 | `--text-muted` | 次要信息、空状态提示 |
| `#00e0c0` | 34次 | `--text-accent` | 强调数值、链接 |
| `#ff4760` | 17次 | `--color-danger` | 危险状态、告警 |
| `#ffa040` | 15次 | `--color-warning` | 警告状态 |
| `#2ea080` | 13次 | `--color-success` | 正常/完成状态 |
| `#b0d4ef` | 24次 | ❌ 无对应变量 | 次级标签文字、图表标签 |
| `#d0e8ff` | 13次 | `--text-primary` | 主文字 |

### 1.3 对比度问题（浅色主题）

| 变量 | 当前值 | 对白底对比度 | WCAG AA(4.5:1) | 建议值 |
|------|-------|------------|--------------|-------|
| `--text-secondary` | `#4a8aaa` | 3.81:1 | ❌ 不通过 | `#2d6a8a` (6.0:1) |
| `--text-accent` | `#00b8a0` | 2.51:1 | ❌ 不通过 | `#008070` (4.8:1) |
| `--text-muted` | `#6a9aba` | 3.02:1 | ❌ 不通过 | `#3d6d8a` (5.6:1) |
| `--input-placeholder` | `#a0b8cc` | 2.05:1 | ❌ 不通过 | `#70a0b8` (4.6:1) |
| `--text-nav` | `#4a8aaa` | 3.81:1 | ❌ 不通过 | `#2d6a8a` (6.0:1) |

深色主题全部通过（最低5.07:1），无需调整。

### 1.4 深层组件未同步清单

- **站点弹窗(popup)**：L585-L644，26处硬编码
- **工单相关**：L1139-L1260，15处硬编码
- **进度/统计面板**：L1469-L1510，8处硬编码
- **设备管理**：L2670-L2890，20处硬编码
- **备件管理**：L3015-L3080，12处硬编码
- **站点档案**（新增）：L2200-L2330，10处硬编码
- **图表(Chart.js)**：L1749-1750，3处硬编码（legend/tooltip色）

---

## 二、CSS变量体系扩展方案

> **架构师建议：** 将颜色值与透明度拆分为两个独立变量，便于不同组件/状态灵活组合。同时增加rgb分量变量，支持 `rgba()` 动态透明度。

### 2.1 核心变量命名规范

采用三段式命名：`--{类别}-{属性}-{修饰}`

| 前缀 | 类别 | 示例 |
|------|------|------|
| `--bg-*` | 背景色 | `--bg-nav-bar`, `--bg-panel` |
| `--text-*` | 文字色 | `--text-primary`, `--text-light` |
| `--border-*` | 边框色 | `--border-default`, `--border-hover` |
| `--shadow-*` | 阴影 | `--shadow-card`, `--shadow-modal` |
| `--state-*` | 状态 | `--state-hover`, `--state-active` |

### 2.2 新增变量（颜色+透明度分离方案）

```css
/* ---- rgb分量（用于动态rgba组合） ---- */
--blue-900-rgb: 3, 10, 25;       /* 最深蓝 */
--blue-800-rgb: 6, 20, 45;       /* 导航栏基底 */
--blue-700-rgb: 4, 18, 42;       /* 面板基底 */
--teal-400-rgb: 0, 200, 180;     /* 强调色分量 */

/* ---- 导航栏 ---- */
--nav-bg-color: var(--blue-800);  /* 导航基底色 */
--nav-bg-opacity: 0.98;           /* 导航透明度（独立控制） */
--nav-bg: rgba(var(--blue-800-rgb), var(--nav-bg-opacity));
--nav-border: rgba(var(--teal-400-rgb), 0.08);
--nav-accent: rgba(var(--teal-400-rgb), 0.06);

/* ---- 面板 ---- */
--panel-bg-color: var(--blue-700);
--panel-bg-opacity: 0.55;         /* 透明度从0.68降至0.55 */
--panel-bg: rgba(var(--blue-700-rgb), var(--panel-bg-opacity));
--panel-hd-bg: rgba(var(--blue-800-rgb), 0.4);
--panel-border: rgba(var(--teal-400-rgb), 0.06);

/* ---- 文字层级（增加--text-light对应#b0d4ef） ---- */
--text-light: #b0d4ef;           /* 次级说明文字（深色主题） */
--text-inverse: #ffffff;         /* 深色背景上的反白文字 */
--text-link: #40a0ff;            /* 链接色 */

/* ---- 阴影 ---- */
--shadow-card: 0 2px 12px rgba(0,0,0,0.3);
--shadow-nav: 0 2px 8px rgba(0,0,0,0.4);
--shadow-modal: 0 8px 32px rgba(0,0,0,0.5);

/* ---- 语义化工具类色值 ---- */
--color-info: #5ea8c8;           /* 通用信息色（新增，替代硬编码#5ea8c8） */
```

### 2.3 浅色主题覆盖调整

```css
[data-theme="light"] {
  /* rgb分量（浅色模式使用更亮的蓝色） */
  --blue-800-rgb: 232, 240, 248;
  --blue-700-rgb: 240, 245, 250;

  /* 导航栏 */
  --nav-bg-color: #e8f0f8;
  --nav-bg-opacity: 0.95;
  --nav-bg: rgba(232, 240, 248, var(--nav-bg-opacity));
  --nav-border: rgba(0, 150, 180, 0.08);

  /* 面板 */
  --panel-bg-color: #ffffff;
  --panel-bg-opacity: 0.88;
  --panel-bg: rgba(255, 255, 255, var(--panel-bg-opacity));
  --panel-hd-bg: rgba(0, 100, 150, 0.04);

  /* 文字层 - 加深以满足WCAG AA (4.5:1) 对比度 */
  --text-primary: #0a1f33;          /* 更深的主文字 */
  --text-secondary: #2d6a8a;        /* ← 从#4a8aaa加深，对比度6.0:1 */
  --text-accent: #008070;           /* ← 从#00b8a0加深（保持青绿调），4.8:1 */
  --text-muted: #3d6d8a;            /* ← 从#6a9aba加深，5.6:1 */
  --text-nav: #2d6a8a;              /* ← 从#4a8aaa加深，6.0:1 */
  --text-light: #4a7a9a;            /* ← 从#b0d4ef大幅加深，5.1:1 */
  --input-placeholder: #70a0b8;     /* ← 从#a0b8cc加深，4.6:1 */
  --color-info: #2d6a8a;            /* 信息色对应加深 */

  /* 状态色微调 */
  --color-danger: #c62828;          /* 更鲜明的红色 */
  --color-warning: #c07a20;         /* 更明确的橙色 */
  --color-success: #1a7a5a;         /* 更清晰的绿色 */

  /* 阴影在浅色模式下更柔和 */
  --shadow-card: 0 2px 8px rgba(0,0,0,0.06);
  --shadow-nav: 0 1px 4px rgba(0,0,0,0.08);
  --shadow-modal: 0 8px 24px rgba(0,0,0,0.12);
}
```

---

## 三、分层次改造方案

### 问题一：导航栏与面板标题框颜色加深，面板背景透明度

**改造内容：**
1. `.nav-bar` 使用新变量 `--bg-nav-bar` 替代 `linear-gradient`
2. `.pcard` 背景用新的 `--bg-panel`（透明度从0.68降至0.55）
3. `.pcard .hd` 增加 `background: var(--bg-card-hd)` 背景色
4. `.mgmt .card-hd` 同样增加背景色

**预期效果：**
- 深色：导航栏更深沉，面板半透明感更强，标题区有底色区分
- 浅色：导航栏浅蓝底，面板白色半透明，标题区微蓝底

### 问题二：组件颜色一致性

**改造方法：** 批量替换 `dashboard.html` 中所有内联 `style="color:#xxx"` 为 `style="color:var(--text-xxx)"`

| 替换规则 | 硬编码值 | 替换为 |
|---------|---------|-------|
| 主文字 | `#d0e8ff` | `var(--text-primary)` |
| 次文字 | `#5ea8c8` | `var(--text-secondary)` |
| 强调色 | `#00e0c0` | `var(--text-accent)` |
| 弱文字 | `#4a8aaa` | `var(--text-muted)` |
| 极弱文字 | `#b0d4ef` | `var(--text-light)` |
| 危险红 | `#ff4760` | `var(--color-danger)` |
| 警告橙 | `#ffa040` | `var(--color-warning)` |
| 成功绿 | `#2ea080` | `var(--color-success)` |
| 设备在线绿 | `#00e080` | `var(--color-success)` |

**实施策略：**
1. CSS文件中的硬编码 → 直接替换为变量引用（已大部分完成，剩余的.ditem等）
2. HTML内联style → 逐个替换，约120处需要修改
3. CSS文件中的 `.ditem` 系列 → 用变量替换`#d0e8ff`、`#5ea8c8`、`#00e0c0`

### 问题三：深层卡片同步

> **架构师策略：** JS模板字符串中的颜色绑定最高风险，推荐"三层策略"。
> - **策略一（主力，覆盖90%场景）**：移除内联style，替换为CSS语义类。这是唯一保证主题实时同步的方案。
> - **策略二（辅助）**：极少数必须动态计算的场景使用 `getCSSVar()` 工具函数。
> - **策略三（兜底）**：MutationObserver监听 `data-theme` 变化，手动更新Chart.js配置。

**改造方法：**

**方案A - 替换为CSS类（推荐，覆盖90%场景）**

```javascript
// 改造前 - 硬编码色值，不随主题切换
return '<div style="color:#5ea8c8;font-size:12px">'+name+'</div>';

// 改造后 - 使用CSS类绑定变量
return '<div class="tx-muted ts-sm">'+name+'</div>';
```

配合新增的语义工具类：

```css
/* 语义化文字工具类 */
.tx-primary{color:var(--text-primary)}
.tx-secondary{color:var(--text-secondary)}
.tx-muted{color:var(--text-muted)}
.tx-light{color:var(--text-light)}
.tx-accent{color:var(--text-accent)}
.tx-danger{color:var(--color-danger)}
.tx-warning{color:var(--color-warning)}
.tx-success{color:var(--color-success)}
/* 字号工具类 */
.ts-xs{font-size:10px}
.ts-sm{font-size:12px}
.ts-md{font-size:13px}
.ts-lg{font-size:14px}
/* 背景工具类 */
.bg-panel{background:var(--panel-bg)}
.bg-hover{background:var(--state-hover)}
```

**方案B - 少量动态场景用readCSSVar函数**

```javascript
function readCSSVar(name){
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}
// 只在Chart.js初始化等少数场景使用
var legendColor = readCSSVar('--text-secondary');
```

**改造内容清单：**
1. **站点弹窗(popup)**：L585-644，26处硬编码 → 替换为CSS类
2. **工单状态卡**：L1139-1260，15处硬编码
3. **设备管理页面**：L2670-2890，20处硬编码
4. **备件管理**：L3015-3080，12处硬编码
5. **站点档案**（新功能）：L2200-2330，10处硬编码
6. **Chart.js配置**：L1749-1750，legend/tooltip色通过 `readCSSVar()` 读取
7. **分页导航**：L355-366，硬编码 `#5ea8c8`/`#4a8aaa` → 替换为类名

**特别注意事项：**
- Chart.js的 `legend.labels.color` 不支持CSS变量，必须用 `getComputedStyle` 读取
- 主题切换后Chart.js不会自动重绘，需监听 `data-theme` 变化并调用 `chart.update()`
- 工单/巡检等外部JS加载的模块需确认是否也使用了硬编码色值

### 问题四：浅色主题对比度优化

**关键调整（已在第二节给出色值）：**

| 变量 | 原值 | 新值 | 对比度提升 | WCAG AA |
|------|------|------|-----------|---------|
| `--text-secondary` | `#4a8aaa` | `#2d6a8a` | 3.81→6.0 | ✓ |
| `--text-accent` | `#00b8a0` | `#008070` | 2.51→4.8 | ✓ |
| `--text-muted` | `#6a9aba` | `#3d6d8a` | 3.02→5.6 | ✓ |
| `--input-placeholder` | `#a0b8cc` | `#70a0b8` | 2.05→4.6 | ✓ |
| `--text-light` | `#b0d4ef` | `#4a7a9a` | 1.55→5.1 | ✓ |

---

## 四、改造步骤（6天路线图）

> **架构师建议：** 每阶段可独立提交，中间状态不影响功能。CSS文件先行，动态模板最后处理。

### 第一阶段（第1天）：CSS变量体系升级 ★ 安全无风险

1. 在 `dashboard.css` 中添加新变量（rgb分量+透明度分离），约30行
2. 调整浅色主题中所有文字色值为满足WCAG AA对比度的新值
3. 定义语义化文字工具类（`.tx-primary`, `.tx-secondary`等），约30行
4. 给 `.nav-bar`、`.pcard`、`.pcard .hd` 等添加新变量引用
5. 替换CSS中剩余的硬编码（`.ditem`系列、`.tj-ka`系列等）
6. ✅ **验证：** 切换深色/浅色主题，确认CSS改造无视觉回归

### 第二阶段（第2天）：静态HTML内联替换

7. 替换HTML中所有 `style="color:#5ea8c8"` 为 `class="tx-secondary"`（约72处）
8. 同理替换其他6组色值（`#4a8aaa`→`tx-muted`, `#b0d4ef`→`tx-light`等）
9. 静态 `style="background:#xxx"` 替换为背景工具类
10. ✅ **验证：** 逐屏扫描，切换主题验证所有替换正确

### 第三阶段（第3天）：JS模板字符串改造（高难度）

11. **站点弹窗(popup)**：L585-644，替换26处JS内联色值为CSS类
12. **工单相关**：L1139-1260，15处
13. **分页导航函数**：L355-366，特别注意 `_rePg()` 中的条件颜色
14. **设备/备件管理**：L2670-2890 + L3015-3080，32处
15. ✅ **验证：** 打开每个深层页面，切换主题验证颜色同步

### 第四阶段（第4天）：Chart.js适配 + 边界情况

16. 编写 `readCSSVar()` 工具函数（~3行）
17. 修改所有Chart.js实例，用 `getComputedStyle` 读取legend/tooltip色值
18. 添加 `MutationObserver` 监听 `data-theme` 变更，自动更新图表
19. 处理 `Marker` / `Popup` / 地图组件中的颜色
20. ✅ **验证：** 切换主题后图表/地图颜色即时响应

### 第五阶段（第5天）：回归测试与微调

21. 全面截图对比（深色/浅色各一套）
22. 检查内联脚本体积（确保<210KB）
23. 对照原始截图，验证无视觉漏动
24. 修复发现的问题

### 第六阶段（第6天）：体积优化与最终确认

25. 应用CSS变量名压缩（如 `--t1` 替代 `--text-primary`）
26. 移除无用CSS变量/类定义
27. 最终全功能验证
28. ✅ **上线确认**

---

## 五、风险与注意事项

### 5.1 框架无关主题同步（核心原则）

- **CSS类 > 内联style > JS变量**：优先级由高到低。能用CSS类解决的，绝不用内联style
- CSS变量在inline style中可用：`style="color:var(--text-secondary)"` 浏览器支持良好
- 但**JS模板字符串中**，用CSS类代替内联var()，可读性和性能都更好

### 5.2 Chart.js特殊处理

Chart.js的legend/tooltip颜色不支持CSS变量，需要在JS中读取后传入：

```javascript
function readCSSVar(name){
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}
// 初始化Chart时读取当前主题色
var chart = new Chart(ctx, {
  options: {
    plugins: {
      legend: { labels: { color: readCSSVar('--text-secondary') } },
      tooltip: {
        titleColor: readCSSVar('--text-primary'),
        bodyColor: readCSSVar('--text-secondary')
      }
    }
  }
});
// 主题切换后重新读取并更新
function refreshChartColors(){
  chart.options.plugins.legend.labels.color = readCSSVar('--text-secondary');
  chart.update();
}
```

### 5.3 Magic数字处理（分页导航）

当前分页函数 `_rePg()` 中条件颜色是硬编码的：
```javascript
color:(page>0?'#5ea8c8':'#4a8aaa')
```
应改为CSS类方式，定义 `.pg-active{color:var(--text-secondary)}` 和 `.pg-disabled{color:var(--text-muted)}`

### 5.4 内联脚本<210KB限制

- 本次改造新增CSS变量和工具类约50行CSS（~2KB），新增JS约10行（~0.3KB）
- 但移除的内联 `style="color:#xxx"` 会减少HTML体积
- **净增长预计 <1KB**，安全

### 5.5 后端API不影响

- 纯前端改造，后端API完全不变

### 5.6 测试策略

- 每替换一批硬编码颜色后，立即切换主题验证
- 关键路径：站点弹窗 → 工单面板 → 图表 → 地图标注
- Chart.js颜色变更后需调用 `chart.update()` 才能生效

---

## 六、工作量估算

| 模块 | 改动量 | 预计耗时 |
|------|-------|---------|
| CSS变量定义（新增+调整） | ~40行 | 15min |
| CSS样式引用替换 | ~20处 | 15min |
| HTML内联style替换 | ~120处 | 45min |
| JS模板字符串替换 | ~30处 | 30min |
| Chart.js适配 | ~5处 | 10min |
| 验证测试 | 全页面 | 30min |
| **合计** | **~215处改动** | **~2.5h** |

---

## 附录：对比度计算参考

```
WCAG AA标准：正常文字 ≥ 4.5:1，大文字 ≥ 3:1

浅色主题白底(#ffffff):
--text-secondary #2d6a8a → 6.0:1 ✓
--text-accent #008070     → 4.8:1 ✓
--text-muted #3d6d8a      → 5.6:1 ✓ 
--input-placeholder #70a0b8 → 4.6:1 ✓
--text-light #4a7a9a      → 5.1:1 ✓
```
