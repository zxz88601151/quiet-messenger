/// Realtime errors (Flutter / Phase 3C).
///
/// Distinct from [ApiException] (REST). Carries a safe, user-facing message —
/// never leaks raw tokens / stack traces / protocol internals.
class RealtimeError implements Exception {
  const RealtimeError(this.code, this.message);

  final String code;
  final String message;

  @override
  String toString() => '[$code] $message'; // 不泄露 token / 内部细节
}

class AuthFailedError extends RealtimeError {
  const AuthFailedError([String message = '实时连接认证失败，请重新登录'])
      : super('WS_AUTH_FAILED', message);
}

class ConnectionLostError extends RealtimeError {
  const ConnectionLostError([String message = '实时连接已断开'])
      : super('WS_CONNECTION_LOST', message);
}
