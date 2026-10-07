/// Presence notifier — tracks friend online/offline state via WebSocket.
///
/// Listens to RealtimeClient `presence.update` events and maintains an
/// in-memory map of user_id -> online bool. UI (FriendsPage) can query
/// [isOnline] to display online indicators.
///
/// Plays `online.mp3` only on genuine offline→online transitions, excluding
/// the current user and duplicate/reconnect events.
import 'package:flutter/foundation.dart';

import '../../core/realtime/event_envelope.dart';
import '../../core/realtime/realtime_client.dart';
import '../../core/sound/sound_service.dart';

class PresenceNotifier extends ChangeNotifier {
  PresenceNotifier(this._realtime, {String? currentUserId}) {
    _currentUserId = currentUserId;
    _unsubscribe = _realtime.addEventListener(_onEvent);
  }

  final RealtimeClient _realtime;
  void Function()? _unsubscribe;
  String? _currentUserId;

  final Map<String, bool> _online = {};

  set currentUserId(String? id) => _currentUserId = id;

  bool isOnline(String userId) => _online[userId] ?? false;

  Map<String, bool> get onlineMap => Map.unmodifiable(_online);

  void _onEvent(EventEnvelope evt) {
    if (evt.type != 'presence.update') return;
    final userId = evt.payload['user_id'] as String?;
    final status = evt.payload['status'] as String?;
    if (userId == null || status == null) return;
    // Never play sound or track presence for the current user.
    if (userId == _currentUserId) return;
    // Initial presence sync events (sent on WS connect) must NOT trigger
    // the online sound — they represent current state, not a transition.
    final isInitial = evt.payload['initial'] == true;
    final wasOnline = _online[userId] ?? false;
    final isNowOnline = status == 'online';
    _online[userId] = isNowOnline;
    if (wasOnline != isNowOnline) {
      // Play online sound only on genuine offline→online transition,
      // excluding initial sync events.
      if (!wasOnline && isNowOnline && !isInitial) {
        SoundService.instance.playOnline();
      }
      notifyListeners();
    }
  }

  @override
  void dispose() {
    _unsubscribe?.call();
    super.dispose();
  }
}
