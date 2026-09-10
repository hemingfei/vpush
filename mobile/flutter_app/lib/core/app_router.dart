import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../features/admin/admin_page.dart';
import '../features/auth/auth_page.dart';
import '../features/knowledge/knowledge_page.dart';
import '../features/news/news_page.dart';
import '../features/plaza/plaza_page.dart';
import '../features/settings/settings_page.dart';
import '../features/shell/app_shell.dart';
import '../features/timeline/timeline_page.dart';
import 'api_client.dart';
import 'session_store.dart';
import 'theme/theme_controller.dart';
import 'widgets/vpush_page.dart';

GoRouter buildRouter({
  required ApiClient api,
  required SessionStore session,
  required ThemeController themeController,
}) {
  return GoRouter(
    initialLocation: session.isAuthenticated ? '/timeline' : '/login',
    refreshListenable: session,
    redirect: (context, state) {
      final path = state.uri.path;
      final isAuthRoute = path == '/login' || path == '/register';
      if (!session.isAuthenticated && !isAuthRoute) return '/login';
      if (session.isAuthenticated && isAuthRoute) return '/timeline';
      if (path.startsWith('/admin') &&
          session.user != null &&
          !session.isAdmin) {
        return '/timeline';
      }
      if (path == '/news' && !session.newsVisible) return '/timeline';
      return null;
    },
    routes: [
      GoRoute(
        path: '/login',
        builder: (context, state) => AuthPage(api: api, session: session),
      ),
      GoRoute(
        path: '/register',
        builder: (context, state) =>
            AuthPage(api: api, session: session, register: true),
      ),
      ShellRoute(
        builder: (context, state, child) => AppShell(
          location: state.uri.path,
          session: session,
          themeController: themeController,
          child: child,
        ),
        routes: [
          GoRoute(
            path: '/timeline',
            builder: (context, state) => const TimelinePage(),
          ),
          GoRoute(path: '/news', builder: (context, state) => const NewsPage()),
          GoRoute(
            path: '/home',
            builder: (context, state) => const PlazaPage(),
          ),
          GoRoute(
            path: '/settings',
            builder: (context, state) => const SettingsPage(),
          ),
          GoRoute(
            path: '/knowledge',
            builder: (context, state) => const KnowledgePage(),
          ),
          GoRoute(
            path: '/more',
            builder: (context, state) => const VPushPage(
              title: '更多',
              description: '管理员功能入口。',
              icon: Icons.more_horiz,
            ),
          ),
          GoRoute(
            path: '/kol/:id',
            builder: (context, state) => VPushPage(
              title: '大 V 详情',
              description: '查看 ${state.pathParameters['id']} 的资料与动态。',
              icon: Icons.person_outline,
            ),
          ),
          GoRoute(
            path: '/admin/:section',
            builder: (context, state) => AdminPage(
              section: state.pathParameters['section'] ?? 'content',
            ),
          ),
        ],
      ),
    ],
  );
}
