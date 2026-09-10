import 'package:flutter/foundation.dart';

import '../../core/api_client.dart';
import '../../core/session_store.dart';

class SettingsController extends ChangeNotifier {
  SettingsController({required this.api, required this.session});

  final ApiClient api;
  final SessionStore session;
  Map<String, dynamic> user = {};
  bool isLoading = false;
  bool isSaving = false;
  String? error;
  String? success;
  String bindCode = '';
  int bindCodeExpiresIn = 0;
  List<String> models = [];

  Future<void> load() async {
    isLoading = true;
    error = null;
    notifyListeners();
    try {
      final data = await api.getJson('/me');
      user = data;
      session.setUser(data);
    } on ApiException catch (exception) {
      error = exception.message;
    } finally {
      isLoading = false;
      notifyListeners();
    }
  }

  Future<bool> save(Map<String, dynamic> updates) async {
    isSaving = true;
    error = null;
    success = null;
    notifyListeners();
    try {
      final data = await api.putJson('/me', body: updates);
      user = data;
      session.setUser(data);
      success = '已保存';
      return true;
    } on ApiException catch (exception) {
      error = exception.message;
      return false;
    } finally {
      isSaving = false;
      notifyListeners();
    }
  }

  Future<bool> changePassword(String oldPassword, String newPassword) async {
    isSaving = true;
    error = null;
    success = null;
    notifyListeners();
    try {
      await api.postJson(
        '/me/password',
        body: {'old_password': oldPassword, 'new_password': newPassword},
      );
      success = '密码已修改';
      return true;
    } on ApiException catch (exception) {
      error = exception.message;
      return false;
    } finally {
      isSaving = false;
      notifyListeners();
    }
  }

  Future<bool> createBindCode() async {
    error = null;
    success = null;
    notifyListeners();
    try {
      final data = await api.postJson('/me/bind-code');
      bindCode = '${data['code'] ?? ''}';
      bindCodeExpiresIn = data['expires_in_seconds'] is int
          ? data['expires_in_seconds'] as int
          : int.tryParse('${data['expires_in_seconds'] ?? 0}') ?? 0;
      success = bindCode.isEmpty ? null : '绑定码已生成';
      return bindCode.isNotEmpty;
    } on ApiException catch (exception) {
      error = exception.message;
      return false;
    } finally {
      notifyListeners();
    }
  }

  Future<void> loadModels(Map<String, dynamic> draft) async {
    error = null;
    success = null;
    notifyListeners();
    try {
      final data = await api.postJson('/me/llm-models', body: draft);
      final raw = data['models'];
      models = raw is List ? raw.map((item) => '$item').toList() : const [];
      success = '模型列表已更新';
    } on ApiException catch (exception) {
      error = exception.message;
    }
    notifyListeners();
  }

  Future<void> testLlm(Map<String, dynamic> draft) async {
    error = null;
    success = null;
    notifyListeners();
    try {
      await api.postJson('/me/llm-test', body: draft);
      success = 'AI 网关连接成功';
    } on ApiException catch (exception) {
      error = exception.message;
    }
    notifyListeners();
  }
}
