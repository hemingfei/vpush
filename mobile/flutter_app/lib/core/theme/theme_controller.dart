import 'dart:async';

import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

class ThemeController extends ValueNotifier<ThemeMode> {
  ThemeController() : super(ThemeMode.system);

  static const _preferenceKey = 'vpush.theme';
  SharedPreferences? _preferences;

  Future<void> load() async {
    try {
      _preferences ??= await SharedPreferences.getInstance();
      final stored = _preferences!.getString(_preferenceKey);
      final mode = switch (stored) {
        'light' => ThemeMode.light,
        'dark' => ThemeMode.dark,
        'system' => ThemeMode.system,
        _ => null,
      };
      if (mode != null) value = mode;
    } on Object {
      // A missing preferences backend should not block the first screen.
    }
  }

  Future<void> setMode(ThemeMode mode) async {
    value = mode;
    try {
      _preferences ??= await SharedPreferences.getInstance();
      await _preferences!.setString(_preferenceKey, _name(mode));
    } on Object {
      // Theme changes remain active for the current process when persistence fails.
    }
  }

  void toggle(Brightness platformBrightness) {
    final mode = value == ThemeMode.dark
        ? ThemeMode.light
        : value == ThemeMode.light
        ? ThemeMode.system
        : platformBrightness == Brightness.dark
        ? ThemeMode.light
        : ThemeMode.dark;
    unawaited(setMode(mode));
  }

  String _name(ThemeMode mode) => switch (mode) {
    ThemeMode.light => 'light',
    ThemeMode.dark => 'dark',
    ThemeMode.system => 'system',
  };
}
