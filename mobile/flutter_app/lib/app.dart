import 'package:flutter/material.dart';

import 'core/api_client.dart';
import 'core/app_router.dart';
import 'core/session_store.dart';
import 'core/theme/theme_controller.dart';
import 'core/theme/vpush_tokens.dart';

class VPushApp extends StatefulWidget {
  const VPushApp({super.key, required this.session, required this.api});

  final SessionStore session;
  final ApiClient api;

  @override
  State<VPushApp> createState() => _VPushAppState();
}

class _VPushAppState extends State<VPushApp> {
  late final ThemeController _themeController = ThemeController();
  late final router = buildRouter(
    api: widget.api,
    session: widget.session,
    themeController: _themeController,
  );

  @override
  void dispose() {
    router.dispose();
    _themeController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return ValueListenableBuilder<ThemeMode>(
      valueListenable: _themeController,
      builder: (context, mode, child) => MaterialApp.router(
        title: 'V Push',
        debugShowCheckedModeBanner: false,
        theme: VPushTokens.theme(Brightness.light),
        darkTheme: VPushTokens.theme(Brightness.dark),
        themeMode: mode,
        routerConfig: router,
      ),
    );
  }
}
