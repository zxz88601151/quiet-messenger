/// ConversationRepository tests — real logic against a fake ApiClient.
///
/// Runs on a host with flutter_tester (BLOCKED BY ENVIRONMENT in this sandbox,
/// same as Phase 3B/3C). No message send is tested here (Phase 3E).
import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';

import '../../../core/api/api_client.dart';
import '../../../core/storage/token_storage.dart';
import '../models/conversation.dart';
import 'conversation_repository.dart';

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
  _FakeAdapter(this._handler);
  final Future<ResponseBody> Function(RequestOptions) _handler;

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) =>
      _handler(options);

  @override
  void close({bool force = false}) {}
}

ResponseBody _json(Object body, [int status = 200]) {
  return ResponseBody.fromString(
    const JsonEncoder().convert(body),
    status,
    headers: {'content-type': ['application/json']},
  );
}

void main() {
  late Dio dio;
  late ApiClient api;
  late ApiConversationRepository repo;

  setUp(() {
    dio = Dio(BaseOptions(baseUrl: 'http://test'));
    api = ApiClient(dioOverride: dio, tokenStorage: _FakeTokenStorage());
    repo = ApiConversationRepository(api);
  });

  test('getConversations maps list with peer + preview', () async {
    dio.httpClientAdapter = _FakeAdapter((opt) async {
      expect(opt.path, '/conversations');
      return _json([
        {
          'id': 'c001',
          'user_a': 'a',
          'user_b': 'b',
          'peer': {'id': 'bob-uuid', 'username': 'bob', 'nickname': 'Bob'},
          'last_message': {'content': 'hi'},
          'unread_count': 2,
        }
      ]);
    });
    final list = await repo.getConversations();
    expect(list, hasLength(1));
    expect(list.first.id, 'c001');
    expect(list.first.peer.username, 'bob');
    expect(list.first.lastMessagePreview, 'hi');
    expect(list.first.unreadCount, 2);
    expect(list.first.type, ConversationType.direct);
  });

  test('getConversation hits GET /conversations/{id}', () async {
    dio.httpClientAdapter = _FakeAdapter((opt) async {
      expect(opt.path, '/conversations/c001');
      return _json({
        'id': 'c001',
        'user_a': 'a',
        'user_b': 'b',
        'peer': {'id': 'bob-uuid', 'username': 'bob', 'nickname': 'Bob'},
      });
    });
    final c = await repo.getConversation('c001');
    expect(c.id, 'c001');
    expect(c.peer.username, 'bob');
  });
}
