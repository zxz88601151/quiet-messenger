/// Auth state notifier — bridges [AuthRepository] and the UI/router.
///
/// Holds the single source of truth for [AuthState] and the current [Session].
/// The router reads [status] to redirect; pages call the action methods and
/// listen to [error] for display. No business logic beyond orchestration.
import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';

import '../../core/errors/api_exception.dart';
import 'auth_error_mapper.dart';
import 'repositories/auth_repository.dart';
import 'models/auth_state.dart';
import 'models/session.dart';
import 'models/user.dart';

class AuthNotifier extends ChangeNotifier {
  AuthNotifier(this._repo);

  final AuthRepository _repo;

  AuthState _status = AuthState.unknown;
  Session? _session;
  AuthError? _error;
  bool _loading = false;

  AuthState get status => _status;
  Session? get session => _session;
  User? get currentUser => _session?.user;
  AuthError? get error => _error;
  bool get loading => _loading;

  /// Restore session on app start. Called once from [App] init.
  Future<void> restore() async {
    _status = AuthState.unknown;
    _error = null;
    notifyListeners();

    final restored = await _repo.restoreSession();
    if (restored != null) {
      _session = restored;
      _status = AuthState.authenticated;
    } else {
      _status = AuthState.unauthenticated;
    }
    notifyListeners();
  }

  Future<void> login({required String identifier, required String password}) async {
    _beginLoading();
    try {
      _session = await _repo.login(identifier: identifier, password: password);
      _status = AuthState.authenticated;
      _error = null;
    } on ApiException catch (e) {
      _fail(e);
    } on DioException catch (e) {
      _fail(_unwrapDioException(e));
    } finally {
      _endLoading();
    }
  }

  Future<void> register({
    required String username,
    required String phone,
    required String password,
    required String nickname,
  }) async {
    _beginLoading();
    try {
      _session = await _repo.register(
        username: username,
        phone: phone,
        password: password,
        nickname: nickname,
      );
      _status = AuthState.authenticated;
      _error = null;
    } on ApiException catch (e) {
      _fail(e);
    } on DioException catch (e) {
      _fail(_unwrapDioException(e));
    } finally {
      _endLoading();
    }
  }

  Future<void> logout() async {
    _beginLoading();
    try {
      await _repo.logout();
    } on ApiException {
      // Even on backend failure we clear local state (repo does this too).
    } finally {
      _session = null;
      _status = AuthState.unauthenticated;
      _error = null;
      _endLoading();
    }
  }

  /// Clear the current error (e.g. when the user dismisses a snackbar).
  void clearError() {
    _error = null;
    notifyListeners();
  }

  /// Update the current user in the session (e.g. after PATCH /users/me).
  /// Used by profile/nickname/privacy flows to reflect server changes.
  void updateCurrentUser(User user) {
    if (_session != null) {
      _session = Session(user: user, tokens: _session!.tokens);
      notifyListeners();
    }
  }

  /// Hook for [ApiClient] 401 handling: attempt one refresh and report
  /// whether the original request should be retried (Phase 3B §11).
  /// Returns false if refresh fails (caller will surface the 401 → redirect
  /// to login via auth state).
  Future<bool> handleUnauthorized() async {
    try {
      await _repo.refresh();
      return true;
    } on ApiException {
      // Refresh failed → session is dead. Clear and go unauthenticated.
      _session = null;
      _status = AuthState.unauthenticated;
      notifyListeners();
      return false;
    } on DioException {
      // Network/transport error during refresh → treat as session dead.
      _session = null;
      _status = AuthState.unauthenticated;
      notifyListeners();
      return false;
    }
  }

  void _beginLoading() {
    _loading = true;
    _error = null;
    notifyListeners();
  }

  void _endLoading() {
    _loading = false;
    notifyListeners();
  }

  void _fail(ApiException e) {
    _error = mapAuthError(e);
    _status = AuthState.unauthenticated;
  }

  /// Extract [ApiException] from a [DioException]. ApiClient wraps backend
  /// errors as `DioException(error: ApiException(...))`, so we unwrap here.
  /// Transport-level errors (no response) map to NETWORK_ERROR.
  ApiException _unwrapDioException(DioException e) {
    if (e.error is ApiException) return e.error as ApiException;
    return ApiException(
      code: 'NETWORK_ERROR',
      message: e.message?.isNotEmpty == true ? e.message! : '网络异常，请检查连接后重试',
      status: e.response?.statusCode,
    );
  }
}
