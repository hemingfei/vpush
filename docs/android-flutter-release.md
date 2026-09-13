# V Push Android 发布

## 构建前提

- Flutter 3.47.x / Dart 3.13.x。
- JDK 17、Android SDK command-line tools、Build Tools 和 API 37（`flutter_secure_storage` 11.0.0 的编译要求；target SDK 仍为 36）。
- 已连接 ARM64 与 ARMv7 测试设备，且 `adb devices -l` 可见。
- 正式签名资料通过本地 `android/key.properties` 注入；该文件和 keystore 不提交。

## 本地构建

从仓库根目录执行：

```bash
API_BASE_URL=https://vpush.net scripts/build_flutter_android.sh
```

脚本先执行格式化检查、Dart 静态分析和 Flutter 测试，再生成：

- `mobile/flutter_app/build/app/outputs/flutter-apk/vpush-<version>-armv7.apk`
- `mobile/flutter_app/build/app/outputs/flutter-apk/vpush-<version>-arm64.apk`

构建参数只包含服务地址，不放 token、cookie 或签名密码。脚本使用 `dart analyze`；Flutter 3.47.2 的 `flutter analyze` 在包含非 ASCII 字符的工作路径下存在 LSP 长度计算问题。

脚本会检查两个 APK 的本地库目录只包含目标 ABI，并打印 SHA-256。CI 使用同一脚本生成并上传未签名（debug signing）测试产物；正式签名需通过受保护的 `android/key.properties` 和 keystore 配置后再构建。

## 签名与 APK 检查

配置正式签名后重新构建，随后对每个 APK 执行：

```bash
apkanalyzer manifest application-id path/to/app.apk
apkanalyzer manifest min-sdk path/to/app.apk
apkanalyzer manifest target-sdk path/to/app.apk
apksigner verify --verbose --print-certs path/to/app.apk
unzip -l path/to/app.apk | rg 'lib/(armeabi-v7a|arm64-v8a)/'
```

v7 包只能包含 `armeabi-v7a` 本地库，arm64 包只能包含 `arm64-v8a` 本地库；两包都必须包含 Flutter engine、应用和插件 native library。记录 split 后实际 versionCode，后续发布对每个 ABI 单调递增。

## 设备验收

```bash
adb shell getprop ro.product.cpu.abilist
adb install -r path/to/vpush-<version>-arm64.apk
adb logcat -c
adb logcat | rg 'AndroidRuntime|FATAL EXCEPTION|flutter'
```

逐个 ABI 验证登录、动态筛选/刷新、订阅、新闻长文、研报摘要和 PDF、主题切换、系统返回、后台恢复。用 `adb shell dumpsys meminfo net.vpush.app.dev` 记录长文/PDF 循环前后内存；在 16KB 页设备或模拟器上再做一次 PDF 和通知流程。

ARMv7 设备不应安装 arm64 包；仅支持 64 位应用的设备不应以 v7 包作为覆盖方案。正式包名、签名和现有 TWA 是否覆盖安装，在首次签名前固定并记录。
