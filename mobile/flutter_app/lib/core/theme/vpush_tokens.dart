import 'package:flutter/material.dart';

abstract final class VPushColors {
  static const paper = Color(0xFFF5F5F7);
  static const surface = Color(0xFFFFFFFF);
  static const ink = Color(0xFF1D1D1F);
  static const inkStrong = Color(0xFF222C3C);
  static const inkMuted = Color(0xFF6E6E73);
  static const inkFaint = Color(0xFF667080);
  static const line = Color(0x1A0C1222);
  static const lineStrong = Color(0x290C1222);
  static const dutyBlue = Color(0xFF1668E0);
  static const dutyBlueStrong = Color(0xFF1258C4);
  static const danger = Color(0xFFDC2626);
  static const success = Color(0xFF3A6E4B);
  static const nightBg = Color(0xFF0F1115);
  static const nightSurface = Color(0xFF171A20);
  static const nightInk = Color(0xFFE4E6EB);
}

abstract final class VPushTokens {
  static const pagePadding = 16.0;
  static const controlHeight = 44.0;
  static const radius = 12.0;
  static const cardRadius = 18.0;
  static const bottomNavHeight = 48.0;

  static TextTheme textTheme(Brightness brightness) {
    final foreground = brightness == Brightness.dark
        ? VPushColors.nightInk
        : VPushColors.ink;
    final muted = brightness == Brightness.dark
        ? VPushColors.nightInk.withValues(alpha: 0.66)
        : VPushColors.inkMuted;
    return TextTheme(
      displaySmall: TextStyle(
        fontSize: 30,
        fontWeight: FontWeight.w600,
        height: 1.2,
        color: foreground,
      ),
      titleMedium: TextStyle(
        fontSize: 17,
        fontWeight: FontWeight.w600,
        height: 1.35,
        color: foreground,
      ),
      bodyLarge: TextStyle(fontSize: 15, height: 1.5, color: foreground),
      bodyMedium: TextStyle(fontSize: 13, height: 1.4, color: muted),
      labelLarge: TextStyle(
        fontSize: 13,
        fontWeight: FontWeight.w600,
        height: 1.3,
        color: foreground,
      ),
    );
  }

  static ThemeData theme(Brightness brightness) {
    final dark = brightness == Brightness.dark;
    final surface = dark ? VPushColors.nightSurface : VPushColors.surface;
    final background = dark ? VPushColors.nightBg : VPushColors.paper;
    final foreground = dark ? VPushColors.nightInk : VPushColors.ink;
    final scheme = ColorScheme(
      brightness: brightness,
      primary: VPushColors.dutyBlue,
      onPrimary: Colors.white,
      secondary: VPushColors.dutyBlueStrong,
      onSecondary: Colors.white,
      error: VPushColors.danger,
      onError: Colors.white,
      surface: surface,
      onSurface: foreground,
    );
    return ThemeData(
      brightness: brightness,
      colorScheme: scheme,
      scaffoldBackgroundColor: background,
      canvasColor: background,
      fontFamily: 'SF Pro SC',
      textTheme: textTheme(brightness),
      appBarTheme: AppBarTheme(
        backgroundColor: background,
        foregroundColor: foreground,
        elevation: 0,
        surfaceTintColor: Colors.transparent,
        centerTitle: false,
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: surface,
        contentPadding: const EdgeInsets.symmetric(
          horizontal: 14,
          vertical: 12,
        ),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(radius),
          borderSide: BorderSide(
            color: dark ? Colors.white24 : VPushColors.line,
          ),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(radius),
          borderSide: BorderSide(
            color: dark ? Colors.white24 : VPushColors.line,
          ),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(radius),
          borderSide: const BorderSide(color: VPushColors.dutyBlue, width: 1.5),
        ),
      ),
      dividerTheme: DividerThemeData(
        color: dark ? Colors.white12 : VPushColors.line,
        thickness: 1,
        space: 1,
      ),
      snackBarTheme: SnackBarThemeData(
        backgroundColor: dark
            ? VPushColors.nightSurface
            : VPushColors.inkStrong,
        contentTextStyle: const TextStyle(color: Colors.white, fontSize: 13),
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(radius),
        ),
      ),
    );
  }
}
