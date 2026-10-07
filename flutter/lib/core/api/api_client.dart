/// API Client foundation — thin wrapper over [Dio].
///
/// Phase 3A base + Phase 3B enhancement: supports an optional
/// [onUnauthorized] hook so the auth layer can attempt ONE token refresh on
/// a 401 and retry the original request (Phase 3B §11 retry guard). Business
/// flows themselves stay in repositories, not here.
import 'package:dio/dio.dart';

import 'api_config.dart';
import '../errors/api_exception.dart';
import '../storage/token_storage.dart';

/// Signature for the 401 handler. Implemented by [AuthRepository] to perform
/// a single refresh + retry. Returns true if the request should be retried.
typedef UnauthorizedHandler = Future<bool> Function();

class ApiClient {
  ApiClient({TokenStorage? tokenStorage, this.onUnauthorized, Dio? dioOverride})
      : _tokenStorage = tokenStorage ?? const TokenStorage(),
        _dioOverride = dioOverride {
    _dio = dioOverride ??
        Dio(BaseOptions(
          baseUrl: ApiConfig.apiBaseUrl,
          connectTimeout: const Duration(seconds: 10),
          receiveTimeout: const Duration(seconds: 10),
          headers: {'Content-Type': 'application/json'},
        ));
    _dio.interceptors.add(InterceptorsWrapper(
      onRequest: _onRequest,
      onError: _onError,
    ));
  }

  late final Dio _dio;
  final TokenStorage _tokenStorage;

  /// Optional hook invoked on a 401. Used by the auth layer to refresh the
  /// access token once and retry. If it returns false, the 401 is surfaced.
  final UnauthorizedHandler? onUnauthorized;

  /// Optional injected Dio (used by tests with a MockAdapter). When null, a
  /// real Dio is created. Not for production use.
  final Dio? _dioOverride;

  /// Guards against infinite 401→refresh→401 loops (Phase 3B §11).
  bool _refreshInFlight = false;

  Future<void> _onRequest(
    RequestOptions options,
    RequestInterceptorHandler handler,
  ) async {
    final token = await _tokenStorage.getAccessToken();
    if (token != null && token.isNotEmpty) {
      options.headers['Authorization'] = 'Bearer $token';
    }
    handler.next(options);
  }

  Future<void> _onError(DioException err, ErrorInterceptorHandler handler) async {
    final normalized = _normalize(err);
    // Attempt a single refresh + retry on 401, only if a handler is wired.
    if (normalized.response?.statusCode == 401 &&
        onUnauthorized != null &&
        !_refreshInFlight) {
      _refreshInFlight = true;
      try {
        final retried = await onUnauthorized!();
        if (retried) {
          // Replay the original request with the fresh access token.
          final token = await _tokenStorage.getAccessToken();
          final opts = err.requestOptions;
          if (token != null && token.isNotEmpty) {
            opts.headers['Authorization'] = 'Bearer $token';
          }
          try {
            final resp = await _dio.fetch(opts);
            _refreshInFlight = false;
            handler.resolve(resp);
            return;
          } on DioException catch (e) {
            handler.next(_normalize(e));
            return;
          }
        }
      } finally {
        _refreshInFlight = false;
      }
    }
    handler.next(normalized);
  }

  DioException _normalize(DioException err) {
    final data = err.response?.data;
    String? code;
    String? message;
    if (data is Map<String, dynamic> && data['error'] is Map) {
      code = data['error']['code'] as String?;
      message = data['error']['message'] as String?;
    }
    return err.copyWith(
      error: ApiException(
        code: code ?? 'UNKNOWN',
        message: message ?? err.message ?? 'Network error',
        status: err.response?.statusCode,
      ),
    );
  }

  Future<Response<T>> get<T>(String path, {Map<String, dynamic>? query}) =>
      _dio.get(path, queryParameters: query);

  Future<Response<T>> post<T>(String path, {dynamic data}) =>
      _dio.post(path, data: data);

  Future<Response<T>> patch<T>(String path, {dynamic data}) =>
      _dio.patch(path, data: data);

  Future<Response<T>> delete<T>(String path) => _dio.delete(path);
}
