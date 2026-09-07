# 安卓 TWA 状态栏与页面背景色不一致 — 解决方案

## 现象

TWA 壳(或 PWA 安装态)打开站点时,状态栏底色与页面内容区背景色存在一条可见色差(浅色模式:状态栏偏亮偏蓝,内容区偏灰;深色模式同样存在、更难察觉)。桌面浏览器全屏无此问题,仅在状态栏被单独涂色的场景(TWA / PWA standalone)可见。

## 根因

Chrome 在 TWA/独立窗口中按网页的 `theme-color` 涂状态栏,而内容区用 CSS 背景令牌,站点上两套值不一致:

| 来源 | 浅色 | 深色 | 用途 |
|---|---|---|---|
| `index.html` `<meta name="theme-color">`(JS 运行时同步写入同值) | `#f8f8fb` | `#11141a` | **状态栏** |
| `vendor/design-tokens.css` `--color-bg` | `#f5f5f7` | `#0f1115` | **页面背景** |

两套颜色值不一致,拼在一起形成色带。TWA/PWA 路径可先从 Web 端修复;内置 WebView 兜底路径仍需真机单独验收。

## 修复(纯 Web 端,4 个文件;TWA/PWA 路径不需要重发 APK)

原则:让 `theme-color` 对齐 `--color-bg`。

1. `app/static/index.html`
   - 静态 meta:`<meta name="theme-color" content="#f8f8fb">` → `#f5f5f7`
   - 内联 JS:`themeColor.content = dark ? "#11141a" : "#f8f8fb"` → `dark ? "#0f1115" : "#f5f5f7"`
   - manifest 版本参数 bump:`/manifest.webmanifest?v=2` → `?v=3`(dark 同理),否则 Chrome 可能继续用缓存的旧 manifest
2. `app/static/manifest.webmanifest`:`theme_color: #f8f8fb` → `#f5f5f7`
   - `background_color: #f8f8fb` 同步改为 `#f5f5f7`,避免冷启动背景产生色差
3. `app/static/manifest-dark.webmanifest`:`theme_color: #11141a` → `#0f1115`
4. `app/static/app.js`
   - `applyTheme()` 写入的浅/深 `theme-color` 同步改为 `#f5f5f7` / `#0f1115`
   - 两条 manifest 链接同步升级为 `?v=3`,避免运行时切回旧版本 URL

不建议反向改 `--color-bg` 去迁就 `#f8f8fb`:那会动全站视觉规范(DESIGN.md 的背景基色)。

## 验收

1. 随常规 Web 发版后,冷启动 VPush 壳(TWA),浅色模式:状态栏与页面顶部应完全无缝;
2. 刷新页面、站内切换深浅主题、自动模式下切换系统主题,状态栏均应与页面顶部一致;
3. 桌面浏览器回归确认无视觉变化(theme-color 不影响桌面渲染);
4. 在无 Custom Tabs 浏览器的设备上单独验证 WebView 兜底路径。

## 备注

- TWA/PWA 路径的修复只涉及 Web 资产,壳 APK 无需变更。WebView 兜底路径是否需要原生同步状态栏颜色,由真机验收结果决定。
- 若状态栏颜色在某些机型仍短暂不跟随,先重启 TWA 会话并确认已加载 `?v=3` manifest;不能仅凭现象判定为缓存问题。
