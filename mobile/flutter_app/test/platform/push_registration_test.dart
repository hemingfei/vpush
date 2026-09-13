import 'package:flutter_test/flutter_test.dart';
import 'package:dio/dio.dart';

import 'package:vpush/core/api_client.dart';
import 'package:vpush/core/session_store.dart';
import 'package:vpush/platform/push_registration.dart';

class _MemoryVault implements SessionVault {
  @override
  Future<String?> read(String key) async => null;

  @override
  Future<void> write(String key, String value) async {}

  @override
  Future<void> delete(String key) async {}
}

class _FakePlatform implements AndroidPushPlatform {
  _FakePlatform(this.device);

  final AndroidPushDevice? device;
  bool permissionRequested = false;

  @override
  Future<AndroidPushDevice?> getDevice() async => device;

  @override
  Future<bool> requestPermission() async {
    permissionRequested = true;
    return true;
  }
}

class _FakeApiClient extends ApiClient {
  _FakeApiClient(SessionStore session) : super(session: session);

  final registered = <Map<String, dynamic>>[];
  final unregistered = <String>[];

  @override
  Future<Map<String, dynamic>> putJson(
    String path, {
    Map<String, dynamic>? body,
    Map<String, dynamic>? query,
    CancelToken? cancelToken,
  }) async {
    registered.add({'path': path, 'body': body});
    return {'ok': true};
  }

  @override
  Future<Map<String, dynamic>> deleteJson(
    String path, {
    Map<String, dynamic>? query,
    CancelToken? cancelToken,
  }) async {
    unregistered.add(path);
    return {'ok': true};
  }
}

void main() {
  test('does not register when the platform has no provider token', () async {
    final session = SessionStore(vault: _MemoryVault());
    await session.load();
    await session.setAuthenticated('token');
    final api = _FakeApiClient(session);
    final service = PushRegistrationService(
      api: api,
      platform: _FakePlatform(
        const AndroidPushDevice(
          installationId: 'install-a',
          provider: 'none',
          token: '',
        ),
      ),
    );

    expect(await service.registerCurrentDevice(), isFalse);
    expect(api.registered, isEmpty);
  });

  test(
    'registers and unregisters a provider device without exposing the token',
    () async {
      final session = SessionStore(vault: _MemoryVault());
      await session.load();
      await session.setAuthenticated('token');
      final api = _FakeApiClient(session);
      final service = PushRegistrationService(
        api: api,
        platform: _FakePlatform(
          const AndroidPushDevice(
            installationId: 'install-a',
            provider: 'fcm',
            token: 'provider-token',
            deviceModel: 'Pixel 9',
            appVersion: '0.1.0+1',
          ),
        ),
      );

      expect(await service.registerCurrentDevice(), isTrue);
      expect(api.registered.single['path'], '/me/android-devices/install-a');
      expect(api.registered.single['body'], {
        'token': 'provider-token',
        'provider': 'fcm',
        'device_model': 'Pixel 9',
        'app_version': '0.1.0+1',
      });
      expect(await service.unregisterCurrentDevice(), isTrue);
      expect(api.unregistered, ['/me/android-devices/install-a']);
    },
  );
}
