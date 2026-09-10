import 'package:flutter/foundation.dart';

import '../../core/api_client.dart';

class AdminController extends ChangeNotifier {
  AdminController({required this.api, required this.section});

  final ApiClient api;
  final String section;
  bool isLoading = false;
  bool isSaving = false;
  String? error;
  String? success;
  final Map<String, dynamic> payload = {};
  int _requestId = 0;

  Future<void> load() async {
    final requestId = ++_requestId;
    isLoading = true;
    error = null;
    notifyListeners();
    try {
      final endpoints = _endpointsFor(section);
      for (final endpoint in endpoints) {
        try {
          payload[endpoint] = _listEndpoints.contains(endpoint)
              ? await api.getList(endpoint)
              : await api.getJson(endpoint);
        } on ApiException catch (exception) {
          payload[endpoint] = {'error': exception.message};
        }
      }
      if (requestId == _requestId) success = null;
    } on ApiException catch (exception) {
      if (requestId == _requestId) error = exception.message;
    } finally {
      if (requestId == _requestId) {
        isLoading = false;
        notifyListeners();
      }
    }
  }

  Future<bool> batchKols({
    required List<int> ids,
    required String action,
    bool? value,
  }) {
    final body = <String, dynamic>{'ids': ids, 'action': action};
    if (value != null) body['value'] = value;
    return _write('/admin/kols/batch', body: body);
  }

  Future<bool> approveRequest(int id, {required bool approve}) =>
      _write('/admin/kol-requests/$id/${approve ? 'approve' : 'reject'}');

  Future<bool> saveNewsSettings(Map<String, dynamic> body) =>
      _write('/admin/news/settings', method: 'PATCH', body: body);

  Future<bool> generateCodes({int count = 1, String note = ''}) =>
      _write('/admin/register-codes', body: {'count': count, 'note': note});

  Future<bool> _write(
    String path, {
    String method = 'POST',
    Map<String, dynamic>? body,
  }) async {
    isSaving = true;
    error = null;
    success = null;
    notifyListeners();
    try {
      if (method == 'PATCH') {
        await api.patchJson(path, body: body);
      } else {
        await api.postJson(path, body: body);
      }
      success = '操作已完成';
      await load();
      return true;
    } on ApiException catch (exception) {
      error = exception.message;
      return false;
    } finally {
      isSaving = false;
      notifyListeners();
    }
  }

  List<String> _endpointsFor(String value) => switch (value) {
    'sources' => const [
      '/admin/plaza-sources',
      '/admin/news/settings',
      '/admin/news/sources',
    ],
    'knowledge' => const ['/admin/ima-collector', '/admin/ima-storage/health'],
    'ops' => const ['/admin/dashboard', '/admin/logs'],
    'accounts' => const ['/admin/register-codes'],
    _ => const ['/admin/kols', '/admin/kol-requests'],
  };

  static const _listEndpoints = {
    '/admin/kol-requests',
    '/admin/logs',
    '/admin/register-codes',
  };
}
