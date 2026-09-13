import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:vpush/core/api_client.dart';
import 'package:vpush/core/session_store.dart';
import 'package:vpush/features/admin/admin_controller.dart';

class _MemoryVault implements SessionVault {
  @override
  Future<String?> read(String key) async => null;

  @override
  Future<void> write(String key, String value) async {}

  @override
  Future<void> delete(String key) async {}
}

class _FakeApi extends ApiClient {
  _FakeApi() : super(session: SessionStore(vault: _MemoryVault()));

  final calls = <String>[];

  @override
  Future<Map<String, dynamic>> getJson(
    String path, {
    Map<String, dynamic>? query,
    CancelToken? cancelToken,
  }) async {
    calls.add('GET $path');
    return path == '/admin/kols'
        ? {
            'items': [
              {'id': 7, 'name': '作者', 'platform': 'xueqiu', 'external_id': '7'},
            ],
          }
        : {'enabled': true};
  }

  @override
  Future<List<dynamic>> getList(
    String path, {
    Map<String, dynamic>? query,
    CancelToken? cancelToken,
  }) async {
    calls.add('GET $path');
    return [
      {'id': 3, 'status': 'pending', 'name': '申请'},
    ];
  }

  @override
  Future<Map<String, dynamic>> postJson(
    String path, {
    Map<String, dynamic>? body,
    Map<String, dynamic>? query,
    CancelToken? cancelToken,
  }) async {
    calls.add('POST $path');
    return {'ok': true};
  }

  @override
  Future<Map<String, dynamic>> patchJson(
    String path, {
    Map<String, dynamic>? body,
    Map<String, dynamic>? query,
    CancelToken? cancelToken,
  }) async {
    calls.add('PATCH $path');
    return {'ok': true};
  }
}

void main() {
  test(
    'loads content endpoints and only reports a write after confirmation',
    () async {
      final api = _FakeApi();
      final controller = AdminController(api: api, section: 'content');

      await controller.load();
      expect((controller.payload['/admin/kols'] as Map)['items'], isNotEmpty);
      expect(controller.payload['/admin/kol-requests'], isA<List>());
      expect(await controller.batchKols(ids: [7], action: 'disable'), isTrue);
      expect(api.calls, contains('POST /admin/kols/batch'));
      controller.dispose();
    },
  );
}
