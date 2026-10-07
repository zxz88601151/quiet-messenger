/// User search result summary — only public, privacy-safe fields.
///
/// Backend `UserSearchItem` (shared/API_CONTRACT.md §2 GET /users/search).
/// Does NOT carry password / phone / tokens / device_id / internal metadata.
class UserSummary {
  const UserSummary({
    required this.id,
    required this.username,
    required this.nickname,
    this.avatar,
  });

  final String id;
  final String username;
  final String nickname;
  final String? avatar;

  /// Parse from backend JSON. Tolerates missing optional fields.
  factory UserSummary.fromJson(Map<String, dynamic> json) {
    return UserSummary(
      id: json['id'] as String,
      username: json['username'] as String,
      nickname: json['nickname'] as String,
      avatar: json['avatar'] as String?,
    );
  }

  Map<String, dynamic> toJson() => {
        'id': id,
        'username': username,
        'nickname': nickname,
        if (avatar != null) 'avatar': avatar,
      };
}
