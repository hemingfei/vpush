package com.icekale.vpush;

import android.content.Intent;
import android.net.Uri;
import android.webkit.WebResourceRequest;
import android.webkit.WebView;

import com.getcapacitor.Bridge;
import com.getcapacitor.BridgeWebViewClient;

/**
 * 自定义链接路由：
 * - 本地壳页面（localhost）发起的跳转 → 允许在应用内加载（进入用户配置的自托管服务器）
 * - 服务器站点内部的跳转（同主机） → 应用内加载
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

        String currentUrl = view.getUrl();
        Uri current = Uri.parse(currentUrl == null ? "" : currentUrl);
        String currentHost = current.getHost() == null ? "" : current.getHost();
        boolean currentIsLocalShell = "localhost".equals(currentHost);

        if (currentIsLocalShell || currentHost.equals(target.getHost())) {
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

    @Override
    public void onPageFinished(WebView view, String url) {
        super.onPageFinished(view, url);
        if (pageLoadListener != null) {
            pageLoadListener.onPageFinished();
        }
    }
}
