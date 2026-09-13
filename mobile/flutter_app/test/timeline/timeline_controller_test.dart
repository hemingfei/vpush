import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:vpush/core/api_client.dart';
import 'package:vpush/core/session_store.dart';
import 'package:vpush/features/timeline/timeline_controller.dart';
import 'package:vpush/features/timeline/timeline_models.dart';

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

  final Future<List<dynamic>> Function(Map<String, dynamic> query) responder;

  @override
  Future<List<dynamic>> getList(
    String path, {
    Map<String, dynamic>? query,
    CancelToken? cancelToken,
  }) => responder(query ?? const {});
}

Map<String, dynamic> _post(int id) => {
  'id': id,
  'kol_name': '作者 $id',
  'platform': 'xueqiu',
  'content': '内容 $id',
};

void main() {
  test('parses translated content, images, tags, and attachment details', () {
    final post = TimelinePost.fromJson({
      'id': '8',
      'kol_name': '作者',
      'kol_id': 4,
      'platform': 'zsxq',
      'title': '标题',
      'content': '译文',
      'content_src': 'Original',
      'images': ['https://example.com/a.jpg'],
      'tags': ['宏观'],
      'detail': '{"files":[{"file_id":"f1","name":"附件.pdf"}]}',
    });

    expect(post.id, 8);
    expect(post.kolId, 4);
    expect(post.contentSource, 'Original');
    expect(post.images, ['https://example.com/a.jpg']);
    expect(post.tags, ['宏观']);
    expect(post.files.single.id, 'f1');
    expect(post.files.single.name, '附件.pdf');
  });

  test('deduplicates repeated IDs from a feed and poll', () async {
    var call = 0;
    final api = _FakeApiClient((_) async {
      call++;
      return call == 1 ? [_post(2), _post(1)] : [_post(3), _post(2)];
    });
    final controller = TimelineController(api: api);

    await controller.load();
    await controller.poll();

    expect(controller.posts.map((post) => post.id), [3, 2, 1]);
    controller.dispose();
  });

  test(
    'late response from an older filter cannot overwrite the newer filter',
    () async {
      final first = Completer<List<dynamic>>();
      final second = Completer<List<dynamic>>();
      var call = 0;
      final api = _FakeApiClient((_) {
        call++;
        return call == 1 ? first.future : second.future;
      });
      final controller = TimelineController(api: api);

      final oldRequest = controller.load();
      controller.query = 'new';
      final newRequest = controller.load();
      second.complete([_post(20)]);
      await newRequest;
      first.complete([_post(10)]);
      await oldRequest;

      expect(controller.posts.map((post) => post.id), [20]);
      controller.dispose();
    },
  );
}
