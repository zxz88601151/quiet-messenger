/// Friends error mapping — translates low-level [ApiException] into
/// user-facing messages.
///
/// Per Phase 3B §10 the UI must NEVER show raw DioException / stack trace /
/// HTTP detail. Switches on backend `code` (API_CONTRACT §7 + backend
/// social_service / errors). Unknown codes fall back to a generic message.
import '../../core/errors/api_exception.dart';

class FriendError {
  const FriendError({required this.message, this.code});

  final String message;
  final String? code;
}

FriendError mapFriendError(ApiException e) {
  switch (e.code) {
    case 'FRIEND_NOT_FOUND':
      return const FriendError(message: '好友请求不存在', code: 'FRIEND_NOT_FOUND');
    case 'DUPLICATE_REQUEST':
      return const FriendError(message: '该好友请求已存在', code: 'DUPLICATE_REQUEST');
    case 'FRIEND_REQUIRED':
      return const FriendError(message: '双方需为好友关系', code: 'FRIEND_REQUIRED');
    case 'CONVERSATION_FORBIDDEN':
      return const FriendError(message: '无权访问该会话', code: 'CONVERSATION_FORBIDDEN');
    case 'CONFLICT':
      return const FriendError(message: '操作状态冲突，请刷新后重试', code: 'CONFLICT');
    case 'VALIDATION_ERROR':
      return FriendError(
        message: e.message.isNotEmpty ? '输入有误：${e.message}' : '请检查输入项',
        code: 'VALIDATION_ERROR',
      );
    case 'UNAUTHENTICATED':
    case 'FORBIDDEN':
      return const FriendError(message: '登录已失效，请重新登录', code: 'UNAUTHENTICATED');
    case 'NETWORK_ERROR':
      return const FriendError(message: '网络异常，请检查连接后重试', code: 'NETWORK_ERROR');
    default:
      return FriendError(
        message: e.message.isNotEmpty ? e.message : '操作失败，请稍后重试',
        code: e.code,
      );
  }
}
