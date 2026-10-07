/// Secure token storage foundation.
///
/// Phase 3A scope: infrastructure only. Persists access + refresh tokens
/// via [FlutterSecureStorage]. No auth-flow logic here — just get/set/clear.
/// Keys are namespaced to avoid collisions with other apps on the device.
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class TokenStorage {
  const TokenStorage({FlutterSecureStorage? storage})
      : _storage = storage ?? const FlutterSecureStorage();

  final FlutterSecureStorage _storage;

  static const String _accessKey = 'liaotian_access_token';
  static const String _refreshKey = 'liaotian_refresh_token';

  Future<String?> getAccessToken() => _storage.read(key: _accessKey);
  Future<String?> getRefreshToken() => _storage.read(key: _refreshKey);

  Future<void> setTokens({required String access, required String refresh}) async {
    await _storage.write(key: _accessKey, value: access);
    await _storage.write(key: _refreshKey, value: refresh);
  }

  Future<void> clear() async {
    await _storage.delete(key: _accessKey);
    await _storage.delete(key: _refreshKey);
  }
}
