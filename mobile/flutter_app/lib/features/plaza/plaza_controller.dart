import 'package:flutter/foundation.dart';

import '../../core/api_client.dart';
import 'plaza_models.dart';

class PlazaController extends ChangeNotifier {
  PlazaController({required this.api});

  final ApiClient api;
  final List<PlazaKol> catalog = [];
  bool isLoading = false;
  String? error;
  String query = '';
  String platform = '';
  bool subscribedOnly = false;
  bool favoriteOnly = false;
  int _requestId = 0;

  void setQuery(String value) {
    query = value;
    notifyListeners();
  }

  Future<void> setPlatform(String value) async {
    if (platform == value) return;
    platform = value;
    await load();
  }

  void setSubscribedOnly(bool value) {
    subscribedOnly = value;
    notifyListeners();
  }

  void setFavoriteOnly(bool value) {
    favoriteOnly = value;
    notifyListeners();
  }

  List<PlazaKol> get filtered => catalog.where((kol) {
    final normalized = query.trim().toLowerCase();
    if (platform.isNotEmpty && kol.platform != platform) return false;
    if (subscribedOnly && !kol.subscribed) return false;
    if (favoriteOnly && !kol.favorite) return false;
    if (normalized.isEmpty) return true;
    return kol.name.toLowerCase().contains(normalized) ||
        kol.externalId.toLowerCase().contains(normalized);
  }).toList();

  Future<void> load() async {
    final requestId = ++_requestId;
    isLoading = true;
    error = null;
    notifyListeners();
    try {
      final rows = await api.getList(
        '/catalog',
        query: platform.isEmpty ? null : {'platform': platform},
      );
      if (requestId != _requestId) return;
      catalog
        ..clear()
        ..addAll(
          rows.whereType<Map>().map(
            (row) => PlazaKol.fromJson(Map<String, dynamic>.from(row)),
          ),
        );
    } on ApiException catch (exception) {
      if (requestId == _requestId) error = exception.message;
    } finally {
      if (requestId == _requestId) {
        isLoading = false;
        notifyListeners();
      }
    }
  }

  Future<bool> toggleSubscription(PlazaKol kol) async {
    try {
      if (kol.subscribed) {
        await api.deleteJson('/subscriptions/${kol.id}');
      } else {
        await api.postJson(
          '/subscriptions',
          body: {'kol_id': kol.id, 'type': 'post'},
        );
      }
      _replace(kol.copyWith(subscribed: !kol.subscribed));
      return true;
    } on ApiException catch (exception) {
      error = exception.message;
      notifyListeners();
      return false;
    }
  }

  Future<bool> toggleFavorite(PlazaKol kol) => _toggleFlag(
    kol,
    next: !kol.favorite,
    path: '/subscriptions/${kol.id}/favorite',
    bodyKey: 'favorite',
    update: (value) => kol.copyWith(favorite: value),
  );

  Future<bool> toggleSecondary(PlazaKol kol) => _toggleFlag(
    kol,
    next: !kol.secondary,
    path: '/subscriptions/${kol.id}/secondary',
    bodyKey: 'secondary',
    update: (value) => kol.copyWith(secondary: value),
  );

  Future<bool> _toggleFlag(
    PlazaKol kol, {
    required bool next,
    required String path,
    required String bodyKey,
    required PlazaKol Function(bool value) update,
  }) async {
    try {
      await api.putJson(path, body: {bodyKey: next});
      _replace(update(next));
      return true;
    } on ApiException catch (exception) {
      error = exception.message;
      notifyListeners();
      return false;
    }
  }

  void _replace(PlazaKol value) {
    final index = catalog.indexWhere((item) => item.id == value.id);
    if (index >= 0) catalog[index] = value;
    notifyListeners();
  }
}
