/// Friendship — backend `FriendPublic` (API_CONTRACT §3 GET /friends).
///
/// Represents an accepted, bidirectional relationship. The `user` field is
/// the *friend* (not me). `friendshipCreatedAt` is when the bond was formed.
import 'user_summary.dart';

class Friendship {
  const Friendship({
    required this.user,
    this.friendshipCreatedAt,
  });

  final UserSummary user;
  final DateTime? friendshipCreatedAt;

  factory Friendship.fromJson(Map<String, dynamic> json) {
    final userRaw = json['user'] as Map<String, dynamic>? ?? {};
    return Friendship(
      user: UserSummary.fromJson(userRaw),
      friendshipCreatedAt: json['friendship_created_at'] == null
          ? null
          : DateTime.tryParse(json['friendship_created_at'] as String),
    );
  }

  Map<String, dynamic> toJson() => {
        'user': user.toJson(),
        if (friendshipCreatedAt != null)
          'friendship_created_at': friendshipCreatedAt!.toIso8601String(),
      };
}
