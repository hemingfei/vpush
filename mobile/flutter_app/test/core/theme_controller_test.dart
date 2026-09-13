import 'package:flutter_test/flutter_test.dart';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:vpush/core/theme/theme_controller.dart';

void main() {
  test('loads and persists the selected theme mode', () async {
    SharedPreferences.setMockInitialValues({'vpush.theme': 'dark'});
    final controller = ThemeController();
    await controller.load();
    expect(controller.value, ThemeMode.dark);

    controller.setMode(ThemeMode.light);
    await Future<void>.delayed(Duration.zero);
    final preferences = await SharedPreferences.getInstance();
    expect(preferences.getString('vpush.theme'), 'light');
    controller.dispose();
  });
}
