/// Friend request — backend `FriendRequestPublic` (API_CONTRACT §3).
///
/// Carries the request id, the pair (sender/receiver), status, and the
/// *other party's* user summary (sender or receiver, whichever is not me).
import 'user_summary.dart';

class FriendRequest {
  const FriendRequest({
    required this.id,
    required this.senderId,
    required this.receiverId,
    required this.status,
    required this.isIncoming,
    this.otherUser,
    this.createdAt,
    this.updatedAt,
  });

  final String id;
  final String senderId;
  final String receiverId;
  final String status;
  final bool isIncoming;
  final UserSummary? otherUser;
  final DateTime? createdAt;
  final DateTime? updatedAt;

  /// [viewerId] is the current user — used to pick the "other" side to show
  /// and to decide whether this is an incoming (needs Accept/Reject) request.
  factory FriendRequest.fromJson(Map<String, dynamic> json, String viewerId) {
    final sender = json['sender'] as Map<String, dynamic>?;
    final receiver = json['receiver'] as Map<String, dynamic>?;
    final otherRaw = sender != null && sender['id'] != viewerId ? sender : receiver;
    final otherUser =
        otherRaw != null ? UserSummary.fromJson(otherRaw) : null;

    final isIncoming = json['receiver_id'] == viewerId;

    return FriendRequest(
      id: json['id'] as String,
      senderId: json['sender_id'] as String,
      receiverId: json['receiver_id'] as String,
      status: json['status'] as String,
      isIncoming: isIncoming,
      otherUser: otherUser,
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
        'sender_id': senderId,
        'receiver_id': receiverId,
        'status': status,
        'is_incoming': isIncoming,
        if (otherUser != null) 'other_user': otherUser!.toJson(),
        if (createdAt != null) 'created_at': createdAt!.toIso8601String(),
        if (updatedAt != null) 'updated_at': updatedAt!.toIso8601String(),
      };
}
