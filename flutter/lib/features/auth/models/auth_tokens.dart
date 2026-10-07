/// Auth domain model — AuthTokens.
///
/// Pair of access + refresh tokens returned by the backend
/// (shared/API_CONTRACT.md §1 register/login/refresh). The backend returns
/// `expires_at` only on refresh in some flows; we keep it optional and let
/// TokenStorage own persistence. No extra fields are added for Phase 3B.
class AuthTokens {
  const AuthTokens({
    required this.accessToken,
    required this.refreshToken,
    this.expiresAt,
  });

  final String accessToken;
  final String refreshToken;
  final DateTime? expiresAt;

  factory AuthTokens.fromJson(Map<String, dynamic> json, {DateTime? expiresAt}) {
    return AuthTokens(
      accessToken: json['access_token'] as String,
      refreshToken: json['refresh_token'] as String,
      expiresAt: expiresAt,
    );
  }

  AuthTokens copyWith({String? accessToken, String? refreshToken}) {
    return AuthTokens(
      accessToken: accessToken ?? this.accessToken,
      refreshToken: refreshToken ?? this.refreshToken,
      expiresAt: expiresAt,
    );
  }
}
