/// Device repository — REAL API implementation (UI Functional Recovery).
///
/// Wires GET /devices and DELETE /devices/{id} to the existing [ApiClient].
/// Endpoints follow shared/API_CONTRACT.md §5. Removing a device revokes its
/// RefreshToken + sets revoked_at on the backend (the device loses access).
///
/// Layering: UI → DeviceNotifier → DeviceRepository → ApiClient → Backend.
import '../../../core/api/api_client.dart';
import '../models/device.dart';

abstract class DeviceRepository {
  /// GET /devices — list all devices for current user, newest first.
  Future<List<Device>> list();

  /// DELETE /devices/{id} — revoke a device (its refresh token + access).
  Future<void> revoke(String deviceId);
}

class ApiDeviceRepository implements DeviceRepository {
  const ApiDeviceRepository(this._client);

  final ApiClient _client;

  @override
  Future<List<Device>> list() async {
    final resp = await _client.get('/devices');
    final list = (resp.data as List?) ?? [];
    return list
        .map((e) => Device.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  @override
  Future<void> revoke(String deviceId) async {
    await _client.delete('/devices/$deviceId');
  }
}
