/// Friend repository — REAL API implementation (Phase 3D).
///
/// Wires the friends feature to the existing [ApiClient] (Dio) from Phase 3A.
/// NO second HTTP client. Endpoints follow shared/API_CONTRACT.md §2/§3.
///
/// Scope (Phase 3D only): search / request / accept / reject / list / delete.
/// NO message / conversation / websocket / QR / group logic here.
///
/// Layering: UI → Provider/Notifier → FriendRepository → ApiClient → Backend.
/// UI never calls ApiClient directly.
import '../../../core/api/api_client.dart';
import '../models/friend_request.dart';
import '../models/friendship.dart';
import '../models/user_summary.dart';

abstract class FriendRepository {
  /// GET /users/search?q= — username/phone search. Returns public summaries.
  Future<List<UserSummary>> searchUsers(String query);

  /// POST /friends/requests — send a friend request by username or phone.
  Future<FriendRequest> sendFriendRequest(String target);

  /// GET /friends/requests?type=incoming|outgoing|all.
  Future<List<FriendRequest>> getRequests({String type = 'all'});

  /// POST /friends/requests/{id}/accept → returns friendship + conversation.
  Future<AcceptResult> acceptFriendRequest(String requestId);

  /// POST /friends/requests/{id}/reject → ok.
  Future<void> rejectFriendRequest(String requestId);

  /// GET /friends — bidirectional friend list.
  Future<List<Friendship>> getFriends();

  /// DELETE /friends/{friendId} — remove friendship (keeps messages).
  Future<void> deleteFriend(String friendId);
}

class AcceptResult {
  const AcceptResult({required this.friendship, required this.conversationId});

  final Friendship friendship;
  final String conversationId;
}

class ApiFriendRepository implements FriendRepository {
  const ApiFriendRepository(this._client, this._currentUserId);

  final ApiClient _client;
  final String _currentUserId;

  @override
  Future<List<UserSummary>> searchUsers(String query) async {
    final resp = await _client.get(
      '/users/search',
      query: {'q': query, 'limit': 20},
    );
    final list = (resp.data as List?) ?? [];
    return list
        .map((e) => UserSummary.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  @override
  Future<FriendRequest> sendFriendRequest(String target) async {
    final resp = await _client.post(
      '/friends/requests',
      data: {'target_username_or_phone': target},
    );
    return FriendRequest.fromJson(resp.data as Map<String, dynamic>, _currentUserId);
  }

  @override
  Future<List<FriendRequest>> getRequests({String type = 'all'}) async {
    final resp = await _client.get(
      '/friends/requests',
      query: {'type': type},
    );
    final list = (resp.data as List?) ?? [];
    return list
        .map((e) => FriendRequest.fromJson(e as Map<String, dynamic>, _currentUserId))
        .toList();
  }

  @override
  Future<AcceptResult> acceptFriendRequest(String requestId) async {
    final resp = await _client.post('/friends/requests/$requestId/accept');
    final data = resp.data as Map<String, dynamic>;
    final friendship = Friendship.fromJson(data['friendship'] as Map<String, dynamic>);
    final conversation = data['conversation'] as Map<String, dynamic>;
    return AcceptResult(
      friendship: friendship,
      conversationId: conversation['id'] as String,
    );
  }

  @override
  Future<void> rejectFriendRequest(String requestId) async {
    await _client.post('/friends/requests/$requestId/reject');
  }

  @override
  Future<List<Friendship>> getFriends() async {
    final resp = await _client.get('/friends');
    final list = (resp.data as List?) ?? [];
    return list
        .map((e) => Friendship.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  @override
  Future<void> deleteFriend(String friendId) async {
    await _client.delete('/friends/$friendId');
  }
}
