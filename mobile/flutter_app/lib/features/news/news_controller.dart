import 'package:flutter/foundation.dart';

import '../../core/api_client.dart';
import 'news_models.dart';

class NewsController extends ChangeNotifier {
  NewsController({required this.api});

  final ApiClient api;
  final List<NewsSource> sources = [];
  final List<NewsItem> items = [];
  bool isLoading = false;
  bool isLoadingMore = false;
  bool hasMore = false;
  String query = '';
  int? sourceId;
  String? error;
  NewsArticle? article;
  String _seenAt = '';
  int _offset = 0;
  int _requestId = 0;

  Future<void> load() async {
    final requestId = ++_requestId;
    isLoading = true;
    error = null;
    notifyListeners();
    try {
      final data = await api.getJson('/news/sources');
      if (requestId != _requestId) return;
      final rows = data['items'];
      sources
        ..clear()
        ..addAll(
          rows is List
              ? rows.whereType<Map>().map(
                  (row) => NewsSource.fromJson(Map<String, dynamic>.from(row)),
                )
              : const [],
        );
      await loadArticles(reset: true, requestId: requestId);
    } on ApiException catch (exception) {
      if (requestId == _requestId) error = exception.message;
    } finally {
      if (requestId == _requestId) {
        isLoading = false;
        notifyListeners();
      }
    }
  }

  Future<void> loadArticles({bool reset = false, int? requestId}) async {
    final currentRequest = requestId ?? ++_requestId;
    if (reset) {
      _offset = 0;
      items.clear();
      hasMore = false;
      isLoadingMore = false;
    } else {
      if (isLoadingMore || !hasMore) return;
      isLoadingMore = true;
    }
    notifyListeners();
    try {
      final data = await api.getJson(
        '/news',
        query: {
          'limit': 30,
          'offset': _offset,
          if (sourceId != null) 'source_id': sourceId,
          if (query.trim().isNotEmpty) 'q': query.trim(),
        },
      );
      if (currentRequest != _requestId) return;
      final rawItems = data['items'];
      final loaded = rawItems is List
          ? rawItems
                .whereType<Map>()
                .map((row) => NewsItem.fromJson(Map<String, dynamic>.from(row)))
                .toList()
          : <NewsItem>[];
      items.addAll(loaded);
      _offset = data['next_offset'] is int
          ? data['next_offset'] as int
          : _offset + loaded.length;
      hasMore = data['has_more'] == true;
      _seenAt = '${data['view_started_at'] ?? ''}';
      if (_seenAt.isNotEmpty && loaded.isNotEmpty) {
        await api.postJson('/news/seen', body: {'view_started_at': _seenAt});
      }
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

  Future<bool> saveSources(Set<int> selectedIds) async {
    try {
      await api.putJson('/me', body: {'news_source_ids': selectedIds.toList()});
      final existingSources = List<NewsSource>.of(sources);
      sources
        ..clear()
        ..addAll(
          existingSources.map(
            (source) => NewsSource(
              id: source.id,
              name: source.name,
              enabled: source.enabled,
              status: source.status,
              selected: selectedIds.contains(source.id),
            ),
          ),
        );
      notifyListeners();
      return true;
    } on ApiException catch (exception) {
      error = exception.message;
      notifyListeners();
      return false;
    }
  }

  void setQuery(String value) {
    query = value;
  }

  Future<void> setSource(int? value) async {
    if (sourceId == value) return;
    sourceId = value;
    await loadArticles(reset: true);
  }

  Future<void> openArticle(int id) async {
    final requestId = ++_requestId;
    article = null;
    error = null;
    notifyListeners();
    try {
      final data = await api.getJson('/news/$id');
      if (requestId != _requestId) return;
      article = NewsArticle.fromJson(data);
    } on ApiException catch (exception) {
      if (requestId == _requestId) error = exception.message;
    }
    if (requestId == _requestId) notifyListeners();
  }
}
