/// Device domain model — backend DevicePublic (API_CONTRACT §5).
///
/// Fields: id, device_type, device_name, device_identifier, last_active_at,
/// created_at, revoked_at, is_current (added by the GET /devices endpoint).
class Device {
  const Device({
    required this.id,
    required this.deviceType,
    this.deviceName,
    this.deviceIdentifier,
    this.lastActiveAt,
    this.createdAt,
    this.revokedAt,
    this.isCurrent = false,
  });

  final String id;
  final String deviceType;
  final String? deviceName;
  final String? deviceIdentifier;
  final DateTime? lastActiveAt;
  final DateTime? createdAt;
  final DateTime? revokedAt;
  final bool isCurrent;

  bool get isRevoked => revokedAt != null;

  String get displayName =>
      deviceName != null && deviceName!.isNotEmpty
          ? deviceName!
          : deviceType;

  factory Device.fromJson(Map<String, dynamic> json) {
    return Device(
      id: json['id'] as String,
      deviceType: json['device_type'] as String? ?? 'unknown',
      deviceName: json['device_name'] as String?,
      deviceIdentifier: json['device_identifier'] as String?,
      lastActiveAt: json['last_active_at'] == null
          ? null
          : DateTime.tryParse(json['last_active_at'] as String),
      createdAt: json['created_at'] == null
          ? null
          : DateTime.tryParse(json['created_at'] as String),
      revokedAt: json['revoked_at'] == null
          ? null
          : DateTime.tryParse(json['revoked_at'] as String),
      isCurrent: json['is_current'] == true,
    );
  }

  Map<String, dynamic> toJson() => {
        'id': id,
        'device_type': deviceType,
        if (deviceName != null) 'device_name': deviceName,
        if (deviceIdentifier != null) 'device_identifier': deviceIdentifier,
        if (lastActiveAt != null)
          'last_active_at': lastActiveAt!.toIso8601String(),
        if (createdAt != null) 'created_at': createdAt!.toIso8601String(),
        if (revokedAt != null) 'revoked_at': revokedAt!.toIso8601String(),
        'is_current': isCurrent,
      };
}
