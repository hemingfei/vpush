import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';

import '../../core/api_client.dart';
import 'timeline_models.dart';

class TimelineController extends ChangeNotifier {
  TimelineController({required this.api});

  final ApiClient api;
  final List<TimelinePost> posts = [];
  bool isLoading = false;
  bool isLoadingMore = false;
  bool isLive = false;
  bool hasMore = true;
  String? error;
  String platform = '';
  String query = '';
  String tag = '';
  bool favoriteOnly = false;
  bool includeSecondary = false;
  String _cursor = '';
  int _offset = 0;
  int _requestId = 0;
  CancelToken? _cancelToken;

  int get latestId => posts.isEmpty
      ? 0
      : posts.map((post) => post.id).reduce((a, b) => a > b ? a : b);

  Future<void> setLive(bool value) async {
    if (isLive == value) return;
    isLive = value;
    await load(reset: true);
  }

  Future<void> load({bool reset = true}) async {
    final requestId = ++_requestId;
    if (reset) {
      _cancelToken?.cancel('route or filter changed');
      _cancelToken = CancelToken();
      _offset = 0;
      _cursor = '';
      hasMore = true;
      posts.clear();
      isLoading = true;
      error = null;
    } else {
      if (isLoadingMore || isLoading || !hasMore) return;
      isLoadingMore = true;
    }
    notifyListeners();
    try {
      final loaded = isLive
          ? await _loadLive(requestId)
          : await _loadFeed(requestId);
      if (requestId != _requestId) return;
      final existing = posts.map((post) => post.id).toSet();
      for (final post in loaded) {
        if (existing.add(post.id)) posts.add(post);
      }
      posts.sort((a, b) => b.id.compareTo(a.id));
      if (!isLive) {
        _offset += loaded.length;
        hasMore = loaded.length >= 50;
      }
      error = null;
    } on DioException catch (exception) {
      if (exception.type == DioExceptionType.cancel ||
          requestId != _requestId) {
        return;
      }
      error = '请求已取消';
    } on ApiException catch (exception) {
      if (requestId != _requestId) return;
      error = exception.message;
    } finally {
      if (requestId == _requestId) {
        isLoading = false;
        isLoadingMore = false;
        notifyListeners();
      }
    }
  }

  Future<void> refresh() => load(reset: true);

  Future<void> poll() async {
    if (isLoading || isLoadingMore || posts.isEmpty) return;
    final requestId = ++_requestId;
    try {
      final loaded = isLive
          ? await _loadLive(requestId, sinceId: latestId)
          : await _loadFeed(requestId, sinceId: latestId);
      if (requestId != _requestId) return;
      final existing = posts.map((post) => post.id).toSet();
      posts.insertAll(0, loaded.where((post) => existing.add(post.id)));
      notifyListeners();
    } on ApiException {
      // Polling failures are intentionally silent; the next poll retries.
    }
  }

  Future<List<TimelinePost>> _loadFeed(int requestId, {int? sinceId}) async {
    final params = <String, dynamic>{'limit': 50, 'offset': _offset};
    if (platform.isNotEmpty) params['platform'] = platform;
    if (query.isNotEmpty) params['q'] = query;
    if (tag.isNotEmpty) params['tag'] = tag;
    if (favoriteOnly) params['favorite'] = 1;
    if (includeSecondary) params['include_secondary'] = 1;
    if (sinceId != null) params['since_id'] = sinceId;
    final data = await api.getList(
      '/my/feed',
      query: params,
      cancelToken: _cancelToken,
    );
    if (requestId != _requestId) return const [];
    return data
        .whereType<Map>()
        .map((item) => TimelinePost.fromJson(Map<String, dynamic>.from(item)))
        .toList();
  }

  Future<List<TimelinePost>> _loadLive(int requestId, {int? sinceId}) async {
    final params = <String, dynamic>{'limit': 30};
    if (_cursor.isNotEmpty) params['cursor'] = _cursor;
    if (sinceId != null) params['since_id'] = sinceId;
    final data = await api.getJson(
      '/live/wscn',
      query: params,
      cancelToken: _cancelToken,
    );
    if (requestId != _requestId) return const [];
    _cursor = '${data['next_cursor'] ?? data['cursor'] ?? ''}';
    final items = data['items'];
    if (items is! List) return const [];
    return items
        .whereType<Map>()
        .map((item) => TimelinePost.fromJson(Map<String, dynamic>.from(item)))
        .toList();
  }

  @override
  void dispose() {
    _cancelToken?.cancel('controller disposed');
    super.dispose();
  }
}
