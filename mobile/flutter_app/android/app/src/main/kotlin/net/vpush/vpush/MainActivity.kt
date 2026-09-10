package net.vpush.app.dev

import android.content.Intent
import androidx.core.content.FileProvider
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel
import java.io.File

class MainActivity : FlutterActivity() {
    private val channelName = "net.vpush/file_actions"

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
    }
}
