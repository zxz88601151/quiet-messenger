/// Conversation domain model (V1.1, DIRECT only).
///
/// Backend `ConversationPublic` (API_CONTRACT §4). V1.1 implements only the
/// DIRECT (one-to-one) type — no GROUP / CHANNEL / COMMUNITY / BROADCAST.
import '../../friends/models/user_summary.dart';

enum ConversationType {
  direct,
  group,
  channel,
  community,
  broadcast,
}

class Conversation {
  const Conversation({
    required this.id,
    required this.type,
    required this.peer,
    this.lastMessagePreview,
    this.unreadCount = 0,
    this.createdAt,
    this.updatedAt,
  });

  final String id;
  final ConversationType type;
  final UserSummary peer;
  final String? lastMessagePreview;
  final int unreadCount;
  final DateTime? createdAt;
  final DateTime? updatedAt;

  /// Parse from backend JSON. `last_message` is optional and only the
  /// backend-owned preview field is shown — we do NOT implement message flow.
  factory Conversation.fromJson(Map<String, dynamic> json) {
    final peerRaw = json['peer'] as Map<String, dynamic>? ?? {};
    final last = json['last_message'] as Map<String, dynamic>?;
    return Conversation(
      id: json['id'] as String,
      type: ConversationType.direct,
      peer: UserSummary.fromJson(peerRaw),
      lastMessagePreview: last?['content'] as String?,
      unreadCount: (json['unread_count'] as int?) ?? 0,
      createdAt: json['created_at'] == null
          ? null
          : DateTime.tryParse(json['created_at'] as String),
      updatedAt: json['updated_at'] == null
          ? null
          : DateTime.tryParse(json['updated_at'] as String),
    );
  }

  Map<String, dynamic> toJson() => {
        'id': id,
        'type': type.name,
        'peer': peer.toJson(),
        if (lastMessagePreview != null) 'last_message_preview': lastMessagePreview,
        'unread_count': unreadCount,
        if (createdAt != null) 'created_at': createdAt!.toIso8601String(),
        if (updatedAt != null) 'updated_at': updatedAt!.toIso8601String(),
      };
}
