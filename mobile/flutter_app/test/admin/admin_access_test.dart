import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:vpush/core/api_client.dart';
import 'package:vpush/core/app_router.dart';
import 'package:vpush/core/session_store.dart';
import 'package:vpush/core/theme/theme_controller.dart';

class _MemoryVault implements SessionVault {
  @override
  Future<String?> read(String key) async => null;

  @override
  Future<void> write(String key, String value) async {}

  @override
  Future<void> delete(String key) async {}
}

void main() {
  testWidgets('a regular user cannot deep-link into admin pages', (
    tester,
  ) async {
    final session = SessionStore(vault: _MemoryVault());
    await session.load();
    await session.setAuthenticated('token', user: {'is_admin': false});
    final router = buildRouter(
      api: ApiClient(session: session),
      session: session,
      themeController: ThemeController(),
    );

    await tester.pumpWidget(MaterialApp.router(routerConfig: router));
    router.go('/admin/content');
    await tester.pumpAndSettle();

    expect(router.routeInformationProvider.value.uri.path, '/timeline');
    router.dispose();
  });

  testWidgets('a hidden news feature blocks article deep links as well', (
    tester,
  ) async {
    final session = SessionStore(vault: _MemoryVault());
    await session.load();
    await session.setAuthenticated('token', user: {'news_visible': false});
    final router = buildRouter(
      api: ApiClient(session: session),
      session: session,
      themeController: ThemeController(),
    );

    await tester.pumpWidget(MaterialApp.router(routerConfig: router));
    router.go('/news/11');
    await tester.pumpAndSettle();

    expect(router.routeInformationProvider.value.uri.path, '/timeline');
    router.dispose();
  });
}
