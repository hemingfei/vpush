import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:vpush/core/api_client.dart';
import 'package:vpush/core/session_store.dart';
import 'package:vpush/features/plaza/plaza_controller.dart';

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
  Future<List<dynamic>> getList(
    String path, {
    Map<String, dynamic>? query,
    CancelToken? cancelToken,
  }) async => [
    {
      'id': 1,
      'name': '雪球作者',
      'platform': 'xueqiu',
      'external_id': '100',
      'subscribed': true,
      'favorite': false,
    },
    {
      'id': 2,
      'name': '微博作者',
      'platform': 'weibo',
      'external_id': '200',
      'subscribed': false,
    },
  ];

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
  Future<Map<String, dynamic>> putJson(
    String path, {
    Map<String, dynamic>? body,
    Map<String, dynamic>? query,
    CancelToken? cancelToken,
  }) async {
    calls.add('PUT $path');
    return {'ok': true};
  }

  @override
  Future<Map<String, dynamic>> deleteJson(
    String path, {
    Map<String, dynamic>? query,
    CancelToken? cancelToken,
  }) async {
    calls.add('DELETE $path');
    return {'ok': true};
  }
}

void main() {
  test('filters catalog and synchronizes subscription flags after server confirmation', () async {
    final api = _FakeApi();
    final controller = PlazaController(api: api);
    await controller.load();

    controller.query = '微博';
    expect(controller.filtered.map((kol) => kol.id), [2]);
    controller.query = '';
    final subscribed = controller.catalog.first;
    expect(await controller.toggleSubscription(subscribed), isTrue);
    expect(controller.catalog.first.subscribed, isFalse);
    expect(api.calls, contains('DELETE /subscriptions/1'));
    controller.dispose();
  });
}
