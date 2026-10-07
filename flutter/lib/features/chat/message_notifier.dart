/// Message notifier — orchestrates the Phase 3E message flow for one
/// conversation.
///
/// Responsibilities (UI ≠ Repository):
/// - Load history (GET /conversations/{id}/messages)
/// - Send (POST), with optimistic insert + server-confirm replacement
/// - Subscribe to [RealtimeClient] `message.created` events → dedup insert
///   (by message.id) so REST response + WS event never double-render (§8)
/// - Track minimal UI state: sending / sent / failed (no status machine bloat)
///
/// Out of scope (NOT implemented): typing, read receipt, reaction, reply,
/// edit, recall, file/image/voice/video, group, AI, push.
import 'package:flutter/foundation.dart';

import '../../core/realtime/event_envelope.dart';
import '../../core/realtime/realtime_client.dart';
import '../../core/realtime/connection_state.dart';
import '../../core/sound/sound_service.dart';
import 'models/message.dart';
import 'repositories/message_repository.dart';

class MessageNotifier extends ChangeNotifier {
  MessageNotifier({
    required MessageRepository repository,
    required RealtimeClient realtime,
    required String currentUserId,
    required this.conversationId,
  })  : _repo = repository,
        _realtime = realtime,
        _currentUserId = currentUserId {
    _unsubscribe = _realtime.addEventListener(_onEvent);
    // Offline message catch-up (DEF-RT-010 parity): when WebSocket
    // transitions disconnected→connected, reload history to recover messages
    // that arrived while the client was offline.
    _unsubscribeState = _realtime.addStateListener(_onConnectionState);
  }

  final MessageRepository _repo;
  final RealtimeClient _realtime;
  final String _currentUserId;
  final String conversationId;
  void Function()? _unsubscribe;
  void Function()? _unsubscribeState;

  // Reconciliation guards: only catch-up on reconnect, not on initial connect.
  bool _hasBeenConnected = false;
  bool _wasDisconnected = false;
  bool _reconciling = false;

  List<Message> _messages = [];
  bool _loading = true;
  final bool _loadingMore = false;
  String? _error;
  String? _nextCursor;
  bool _hasMore = false;

  List<Message> get messages => List.unmodifiable(_messages);
  bool get loading => _loading;
  bool get loadingMore => _loadingMore;
  String? get error => _error;
  bool get hasMore => _hasMore;

  /// Load initial history (newest first in DB; we render ascending).
  Future<void> load() async {
    _loading = true;
    _error = null;
    notifyListeners();
    try {
      final page = await _repo.getMessages(conversationId, limit: 50);
      _messages = page; // ascending by created_at
      _nextCursor = null; // first page; backend returns oldest-first already
      _hasMore = page.length >= 50;
      _error = null;
    } catch (e) {
      _error = e.toString();
    } finally {
      _loading = false;
      notifyListeners();
    }
  }

  /// RealtimeClient state listener for offline message catch-up.
  ///
  /// On disconnected→connected transition, reload history to recover messages
  /// that arrived while offline. Uses the same guard pattern as FriendNotifier
  /// (DEF-RT-010): initial connect does NOT trigger reconciliation.
  void _onConnectionState(ConnectionState state) {
    if (state == ConnectionState.connected) {
      if (_hasBeenConnected && _wasDisconnected && !_reconciling) {
        _reconcile();
      }
      _hasBeenConnected = true;
      _wasDisconnected = false;
    } else if (state == ConnectionState.disconnected ||
        state == ConnectionState.reconnecting) {
      _wasDisconnected = true;
    }
  }

  /// Reconcile: fetch latest history and merge with local state.
  ///
  /// Preserves failed messages (not on server) and sending messages (in-flight).
  /// Dedup by message.id ensures no duplicates from REST + WS overlap.
  Future<void> _reconcile() async {
    if (_reconciling) return;
    _reconciling = true;
    try {
      // Preserve local-only messages before reload
      final failed = _messages
          .where((m) => m.uiState == MessageUiState.failed)
          .toList();
      final sending = _messages
          .where((m) => m.uiState == MessageUiState.sending)
          .toList();

      final page = await _repo.getMessages(conversationId, limit: 50);
      _messages = List.from(page);

      // Re-append failed messages (not on server) — dedup by id
      for (final m in failed) {
        if (!_messages.any((existing) => existing.id == m.id)) {
          _messages.add(m);
        }
      }
      // Re-append sending messages (in-flight, may or may not be on server)
      for (final m in sending) {
        if (!_messages.any((existing) => existing.id == m.id)) {
          _messages.add(m);
        }
      }

      // Sort by created_at to maintain order
      _messages.sort((a, b) {
        if (a.createdAt == null && b.createdAt == null) return 0;
        if (a.createdAt == null) return -1;
        if (b.createdAt == null) return 1;
        return a.createdAt!.compareTo(b.createdAt!);
      });

      _error = null;
      notifyListeners();
    } catch (e) {
      _error = e.toString();
      notifyListeners();
    } finally {
      _reconciling = false;
    }
  }

  /// Send a message. Optimistic insert, then replace with server confirmation.
  Future<void> send(String content) async {
    final text = content.trim();
    if (text.isEmpty) return;
    final clientId = 'c_${DateTime.now().microsecondsSinceEpoch}_${_messages.length}';
    final optimistic = Message.optimistic(
      conversationId: conversationId,
      senderId: _currentUserId,
      content: text,
      clientMessageId: clientId,
    );
    _messages.add(optimistic);
    notifyListeners();
    try {
      final confirmed = await _repo.sendMessage(conversationId, text, clientId);
      _replaceById(optimistic.id, confirmed.copyWith(uiState: MessageUiState.sent));
      _error = null;
    } catch (e) {
      _replaceById(optimistic.id, optimistic.copyWith(uiState: MessageUiState.failed));
      _error = e.toString();
      notifyListeners();
    }
  }

  /// Retry a failed optimistic message.
  Future<void> retry(Message failed) async {
    if (failed.clientMessageId == null) return;
    _replaceById(failed.id, failed.copyWith(uiState: MessageUiState.sending));
    try {
      final confirmed = await _repo.sendMessage(
        conversationId,
        failed.content,
        failed.clientMessageId!,
      );
      _replaceById(failed.id, confirmed.copyWith(uiState: MessageUiState.sent));
      _error = null;
    } catch (e) {
      _replaceById(failed.id, failed.copyWith(uiState: MessageUiState.failed));
      _error = e.toString();
      notifyListeners();
    }
  }

  void _onEvent(EventEnvelope evt) {
    if (evt.type != 'message.created') return;
    final payload = evt.payload;
    final convId = payload['conversation_id'] as String?;
    if (convId != conversationId) return; // not for this conversation
    final msg = Message.fromJson(payload);
    // 收到他人发来的消息时播放提示音
    if (msg.senderId != _currentUserId) {
      SoundService.instance.playNewMessage();
    }
    _upsert(msg); // dedup by id (REST + WS safe)
  }

  void _upsert(Message msg) {
    final idx = _messages.indexWhere((m) => m.id == msg.id);
    if (idx >= 0) {
      // Replace (e.g. optimistic → confirmed, or WS duplicate).
      _messages[idx] = msg.copyWith(uiState: MessageUiState.sent);
    } else {
      _messages.add(msg);
    }
    notifyListeners();
  }

  void _replaceById(String oldId, Message next) {
    final idx = _messages.indexWhere((m) => m.id == oldId);
    if (idx >= 0) {
      _messages[idx] = next;
    } else {
      _messages.add(next);
    }
    notifyListeners();
  }

  @override
  void dispose() {
    _unsubscribe?.call();
    _unsubscribeState?.call();
    super.dispose();
  }
}
