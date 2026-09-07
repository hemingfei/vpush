package net.vpush.twa;

import android.app.Activity;
import android.content.Intent;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.util.Log;
import androidx.browser.customtabs.CustomTabColorSchemeParams;
import androidx.browser.customtabs.CustomTabsIntent;
import androidx.browser.trusted.TrustedWebActivityIntentBuilder;
import com.google.androidbrowserhelper.trusted.QualityEnforcer;
import com.google.androidbrowserhelper.trusted.TwaLauncher;

/**
 * 分发入口：设备上有支持 Custom Tabs 的浏览器（Chrome/Edge 等）时走 TWA 全屏壳；
 * 没有（多数国内 ROM）时退回内置 WebView。两条路径都只加载线上站点，无业务逻辑。
 */
public class SplashActivity extends Activity {
    private static final String TAG = "VPushTWA";
    private static final Uri LAUNCHER_URI = Uri.parse("https://vpush.net/");
    private static final int LIGHT_SYSTEM_BAR_COLOR = Color.rgb(245, 245, 247);
    private static final int DARK_SYSTEM_BAR_COLOR = Color.rgb(15, 17, 21);

    private TwaLauncher twaLauncher;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        if (hasCustomTabsProvider()) {
            Log.i(TAG, "custom tabs provider found, launching TWA");
            twaLauncher = new TwaLauncher(this);
            CustomTabColorSchemeParams lightColors = new CustomTabColorSchemeParams.Builder()
                    .setToolbarColor(LIGHT_SYSTEM_BAR_COLOR)
                    .build();
            CustomTabColorSchemeParams darkColors = new CustomTabColorSchemeParams.Builder()
                    .setToolbarColor(DARK_SYSTEM_BAR_COLOR)
                    .build();
            TrustedWebActivityIntentBuilder builder = new TrustedWebActivityIntentBuilder(LAUNCHER_URI)
                    .setDefaultColorSchemeParams(lightColors)
                    .setColorScheme(CustomTabsIntent.COLOR_SCHEME_SYSTEM)
                    .setColorSchemeParams(CustomTabsIntent.COLOR_SCHEME_DARK, darkColors);
            twaLauncher.launch(builder, new QualityEnforcer(), null, null);
        } else {
            Log.i(TAG, "no custom tabs provider, falling back to WebView");
            startActivity(new Intent(this, WebViewActivity.class));
            finish();
        }
    }

    @Override
    protected void onDestroy() {
        if (twaLauncher != null) {
            twaLauncher.destroy();
        }
        super.onDestroy();
    }

    private boolean hasCustomTabsProvider() {
        Intent service = new Intent("android.support.customtabs.action.CustomTabsService");
        return !getPackageManager().queryIntentServices(service, 0).isEmpty();
    }
}
