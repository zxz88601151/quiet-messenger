/// App router — declarative navigation with auth-state redirects.
///
/// Phase 3B: the router now reacts to [AuthNotifier] state:
/// - [AuthState.unknown]    : mid-restore, no redirect yet
/// - [AuthState.unauthenticated] : force /login (and its sub-routes)
/// - [AuthState.authenticated]   : force the home shell (/chat)
/// - [AuthState.loading]    : no redirect
///
/// QR / Desktop login (M13/M14, D1–D3) remains PHASE 6 (POSTPONE) and is
/// intentionally NOT wired.
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../features/auth/auth_notifier.dart';
import '../features/auth/models/auth_state.dart';
import '../features/auth/pages/login_page.dart';
import '../features/auth/pages/register_page.dart';
import '../features/auth/pages/forgot_password_page.dart';
import '../features/chat/pages/chat_list_page.dart';
import '../features/chat/pages/chat_page.dart';
import '../features/friends/pages/friends_page.dart';
import '../features/friends/pages/friend_requests_page.dart';
import '../features/friends/pages/add_friend_page.dart';
import '../features/devices/pages/devices_page.dart';
import '../features/profile/pages/profile_page.dart';
import '../features/profile/pages/privacy_settings_page.dart';

/// Auth route paths (no shell).
const List<String> _authPaths = ['/login', '/register', '/forgot'];

GoRouter makeRouter(AuthNotifier auth) => GoRouter(
      initialLocation: '/login',
      refreshListenable: auth,
      redirect: (context, state) {
        final status = auth.status;
        final loc = state.matchedLocation;
        final onAuthRoute = _authPaths.contains(loc);

        if (status == AuthState.unauthenticated && !onAuthRoute) {
          return '/login';
        }
        if (status == AuthState.authenticated && onAuthRoute) {
          return '/chat';
        }
        return null;
      },
      routes: [
        GoRoute(path: '/login', builder: (_, __) => const LoginPage()),
        GoRoute(path: '/register', builder: (_, __) => const RegisterPage()),
        GoRoute(
          path: '/forgot',
          builder: (_, __) => const ForgotPasswordPage(),
        ),
        ShellRoute(
          builder: (context, state, child) => _AppShell(child: child),
          routes: [
            GoRoute(path: '/chat', builder: (_, __) => const ChatListPage()),
            GoRoute(
              path: '/chat/:id',
              builder: (_, state) =>
                  ChatPage(conversationId: state.pathParameters['id']),
            ),
            GoRoute(path: '/friends', builder: (_, __) => const FriendsPage()),
            GoRoute(
              path: '/friends/requests',
              builder: (_, __) => const FriendRequestsPage(),
            ),
            GoRoute(
              path: '/friends/add',
              builder: (_, __) => const AddFriendPage(),
            ),
            GoRoute(path: '/devices', builder: (_, __) => const DevicesPage()),
            GoRoute(path: '/profile', builder: (_, __) => const ProfilePage()),
            GoRoute(
              path: '/privacy',
              builder: (_, __) => const PrivacySettingsPage(),
            ),
          ],
        ),
      ],
    );

class _AppShell extends StatelessWidget {
  const _AppShell({required this.child});
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: child,
      bottomNavigationBar: NavigationBar(
        destinations: const [
          NavigationDestination(icon: Icon(Icons.chat_bubble_outline), label: '聊天'),
          NavigationDestination(icon: Icon(Icons.people_outline), label: '好友'),
          NavigationDestination(icon: Icon(Icons.person_outline), label: '我的'),
        ],
        onDestinationSelected: (i) {
          const paths = ['/chat', '/friends', '/profile'];
          // Tapping "我的" goes to profile; logout is on the settings page.
          context.go(paths[i]);
        },
      ),
    );
  }
}
