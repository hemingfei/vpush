import 'package:flutter_test/flutter_test.dart';

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
  test('session clears only for the current generation', () async {
    final session = SessionStore(vault: _MemoryVault());
    await session.load();
    await session.setAuthenticated('token-a', user: {'is_admin': false});
    final generation = session.generation;

    await session.clearIfGeneration(generation - 1);
    expect(session.isAuthenticated, isTrue);

    await session.clearIfGeneration(generation);
    expect(session.isAuthenticated, isFalse);
  });
}
