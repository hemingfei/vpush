import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:vpush/core/api_client.dart';
import 'package:vpush/core/session_store.dart';
import 'package:vpush/features/settings/settings_controller.dart';

class _MemoryVault implements SessionVault {
  @override
  Future<String?> read(String key) async => null;

  @override
  Future<void> write(String key, String value) async {}

  @override
  Future<void> delete(String key) async {}
}

class _FakeApi extends ApiClient {
  _FakeApi({this.failSave = false})
    : super(session: SessionStore(vault: _MemoryVault()));

  final bool failSave;
  final calls = <String>[];
  int registrationPolls = 0;

  @override
  Future<Map<String, dynamic>> getJson(
    String path, {
    Map<String, dynamic>? query,
    CancelToken? cancelToken,
  }) async {
    if (path.contains('/feishu-personal/register/')) {
      registrationPolls++;
      return {'status': 'active'};
    }
    return {
      'username': 'tester',
      'notify_enabled': true,
      'keywords': ['ETF'],
      'push_channels': 'telegram',
      'feishu_personal': {'available': true, 'status': ''},
    };
  }

  @override
  Future<Map<String, dynamic>> putJson(
    String path, {
    Map<String, dynamic>? body,
    Map<String, dynamic>? query,
    CancelToken? cancelToken,
  }) async {
    calls.add('PUT $path');
    if (failSave) throw ApiException('保存失败', statusCode: 400);
    return {'username': 'tester', ...?body};
  }

  @override
  Future<Map<String, dynamic>> postJson(
    String path, {
    Map<String, dynamic>? body,
    Map<String, dynamic>? query,
    CancelToken? cancelToken,
  }) async {
    calls.add('POST $path');
    if (path == '/me/bind-code') {
      return {'code': '123456', 'expires_in_seconds': 300};
    }
    if (path == '/me/feishu-personal/register') {
      return {
        'session_id': 'session-1',
        'status': 'pending',
        'verification_uri': 'https://example.com/verify',
      };
    }
    return {'ok': true};
  }
}

void main() {
  test('loads profile, saves settings, and creates a bind code', () async {
    final api = _FakeApi();
    final session = SessionStore(vault: _MemoryVault());
    final controller = SettingsController(api: api, session: session);

    await controller.load();
    expect(controller.user['username'], 'tester');
    expect(await controller.save({'notify_enabled': false}), isTrue);
    expect(await controller.createBindCode(), isTrue);
    expect(controller.bindCode, '123456');
    expect(api.calls, contains('PUT /me'));
    expect(api.calls, contains('POST /me/bind-code'));
    controller.dispose();
  });

  test('save errors leave the existing profile intact', () async {
    final controller = SettingsController(
      api: _FakeApi(failSave: true),
      session: SessionStore(vault: _MemoryVault()),
    );
    await controller.load();
    expect(await controller.save({'notify_enabled': false}), isFalse);
    expect(controller.user['notify_enabled'], isTrue);
    expect(controller.error, '保存失败');
    controller.dispose();
  });

  test('feishu registration polls to active and can be cancelled', () async {
    final api = _FakeApi();
    final controller = SettingsController(
      api: api,
      session: SessionStore(vault: _MemoryVault()),
    );

    expect(await controller.startFeishuRegistration(), isTrue);
    expect(controller.feishuSessionId, 'session-1');
    await controller.pollFeishuRegistration();
    expect(controller.isRegisteringFeishu, isFalse);
    expect(controller.success, '飞书个人机器人已绑定');
    expect(api.registrationPolls, 1);
    await controller.cancelFeishuRegistration();
    controller.dispose();
  });
}
