/// Realtime connection states (Flutter / Phase 3C).
///
/// Mirrors the backend ConnectionState enum. Client-only view adds
/// [reconnecting] (client-driven exponential backoff) which the server
/// does not track.
enum ConnectionState {
  disconnected,
  connecting,
  authenticating,
  connected,
  reconnecting,
  error;

  bool get isConnected => this == ConnectionState.connected;
}
