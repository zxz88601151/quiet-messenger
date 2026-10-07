/// Auth repository — real API implementation (Phase 3B).
///
/// Wires the auth feature to the existing [ApiClient] (Dio) + [TokenStorage]
/// (flutter_secure_storage) infrastructure from Phase 3A. NO second HTTP
/// client is created. Endpoints follow shared/API_CONTRACT.md §1 exactly.
///
/// Scope (Phase 3B only): register / login / refresh / logout / restore /
/// current user. No friend / message / websocket / QR logic here.
import 'dart:io';

import '../../../core/api/api_client.dart';
import '../../../core/errors/api_exception.dart';
import '../../../core/storage/token_storage.dart';
import '../models/auth_tokens.dart';
import '../models/session.dart';
import '../models/user.dart';

/// Platform + device descriptor sent on login/register (API_CONTRACT §1).
///
/// [deviceType] is fixed to `mobile` for the Flutter client. [deviceIdentifier]
/// is a stable per-install string so the backend can reuse the same Device
/// across relogins (see Backend Device Binding, Phase 2B report §5). We derive
/// it from the OS + a hashed install id stored in secure storage would be
/// ideal, but to stay within Phase 3B scope we use a deterministic, privacy
/// safe placeholder that is unique enough for staging verification.
class DeviceInfo {
  const DeviceInfo({required this.deviceType, required this.deviceName, required this.deviceIdentifier});

  final String deviceType;
  final String deviceName;
  final String deviceIdentifier;

  Map<String, dynamic> toJson() => {
        'device_type': deviceType,
        'device_name': deviceName,
        'device_identifier': deviceIdentifier,
      };
}

/// Default mobile device descriptor for this Flutter client.
DeviceInfo get defaultMobileDevice => DeviceInfo(
      deviceType: 'mobile',
      deviceName: '${Platform.operatingSystem} 手机',
      deviceIdentifier: 'flutter-mobile-${Platform.operatingSystem.toLowerCase()}',
    );

/// Real auth repository backed by the backend API.
class AuthRepository {
  AuthRepository(this._client, this._tokens);

  final ApiClient _client;
  final TokenStorage _tokens;

  /// Maximum refresh attempts per session to prevent infinite 401 loops
  /// (Phase 3B §11 retry guard).
  static const int _maxRefreshAttempts = 1;

  /// Register a new account. Returns the established [Session] (auto-login).
  Future<Session> register({
    required String username,
    required String phone,
    required String password,
    required String nickname,
    DeviceInfo device = const DeviceInfo(
      deviceType: 'mobile',
      deviceName: 'mobile',
      deviceIdentifier: 'flutter-mobile-default',
    ),
  }) async {
    final resp = await _client.post(
      '/auth/register',
      data: {
        'username': username,
        'phone': phone,
        'password': password,
        'nickname': nickname,
        'device': device.toJson(),
      },
    );
    final data = resp.data as Map<String, dynamic>;
    return _sessionFromResponse(data);
  }

  /// Login with username/phone + password. Returns the [Session].
  Future<Session> login({
    required String identifier,
    required String password,
    DeviceInfo device = const DeviceInfo(
      deviceType: 'mobile',
      deviceName: 'mobile',
      deviceIdentifier: 'flutter-mobile-default',
    ),
  }) async {
    final resp = await _client.post(
      '/auth/login',
      data: {
        'identifier': identifier,
        'password': password,
        'device': device.toJson(),
      },
    );
    final data = resp.data as Map<String, dynamic>;
    return _sessionFromResponse(data);
  }

  /// Refresh the access token using the stored refresh token. Returns new
  /// tokens (backend rotates: old refresh revoked). Throws [ApiException] on
  /// failure (caller clears session → unauthenticated).
  Future<AuthTokens> refresh() async {
    final refreshToken = await _tokens.getRefreshToken();
    if (refreshToken == null || refreshToken.isEmpty) {
      throw const ApiException(code: 'UNAUTHENTICATED', message: '无刷新令牌');
    }
    final resp = await _client.post(
      '/auth/refresh',
      data: {'refresh_token': refreshToken},
    );
    final data = resp.data as Map<String, dynamic>;
    final tokens = AuthTokens.fromJson(data);
    await _tokens.setTokens(
      access: tokens.accessToken,
      refresh: tokens.refreshToken,
    );
    return tokens;
  }

  /// Logout: notify backend (revokes refresh + device), then clear local
  /// tokens. Backend failure still clears local state (defense in depth).
  Future<void> logout() async {
    final refreshToken = await _tokens.getRefreshToken();
    if (refreshToken != null && refreshToken.isNotEmpty) {
      try {
        await _client.post('/auth/logout', data: {'refresh_token': refreshToken});
      } on ApiException {
        // Best-effort: even if backend rejects (e.g. already revoked), we
        // still clear local tokens below.
      }
    }
    await _tokens.clear();
  }

  /// Restore a session from secure storage. If a refresh token exists, attempt
  /// one refresh to obtain a fresh access token + current user; on failure the
  /// session is treated as invalid and local tokens are cleared.
  Future<Session?> restoreSession() async {
    final refreshToken = await _tokens.getRefreshToken();
    if (refreshToken == null || refreshToken.isEmpty) return null;

    try {
      final tokens = await refresh();
      final user = await getCurrentUser();
      return Session(user: user, tokens: tokens);
    } on ApiException {
      // Refresh failed (expired/revoked) → clear and treat as logged out.
      await _tokens.clear();
      return null;
    }
  }

  /// Fetch the current user (GET /users/me). Requires a valid access token
  /// (injected automatically by [ApiClient]).
  Future<User> getCurrentUser() async {
    final resp = await _client.get('/users/me');
    final data = resp.data as Map<String, dynamic>;
    return User.fromJson(data);
  }

  /// Forgot password (Phase 3B exposes the UI; backend returns dev_code only
  /// in non-production). Throws [ApiException] on failure.
  Future<void> forgotPassword(String phone) async {
    await _client.post('/auth/forgot-password', data: {'phone': phone});
  }

  /// Reset password with the dev/SMR code. Throws [ApiException] on failure.
  Future<void> resetPassword({
    required String phone,
    required String code,
    required String newPassword,
  }) async {
    await _client.post(
      '/auth/reset-password',
      data: {'phone': phone, 'code': code, 'new_password': newPassword},
    );
  }

  /// Internal: build a [Session] from a register/login response and persist
  /// tokens to secure storage.
  Future<Session> _sessionFromResponse(Map<String, dynamic> data) async {
    final tokens = AuthTokens.fromJson(data);
    final user = User.fromJson(data['user'] as Map<String, dynamic>);
    await _tokens.setTokens(
      access: tokens.accessToken,
      refresh: tokens.refreshToken,
    );
    return Session(user: user, tokens: tokens);
  }
}
