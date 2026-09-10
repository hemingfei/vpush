import 'package:flutter/material.dart';

import 'app.dart';
import 'core/api_client.dart';
import 'core/session_store.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final session = SessionStore();
  await session.load();
  final api = ApiClient(session: session);
  if (session.isAuthenticated) {
    try {
      final user = await api.getJson('/me');
      session.setUser(user);
    } on Object {
      // Keep the stored session while offline; an authenticated request will
      // clear it when the server confirms that it is no longer valid.
    }
  }
  runApp(VPushApp(session: session, api: api));
}
