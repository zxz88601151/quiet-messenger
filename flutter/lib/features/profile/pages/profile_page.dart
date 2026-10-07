/// Profile — real current user data (UI Functional Recovery).
///
/// Reads the authenticated user from [AuthNotifier.currentUser] (populated
/// from login/register response or restore via GET /users/me). Supports
/// nickname edit via PATCH /users/me and navigation to devices/privacy.
///
/// V1.1 scope: nickname, username, avatar display, edit nickname, privacy
/// settings entry, devices entry. No QR (V1.2 POSTPONE).
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';

import '../../../app/theme/colors.dart';
import '../../../app/theme/typography.dart';
import '../../auth/auth_notifier.dart';
import '../../auth/models/user.dart';
import '../repositories/user_repository.dart';

class ProfilePage extends StatefulWidget {
  const ProfilePage({super.key});

  @override
  State<ProfilePage> createState() => _ProfilePageState();
}

class _ProfilePageState extends State<ProfilePage> {
  bool _saving = false;

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthNotifier>();
    final user = auth.currentUser;

    return Scaffold(
      appBar: AppBar(title: const Text('个人资料')),
      body: _buildBody(auth, user),
    );
  }

  Widget _buildBody(AuthNotifier auth, User? user) {
    if (auth.loading && user == null) {
      return const Center(child: CircularProgressIndicator());
    }
    if (user == null) {
      return Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Text('未登录', style: AppTypography.subtitle),
            const SizedBox(height: 12),
            ElevatedButton(
              onPressed: () => context.go('/login'),
              child: const Text('去登录'),
            ),
          ],
        ),
      );
    }

    final displayName =
        user.nickname.isNotEmpty ? user.nickname : user.username;
    final initial =
        displayName.isNotEmpty ? displayName[0].toUpperCase() : '?';

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Center(
          child: CircleAvatar(
            radius: 36,
            backgroundColor: AppColors.primaryLight,
            backgroundImage: user.avatar != null && user.avatar!.isNotEmpty
                ? NetworkImage(user.avatar!)
                : null,
            child: user.avatar != null && user.avatar!.isNotEmpty
                ? null
                : Text(initial,
                    style: const TextStyle(
                        fontSize: 28, color: AppColors.primary)),
          ),
        ),
        const SizedBox(height: 12),
        Center(child: Text(displayName, style: AppTypography.title)),
        Center(child: Text('@${user.username}', style: AppTypography.caption)),
        const SizedBox(height: 8),
        Center(
          child: Text('ID: ${user.id}',
              style: const TextStyle(fontSize: 11, color: AppColors.text3)),
        ),
        const SizedBox(height: 16),
        const Divider(height: 1),
        ListTile(
          leading: const Icon(Icons.edit_outlined),
          title: const Text('编辑昵称'),
          subtitle: Text(user.nickname,
              style: const TextStyle(fontSize: 12, color: AppColors.text2)),
          trailing: _saving
              ? const SizedBox(
                  width: 16,
                  height: 16,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : const Icon(Icons.chevron_right, color: AppColors.text3),
          onTap: _saving ? null : () => _showEditNicknameDialog(user),
        ),
        ListTile(
          leading: const Icon(Icons.lock_outline),
          title: const Text('隐私设置'),
          trailing: const Icon(Icons.chevron_right, color: AppColors.text3),
          onTap: () => context.push('/privacy'),
        ),
        ListTile(
          leading: const Icon(Icons.devices_outlined),
          title: const Text('登录设备'),
          trailing: const Icon(Icons.chevron_right, color: AppColors.text3),
          onTap: () => context.push('/devices'),
        ),
        const Divider(height: 1),
        ListTile(
          leading: const Icon(Icons.logout, color: AppColors.error),
          title: const Text('退出登录',
              style: TextStyle(color: AppColors.error)),
          onTap: () => _showLogoutConfirm(),
        ),
      ],
    );
  }

  Future<void> _showLogoutConfirm() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('退出登录'),
        content: const Text('确定要退出当前账号吗？'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext, false),
            child: const Text('取消'),
          ),
          ElevatedButton(
            style: ElevatedButton.styleFrom(backgroundColor: AppColors.error),
            onPressed: () => Navigator.pop(dialogContext, true),
            child: const Text('退出'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    final auth = context.read<AuthNotifier>();
    await auth.logout();
    if (mounted) context.go('/login');
  }

  Future<void> _showEditNicknameDialog(User user) async {
    final controller = TextEditingController(text: user.nickname);
    final result = await showDialog<String>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('编辑昵称'),
        content: TextField(
          controller: controller,
          autofocus: true,
          maxLength: 30,
          decoration: const InputDecoration(
            hintText: '输入新昵称',
            border: OutlineInputBorder(),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext),
            child: const Text('取消'),
          ),
          ElevatedButton(
            onPressed: () {
              final v = controller.text.trim();
              if (v.isNotEmpty) Navigator.pop(dialogContext, v);
            },
            child: const Text('保存'),
          ),
        ],
      ),
    );

    if (result == null || result.isEmpty || result == user.nickname) return;

    setState(() => _saving = true);
    try {
      final repo = context.read<UserRepository>();
      final updated = await repo.patchMe({'nickname': result});
      if (mounted) {
        context.read<AuthNotifier>().updateCurrentUser(updated);
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('昵称已更新')),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('更新失败: ${e.toString().split('\n').first}'),
            backgroundColor: AppColors.error,
          ),
        );
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }
}
