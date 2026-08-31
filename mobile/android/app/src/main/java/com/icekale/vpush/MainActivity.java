package com.icekale.vpush;

import android.content.Intent;
import android.os.Bundle;
import android.webkit.WebView;

import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {

    private static final String EXTRA_SWITCH_SERVER = "switch_server";

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        if (getBridge() != null && getBridge().getWebView() != null) {
            getBridge().getWebView().setWebViewClient(new AppLinkWebViewClient(getBridge()));
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
}
