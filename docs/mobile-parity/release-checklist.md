# V Push Flutter Android 发布核对

更新时间：2026-09-10

## 已验证

- Flutter 3.47.2 / Dart 3.13.2；`dart analyze` 无问题。
- `flutter test`：24 项通过。
- `scripts/build_flutter_android.sh`：双 ABI release 构建和 ABI 集合检查通过。
- ARM64 API 35 模拟器：安装、冷启动和登录首屏渲染通过；冷启动 `TotalTime` 约 1062 ms；未见 `FATAL EXCEPTION`。
- v7 包：`net.vpush.app.dev`，versionName `0.1.0`，versionCode `1001`，minSdk `26`，targetSdk `36`，仅含 `armeabi-v7a`。
- arm64 包：`net.vpush.app.dev`，versionName `0.1.0`，versionCode `2001`，minSdk `26`，targetSdk `36`，仅含 `arm64-v8a`。
- 两个 APK 均通过 `apksigner verify`（APK Signature Scheme v2）和 `zipalign -c -P 16`；当前使用 debug 签名证书。

本次构建产物（2026-09-10）：

| 文件 | 大小 | SHA-256 |
| --- | ---: | --- |
| `vpush-0.1.0-armv7.apk` | 23,507,373 bytes | `b6e4ed295cefb3242b216515b1d1c0c03859f5b7148f204786672595b88aa53a` |
| `vpush-0.1.0-arm64.apk` | 27,929,527 bytes | `7c2feed8e994bb354944a84ee064c2fc75f9df9ce6e1d2f1634320ecd2f56e8c` |

## 尚未通过

- 正式签名、干净安装/覆盖升级和 App Links 证书配置。
- ARMv7 真机安装及运行；当前主机没有 ARMv7 设备或系统镜像。
- 真实账号的 Web ↔ Flutter 三种宽度、双主题截图/动效对照。
- Turnstile、原生 Android 通知、无 GMS 设备通道和通知点击路由。
- 完整管理员子页面、真实飞书附件/长 PDF 循环和 profile 性能采样。

以上未完成项关闭前，产物只能作为可运行 Beta 测试包分发。
