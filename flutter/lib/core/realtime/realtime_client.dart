/// Realtime WebSocket Client (Flutter / Phase 3C).
///
/// Layering: UI → Provider/Notifier → RealtimeClient → WebSocket.
/// A Widget must never hold a raw WebSocket connection.
///
/// Features (infrastructure only, no chat/friend business):
/// - Bearer-header auth (`Authorization: Bearer <access_token>`); token is
///   never placed in the URL (§8).
/// - On `connection.ready` → [ConnectionState.connected].
/// - On `connection.ping` → replies `connection.pong` (§16 heartbeat).
/// - Exponential-backoff reconnect (1/2/4/8/16s cap), no infinite fast loop (§17).
/// - Access-token expiry: via injected refresh callback → re-establish with new
///   token (§18); never mints its own token.
/// - State changes broadcast through [onStateChange] (UI shows minimal
///   Connected/Connecting/Offline).
import 'dart:async';
import 'dart:convert';

import 'package:stream_channel/stream_channel.dart';
import 'package:web_socket_channel/io.dart';

import 'connection_state.dart';
import 'event_envelope.dart';

/// Exponential backoff schedule (seconds), capped at 16s (§17).
const List<int> _backoffSchedule = [1, 2, 4, 8, 16];

class RealtimeClient {
  RealtimeClient({
    required this.baseUrl,
    required this.getToken,
    required this.onTokenExpired,
    this.onStateChange,
    this.onEvent,
    this.wsPath = '/ws/v1',
    this.channelFactory = _defaultChannelFactory,
  });

  final String baseUrl;
  final String wsPath;
  final String? Function() getToken;
  final Future<bool> Function() onTokenExpired;
  final void Function(ConnectionState)? onStateChange;
  final void Function(EventEnvelope)? onEvent;

  /// Injectable transport factory (test seam). Production default opens a real
  /// `IOWebSocketChannel`; tests pass an in-memory [StreamChannel] so the full
  /// state machine / event dispatch / backoff can be exercised without a
  /// network. Type is `StreamChannel<dynamic>` (the contract `RealtimeClient`
  /// actually depends on: `stream.listen` + `sink.add/close`) — `WebSocketChannel`
  /// satisfies it via `StreamChannelMixin`, so production behavior is unchanged.
  final StreamChannel<dynamic> Function(
    Uri uri, {
    Map<String, String> headers,
  }) channelFactory;

  static StreamChannel<dynamic> _defaultChannelFactory(
    Uri uri, {
    Map<String, String> headers = const {},
  }) =>
      IOWebSocketChannel.connect(uri, headers: headers);

  /// Additional event listeners (multi-cast). Phase 3E chat uses this so the
  /// MessageNotifier can subscribe without clobbering [onEvent].
  final List<void Function(EventEnvelope)> _eventListeners = [];

  /// Additional connection-state listeners (multi-cast). Used for REST
  /// reconciliation on reconnect (DEF-RT-010): when the connection transitions
  /// disconnected→connected after a prior drop, subscribers can refresh state.
  final List<void Function(ConnectionState)> _stateListeners = [];

  /// Register an additional event listener. Returns an unsubscribe callback.
  void Function() addEventListener(void Function(EventEnvelope) listener) {
    _eventListeners.add(listener);
    return () => removeEventListener(listener);
  }

  void removeEventListener(void Function(EventEnvelope) listener) {
    _eventListeners.remove(listener);
  }

  /// Register a connection-state listener. Returns an unsubscribe callback.
  void Function() addStateListener(void Function(ConnectionState) listener) {
    _stateListeners.add(listener);
    return () => removeStateListener(listener);
  }

  void removeStateListener(void Function(ConnectionState) listener) {
    _stateListeners.remove(listener);
  }

  ConnectionState _state = ConnectionState.disconnected;
  bool _running = false;
  StreamChannel<dynamic>? _channel;
  StreamSubscription<dynamic>? _subscription;
  Timer? _reconnectTimer;
  int _reconnectAttempts = 0;
  String? _currentConnId;

  ConnectionState get state => _state;

  void connect() {
    if (_running) return;
    _running = true;
    _open();
  }

  void disconnect() {
    _running = false;
    _reconnectTimer?.cancel();
    _reconnectTimer = null;
    _subscription?.cancel();
    _channel?.sink.close();
    _channel = null;
    _setState(ConnectionState.disconnected);
  }

  void send(Map<String, dynamic> event) {
    try {
      _channel?.sink.add(jsonEncode(event));
    } catch (_) {
      // best-effort; reconnect loop will re-establish.
    }
  }

  void _setState(ConnectionState next) {
    if (next == _state) return;
    _state = next;
    onStateChange?.call(next);
    for (final l in List<void Function(ConnectionState)>.of(_stateListeners)) {
      try {
        l(next);
      } catch (_) {
        // listener errors must not break the realtime loop
      }
    }
  }

  String _wsUri() {
    final http = baseUrl.replaceAll(RegExp(r'/$'), '');
    final ws = http.startsWith('https://')
        ? 'wss://${http.substring(8)}'
        : http.startsWith('http://')
            ? 'ws://${http.substring(7)}'
            : 'ws://$http';
    return '$ws$wsPath';
  }

  void _open() {
    final token = getToken();
    if (token == null || token.isEmpty) {
      _setState(ConnectionState.error);
      _scheduleReconnect();
      return;
    }

    _setState(_reconnectAttempts > 0
        ? ConnectionState.reconnecting
        : ConnectionState.connecting);

    try {
      final uri = Uri.parse(_wsUri());
      final channel = channelFactory(
        uri,
        headers: {'Authorization': 'Bearer $token'},
      );
      _channel = channel;
      _setState(ConnectionState.authenticating);

      _subscription = channel.stream.listen(
        (raw) => _onMessage(raw),
        onError: (_) => _onDrop(),
        onDone: () => _onDrop(),
        cancelOnError: false,
      );
    } catch (_) {
      _onDrop();
    }
  }

  void _onMessage(dynamic raw) {
    late final Map<String, dynamic> data;
    try {
      data = jsonDecode(raw as String) as Map<String, dynamic>;
    } catch (_) {
      return;
    }
    // EventEnvelope.fromJson 对非法字段类型（如 type 为 int/object/array）抛出
    // FormatException。捕获后视为 malformed event 静默忽略，不让异常逃逸到 stream
    // zone（DEFECT-001 修复）。仅捕获 FormatException，不吞掉其他未知异常。
    final EventEnvelope evt;
    try {
      evt = EventEnvelope.fromJson(data);
    } on FormatException {
      return;
    }
    onEvent?.call(evt);
    for (final l in List<void Function(EventEnvelope)>.of(_eventListeners)) {
      l(evt);
    }

    switch (evt.type) {
      case 'connection.ready':
        _currentConnId = evt.payload['connection_id'] as String?;
        _reconnectAttempts = 0;
        _setState(ConnectionState.connected);
      case 'connection.error':
        if (evt.payload['code'] == 'WS_AUTH_FAILED') {
          _onAuthFailed();
        }
      case 'connection.ping':
        send(EventEnvelope.pong());
    }
  }

  void _onAuthFailed() {
    _subscription?.cancel();
    _channel?.sink.close();
    _channel = null;
    _tryRefreshThenReconnect();
  }

  void _onDrop() {
    _subscription?.cancel();
    _channel?.sink.close();
    _channel = null;
    _currentConnId = null;
    if (!_running) {
      _setState(ConnectionState.disconnected);
      return;
    }
    _setState(ConnectionState.disconnected);
    _scheduleReconnect();
  }

  Future<void> _tryRefreshThenReconnect() async {
    final ok = await onTokenExpired();
    if (!ok) {
      _setState(ConnectionState.error);
      _scheduleReconnect();
      return;
    }
    _open();
  }

  void _scheduleReconnect() {
    if (!_running) return;
    final delay = _backoff();
    _reconnectTimer?.cancel();
    _reconnectTimer = Timer(Duration(seconds: delay), () {
      if (_running) _open();
    });
  }

  int _backoff() {
    final i = _reconnectAttempts;
    final delay = i < _backoffSchedule.length
        ? _backoffSchedule[i]
        : _backoffSchedule.last;
    _reconnectAttempts++;
    return delay;
  }
}
