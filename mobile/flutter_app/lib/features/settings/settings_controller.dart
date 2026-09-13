import 'dart:async';

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
  String feishuSessionId = '';
  String feishuBindCommand = '';
  String feishuVerificationUri = '';
  String feishuQrUri = '';
  int feishuBindExpiresAt = 0;
  String feishuRegistrationStatus = '';
  Timer? _feishuPoll;
  bool isRegisteringFeishu = false;

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

  Future<bool> startFeishuRegistration() async {
    stopFeishuRegistration();
    error = null;
    success = null;
    isRegisteringFeishu = true;
    notifyListeners();
    try {
      final data = await api.postJson('/me/feishu-personal/register');
      feishuSessionId = '${data['session_id'] ?? ''}';
      feishuVerificationUri = '${data['verification_uri'] ?? ''}';
      feishuQrUri = '${data['qr_uri'] ?? ''}';
      feishuRegistrationStatus = '${data['status'] ?? 'pending'}';
      if (feishuSessionId.isEmpty) throw ApiException('服务端未返回注册会话');
      _feishuPoll = Timer.periodic(
        const Duration(seconds: 1),
        (_) => pollFeishuRegistration(),
      );
      return true;
    } on ApiException catch (exception) {
      error = exception.message;
      isRegisteringFeishu = false;
      return false;
    } finally {
      notifyListeners();
    }
  }

  Future<void> pollFeishuRegistration() async {
    final sessionId = feishuSessionId;
    if (sessionId.isEmpty || !isRegisteringFeishu) return;
    try {
      final data = await api.getJson('/me/feishu-personal/register/$sessionId');
      if (sessionId != feishuSessionId) return;
      feishuRegistrationStatus =
          '${data['status'] ?? feishuRegistrationStatus}';
      feishuVerificationUri =
          '${data['verification_uri'] ?? feishuVerificationUri}';
      feishuQrUri = '${data['qr_uri'] ?? feishuQrUri}';
      final bindCommand = '${data['bind_command'] ?? ''}';
      if (bindCommand.isNotEmpty) feishuBindCommand = bindCommand;
      final expires = data['bind_code_expires_at'];
      if (expires is num) feishuBindExpiresAt = expires.toInt();
      if (feishuRegistrationStatus == 'active') {
        stopFeishuRegistration();
        success = '飞书个人机器人已绑定';
        await load();
      } else if (const {
        'expired',
        'cancelled',
        'degraded',
      }.contains(feishuRegistrationStatus)) {
        stopFeishuRegistration();
      }
    } on ApiException catch (exception) {
      if (exception.statusCode == 404) stopFeishuRegistration();
    }
    notifyListeners();
  }

  Future<void> refreshFeishuBindCode() async {
    final sessionId = feishuSessionId;
    if (sessionId.isEmpty) return;
    try {
      final data = await api.postJson(
        '/me/feishu-personal/register/$sessionId/refresh-code',
      );
      feishuBindCommand = '${data['bind_command'] ?? ''}';
      final expires = data['bind_code_expires_at'];
      if (expires is num) feishuBindExpiresAt = expires.toInt();
      notifyListeners();
    } on ApiException catch (exception) {
      error = exception.message;
      notifyListeners();
    }
  }

  Future<void> cancelFeishuRegistration() async {
    final sessionId = feishuSessionId;
    if (sessionId.isNotEmpty) {
      try {
        await api.postJson('/me/feishu-personal/register/$sessionId/cancel');
      } on ApiException {
        // Local cancellation still stops polling when the session is gone.
      }
    }
    stopFeishuRegistration();
    notifyListeners();
  }

  void stopFeishuRegistration() {
    _feishuPoll?.cancel();
    _feishuPoll = null;
    feishuSessionId = '';
    feishuBindCommand = '';
    feishuBindExpiresAt = 0;
    isRegisteringFeishu = false;
  }

  Future<bool> unbind(String channel) async {
    final updates = switch (channel) {
      'telegram' => {'telegram_chat_id': '', 'telegram_bot_token': ''},
      'feishu' => {'feishu_open_id': '', 'feishu_chat_id': ''},
      'wecom' => {'wecom_webhook': ''},
      'bark' => {'bark_key': ''},
      _ => <String, dynamic>{},
    };
    if (channel == 'feishu_personal') {
      try {
        await api.deleteJson('/me/feishu-personal');
        await load();
        return true;
      } on ApiException catch (exception) {
        error = exception.message;
        notifyListeners();
        return false;
      }
    }
    if (updates.isEmpty) return false;
    return save(updates);
  }

  @override
  void dispose() {
    stopFeishuRegistration();
    super.dispose();
  }
}
