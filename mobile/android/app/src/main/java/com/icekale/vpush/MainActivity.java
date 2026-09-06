package com.icekale.vpush;

import android.app.AlertDialog;
import android.content.Intent;
import android.os.Build;
import android.os.Bundle;
import android.view.ViewGroup.MarginLayoutParams;
import android.webkit.WebView;

import androidx.activity.OnBackPressedCallback;
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
                    Insets ime = windowInsets.getInsets(WindowInsetsCompat.Type.ime());
                    // getInsets() 返回物理像素，而 WebView 里 1 CSS px = 1dp（viewport 为
                    // width=device-width），必须除以屏幕密度换算，否则注入的
                    // --safe-top/--safe-bottom 会放大 density 倍，顶部出现巨大留白。
                    float density = v.getResources().getDisplayMetrics().density;
                    barInsetTop = Math.round(bars.top / density);
                    barInsetBottom = Math.round(bars.bottom / density);
                    injectSafeAreaInsets();
                    // 键盘：edge-to-edge 下 manifest 的 adjustResize 对 IME 不再生效——窗口
                    // 不随键盘收缩、键盘纯悬浮，WebView 不知道键盘存在，登录页等表单聚焦时
                    // 输入框被盖住只能盲输。把 ime inset 作为 WebView 底部 margin（物理像素；
                    // ime.bottom 自窗口底边量起、已含导航栏区域），视口随键盘收窄，浏览器会
                    // 自动把聚焦输入框滚到键盘上方，等价旧版 adjustResize；收起时 ime.bottom
                    // 回 0 还原。只在值变化时 setLayoutParams，避免 insets 分发触发多余重排。
                    MarginLayoutParams lp = (MarginLayoutParams) v.getLayoutParams();
                    if (lp.bottomMargin != ime.bottom) {
                        lp.bottomMargin = ime.bottom;
                        v.setLayoutParams(lp);
                    }
                    return windowInsets;
                });
            }
        }
        handleBackPress();
        if (hasSwitchServer(getIntent())) {
            gotoSetupPage();
        }
    }

    /**
     * 返回键改为页面级返回：先问当前页面要不要自己消费（关抽屉/弹窗、页内子页返回，
     * 见服务器前端 app.js 的 window.__VPUSH_BACK__），页面没消费时退 WebView 历史，
     * 已到根再弹「退出」确认框，而不是按一下就退 APP。
     * 连接设置壳页没有该钩子（返回 false），行为退化为确认退出，符合预期。
     */
    private void handleBackPress() {
        getOnBackPressedDispatcher().addCallback(this, new OnBackPressedCallback(true) {
            @Override
            public void handleOnBackPressed() {
                WebView webView = getBridge() != null ? getBridge().getWebView() : null;
                if (webView == null) {
                    finish();
                    return;
                }
                // 表达式返回 JS 布尔值，evaluateJavascript 回调收到 JSON 字面量 true/false（无引号）；
                // 若返回字符串则带 JSON 引号，equals 会永远不成立
                webView.evaluateJavascript(
                        "(function(){try{return !!(window.__VPUSH_BACK__"
                                + "&&window.__VPUSH_BACK__());}catch(e){return false;}})();",
                        value -> webView.post(() -> {
                            if ("true".equals(value)) {
                                return; // 页面已消费（关了抽屉/弹窗或做了页内返回）
                            }
                            if (webView.canGoBack()) {
                                webView.goBack();
                                return;
                            }
                            new AlertDialog.Builder(MainActivity.this)
                                    .setMessage(R.string.exit_confirm_message)
                                    .setNegativeButton(R.string.exit_cancel, null)
                                    .setPositiveButton(R.string.exit_ok,
                                            (d, w) -> finish())
                                    .show();
                        }));
            }
        });
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
