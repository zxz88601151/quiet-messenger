/// Auth domain model — User.
///
/// Maps the backend `UserPublic` (shared/API_CONTRACT.md §2 GET /users/me).
/// Only fields needed by Phase 3B (auth/session) are modeled; no friend /
/// message / presence fields are added (Scope discipline).
class User {
  const User({
    required this.id,
    required this.username,
    required this.phone,
    required this.nickname,
    this.avatar,
    this.bio,
    this.privacySettings = const {},
    this.createdAt,
  });

  final String id;
  final String username;
  final String phone;
  final String nickname;
  final String? avatar;
  final String? bio;
  /// V1.1 privacy settings (5 keys). Default empty = backend defaults apply.
  final Map<String, dynamic> privacySettings;
  final DateTime? createdAt;

  /// Parse from backend JSON. Tolerates missing optional fields.
  factory User.fromJson(Map<String, dynamic> json) {
    return User(
      id: json['id'] as String,
      username: json['username'] as String,
      phone: json['phone'] as String,
      nickname: json['nickname'] as String,
      avatar: json['avatar'] as String?,
      bio: json['bio'] as String?,
      privacySettings:
          (json['privacy_settings'] as Map<String, dynamic>?) ?? const {},
      createdAt: json['created_at'] == null
          ? null
          : DateTime.tryParse(json['created_at'] as String),
    );
  }

  User copyWith({
    String? nickname,
    String? avatar,
    String? bio,
    Map<String, dynamic>? privacySettings,
  }) {
    return User(
      id: id,
      username: username,
      phone: phone,
      nickname: nickname ?? this.nickname,
      avatar: avatar ?? this.avatar,
      bio: bio ?? this.bio,
      privacySettings: privacySettings ?? this.privacySettings,
      createdAt: createdAt,
    );
  }

  Map<String, dynamic> toJson() => {
        'id': id,
        'username': username,
        'phone': phone,
        'nickname': nickname,
        if (avatar != null) 'avatar': avatar,
        if (bio != null) 'bio': bio,
        'privacy_settings': privacySettings,
        if (createdAt != null) 'created_at': createdAt!.toIso8601String(),
      };
}
