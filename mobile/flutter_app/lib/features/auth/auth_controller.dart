import 'package:flutter/foundation.dart';

import '../../core/api_client.dart';
import '../../core/session_store.dart';

class AuthController extends ChangeNotifier {
  AuthController({required this.api, required this.session});

  final ApiClient api;
  final SessionStore session;
  bool isBusy = false;
  String? error;

  Future<bool> login(String username, String password) async {
    return _submit('/auth/login', {
      'username': username.trim(),
      'password': password,
      'cf-turnstile-response': '',
    });
  }

  Future<bool> register(String username, String password, String code) async {
    return _submit('/auth/register', {
      'username': username.trim(),
      'password': password,
      'code': code.trim(),
      'cf-turnstile-response': '',
    });
  }

  Future<bool> _submit(String path, Map<String, dynamic> body) async {
    if (isBusy) return false;
    isBusy = true;
    error = null;
    notifyListeners();
    try {
      final data = await api.postJson(path, body: body);
      final token = data['token'];
      if (token is! String || token.isEmpty) {
        throw ApiException('登录响应缺少会话 token');
      }
      final user = data['user'];
      await session.setAuthenticated(
        token,
        user: user is Map ? Map<String, dynamic>.from(user) : null,
      );
      return true;
    } on ApiException catch (exception) {
      error = exception.message;
      return false;
    } finally {
      isBusy = false;
      notifyListeners();
    }
  }
}
