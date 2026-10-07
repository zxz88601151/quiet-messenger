/// App root — composes theme, providers, and router.
///
/// Phase 3B: wires [AuthNotifier] (ChangeNotifier) so auth state drives
/// routing. [AuthRepository] is the real implementation (no stub). On app
/// start we call [AuthNotifier.restore] to recover a session from secure
/// storage before the router decides the initial route.
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'router.dart';
import 'theme/app_theme.dart';
import '../core/api/api_client.dart';
import '../core/api/api_config.dart';
import '../core/storage/token_storage.dart';
import '../features/auth/auth_notifier.dart';
import '../features/auth/models/auth_state.dart';
import '../features/auth/repositories/auth_repository.dart';
import '../features/chat/repositories/conversation_repository.dart';
import '../features/chat/repositories/message_repository.dart';
import '../features/friends/repositories/friend_repository.dart';
import '../features/friends/friend_notifier.dart';
import '../features/presence/presence_notifier.dart';
import '../core/realtime/realtime_client.dart';
// ApiFriendRepository / ApiConversationRepository are the concrete types.
import '../features/devices/repositories/device_repository.dart';
import '../features/profile/repositories/user_repository.dart';

class App extends StatefulWidget {
  const App({super.key});

  @override
  State<App> createState() => _AppState();
}

class _AppState extends State<App> {
  late final ApiClient _api;
  late final TokenStorage _tokenStorage;
  late final AuthRepository _authRepo;
  late final AuthNotifier _auth;
  late final RealtimeClient _realtime;
  late final PresenceNotifier _presence;
  // Access token loaded async from secure storage; read by the synchronous
  // getToken() closure (RealtimeClient.getToken is String? Function()).
  String? _accessToken;

  @override
  void initState() {
    super.initState();
    // Single-direction init order: tokenStorage → api → authRepo → auth →
    // realtime. (Phase 1 fix: _api was previously used before assignment —
    // late final read-before-assign crash; and _realtime must exist before
    // build() runs synchronously on the first frame.)
    _tokenStorage = const TokenStorage();
    // ApiClient gets a 401→refresh hook wired to the auth layer. The closure
    // defers to [_auth] which is created below. Phase 3B §11 retry guard.
    _api = ApiClient(
      tokenStorage: _tokenStorage,
      onUnauthorized: () => _auth.handleUnauthorized(),
    );
    _authRepo = AuthRepository(_api, _tokenStorage);
    _auth = AuthNotifier(_authRepo);
    // Realtime client (Phase 3C): global singleton, Bearer-auth WebSocket.
    // Created synchronously so it is available in build(); the token is read
    // via a closure over [_accessToken], which is populated async below.
    // NOTE: baseUrl uses ApiConfig.baseUrl (NO /api/v1 prefix) because the
    // backend WebSocket route is /ws/v1 (mounted outside the REST /api/v1
    // prefix). Using apiBaseUrl would produce /api/v1/ws/v1 → 403.
    _realtime = RealtimeClient(
      baseUrl: ApiConfig.baseUrl,
      getToken: () => _accessToken,
      onTokenExpired: () => _auth.handleUnauthorized(),
      onEvent: (_) {}, // message events are routed per-conversation by ChatPage.
    );
    // PresenceNotifier: tracks friend online/offline via WS, plays online.mp3
    // on genuine offline→online transitions. currentUserId updated on auth change.
    _presence = PresenceNotifier(_realtime);
    // DEF-RT-003: Logout must close WebSocket; re-login must open a new one.
    // Listen to auth state transitions and drive realtime lifecycle accordingly.
    _auth.addListener(_onAuthStateChanged);
    _loadTokenAndConnect();
    // Restore session on startup (drives router initial redirect).
    _auth.restore();
  }

  /// Loads the access token (async) then connects the realtime client. Kept
  /// separate so the await happens before connect() — no sync-over-async hack.
  Future<void> _loadTokenAndConnect() async {
    _accessToken = await _tokenStorage.getAccessToken();
    _realtime.connect();
  }

  /// DEF-RT-003: Drive RealtimeClient lifecycle from AuthNotifier state.
  /// - Logout (unauthenticated): disconnect WS, cancel reconnect timers.
  /// - Re-login (authenticated): reload token and open a NEW WS connection.
  void _onAuthStateChanged() {
    if (_auth.status == AuthState.unauthenticated) {
      _realtime.disconnect();
      _accessToken = null;
      _presence.currentUserId = null;
    } else if (_auth.status == AuthState.authenticated) {
      // Reload token from storage (login writes it there) then connect.
      _tokenStorage.getAccessToken().then((token) {
        _accessToken = token;
        _realtime.connect();
      });
      _presence.currentUserId = _auth.currentUser?.id;
    }
  }

  @override
  void dispose() {
    _auth.removeListener(_onAuthStateChanged);
    _presence.dispose();
    _realtime.disconnect();
    _auth.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return MultiProvider(
      providers: [
        Provider<ApiClient>.value(value: _api),
        Provider<TokenStorage>.value(value: _tokenStorage),
        ChangeNotifierProvider<AuthNotifier>.value(value: _auth),
        Provider<AuthRepository>.value(value: _authRepo),
        // Phase 3D: real implementations. FriendRepository needs the current
        // user id (for request direction) — derived from the restored session.
        ProxyProvider2<ApiClient, AuthNotifier, FriendRepository>(
          update: (_, api, auth, __) => ApiFriendRepository(
            api,
            auth.currentUser?.id ?? '',
          ),
        ),
        // RealtimeClient must be available before FriendNotifier (which
        // subscribes to friend.request.created WS events for real-time updates).
        Provider<RealtimeClient>.value(value: _realtime),
        // PresenceNotifier tracks friend online/offline state via WS presence.update.
        ChangeNotifierProvider<PresenceNotifier>.value(value: _presence),
        // FriendNotifier depends on FriendRepository (which depends on currentUser).
        // On auth change we update the repo without resetting friend state.
        ChangeNotifierProxyProvider<FriendRepository, FriendNotifier>(
          create: (context) {
            final notifier = FriendNotifier(context.read<FriendRepository>());
            notifier.subscribeRealtime(context.read<RealtimeClient>());
            return notifier;
          },
          update: (context, repo, previous) {
            if (previous != null) {
              previous.updateRepository(repo);
              previous.subscribeRealtime(context.read<RealtimeClient>());
              return previous;
            }
            final notifier = FriendNotifier(repo);
            notifier.subscribeRealtime(context.read<RealtimeClient>());
            return notifier;
          },
        ),
        ProxyProvider<ApiClient, ConversationRepository>(
          update: (_, api, __) => ApiConversationRepository(api),
        ),
        ProxyProvider<ApiClient, MessageRepository>(
          update: (_, api, __) => ApiMessageRepository(api),
        ),
        Provider<DeviceRepository>(
          create: (_) => ApiDeviceRepository(_api),
        ),
        Provider<UserRepository>(
          create: (_) => ApiUserRepository(_api),
        ),
      ],
      child: MaterialApp.router(
        title: '极简私人通讯',
        theme: AppTheme.light,
        routerConfig: makeRouter(_auth),
        debugShowCheckedModeBanner: false,
      ),
    );
  }
}
