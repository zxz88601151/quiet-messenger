/// Friends state orchestration (Flutter / Phase 3D).
///
/// Drives the friends feature UI. UI pages call these actions; the notifier
/// talks to [FriendRepository] and exposes loading/error/list state. UI never
/// touches [ApiClient] directly (layering: UI → Notifier → Repository → API).
import 'package:flutter/material.dart' hide ConnectionState;

import '../../core/errors/api_exception.dart';
import '../../core/realtime/connection_state.dart';
import '../../core/realtime/event_envelope.dart';
import '../../core/realtime/realtime_client.dart';
import '../../core/sound/sound_service.dart';
import 'friends_error_mapper.dart';
import 'models/friend_request.dart';
import 'models/friendship.dart';
import 'models/user_summary.dart';
import 'repositories/friend_repository.dart';

class FriendNotifier extends ChangeNotifier {
  FriendNotifier(this._repo);

  FriendRepository _repo;
  RealtimeClient? _realtime;
  void Function()? _unsubscribeRealtime;
  void Function()? _unsubscribeState;

  /// Tracks whether we have been connected at least once. Used to distinguish
  /// initial connect (no reconciliation needed) from reconnect (refresh state).
  bool _hasBeenConnected = false;
  bool _wasDisconnected = false;

  /// Update the injected repository (called by DI when AuthNotifier changes
  /// the current user id). Does not reset state.
  void updateRepository(FriendRepository repo) {
    _repo = repo;
  }

  /// Subscribe to RealtimeClient events for real-time friend request updates.
  /// Called by DI after creation. Idempotent: safe to call multiple times.
  /// Also subscribes to connection-state changes for REST reconciliation on
  /// reconnect (DEF-RT-010): when the connection drops and reconnects, we
  /// refresh pending requests to catch any missed events.
  void subscribeRealtime(RealtimeClient realtime) {
    _unsubscribeRealtime?.call();
    _unsubscribeState?.call();
    _realtime = realtime;
    _unsubscribeRealtime = realtime.addEventListener(_onRealtimeEvent);
    _unsubscribeState = realtime.addStateListener(_onConnectionState);
  }

  /// Handle connection state changes for REST reconciliation on reconnect.
  /// Initial connect (first time reaching connected) does NOT trigger
  /// reconciliation — the UI loads data on page open. Only a reconnect
  /// (disconnected → connected after a prior drop) triggers a refresh.
  void _onConnectionState(ConnectionState state) {
    if (state == ConnectionState.connected) {
      if (!_hasBeenConnected) {
        _hasBeenConnected = true;
        return; // initial connect — no reconciliation needed
      }
      if (_wasDisconnected) {
        _wasDisconnected = false;
        // Reconnect detected — refresh pending requests to catch missed events.
        // Fire-and-forget: errors are handled inside loadRequests.
        loadRequests();
      }
    } else if (state == ConnectionState.disconnected) {
      _wasDisconnected = true;
    }
  }

  /// Handle incoming WebSocket events. Only friend.request.created is
  /// processed here; other events are ignored (handled by other notifiers).
  void _onRealtimeEvent(EventEnvelope evt) {
    if (evt.type != 'friend.request.created') return;
    final payload = evt.payload;
    final reqId = payload['id'] as String?;
    if (reqId == null) return;
    // Dedup: don't add or play sound for a request we already know about.
    if (_seenRequestIds.contains(reqId)) return;
    _seenRequestIds.add(reqId);
    // Parse and prepend to the requests list (newest first).
    // The event is pushed to the receiver, so receiver_id == current user.
    final viewerId = payload['receiver_id'] as String? ?? '';
    try {
      final req = FriendRequest.fromJson(payload, viewerId);
      requests = [req, ...requests];
      notifyListeners();
    } catch (_) {
      // Malformed payload: still track the ID to avoid repeated attempts,
      // but don't crash the notifier.
    }
    // Play sound only after initial sync is complete (first load via REST
    // does not play sound; real-time WS events do).
    if (_requestsInitialized) {
      SoundService.instance.playFriendAdded();
    }
  }

  @override
  void dispose() {
    _unsubscribeRealtime?.call();
    _unsubscribeState?.call();
    super.dispose();
  }

  List<UserSummary> searchResults = const [];
  List<FriendRequest> requests = const [];
  List<Friendship> friends = const [];

  bool loading = false;
  FriendError? error;

  /// 已见过的好友请求 ID 集合（用于去重，避免同一请求重复触发音效）。
  final Set<String> _seenRequestIds = {};

  /// 是否完成过首次请求加载（首次为初始同步，不播放音效）。
  bool _requestsInitialized = false;

  /// Set after a successful accept — lets the UI navigate to the conversation.
  String? lastAcceptedConversationId;

  void clearError() {
    error = null;
    notifyListeners();
  }

  Future<void> search(String query) async {
    _setLoading();
    try {
      searchResults = await _repo.searchUsers(query);
      error = null;
    } on ApiException catch (e) {
      error = mapFriendError(e);
    } finally {
      loading = false;
      notifyListeners();
    }
  }

  Future<void> loadRequests({String type = 'all'}) async {
    _setLoading();
    try {
      requests = await _repo.getRequests(type: type);
      error = null;
      _detectNewIncomingRequests();
    } on ApiException catch (e) {
      error = mapFriendError(e);
    } finally {
      loading = false;
      notifyListeners();
    }
  }

  /// 检测新的 incoming pending 好友请求并触发音效（去重 + 初始同步排除）。
  ///
  /// 规则：
  /// - 首次加载为初始同步，只记录 ID 不播放
  /// - 后续加载中，发现 isIncoming && status=='pending' 且 ID 未见过 → 触发音效
  /// - SoundService 内部负责短时间节流（多个新请求只播一次）
  void _detectNewIncomingRequests() {
    final currentIds = requests.map((r) => r.id).toSet();
    if (!_requestsInitialized) {
      // 初始同步：只记录，不播放
      _seenRequestIds.addAll(currentIds);
      _requestsInitialized = true;
      return;
    }
    // 查找新的 incoming pending 请求
    final hasNewIncoming = requests.any((r) =>
        r.isIncoming &&
        r.status == 'pending' &&
        !_seenRequestIds.contains(r.id));
    if (hasNewIncoming) {
      SoundService.instance.playFriendAdded();
    }
    // 更新已见集合（只增不减，确保历史请求不会重复触发）
    _seenRequestIds.addAll(currentIds);
  }

  Future<void> loadFriends() async {
    _setLoading();
    try {
      friends = await _repo.getFriends();
      error = null;
    } on ApiException catch (e) {
      error = mapFriendError(e);
    } finally {
      loading = false;
      notifyListeners();
    }
  }

  Future<bool> sendRequest(String target) async {
    _setLoading();
    try {
      await _repo.sendFriendRequest(target);
      error = null;
      return true;
    } on ApiException catch (e) {
      error = mapFriendError(e);
      return false;
    } finally {
      loading = false;
      notifyListeners();
    }
  }

  /// Accept a request. On success stores [lastAcceptedConversationId] so the
  /// caller can navigate into the (pre-created) direct conversation.
  Future<bool> accept(String requestId) async {
    _setLoading();
    try {
      final result = await _repo.acceptFriendRequest(requestId);
      lastAcceptedConversationId = result.conversationId;
      error = null;
      return true;
    } on ApiException catch (e) {
      error = mapFriendError(e);
      return false;
    } finally {
      loading = false;
      notifyListeners();
    }
  }

  Future<bool> reject(String requestId) async {
    _setLoading();
    try {
      await _repo.rejectFriendRequest(requestId);
      error = null;
      return true;
    } on ApiException catch (e) {
      error = mapFriendError(e);
      return false;
    } finally {
      loading = false;
      notifyListeners();
    }
  }

  Future<bool> deleteFriend(String friendId) async {
    _setLoading();
    try {
      await _repo.deleteFriend(friendId);
      error = null;
      return true;
    } on ApiException catch (e) {
      error = mapFriendError(e);
      return false;
    } finally {
      loading = false;
      notifyListeners();
    }
  }

  void _setLoading() {
    loading = true;
    error = null;
    notifyListeners();
  }
}
