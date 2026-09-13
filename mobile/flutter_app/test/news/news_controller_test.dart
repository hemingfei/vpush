import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:vpush/core/api_client.dart';
import 'package:vpush/core/session_store.dart';
import 'package:vpush/features/news/news_controller.dart';

class _MemoryVault implements SessionVault {
  @override
  Future<String?> read(String key) async => null;

  @override
  Future<void> write(String key, String value) async {}

  @override
  Future<void> delete(String key) async {}
}

class _FakeApi extends ApiClient {
  _FakeApi({this.failArticle = false})
    : super(session: SessionStore(vault: _MemoryVault()));

  final bool failArticle;
  final calls = <String>[];

  @override
  Future<Map<String, dynamic>> getJson(
    String path, {
    Map<String, dynamic>? query,
    CancelToken? cancelToken,
  }) async {
    calls.add('GET $path');
    if (path == '/news/sources') {
      return {
        'items': [
          {'id': 1, 'name': '媒体 A', 'selected': true},
          {'id': 2, 'name': '媒体 B', 'selected': false},
        ],
      };
    }
    if (path == '/news') {
      return {
        'items': [
          {
            'id': 11,
            'title': '标题',
            'summary': '摘要',
            'source_name': '媒体 A',
            'published_at': '2026-09-10T10:00:00Z',
          },
        ],
        'next_offset': 1,
        'has_more': false,
        'view_started_at': '2026-09-10T10:00:00Z',
      };
    }
    if (failArticle) throw ApiException('文章不存在', statusCode: 404);
    return {
      'id': 11,
      'title': '标题',
      'content_html': '<p>正文</p>',
      'source_name': '媒体 A',
      'published_at': '2026-09-10T10:00:00Z',
      'url': 'https://example.com/article',
    };
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
  Future<Map<String, dynamic>> putJson(
    String path, {
    Map<String, dynamic>? body,
    Map<String, dynamic>? query,
    CancelToken? cancelToken,
  }) async {
    calls.add('PUT $path');
    return {'ok': true};
  }
}

void main() {
  test(
    'loads sources and articles, then preserves source rows when saving',
    () async {
      final api = _FakeApi();
      final controller = NewsController(api: api);

      await controller.load();
      expect(controller.items.single.id, 11);
      expect(controller.sources.map((source) => source.id), [1, 2]);

      expect(await controller.saveSources({2}), isTrue);
      expect(controller.sources.map((source) => source.id), [1, 2]);
      expect(controller.sources.first.selected, isFalse);
      expect(controller.sources.last.selected, isTrue);
      expect(api.calls, contains('PUT /me'));
      controller.dispose();
    },
  );

  test(
    'article errors remain visible instead of replacing content with a spinner',
    () async {
      final controller = NewsController(api: _FakeApi(failArticle: true));

      await controller.openArticle(11);

      expect(controller.article, isNull);
      expect(controller.error, '文章不存在');
      controller.dispose();
    },
  );
}
