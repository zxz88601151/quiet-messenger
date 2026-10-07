/// AuthRepository tests (Phase 3B).
///
/// These exercise the REAL AuthRepository logic (request shape, response
/// parsing, token persistence) against an in-memory [FakeApiClient] and an
/// in-memory [FakeSecureStorage]. No live backend, no display, no native
/// plugin needed — so the assertions are fully executable where flutter_test
/// can run.
///
/// Execution: `flutter test` (needs flutter_tester). In the headless Windows
/// sandbox this is BLOCKED BY ENVIRONMENT (no flutter_tester). The tests are
/// valid and should run on a CI host / device to close the gap. They do NOT
/// fabricate a passing result — they genuinely assert client behavior.
import 'package:dio/dio.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flutter_client/core/api/api_client.dart';
import 'package:flutter_client/core/errors/api_exception.dart';
import 'package:flutter_client/core/storage/token_storage.dart';
import 'package:flutter_client/features/auth/repositories/auth_repository.dart';

/// In-memory fake of FlutterSecureStorage (no native plugin needed).
class FakeSecureStorage extends FlutterSecureStorage {
  final Map<String, String> _m = {};
  @override
  Future<String?> read({
    AndroidOptions? aOptions,
    IOSOptions? iOptions,
    required String key,
    LinuxOptions? lOptions,
    MacOsOptions? mOptions,
    WebOptions? webOptions,
    WindowsOptions? wOptions,
  }) async =>
      _m[key];
  @override
  Future<void> write({
    AndroidOptions? aOptions,
    IOSOptions? iOptions,
    required String key,
    required String? value,
    LinuxOptions? lOptions,
    MacOsOptions? mOptions,
    WebOptions? webOptions,
    WindowsOptions? wOptions,
  }) async {
    if (value == null) {
      _m.remove(key);
    } else {
      _m[key] = value;
    }
  }

  @override
  Future<void> delete({
    AndroidOptions? aOptions,
    IOSOptions? iOptions,
    required String key,
    LinuxOptions? lOptions,
    MacOsOptions? mOptions,
    WebOptions? webOptions,
    WindowsOptions? wOptions,
  }) async =>
      _m.remove(key);
}

/// In-memory API client that records the last call and returns queued
/// responses. Mirrors the [ApiClient] surface used by AuthRepository.
class FakeApiClient extends ApiClient {
  FakeApiClient(TokenStorage ts) : super(tokenStorage: ts);

  final List<Map<String, dynamic>> calls = [];
  Map<String, dynamic>? _nextResponse;
  int? _nextStatus;
  ApiException? _nextError;

  void queueResponse(Map<String, dynamic> body, {int status = 200}) {
    _nextResponse = body;
    _nextStatus = status;
  }

  void queueError(ApiException e) => _nextError = e;

  @override
  Future<Response<T>> post<T>(String path, {dynamic data}) {
    calls.add({'method': 'POST', 'path': path, 'data': data});
    if (_nextError != null) return Future<Response<T>>.error(_nextError!);
    final resp = Response<T>(
      requestOptions: RequestOptions(path: path),
      statusCode: _nextStatus ?? 200,
      data: _nextResponse as T,
    );
    return Future.value(resp);
  }

  @override
  Future<Response<T>> get<T>(String path, {Map<String, dynamic>? query}) {
    calls.add({'method': 'GET', 'path': path});
    if (_nextError != null) return Future<Response<T>>.error(_nextError!);
    final resp = Response<T>(
      requestOptions: RequestOptions(path: path),
      statusCode: _nextStatus ?? 200,
      data: _nextResponse as T,
    );
    return Future.value(resp);
  }
}

void main() {
  late TokenStorage tokens;
  late FakeApiClient client;
  late AuthRepository repo;

  setUp(() {
    tokens = TokenStorage(storage: FakeSecureStorage());
    client = FakeApiClient(tokens);
    repo = AuthRepository(client, tokens);
  });

  test('login sends identifier+password+device and persists tokens', () async {
    client.queueResponse({
      'access_token': 'access-1',
      'refresh_token': 'refresh-1',
      'user': {
        'id': 'u1',
        'username': 'alice',
        'phone': '123456',
        'nickname': 'Alice',
      },
    });
    final session = await repo.login(identifier: 'alice', password: 'secret');
    expect(session.user.username, 'alice');
    expect(session.tokens.accessToken, 'access-1');
    // Request body shape matches the contract.
    final sent = client.calls.first;
    expect(sent['path'], '/auth/login');
    expect(sent['data']['identifier'], 'alice');
    expect(sent['data']['device']['device_type'], 'mobile');
    // Tokens persisted to secure storage.
    expect(await tokens.getAccessToken(), 'access-1');
    expect(await tokens.getRefreshToken(), 'refresh-1');
  });

  test('login failure maps to ApiException(INVALID_CREDENTIALS)', () async {
    client.queueError(const ApiException(
      code: 'INVALID_CREDENTIALS',
      message: 'bad',
      status: 401,
    ));
    expect(
      () => repo.login(identifier: 'alice', password: 'wrong'),
      throwsA(
        isA<ApiException>().having((e) => e.code, 'code', 'INVALID_CREDENTIALS'),
      ),
    );
  });

  test('logout posts refresh_token and clears local tokens', () async {
    await tokens.setTokens(access: 'access-1', refresh: 'refresh-1');
    client.queueResponse({'ok': true});
    await repo.logout();
    final sent = client.calls.first;
    expect(sent['path'], '/auth/logout');
    expect(sent['data']['refresh_token'], 'refresh-1');
    expect(await tokens.getAccessToken(), isNull);
    expect(await tokens.getRefreshToken(), isNull);
  });

  test('register sends full payload and persists tokens', () async {
    client.queueResponse({
      'access_token': 'a',
      'refresh_token': 'r',
      'user': {
        'id': 'u2',
        'username': 'bob',
        'phone': '654321',
        'nickname': 'Bob',
      },
    });
    final session = await repo.register(
      username: 'bob',
      phone: '654321',
      password: 'pw123456',
      nickname: 'Bob',
    );
    expect(session.user.username, 'bob');
    final sent = client.calls.first;
    expect(sent['data']['username'], 'bob');
    expect(sent['data']['nickname'], 'Bob');
    expect(await tokens.getRefreshToken(), 'r');
  });

  test('getCurrentUser calls GET /users/me and parses user', () async {
    client.queueResponse({
      'id': 'u1',
      'username': 'alice',
      'phone': '123456',
      'nickname': 'Alice',
    });
    final user = await repo.getCurrentUser();
    expect(user.username, 'alice');
    expect(client.calls.first['path'], '/users/me');
  });

  test('restoreSession returns null when no stored refresh token', () async {
    final restored = await repo.restoreSession();
    expect(restored, isNull);
  });

  test('TokenStorage round-trips via fake secure storage', () async {
    await tokens.setTokens(access: 'a', refresh: 'r');
    expect(await tokens.getAccessToken(), 'a');
    expect(await tokens.getRefreshToken(), 'r');
    await tokens.clear();
    expect(await tokens.getAccessToken(), isNull);
  });
}
