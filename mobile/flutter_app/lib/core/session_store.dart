import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

abstract interface class SessionVault {
  Future<String?> read(String key);
  Future<void> write(String key, String value);
  Future<void> delete(String key);
}

class SecureSessionVault implements SessionVault {
  SecureSessionVault({FlutterSecureStorage? storage})
    : _storage = storage ?? const FlutterSecureStorage();

  final FlutterSecureStorage _storage;

  @override
  Future<String?> read(String key) => _storage.read(key: key);

  @override
  Future<void> write(String key, String value) =>
      _storage.write(key: key, value: value);

  @override
  Future<void> delete(String key) => _storage.delete(key: key);
}

class SessionStore extends ChangeNotifier {
  SessionStore({SessionVault? vault}) : _vault = vault ?? SecureSessionVault();

  static const _tokenKey = 'dav_token';
  final SessionVault _vault;
  String? _token;
  Map<String, dynamic>? _user;
  int _generation = 0;
  bool _loaded = false;

  String? get token => _token;
  Map<String, dynamic>? get user => _user;
  bool get isAuthenticated => _token?.isNotEmpty == true;
  bool get isLoaded => _loaded;
  int get generation => _generation;
  bool get isAdmin => _user?['is_admin'] == true;
  bool get newsVisible => _user?['news_visible'] != false;

  Future<void> load() async {
    _token = await _vault.read(_tokenKey);
    _loaded = true;
    notifyListeners();
  }

  Future<void> setAuthenticated(
    String token, {
    Map<String, dynamic>? user,
  }) async {
    await _vault.write(_tokenKey, token);
    _token = token;
    _user = user;
    _generation++;
    notifyListeners();
  }

  void setUser(Map<String, dynamic> user) {
    _user = user;
    notifyListeners();
  }

  Future<void> clearIfGeneration(int generation) async {
    if (_generation == generation) await clear();
  }

  Future<void> clear() async {
    await _vault.delete(_tokenKey);
    _token = null;
    _user = null;
    _generation++;
    notifyListeners();
  }
}
