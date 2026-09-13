import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:vpush/core/api_client.dart';
import 'package:vpush/core/session_store.dart';
import 'package:vpush/features/knowledge/knowledge_controller.dart';

class _MemoryVault implements SessionVault {
  @override
  Future<String?> read(String key) async => null;

  @override
  Future<void> write(String key, String value) async {}

  @override
  Future<void> delete(String key) async {}
}

class _FakeApi extends ApiClient {
  _FakeApi({this.pdf = const [1, 2, 3]})
    : super(session: SessionStore(vault: _MemoryVault()));

  final List<int> pdf;
  final calls = <String>[];

  @override
  Future<Map<String, dynamic>> getJson(
    String path, {
    Map<String, dynamic>? query,
    CancelToken? cancelToken,
  }) async {
    calls.add('GET $path');
    if (path == '/ima-documents/catalog') {
      return {
        'subscribed': [
          {'id': 'research', 'name': '研究库', 'enabled': true},
        ],
        'available': [
          {'id': 'premium', 'name': '高级库', 'enabled': true},
        ],
      };
    }
    if (path == '/ima-documents') {
      return {
        'items': [
          {
            'media_id': 'doc-a',
            'name': '公司研报',
            'day': '2026-09-10',
            'group_id': 'research',
            'group_name': '研究库',
            'abstract': '摘要',
            'has_pdf': true,
            'tags': ['科技'],
          },
        ],
        'days': ['2026-09-10'],
        'tags': ['科技'],
        'has_more': false,
        'offset': 0,
      };
    }
    return {
      'media_id': 'doc-a',
      'name': '公司研报',
      'day': '2026-09-10',
      'group_id': 'research',
      'group_name': '研究库',
      'abstract': '摘要',
      'needs_translation': true,
      'has_pdf': true,
      'has_txt': true,
    };
  }

  @override
  Future<List<int>> getBytes(
    String path, {
    Map<String, dynamic>? query,
    CancelToken? cancelToken,
  }) async {
    calls.add('BYTES $path');
    return pdf;
  }

  @override
  Future<String> getText(
    String path, {
    Map<String, dynamic>? query,
    CancelToken? cancelToken,
  }) async => '全文内容';

  @override
  Future<Map<String, dynamic>> postJson(
    String path, {
    Map<String, dynamic>? body,
    Map<String, dynamic>? query,
    CancelToken? cancelToken,
  }) async {
    calls.add('POST $path');
    return {'abstract_zh': '中文摘要'};
  }
}

void main() {
  test(
    'loads catalog and preserves filters while opening a document',
    () async {
      final controller = KnowledgeController(api: _FakeApi());

      await controller.load();
      expect(controller.subscribedGroups.single.id, 'research');
      expect(controller.availableGroups.single.id, 'premium');
      expect(controller.documents.single.mediaId, 'doc-a');
      expect(controller.tags, ['科技']);

      await controller.openDocument('doc-a', groupId: 'research');
      expect(controller.document?.groupId, 'research');
      controller.dispose();
    },
  );

  test('rejects a non-PDF response before exposing bytes', () async {
    final controller = KnowledgeController(api: _FakeApi());
    await controller.openDocument('doc-a', groupId: 'research');

    await controller.downloadPdf();

    expect(controller.pdfBytes, isNull);
    expect(controller.readerError, '服务端返回的文件不是有效 PDF');
    controller.dispose();
  });

  test(
    'accepts a PDF magic header and translates the active document',
    () async {
      final controller = KnowledgeController(
        api: _FakeApi(pdf: Uint8List.fromList('%PDF-1.7'.codeUnits)),
      );
      await controller.openDocument('doc-a', groupId: 'research');
      await controller.translateDocument();
      expect(controller.document?.abstractZh, '中文摘要');

      await controller.loadText();
      expect(controller.textContent, '全文内容');

      await controller.downloadPdf();
      expect(controller.pdfBytes, isNotNull);
      controller.dispose();
    },
  );
}
