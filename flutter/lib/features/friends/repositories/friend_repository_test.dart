/// FriendRepository tests — real logic against a fake ApiClient.
///
/// These run on a host with flutter_tester (see Phase 3B/3C: BLOCKED BY
/// ENVIRONMENT in this sandbox). The fake client is NOT a stub of the real
/// backend — it asserts the exact request shape and returns real backend
/// JSON so the repository mapping is genuinely exercised.
import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';

import '../../../core/api/api_client.dart';
import '../models/friend_request.dart';
import '../models/friendship.dart';
import '../models/user_summary.dart';
import 'friend_repository.dart';

/// In-memory fake Dio adapter capturing requests + returning canned JSON.
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
  late ApiFriendRepository repo;

  setUp(() {
    dio = Dio(BaseOptions(baseUrl: 'http://test'));
    api = ApiClient(dioOverride: dio);
    repo = ApiFriendRepository(api, 'me-uuid');
  });

  test('searchUsers hits GET /users/search and maps public fields', () async {
    dio.httpClientAdapter = _FakeAdapter((opt) async {
      expect(opt.method, 'GET');
      expect(opt.path, '/users/search');
      expect(opt.queryParameters['q'], 'alice');
      return _json([
        {'id': 'u1', 'username': 'alice', 'nickname': 'Alice', 'avatar': null}
      ]);
    });
    final res = await repo.searchUsers('alice');
    expect(res, hasLength(1));
    expect(res.first.username, 'alice');
    expect(res.first.nickname, 'Alice');
  });

  test('sendFriendRequest posts target_username_or_phone', () async {
    dio.httpClientAdapter = _FakeAdapter((opt) async {
      expect(opt.method, 'POST');
      expect(opt.path, '/friends/requests');
      expect(opt.data['target_username_or_phone'], 'bob');
      return _json({
        'id': 'r1',
        'sender_id': 'me-uuid',
        'receiver_id': 'bob-uuid',
        'status': 'pending',
        'sender': {'id': 'me-uuid', 'username': 'me', 'nickname': 'Me'},
        'receiver': {'id': 'bob-uuid', 'username': 'bob', 'nickname': 'Bob'},
      }, 201);
    });
    final req = await repo.sendFriendRequest('bob');
    expect(req.id, 'r1');
    expect(req.isIncoming, isFalse);
    expect(req.otherUser?.username, 'bob');
  });

  test('acceptFriendRequest returns conversation id', () async {
    dio.httpClientAdapter = _FakeAdapter((opt) async {
      expect(opt.method, 'POST');
      expect(opt.path, '/friends/requests/r1/accept');
      return _json({
        'friendship': {
          'user': {'id': 'bob-uuid', 'username': 'bob', 'nickname': 'Bob'},
          'friendship_created_at': null,
        },
        'conversation': {'id': 'c001', 'user_a': 'a', 'user_b': 'b'},
      });
    });
    final result = await repo.acceptFriendRequest('r1');
    expect(result.conversationId, 'c001');
    expect(result.friendship.user.username, 'bob');
  });

  test('getFriends maps friend list', () async {
    dio.httpClientAdapter = _FakeAdapter((opt) async {
      expect(opt.path, '/friends');
      return _json([
        {
          'user': {'id': 'bob-uuid', 'username': 'bob', 'nickname': 'Bob'},
          'friendship_created_at': '2026-01-01T00:00:00+00:00',
        }
      ]);
    });
    final friends = await repo.getFriends();
    expect(friends, hasLength(1));
    expect(friends.first.user.username, 'bob');
  });

  test('deleteFriend hits DELETE /friends/{id}', () async {
    var called = false;
    dio.httpClientAdapter = _FakeAdapter((opt) async {
      expect(opt.method, 'DELETE');
      expect(opt.path, '/friends/bob-uuid');
      called = true;
      return _json({'ok': true});
    });
    await repo.deleteFriend('bob-uuid');
    expect(called, isTrue);
  });
}
