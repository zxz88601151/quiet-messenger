/// Unified API error type.
///
/// Maps the backend error envelope `{error:{code,message,status}}`
/// (shared/API_CONTRACT.md §7) into a single Dart exception so feature
/// code can switch on [code] (e.g. 'FRIEND_REQUIRED', 'VALIDATION_ERROR').
class ApiException implements Exception {
  const ApiException({required this.code, required this.message, this.status});

  final String code;
  final String message;
  final int? status;

  @override
  String toString() => 'ApiException($code, $status): $message';
}
