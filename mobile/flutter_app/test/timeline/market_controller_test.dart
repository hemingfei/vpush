import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:vpush/core/api_client.dart';
import 'package:vpush/core/session_store.dart';
import 'package:vpush/features/timeline/market_controller.dart';

class _MemoryVault implements SessionVault {
  @override
  Future<String?> read(String key) async => null;

  @override
  Future<void> write(String key, String value) async {}

  @override
  Future<void> delete(String key) async {}
}

class _FakeApiClient extends ApiClient {
  _FakeApiClient(this.responder)
    : super(session: SessionStore(vault: _MemoryVault()));

  final Future<Map<String, dynamic>> Function(String group) responder;

  @override
  Future<Map<String, dynamic>> getJson(
    String path, {
    Map<String, dynamic>? query,
    CancelToken? cancelToken,
  }) => responder('${query?['group'] ?? ''}');
}

void main() {
  test('loads quotes and preserves the selected market group', () async {
    final api = _FakeApiClient(
      (group) async => {
        'status': '交易中',
        'items': [
          {'symbol': '000001', 'name': '上证指数', 'price': 3000, 'percent': 1.2},
        ],
      },
    );
    final controller = MarketController(api: api);

    await controller.load(requestedGroup: 'night');

    expect(controller.group, 'night');
    expect(controller.status, '交易中');
    expect(controller.quotes.single.percent, 1.2);
    controller.dispose();
  });

  test('late quote response cannot replace a newer group', () async {
    final day = Completer<Map<String, dynamic>>();
    final night = Completer<Map<String, dynamic>>();
    final api = _FakeApiClient(
      (group) => group == 'day' ? day.future : night.future,
    );
    final controller = MarketController(api: api);

    final first = controller.load(requestedGroup: 'day');
    final second = controller.load(requestedGroup: 'night');
    night.complete({
      'items': [
        {'symbol': 'A', 'price': 2, 'percent': -1.0},
      ],
    });
    await second;
    day.complete({
      'items': [
        {'symbol': 'B', 'price': 1, 'percent': 4.0},
      ],
    });
    await first;

    expect(controller.group, 'night');
    expect(controller.quotes.single.symbol, 'A');
    controller.dispose();
  });
}
