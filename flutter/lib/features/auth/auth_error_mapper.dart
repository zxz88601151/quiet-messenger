/// Auth error mapping — translates low-level [ApiException] into
/// user-facing messages.
///
/// Per Phase 3B §10 the UI must NEVER show raw DioException / stack trace /
/// HTTP implementation detail. This mapper switches on the backend `code`
/// (shared/API_CONTRACT.md §7) and returns a localized, human-readable
/// message. Unknown codes fall back to a generic message.
import '../../core/errors/api_exception.dart';

/// Result of mapping an [ApiException] for display.
class AuthError {
  const AuthError({required this.message, this.code});

  final String message;
  final String? code;
}

/// Map a backend [ApiException] to a user-facing [AuthError].
///
/// Known codes (API_CONTRACT §7 + backend auth_service):
/// - INVALID_CREDENTIALS : login failed (no user enumeration by design)
/// - VALIDATION_ERROR    : field validation (register/reset/device_type)
/// - UNAUTHENTICATED     : missing/expired token (token invalid flow)
/// - NETWORK_ERROR       : no connectivity (client-side injection)
/// - UNKNOWN             : anything else
AuthError mapAuthError(ApiException e) {
  switch (e.code) {
    case 'INVALID_CREDENTIALS':
      return const AuthError(
        message: '用户名或密码错误，请重试',
        code: 'INVALID_CREDENTIALS',
      );
    case 'VALIDATION_ERROR':
      return AuthError(
        message: e.message.isNotEmpty
            ? '输入有误：${e.message}'
            : '请检查输入项是否合法',
        code: 'VALIDATION_ERROR',
      );
    case 'UNAUTHENTICATED':
    case 'FORBIDDEN':
      return const AuthError(
        message: '登录已失效，请重新登录',
        code: 'UNAUTHENTICATED',
      );
    case 'NETWORK_ERROR':
      return const AuthError(
        message: '网络异常，请检查连接后重试',
        code: 'NETWORK_ERROR',
      );
    case 'QR_EXCHANGE_INVALID':
      // Not used by Phase 3B (QR is Phase 6) but kept for completeness.
      return const AuthError(message: '二维码登录已失效', code: 'QR_EXCHANGE_INVALID');
    default:
      return AuthError(
        message: e.message.isNotEmpty ? e.message : '操作失败，请稍后重试',
        code: e.code,
      );
  }
}
