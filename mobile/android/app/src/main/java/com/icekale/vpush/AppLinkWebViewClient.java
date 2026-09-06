package com.icekale.vpush;

import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.net.Uri;
import android.webkit.WebResourceRequest;
import android.webkit.WebView;

import com.getcapacitor.Bridge;
import com.getcapacitor.BridgeWebViewClient;

/**
 * 自定义链接路由：
 * - 本地壳页面（localhost）发起的跳转 → 仅当指向用户配置的自托管服务器时应用内加载，
 *   其余外部主机打开系统浏览器
 * - 服务器站点内部的跳转（同主机同端口） → 应用内加载
 * - 其他外部主机（雪球 / 微博 / X 等） → 打开系统浏览器
 *
 * 不这样做的话，Capacitor 默认的 launchIntent 会把远端站点的所有
 * 同站导航都判定为「外链」甩到浏览器（因为 appUrl 始终是本地壳页面）。
 */
public class AppLinkWebViewClient extends BridgeWebViewClient {

    /** 每次页面加载完成（本地壳页或远端服务器页）后的回调，用于重新注入系统栏 inset。 */
    interface PageLoadListener {
        void onPageFinished();
    }

    // 壳页连接逻辑把服务器地址存在 @capacitor/preferences（Android 实现为
    // 名为 CapacitorStorage 的 SharedPreferences，值为原始字符串，见 mobile/www/index.html 的 KEY）
    private static final String PREFS_GROUP = "CapacitorStorage";
    private static final String SERVER_URL_KEY = "serverUrl";

    private final Bridge bridge;
    private final PageLoadListener pageLoadListener;

    public AppLinkWebViewClient(Bridge bridge) {
        this(bridge, null);
    }

    public AppLinkWebViewClient(Bridge bridge, PageLoadListener pageLoadListener) {
        super(bridge);
        this.bridge = bridge;
        this.pageLoadListener = pageLoadListener;
    }

    @Override
    public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
        Uri target = request.getUrl();
        String scheme = target.getScheme() == null ? "" : target.getScheme();
        if (!scheme.equals("http") && !scheme.equals("https")) {
            // intent://、market:// 等交给 Capacitor 默认处理
            return super.shouldOverrideUrlLoading(view, request);
        }
        // 说明：这里刻意不限制 http 明文流量——局域网 http 自托管是核心场景，
        // 强升 https 会直接断掉大部分自托管用户；安全性由用户自己选择的服务器地址决定。

        // 计算「允许应用内加载」的源（host + 有效端口）：
        // 当前在壳页时取用户配置的服务器地址；当前在服务器页时取当前地址本身
        String currentUrl = view.getUrl();
        Uri current = Uri.parse(currentUrl == null ? "" : currentUrl);
        String currentHost = current.getHost() == null ? "" : current.getHost();
        boolean currentIsLocalShell = "localhost".equals(currentHost);

        String allowedHost;
        int allowedPort;
        String allowedScheme;
        if (currentIsLocalShell) {
            // 壳页上不能「当前在壳页就放行任意链接」：只有指向配置服务器的链接才在应用内打开。
            // 读不到（尚未配置/存储被清）时保守放行应用内，保证首连流程（连接成功后
            // window.location.replace 跳服务器）不被卡死
            SharedPreferences prefs = bridge.getContext()
                    .getSharedPreferences(PREFS_GROUP, Context.MODE_PRIVATE);
            Uri server = Uri.parse(prefs.getString(SERVER_URL_KEY, ""));
            String host = server.getHost();
            if (host == null || host.isEmpty()) {
                return false; // 应用内加载（保守兜底，维持壳页可用）
            }
            allowedHost = host;
            allowedPort = server.getPort();
            allowedScheme = server.getScheme() == null ? "" : server.getScheme();
        } else {
            allowedHost = currentHost;
            allowedPort = current.getPort();
            allowedScheme = current.getScheme() == null ? "" : current.getScheme();
        }

        // 同主机同端口（端口按各自 scheme 归一化，未写端口视为 http=80 / https=443）→ 应用内加载
        if (target.getHost() != null
                && target.getHost().equals(allowedHost)
                && effectivePort(target.getScheme(), target.getPort())
                        == effectivePort(allowedScheme, allowedPort)) {
            return false; // 应用内加载
        }

        try {
            Intent intent = new Intent(Intent.ACTION_VIEW, target);
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            bridge.getContext().startActivity(intent);
        } catch (Exception ignored) {
            // 无可处理的应用时留在原地
        }
        return true;
    }

    /** 端口归一化：未显式指定时按 scheme 的默认端口（http=80、https=443）比较。 */
    private static int effectivePort(String scheme, int port) {
        if (port > 0) {
            return port;
        }
        return "https".equals(scheme) ? 443 : 80;
    }

    @Override
    public void onPageFinished(WebView view, String url) {
        super.onPageFinished(view, url);
        if (pageLoadListener != null) {
            pageLoadListener.onPageFinished();
        }
    }
}
