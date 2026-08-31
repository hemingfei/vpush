# V Push 跨平台客户端（mobile/）

用 **Capacitor** 把 V Push 现有网页前端封装成原生 App。App 本身只是一个很薄的"壳"：
首次启动填写你自托管服务器的地址，之后 WebView 直接加载服务器上的网页前端，
**功能与电脑浏览器访问完全一致**，服务器升级后 App 界面自动跟随，无需发版。

```
┌─────────────── App（Android WebView）───────────────┐
│  本地壳页面 www/index.html                            │
│  · 首次启动：输入服务器地址 → 探测可达性 → 记住        │
│  · 下次启动：自动探测后直接进入服务器前端              │
│           │ window.location.replace(服务器地址)       │
│           ▼                                          │
│  服务器上的网页前端（登录 / 订阅广场 / 设置 / 管理后台）│
│  · Bearer token 存在 WebView 的 localStorage，按域隔离 │
└──────────────────────────────────────────────────────┘
```

## 目录结构

| 路径 | 说明 |
| --- | --- |
| `www/index.html` | 本地壳页面：服务器地址设置 + 可达性探测 + 自动跳转 |
| `www/capacitor.js` | Capacitor 运行时（从 `@capacitor/core` 复制，`cap sync` 会保留） |
| `assets/` | 图标/启动图源文件（由 `app/static` 的现有资源生成） |
| `android/` | Android 原生工程（Gradle） |
| `capacitor.config.json` | Capacitor 配置 |

## 用户侧行为

- **首次启动**：显示"连接到你的自托管服务器"设置页，输入地址（支持局域网 `http://192.168.x.x:8000` 或公网 HTTPS），连接成功后自动进入网页前端
- **再次启动**：自动探测上次的服务器并直达；服务器不可达时回落到设置页并显示原因
- **切换服务器**：在桌面**长按 App 图标 → 切换服务器**快捷方式
- **外部链接**：帖子里的雪球 / 微博 / X 等站外链接会用系统浏览器打开，不会把用户带离 App
- **登录态**：与手机浏览器一致，存在 WebView 的 localStorage 里，退出登录 / 重新登录都走网页前端自己的逻辑

## Android 构建与运行

依赖：**JDK 21+**（Capacitor 7 要求源级别 21）、Android SDK（Platform 35）、Node.js。

```bash
cd mobile
npm install
npx cap sync android

# Windows 下没有全局 JDK 时，可用 Android Studio 自带 JBR（需为 21）或任意 JDK 21：
export JAVA_HOME="C:/Program Files/Android/Android Studio/jbr"
export ANDROID_HOME="$LOCALAPPDATA/Android/Sdk"

cd android
./gradlew assembleDebug     # 产物: app/build/outputs/apk/debug/app-debug.apk
./gradlew assembleRelease   # 正式包需要自行配置签名（见下）
```

仓库内 `.tools/` 曾用于放置便携 JDK 与 Gradle 离线包（构建加速用，不入库，已被 gitignore）。
`android/gradle/wrapper/gradle-wrapper.properties` 若指向了本地文件路径，构建后请还原为官方地址：

```
distributionUrl=https\://services.gradle.org/distributions/gradle-8.11.1-bin.zip
```

### 签名发布

生成 keystore 后在 `android/app/build.gradle` 补充 signingConfig（标准 Android 流程），
或直接用 Android Studio（`npx cap open android`）走 GUI 签名导出。

### 修改 App 图标 / 启动图

替换 `assets/icon*.png` / `assets/splash*.png` 后执行：

```bash
npx @capacitor/assets generate --android --assetPath assets
```

## iOS

iOS 构建必须在 macOS + Xcode 环境进行（本仓库在 Windows 上无法生成 ipa）：

```bash
cd mobile
npm install
npx cap add ios      # 仅在 macOS 上执行
npx cap sync ios
npx cap open ios     # Xcode 中配置签名后打包
```

注意：iOS 默认 ATS 会阻止 http 明文请求。若你的服务器只有 http（局域网），
需要在 `ios/App/App/Info.plist` 加 `NSAppTransportSecurity → NSAllowsArbitraryLoads = true`。

## Android 关键配置说明

| 配置 | 位置 | 作用 |
| --- | --- | --- |
| `usesCleartextTraffic="true"` | `AndroidManifest.xml` | 允许访问局域网 http 自托管服务 |
| `allowMixedContent` | `capacitor.config.json` | 壳页面（https）里探测 http 服务器时放行 |
| `AppLinkWebViewClient` | `MainActivity` 侧自定义 WebViewClient | 站内跳转留在 App，外部主机走系统浏览器；否则 Capacitor 默认会把远端站点的所有同站导航甩到浏览器 |
| `shortcuts.xml` | `res/xml/` | 桌面长按图标"切换服务器"快捷方式 |

## 已知限制（v1）

- ima 知识库 PDF 预览用 `window.open` 打开，Android WebView 无内置 PDF 渲染器，App 内可能显示空白；可在网页前端里长按链接复制地址后用浏览器打开（后续可加原生 PDF 打开插件）
- 壳页面探测用的是前端静态资源（`/icon-192.png`），只验证"服务器可达且是 V Push 前端"，不做版本比对
- 服务器地址必须填到根路径（网页前端本身用根相对路径请求 `/api/*`，不支持子路径反代部署——与网页端限制一致）
- 推送通知（浏览器 Web Push 渠道）在 WebView 内不可用，接收推送请继续用 Telegram / 飞书 / 企业微信 / Bark 等渠道
