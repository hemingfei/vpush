import 'package:go_router/go_router.dart';

import '../features/admin/admin_page.dart';
import '../features/auth/auth_page.dart';
import '../features/knowledge/knowledge_page.dart';
import '../features/news/news_page.dart';
import '../features/plaza/plaza_page.dart';
import '../features/plaza/kol_detail_page.dart';
import '../features/settings/settings_page.dart';
import '../features/shell/app_shell.dart';
import '../features/timeline/timeline_page.dart';
import 'api_client.dart';
import 'session_store.dart';
import 'theme/theme_controller.dart';

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
      if (path.startsWith('/news') && !session.newsVisible) return '/timeline';
      if ((path == '/more' || path.startsWith('/admin')) && !session.isAdmin) {
        return '/timeline';
      }
      return null;
    },
    routes: [
      GoRoute(
        path: '/login',
        builder: (context, state) => AuthPage(
          api: api,
          session: session,
          themeController: themeController,
        ),
      ),
      GoRoute(
        path: '/register',
        builder: (context, state) => AuthPage(
          api: api,
          session: session,
          themeController: themeController,
          register: true,
        ),
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
            builder: (context, state) => TimelinePage(api: api),
          ),
          GoRoute(
            path: '/news',
            builder: (context, state) => NewsPage(api: api),
          ),
          GoRoute(
            path: '/news/:id',
            builder: (context, state) => NewsArticlePage(
              api: api,
              articleId: int.tryParse(state.pathParameters['id'] ?? '') ?? 0,
            ),
          ),
          GoRoute(
            path: '/home',
            builder: (context, state) => PlazaPage(
              api: api,
              subscribedOnly: state.uri.queryParameters['subscribed'] == '1',
            ),
          ),
          GoRoute(
            path: '/mysubs',
            redirect: (context, state) => '/home?subscribed=1',
          ),
          GoRoute(path: '/combinations', redirect: (context, state) => '/home'),
          GoRoute(
            path: '/settings',
            builder: (context, state) =>
                SettingsPage(api: api, session: session),
          ),
          GoRoute(
            path: '/knowledge',
            builder: (context, state) => KnowledgePage(api: api),
          ),
          GoRoute(
            path: '/knowledge/:id',
            builder: (context, state) => KnowledgePage(
              api: api,
              mediaId: state.pathParameters['id'],
              groupId: state.uri.queryParameters['group'] ?? '',
            ),
          ),
          GoRoute(
            path: '/more',
            builder: (context, state) => AdminPage(api: api, section: 'hub'),
          ),
          GoRoute(
            path: '/kol/:id',
            builder: (context, state) => KolDetailPage(
              api: api,
              kolId: int.tryParse(state.pathParameters['id'] ?? '') ?? 0,
            ),
          ),
          GoRoute(
            path: '/admin/:section',
            builder: (context, state) => AdminPage(
              api: api,
              section: state.pathParameters['section'] ?? 'content',
            ),
          ),
        ],
      ),
    ],
  );
}
