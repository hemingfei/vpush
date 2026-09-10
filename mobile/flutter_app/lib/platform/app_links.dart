import 'package:flutter/services.dart';

/// Converts Android App Links and the vpush:// scheme into internal routes.
/// Only routes understood by the app are accepted; external URLs stay external.
class AppLinkResolver {
  const AppLinkResolver._();

  static const _hosts = {'vpush.net', 'www.vpush.net'};

  static String? resolve(Uri uri) {
    String path;
    if (uri.scheme == 'https') {
      if (!_hosts.contains(uri.host.toLowerCase())) return null;
      path = uri.path;
    } else if (uri.scheme == 'vpush') {
      path = uri.host.isEmpty ? uri.path : '/${uri.host}${uri.path}';
    } else {
      return null;
    }
    return _resolvePath(path, uri.queryParameters);
  }

  static String? resolveRoute(String value) {
    final uri = Uri.tryParse(value);
    if (uri == null || uri.path.isEmpty || uri.hasScheme) return null;
    return _resolvePath(uri.path, uri.queryParameters);
  }

  static String? _resolvePath(String value, Map<String, String> query) {
    var path = value;
    if (!path.startsWith('/')) path = '/$path';
    path = path.replaceFirst(RegExp(r'/+$'), '');
    if (path.isEmpty) path = '/timeline';

    if (path == '/timeline' ||
        path == '/news' ||
        path == '/settings' ||
        path == '/knowledge' ||
        path == '/more') {
      return query.isEmpty ? path : null;
    }
    if (path == '/mysubs') {
      return query.isEmpty ? '/home?subscribed=1' : null;
    }
    if (path == '/combinations') {
      return query.isEmpty ? '/home' : null;
    }
    if (path == '/home') {
      if (query.isEmpty) return path;
      if (query.length == 1 &&
          (query['subscribed'] == '0' || query['subscribed'] == '1')) {
        return '/home?subscribed=${query['subscribed']}';
      }
      return null;
    }
    if (RegExp(r'^/news/[1-9][0-9]*$').hasMatch(path) ||
        RegExp(r'^/kol/[1-9][0-9]*$').hasMatch(path)) {
      return query.isEmpty ? path : null;
    }
    if (RegExp(r'^/knowledge/[A-Za-z0-9._-]{1,128}$').hasMatch(path)) {
      if (query.isEmpty) return path;
      final group = query['group'];
      if (query.length == 1 &&
          group != null &&
          RegExp(r'^[A-Za-z0-9._:-]{1,128}$').hasMatch(group)) {
        return '$path?group=$group';
      }
      return null;
    }
    if (RegExp(r'^/admin/[A-Za-z0-9_-]{1,64}$').hasMatch(path)) {
      return query.isEmpty ? path : null;
    }
    return null;
  }
}

/// Receives initial and subsequent Android intents from MainActivity.
class AppLinksBridge {
  AppLinksBridge({MethodChannel? channel})
    : _channel = channel ?? const MethodChannel('net.vpush/app_links');

  final MethodChannel _channel;
  void Function(String route)? _onRoute;

  static Future<String?> initialRoute({MethodChannel? channel}) async {
    final bridge = AppLinksBridge(channel: channel);
    try {
      final value = await bridge._channel.invokeMethod<String>(
        'getInitialLink',
      );
      final uri = value == null ? null : Uri.tryParse(value);
      return uri == null ? null : AppLinkResolver.resolve(uri);
    } on Object {
      return null;
    }
  }

  void listen(void Function(String route) onRoute) {
    _onRoute = onRoute;
    _channel.setMethodCallHandler((call) async {
      if (call.method != 'onLink' || call.arguments is! String) return;
      final uri = Uri.tryParse(call.arguments as String);
      final route = uri == null ? null : AppLinkResolver.resolve(uri);
      if (route != null) _onRoute?.call(route);
    });
  }

  void dispose() {
    _onRoute = null;
    _channel.setMethodCallHandler(null);
  }
}
