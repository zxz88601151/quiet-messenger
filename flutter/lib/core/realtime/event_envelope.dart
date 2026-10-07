/// Unified WebSocket event envelope (Flutter / Phase 3C).
///
/// Matches backend make_event():
/// `{ "type": str, "id": str, "timestamp": str, "payload": dict }`
///
/// Server→Client (Phase 3C): connection.authenticated / connection.ready /
///   connection.ping / connection.error
/// Client→Server: connection.auth / connection.pong / connection.close
///
/// Only infrastructure events are modeled. Business events (message.* /
/// friend.* / conversation.* / handoff.*) are NOT defined here — they belong
/// to later phases.
class EventEnvelope {
  const EventEnvelope({
    required this.type,
    this.id = '',
    this.timestamp = '',
    this.payload = const <String, dynamic>{},
  });

  final String type;
  final String id;
  final String timestamp;
  final Map<String, dynamic> payload;

  factory EventEnvelope.fromJson(Map<String, dynamic> data) {
    final dynamic type = data['type'];
    final dynamic id = data['id'];
    final dynamic timestamp = data['timestamp'];
    final dynamic payload = data['payload'];

    // 全字段类型安全检查（DEFECT-001/002/003）：
    // 字段为 null（缺失）时兼容默认值，与既有行为一致；
    // 非 null 且类型不匹配时视为 malformed envelope，抛出 FormatException
    // 由调用方（RealtimeClient._onMessage）捕获并静默忽略。
    // 原 as String? / as Map? 对非匹配类型抛出未捕获 TypeError。
    if (type != null && type is! String) {
      throw FormatException(
        'EventEnvelope.type must be a String or null, got ${type.runtimeType}',
      );
    }
    if (id != null && id is! String) {
      throw FormatException(
        'EventEnvelope.id must be a String or null, got ${id.runtimeType}',
      );
    }
    if (timestamp != null && timestamp is! String) {
      throw FormatException(
        'EventEnvelope.timestamp must be a String or null, got ${timestamp.runtimeType}',
      );
    }
    if (payload != null && payload is! Map<String, dynamic>) {
      throw FormatException(
        'EventEnvelope.payload must be a Map or null, got ${payload.runtimeType}',
      );
    }

    return EventEnvelope(
      type: type as String? ?? '',
      id: id as String? ?? '',
      timestamp: timestamp as String? ?? '',
      payload: payload as Map<String, dynamic>? ?? <String, dynamic>{},
    );
  }

  static Map<String, dynamic> pong() => const {'type': 'connection.pong'};
  static Map<String, dynamic> close() => const {'type': 'connection.close'};
}
