/// Message domain model (Phase 3E).
///
/// Minimal DIRECT message. Matches backend `MessagePublic` (API_CONTRACT §4).
/// Fields: id / conversation_id / sender_id / client_message_id / content /
/// created_at. No status/typing/read-receipt/edit/recall — those are out of
/// scope (Phase 3E authorization §3).
///
/// Client-only UI state ([uiState]) is NOT persisted; it tracks sending/sent/
/// failed for the local composer feedback only.
enum MessageUiState {
  sending,
  sent,
  failed,
}

class Message {
  const Message({
    required this.id,
    required this.conversationId,
    required this.senderId,
    required this.content,
    this.clientMessageId,
    this.createdAt,
    this.uiState = MessageUiState.sent,
  });

  final String id;
  final String conversationId;
  final String senderId;
  final String content;
  final String? clientMessageId;
  final DateTime? createdAt;

  /// Local-only UI state for the sender's own pending message.
  final MessageUiState uiState;

  /// Ownership attribution. The ONLY correct rule is
  /// `sender_id == current_user_id`. `clientMessageId` is an idempotency key
  /// returned by the backend for BOTH peers and MUST NOT be used for
  /// attribution. The prior `isMine => clientMessageId != null` getter was
  /// wrong and rendered every received message as "mine" (Phase 3F fix).
  bool isOwnMessage(String currentUserId) => senderId == currentUserId;

  factory Message.fromJson(Map<String, dynamic> json, {String? currentUserId}) {
    final senderId = json['sender_id'] as String? ?? '';
    return Message(
      id: json['id'] as String,
      conversationId: json['conversation_id'] as String,
      senderId: senderId,
      content: json['content'] as String,
      clientMessageId: json['client_message_id'] as String?,
      createdAt: json['created_at'] == null
          ? null
          : DateTime.tryParse(json['created_at'] as String),
      // A message coming from REST/WS is always confirmed.
      uiState: MessageUiState.sent,
    );
  }

  /// Build a local optimistic message before the server confirms it.
  factory Message.optimistic({
    required String conversationId,
    required String senderId,
    required String content,
    required String clientMessageId,
  }) =>
      Message(
        id: clientMessageId,
        conversationId: conversationId,
        senderId: senderId,
        content: content,
        clientMessageId: clientMessageId,
        createdAt: DateTime.now(),
        uiState: MessageUiState.sending,
      );

  Message copyWith({MessageUiState? uiState, String? id}) => Message(
        id: id ?? this.id,
        conversationId: conversationId,
        senderId: senderId,
        content: content,
        clientMessageId: clientMessageId,
        createdAt: createdAt,
        uiState: uiState ?? this.uiState,
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'conversation_id': conversationId,
        'sender_id': senderId,
        'content': content,
        if (clientMessageId != null) 'client_message_id': clientMessageId,
        if (createdAt != null) 'created_at': createdAt!.toIso8601String(),
      };
}
