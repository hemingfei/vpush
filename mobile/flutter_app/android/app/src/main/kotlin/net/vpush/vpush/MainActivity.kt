package net.vpush.app.dev

import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.content.FileProvider
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel
import java.io.File
import java.util.UUID

class MainActivity : FlutterActivity() {
    private val channelName = "net.vpush/file_actions"
    private val appLinksChannelName = "net.vpush/app_links"
    private val pushChannelName = "net.vpush/push"
    private var appLinksChannel: MethodChannel? = null

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, channelName)
            .setMethodCallHandler { call, result ->
                if (call.method != "openFile") {
                    result.notImplemented()
                    return@setMethodCallHandler
                }
                val path = call.argument<String>("path")
                val mimeType = call.argument<String>("mimeType") ?: "application/octet-stream"
                if (path.isNullOrBlank()) {
                    result.success(false)
                    return@setMethodCallHandler
                }
                val file = File(path)
                val cacheRoot = cacheDir.canonicalFile
                val canonical = runCatching { file.canonicalFile }.getOrNull()
                if (canonical == null || !canonical.path.startsWith("${cacheRoot.path}/") || !canonical.isFile) {
                    result.success(false)
                    return@setMethodCallHandler
                }
                runCatching {
                    val uri = FileProvider.getUriForFile(this, "${packageName}.fileprovider", canonical)
                    val intent = Intent(Intent.ACTION_VIEW).apply {
                        setDataAndType(uri, mimeType)
                        addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                        addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                    }
                    startActivity(intent)
                }.onSuccess { result.success(true) }
                    .onFailure { result.success(false) }
            }
        appLinksChannel = MethodChannel(flutterEngine.dartExecutor.binaryMessenger, appLinksChannelName)
        appLinksChannel?.setMethodCallHandler { call, result ->
            if (call.method == "getInitialLink") {
                result.success(intent?.dataString)
            } else {
                result.notImplemented()
            }
        }
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, pushChannelName)
            .setMethodCallHandler { call, result ->
                when (call.method) {
                    "getDeviceInfo" -> result.success(deviceInfo())
                    "requestNotifications" -> {
                        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU ||
                            checkSelfPermission(android.Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED
                        ) {
                            result.success(true)
                        } else {
                            requestPermissions(arrayOf(android.Manifest.permission.POST_NOTIFICATIONS), 4101)
                            result.success(false)
                        }
                    }
                    else -> result.notImplemented()
                }
            }
    }

    override fun onNewIntent(newIntent: Intent) {
        super.onNewIntent(newIntent)
        setIntent(newIntent)
        newIntent.dataString?.let { appLinksChannel?.invokeMethod("onLink", it) }
    }

    private fun deviceInfo(): Map<String, String> {
        val preferences = getSharedPreferences("vpush.device", MODE_PRIVATE)
        val installationId = preferences.getString("installation_id", null)
            ?.trim()
            ?.takeIf { it.isNotEmpty() }
            ?: "android-${UUID.randomUUID()}".also {
                preferences.edit().putString("installation_id", it).apply()
            }
        val packageInfo = packageManager.getPackageInfo(packageName, 0)
        return mapOf(
            "installationId" to installationId,
            "provider" to "none",
            "token" to "",
            "deviceModel" to "${Build.MANUFACTURER} ${Build.MODEL}".trim(),
            "appVersion" to (packageInfo.versionName ?: ""),
        )
    }
}
