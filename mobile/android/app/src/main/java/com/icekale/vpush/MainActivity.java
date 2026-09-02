package com.icekale.vpush;

import android.content.Intent;
import android.os.Build;
import android.os.Bundle;
import android.webkit.WebView;

import androidx.core.graphics.Insets;
import androidx.core.view.ViewCompat;
import androidx.core.view.WindowInsetsCompat;

import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {

    private static final String EXTRA_SWITCH_SERVER = "switch_server";

    // 最近一次系统栏 inset（CSS px，已按屏幕密度从物理像素换算）；
    // 页面每次加载完成后注入 CSS 变量，见 injectSafeAreaInsets()
    private int barInsetTop = 0;
    private int barInsetBottom = 0;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        if (getBridge() != null && getBridge().getWebView() != null) {
            WebView webView = getBridge().getWebView();
            webView.setWebViewClient(new AppLinkWebViewClient(getBridge(), this::injectSafeAreaInsets));
            if (Build.VERSION.SDK_INT >= 35) {
                // targetSdk 35 在 Android 15 上强制 edge-to-edge，WebView 会画到状态栏/导航栏下面。
                // 这里只负责把真实系统栏高度经 CSS 变量（--safe-top / --safe-bottom，
                // 定义见服务器前端 style.css 顶部）交给页面，由页面自己腾出空间；
                // Android 15 以下窗口仍自动避让系统栏，不注入以免出现双重留白。
                ViewCompat.setOnApplyWindowInsetsListener(webView, (v, windowInsets) -> {
                    Insets bars = windowInsets.getInsets(
                            WindowInsetsCompat.Type.statusBars()
                                    | WindowInsetsCompat.Type.navigationBars()
                                    | WindowInsetsCompat.Type.displayCutout());
                    // getInsets() 返回物理像素，而 WebView 里 1 CSS px = 1dp（viewport 为
                    // width=device-width），必须除以屏幕密度换算，否则注入的
                    // --safe-top/--safe-bottom 会放大 density 倍，顶部出现巨大留白。
                    float density = v.getResources().getDisplayMetrics().density;
                    barInsetTop = Math.round(bars.top / density);
                    barInsetBottom = Math.round(bars.bottom / density);
                    injectSafeAreaInsets();
                    return windowInsets;
                });
            }
        }
        if (hasSwitchServer(getIntent())) {
            gotoSetupPage();
        }
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        if (hasSwitchServer(intent)) {
            gotoSetupPage();
        }
    }

    private boolean hasSwitchServer(Intent intent) {
        return intent != null && intent.getBooleanExtra(EXTRA_SWITCH_SERVER, false);
    }

    /**
     * 回到本地壳页面并带 reset 标记：壳页面会清除已保存的服务器地址，
     * 显示「连接服务器」设置表单（见 mobile/www/index.html）。
     */
    private void gotoSetupPage() {
        if (getBridge() == null || getBridge().getWebView() == null) {
            return;
        }
        WebView webView = getBridge().getWebView();
        webView.post(() -> webView.loadUrl(getBridge().getAppUrl() + "?reset=1"));
    }

    /** 把系统栏高度写入当前页面（本地壳页或远端服务器页）的 CSS 变量；跨页导航后由 onPageFinished 重注入。 */
    private void injectSafeAreaInsets() {
        if (getBridge() == null || getBridge().getWebView() == null) {
            return;
        }
        WebView webView = getBridge().getWebView();
        webView.post(() -> webView.evaluateJavascript(
                "(function(){try{var s=document.documentElement.style;"
                        + "s.setProperty('--safe-top','" + barInsetTop + "px');"
                        + "s.setProperty('--safe-bottom','" + barInsetBottom + "px');}catch(e){}})();",
                null));
    }
}
