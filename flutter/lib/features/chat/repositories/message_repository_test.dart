/// ApiMessageRepository tests (Phase 3E).
///
/// Uses a fake Dio HTTP client (MockAdapter) to assert the real request
/// shape (path, method, body) and response parsing — no mock backend, no
/// fabricated PASS. Mirrors the pattern from friend_repository_test.
import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';

import '../../../core/api/api_client.dart';
import '../../../core/errors/api_exception.dart';
import '../../../core/storage/token_storage.dart';
import 'message_repository.dart';

/// In-memory token storage so the request interceptor does not hit
/// FlutterSecureStorage (unavailable in `flutter test` headless).
class _FakeTokenStorage implements TokenStorage {
  @override
  Future<String?> getAccessToken() async => 'test-token';
  @override
  Future<String?> getRefreshToken() async => 'test-refresh';
  @override
  Future<void> setTokens({required String access, required String refresh}) async {}
  @override
  Future<void> clear() async {}
}

class _FakeAdapter implements HttpClientAdapter {
  _FakeAdapter(this.handler);
  final Future<ResponseBody> Function(RequestOptions) handler;

  @override
  Future<ResponseBody> fetch(RequestOptions options, Stream<Uint8List>? requestStream, Future<void>? cancelFuture) =>
      handler(options);

  @override
  void close({bool force = false}) {}
}

ResponseBody _json(Map<String, dynamic> data, [int status = 200]) => ResponseBody.fromString(
      const JsonEncoder().convert(data), status,
      headers: {'content-type': ['application/json']});

void main() {
  late Dio dio;
  late ApiMessageRepository repo;

  setUp(() {
    dio = Dio();
  });

  test('getMessages maps items ascending + request shape', () async {
    dio.httpClientAdapter = _FakeAdapter((opts) async {
      expect(opts.method, 'GET');
      expect(opts.path, '/conversations/conv1/messages');
      expect(opts.queryParameters['limit'], 50);
      return _json({
        'items': [
          {'id': 'm1', 'conversation_id': 'conv1', 'sender_id': 'u2', 'content': 'hi', 'created_at': '2026-08-24T00:00:00+00:00'},
          {'id': 'm2', 'conversation_id': 'conv1', 'sender_id': 'u1', 'content': 'yo', 'created_at': '2026-08-24T00:00:01+00:00'},
        ],
        'next_cursor': '',
      });
    });
    repo = ApiMessageRepository(ApiClient(dioOverride: dio, tokenStorage: _FakeTokenStorage()));
    final msgs = await repo.getMessages('conv1');
    expect(msgs.length, 2);
    expect(msgs.first.id, 'm1');
    expect(msgs.last.content, 'yo');
  });

  test('sendMessage posts content + client_message_id', () async {
    dio.httpClientAdapter = _FakeAdapter((opts) async {
      expect(opts.method, 'POST');
      expect(opts.path, '/conversations/conv1/messages');
      final body = opts.data as Map<String, dynamic>;
      expect(body['content'], 'hello');
      expect(body['client_message_id'], 'c1');
      return _json({
        'id': 'm9', 'conversation_id': 'conv1', 'sender_id': 'u1',
        'content': 'hello', 'client_message_id': 'c1',
        'created_at': '2026-08-24T00:00:00+00:00',
      }, 201);
    });
    repo = ApiMessageRepository(ApiClient(dioOverride: dio, tokenStorage: _FakeTokenStorage()));
    final m = await repo.sendMessage('conv1', 'hello', 'c1');
    expect(m.id, 'm9');
    expect(m.content, 'hello');
  });

  test('sendMessage empty content surfaces server 400', () async {
    dio.httpClientAdapter = _FakeAdapter((_) async => _json(
        {'error': {'code': 'VALIDATION_ERROR', 'message': '内容不能为空'}}, 400));
    repo = ApiMessageRepository(ApiClient(dioOverride: dio, tokenStorage: _FakeTokenStorage()));
    // ApiClient normalizes non-2xx into DioException with .error = ApiException.
    try {
      await repo.sendMessage('conv1', '', 'c1');
      fail('expected a DioException carrying ApiException');
    } on DioException catch (e) {
      final apiErr = e.error;
      expect(apiErr, isA<ApiException>());
      expect((apiErr as ApiException).code, 'VALIDATION_ERROR');
    }
  });
}
