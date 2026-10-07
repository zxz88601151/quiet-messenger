/// User/Profile repository — REAL API implementation (UI Functional Recovery).
///
/// Wires GET /users/me and PATCH /users/me to the existing [ApiClient] (Dio).
/// Endpoints follow shared/API_CONTRACT.md §2. PATCH is merge-patch: only
/// submitted fields are updated, unsubmitted keys retain their server value.
///
/// Layering: UI → Notifier → UserRepository → ApiClient → Backend.
import '../../../core/api/api_client.dart';
import '../../auth/models/user.dart';

abstract class UserRepository {
  /// GET /users/me — current user with full privacy_settings (5 keys).
  Future<User> me();

  /// PATCH /users/me — merge patch. Keys: nickname, avatar, bio, privacy_settings.
  Future<User> patchMe(Map<String, dynamic> patch);
}

class ApiUserRepository implements UserRepository {
  const ApiUserRepository(this._client);

  final ApiClient _client;

  @override
  Future<User> me() async {
    final resp = await _client.get('/users/me');
    return User.fromJson(resp.data as Map<String, dynamic>);
  }

  @override
  Future<User> patchMe(Map<String, dynamic> patch) async {
    final resp = await _client.patch('/users/me', data: patch);
    return User.fromJson(resp.data as Map<String, dynamic>);
  }
}
