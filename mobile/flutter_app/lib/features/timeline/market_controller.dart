import 'dart:async';

import 'package:flutter/foundation.dart';

import '../../core/api_client.dart';
import 'timeline_models.dart';

class MarketController extends ChangeNotifier {
  MarketController({required this.api});

  final ApiClient api;
  List<MarketQuote> quotes = const [];
  String group = 'day';
  String status = '';
  String? error;
  bool isLoading = false;
  Timer? _timer;
  int _requestId = 0;

  Future<void> load({String? requestedGroup}) async {
    if (requestedGroup != null && requestedGroup.isNotEmpty) {
      group = requestedGroup;
    }
    final requestId = ++_requestId;
    isLoading = true;
    error = null;
    notifyListeners();
    try {
      final data = await api.getJson(
        '/market/indices',
        query: {'group': group},
      );
      if (requestId != _requestId) return;
      final raw = data['items'];
      quotes = raw is List
          ? raw
                .whereType<Map>()
                .map(
                  (item) =>
                      MarketQuote.fromJson(Map<String, dynamic>.from(item)),
                )
                .toList()
          : const [];
      status = '${data['status'] ?? ''}';
    } on ApiException catch (exception) {
      if (requestId == _requestId) error = exception.message;
    } finally {
      if (requestId == _requestId) {
        isLoading = false;
        notifyListeners();
      }
    }
  }

  void startPolling() {
    _timer?.cancel();
    _timer = Timer.periodic(const Duration(seconds: 30), (_) => load());
  }

  void stopPolling() {
    _timer?.cancel();
    _timer = null;
  }

  @override
  void dispose() {
    stopPolling();
    _requestId++;
    super.dispose();
  }
}
