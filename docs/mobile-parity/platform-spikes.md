# Flutter Android 平台验证

## 2026-09-10 首轮结果

| 项目 | 结果 | 证据/下一步 |
| --- | --- | --- |
| Flutter/Dart | 通过，Flutter 3.47.2 / Dart 3.13.2 | `flutter doctor -v` |
| Android SDK command-line tools | 阻塞 | doctor 报告 `cmdline-tools component is missing` |
| Java/Gradle | 阻塞 | 当前 shell 未找到 Java Runtime；安装 JDK 17 后重跑 |
| Android 设备 | 未提供 | `adb devices -l` 无设备；需 ARM64 与 32 位 ARM 测试机/模拟器 |
| 空 Flutter 工程 pub get | 通过 | Flutter 工程已创建，依赖解析通过 |
| Android release APK | 未执行 | 等待 Android SDK/JDK 与设备 |
| `pdfrx` / Android PdfRenderer | 未选定 | 在工具链恢复后先跑中文、鉴权 PDF、100 页、缩放和内存测试 |
| HTML 正文渲染 | 未选定 | 用真实脱敏新闻/研报 fixture 比较段落、表格、图片、链接、选中文本 |
| Turnstile | 未执行 | 需要 HTTPS 测试实例和一次性 challenge；不在没有服务端验证的情况下绕过 |
| Android 远程通知 | 未选定 | 需要明确目标厂商/GMS 范围、SDK 凭证与服务许可；先不锁定 FCM 或厂商 SDK |

## 需要安装/提供的环境

1. Android Studio 或独立 Android command-line tools，并设置 `ANDROID_HOME`/`ANDROID_SDK_ROOT`。
2. JDK 17，并确保 `java -version` 和 Gradle 使用同一 JDK。
3. 一个支持 ARM64 的 Android 真机和一个能安装 `armeabi-v7a` 的 ARM 设备或模拟器；打开 USB 调试。
4. 脱敏测试账号、测试实例地址和稳定 fixture；如启用 Turnstile，提供允许的测试域名。
5. 若要求 App 关后台仍收通知，明确厂商通道、服务端凭证与测试范围。

恢复工具链后按顺序执行：`flutter doctor -v` → `flutter pub get` → `flutter build apk --release --split-per-abi` → 双 ABI 安装 → 插件 spike → 页面实现。
