import 'package:flutter_test/flutter_test.dart';

import 'package:vpush/features/shell/app_shell.dart';

void main() {
  test('bottom navigation hides only after 24px downward travel', () {
    final navigation = BottomNavVisibility();
    navigation.update(pixels: 23, maxScrollExtent: 200);
    expect(navigation.visible, isTrue);

    navigation.update(pixels: 24, maxScrollExtent: 200);
    expect(navigation.visible, isFalse);
  });

  test('bottom navigation reappears after 8px upward travel', () {
    final navigation = BottomNavVisibility();
    navigation.update(pixels: 24, maxScrollExtent: 200);
    expect(navigation.visible, isFalse);

    navigation.update(pixels: 18, maxScrollExtent: 200);
    expect(navigation.visible, isFalse);
    navigation.update(pixels: 16, maxScrollExtent: 200);
    expect(navigation.visible, isTrue);
  });
}
