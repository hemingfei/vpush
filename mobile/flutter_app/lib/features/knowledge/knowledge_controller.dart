import 'package:flutter/foundation.dart';

import '../../core/api_client.dart';
import 'knowledge_models.dart';

class KnowledgeController extends ChangeNotifier {
  KnowledgeController({required this.api});

  final ApiClient api;
  final List<KnowledgeGroup> subscribedGroups = [];
  final List<KnowledgeGroup> availableGroups = [];
  final List<KnowledgeDocument> documents = [];
  final List<String> days = [];
  final List<String> tags = [];
  String query = '';
  String group = '';
  String day = '';
  String tag = '';
  bool isLoading = false;
  bool isLoadingMore = false;
  bool hasMore = false;
  String? error;
  KnowledgeDocument? document;
  String? readerError;
  bool isTranslating = false;
  bool isDownloadingPdf = false;
  Uint8List? pdfBytes;
  String? textContent;
  bool isLoadingText = false;
  int _offset = 0;
  int _requestId = 0;
  int _readerRequestId = 0;

  Future<void> load() async {
    final requestId = ++_requestId;
    isLoading = true;
    error = null;
    notifyListeners();
    try {
      final catalog = await api.getJson('/ima-documents/catalog');
      if (requestId != _requestId) return;
      _replaceGroups(catalog);
      await loadDocuments(reset: true, requestId: requestId);
    } on ApiException catch (exception) {
      if (requestId == _requestId) error = exception.message;
    } finally {
      if (requestId == _requestId) {
        isLoading = false;
        notifyListeners();
      }
    }
  }

  Future<void> loadDocuments({bool reset = false, int? requestId}) async {
    final currentRequest = requestId ?? ++_requestId;
    if (reset) {
      _offset = 0;
      documents.clear();
      hasMore = false;
    } else {
      if (isLoadingMore || !hasMore) return;
      isLoadingMore = true;
    }
    notifyListeners();
    try {
      final data = await api.getJson(
        '/ima-documents',
        query: {
          'limit': 50,
          'offset': _offset,
          if (query.trim().isNotEmpty) 'q': query.trim(),
          if (group.isNotEmpty) 'group': group,
          if (day.isNotEmpty && query.trim().isEmpty && tag.isEmpty) 'day': day,
          if (tag.isNotEmpty) 'tag': tag,
        },
      );
      if (currentRequest != _requestId) return;
      final rawItems = data['items'];
      final loaded = rawItems is List
          ? rawItems
                .whereType<Map>()
                .map(
                  (item) => KnowledgeDocument.fromJson(
                    Map<String, dynamic>.from(item),
                  ),
                )
                .where((item) => item.mediaId.isNotEmpty)
                .toList()
          : <KnowledgeDocument>[];
      documents.addAll(loaded);
      _offset = data['offset'] is int
          ? (data['offset'] as int) + loaded.length
          : _offset + loaded.length;
      hasMore = data['has_more'] == true;
      _replaceFacetValues(data);
      error = null;
    } on ApiException catch (exception) {
      if (currentRequest == _requestId) error = exception.message;
    } finally {
      if (currentRequest == _requestId) {
        isLoadingMore = false;
        notifyListeners();
      }
    }
  }

  Future<bool> toggleGroup(KnowledgeGroup target) async {
    try {
      final path =
          '/ima-documents/groups/${Uri.encodeComponent(target.id)}/subscribe';
      if (target.subscribed) {
        await api.deleteJson(path);
      } else {
        await api.postJson(path);
      }
      final replacement = target.copyWith(subscribed: !target.subscribed);
      final source = target.subscribed ? subscribedGroups : availableGroups;
      final destination = target.subscribed
          ? availableGroups
          : subscribedGroups;
      source.removeWhere((item) => item.id == target.id);
      destination.removeWhere((item) => item.id == target.id);
      destination.add(replacement);
      notifyListeners();
      await loadDocuments(reset: true);
      return true;
    } on ApiException catch (exception) {
      error = exception.message;
      notifyListeners();
      return false;
    }
  }

  void setQuery(String value) {
    query = value;
    notifyListeners();
  }

  Future<void> setDay(String value) async {
    if (day == value) return;
    day = value;
    await loadDocuments(reset: true);
  }

  Future<void> setTag(String value) async {
    if (tag == value) return;
    tag = value;
    await loadDocuments(reset: true);
  }

  Future<void> setGroup(String value) async {
    if (group == value) return;
    group = value;
    await loadDocuments(reset: true);
  }

  Future<void> openDocument(String mediaId, {String groupId = ''}) async {
    final requestId = ++_readerRequestId;
    document = null;
    pdfBytes = null;
    textContent = null;
    readerError = null;
    notifyListeners();
    try {
      final data = await api.getJson(
        '/ima-documents/${Uri.encodeComponent(mediaId)}',
        query: groupId.isEmpty ? null : {'group': groupId},
      );
      if (requestId != _readerRequestId) return;
      document = KnowledgeDocument.fromJson(data);
    } on ApiException catch (exception) {
      if (requestId == _readerRequestId) readerError = exception.message;
    }
    if (requestId == _readerRequestId) notifyListeners();
  }

  Future<void> translateDocument() async {
    final current = document;
    if (current == null || isTranslating) return;
    final requestId = _readerRequestId;
    isTranslating = true;
    readerError = null;
    notifyListeners();
    try {
      final data = await api.postJson(
        '/ima-documents/${Uri.encodeComponent(current.mediaId)}/translate',
        query: current.groupId.isEmpty ? null : {'group': current.groupId},
      );
      if (requestId != _readerRequestId ||
          document?.mediaId != current.mediaId) {
        return;
      }
      document = KnowledgeDocument(
        mediaId: current.mediaId,
        name: current.name,
        day: current.day,
        groupId: current.groupId,
        groupName: current.groupName,
        abstractText: current.abstractText,
        abstractZh: '${data['abstract_zh'] ?? current.abstractText}',
        needsTranslation: false,
        tags: current.tags,
        hasPdf: current.hasPdf,
        hasTxt: current.hasTxt,
        size: current.size,
        chars: current.chars,
        coverUrl: current.coverUrl,
        type: current.type,
        sourceUrl: current.sourceUrl,
      );
    } on ApiException catch (exception) {
      if (requestId == _readerRequestId) readerError = exception.message;
    } finally {
      if (requestId == _readerRequestId) {
        isTranslating = false;
        notifyListeners();
      }
    }
  }

  Future<void> downloadPdf() async {
    final current = document;
    if (current == null || !current.hasPdf || isDownloadingPdf) return;
    final requestId = _readerRequestId;
    isDownloadingPdf = true;
    readerError = null;
    notifyListeners();
    try {
      final bytes = await api.getBytes(
        '/ima-documents/${Uri.encodeComponent(current.mediaId)}/pdf',
        query: current.groupId.isEmpty ? null : {'group': current.groupId},
      );
      if (bytes.length < 5 || String.fromCharCodes(bytes.take(5)) != '%PDF-') {
        throw ApiException('服务端返回的文件不是有效 PDF');
      }
      if (requestId == _readerRequestId &&
          document?.mediaId == current.mediaId) {
        pdfBytes = Uint8List.fromList(bytes);
      }
    } on ApiException catch (exception) {
      if (requestId == _readerRequestId) readerError = exception.message;
    } finally {
      if (requestId == _readerRequestId) {
        isDownloadingPdf = false;
        notifyListeners();
      }
    }
  }

  Future<void> loadText() async {
    final current = document;
    if (current == null || !current.hasTxt || isLoadingText) return;
    final requestId = _readerRequestId;
    isLoadingText = true;
    readerError = null;
    notifyListeners();
    try {
      final text = await api.getText(
        '/ima-documents/${Uri.encodeComponent(current.mediaId)}/text',
        query: current.groupId.isEmpty ? null : {'group': current.groupId},
      );
      if (requestId == _readerRequestId &&
          document?.mediaId == current.mediaId) {
        textContent = text;
      }
    } on ApiException catch (exception) {
      if (requestId == _readerRequestId) readerError = exception.message;
    } finally {
      if (requestId == _readerRequestId) {
        isLoadingText = false;
        notifyListeners();
      }
    }
  }

  void _replaceGroups(Map<String, dynamic> data) {
    final subscribed = data['subscribed'];
    final available = data['available'];
    subscribedGroups
      ..clear()
      ..addAll(_groupList(subscribed, subscribed: true));
    availableGroups
      ..clear()
      ..addAll(_groupList(available, subscribed: false));
    if (group.isNotEmpty && !subscribedGroups.any((item) => item.id == group)) {
      group = '';
    }
  }

  List<KnowledgeGroup> _groupList(Object? raw, {required bool subscribed}) =>
      raw is List
      ? raw
            .whereType<Map>()
            .map(
              (item) => KnowledgeGroup.fromJson(
                Map<String, dynamic>.from(item),
                subscribed: subscribed,
              ),
            )
            .where((item) => item.id.isNotEmpty)
            .toList()
      : <KnowledgeGroup>[];

  void _replaceFacetValues(Map<String, dynamic> data) {
    final rawDays = data['days'];
    final rawTags = data['tags'];
    days
      ..clear()
      ..addAll(rawDays is List ? rawDays.map((item) => '$item') : const []);
    tags
      ..clear()
      ..addAll(rawTags is List ? rawTags.map((item) => '$item') : const []);
  }
}
