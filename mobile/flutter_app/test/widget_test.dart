import 'package:flutter_test/flutter_test.dart';

import 'package:vpush/app.dart';
import 'package:vpush/core/api_client.dart';
import 'package:vpush/core/session_store.dart';

class _MemoryVault implements SessionVault {
  String? value;

  @override
  Future<String?> read(String key) async => value;

  @override
  Future<void> write(String key, String value) async => this.value = value;

  @override
  Future<void> delete(String key) async => value = null;
}

void main() {
  testWidgets('unauthenticated app opens the V Push login shell', (
    tester,
  ) async {
    final session = SessionStore(vault: _MemoryVault());
    await session.load();
    final api = ApiClient(session: session);
    await tester.pumpWidget(VPushApp(session: session, api: api));
    await tester.pumpAndSettle();

    expect(find.text('V Push'), findsOneWidget);
    expect(find.text('登录'), findsOneWidget);
  });
}
