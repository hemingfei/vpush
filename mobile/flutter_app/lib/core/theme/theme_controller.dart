import 'package:flutter/material.dart';

class ThemeController extends ValueNotifier<ThemeMode> {
  ThemeController() : super(ThemeMode.system);

  void toggle(Brightness platformBrightness) {
    value = value == ThemeMode.dark
        ? ThemeMode.light
        : value == ThemeMode.light
        ? ThemeMode.system
        : platformBrightness == Brightness.dark
        ? ThemeMode.light
        : ThemeMode.dark;
  }
}
