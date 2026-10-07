/// Settings — navigation entries + logout (UI Functional Recovery).
///
/// V1.1 scope: profile entry, devices entry, about (placeholder), logout.
/// No Dark Mode (POSTPONE), no shortcut settings (POSTPONE).
/// Logout is the only auth action here — clears tokens + redirects to login.
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';

import '../../../app/theme/colors.dart';
import '../../../app/theme/typography.dart';
import '../../auth/auth_notifier.dart';

class SettingsPage extends StatelessWidget {
  const SettingsPage({super.key});

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthNotifier>();

    return Scaffold(
      appBar: AppBar(title: const Text('设置')),
      body: ListView(
        children: [
          _Entry(
            icon: Icons.person_outline,
            label: '个人资料',
            onTap: () => context.push('/profile'),
          ),
          _Entry(
            icon: Icons.devices_outlined,
            label: '登录设备',
            onTap: () => context.push('/devices'),
          ),
          const _Entry(icon: Icons.info_outline, label: '关于'),
          const Divider(height: 1),
          ListTile(
            leading: const Icon(Icons.logout, color: AppColors.error),
            title: Text(
              '退出登录',
              style: AppTypography.label.copyWith(color: AppColors.error),
            ),
            onTap: auth.loading
                ? null
                : () async {
                    await auth.logout();
                    if (context.mounted) context.go('/login');
                  },
          ),
        ],
      ),
    );
  }
}

class _Entry extends StatelessWidget {
  const _Entry({required this.icon, required this.label, this.onTap});
  final IconData icon;
  final String label;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return ListTile(
      leading: Icon(icon),
      title: Text(label, style: AppTypography.label),
      trailing: const Icon(Icons.chevron_right, color: AppColors.text3),
      onTap: onTap,
    );
  }
}
