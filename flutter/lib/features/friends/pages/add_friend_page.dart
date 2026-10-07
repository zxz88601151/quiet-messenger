/// Add Friend — real search + request (Phase 3D).
///
/// Per V1.1_SCOPE, add-by is 手机号/用户ID only (扫码加好友 is V1.2 POSTPONE).
/// The prototype's "可能认识的人" section was already removed in Phase 1.
/// Driven by [FriendNotifier]; UI never touches ApiClient directly.
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../../app/theme/colors.dart';
import '../../../app/theme/typography.dart';
import '../friend_notifier.dart';
import '../models/user_summary.dart';

class AddFriendPage extends StatefulWidget {
  const AddFriendPage({super.key});

  @override
  State<AddFriendPage> createState() => _AddFriendPageState();
}

class _AddFriendPageState extends State<AddFriendPage> {
  final _controller = TextEditingController();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final notifier = context.watch<FriendNotifier>();
    return Scaffold(
      appBar: AppBar(title: const Text('添加好友')),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          children: [
            TextField(
              controller: _controller,
              decoration: const InputDecoration(
                labelText: '手机号 / 用户 ID',
                hintText: '输入以搜索',
              ),
              onSubmitted: (_) => _doSearch(context),
            ),
            const SizedBox(height: 12),
            SizedBox(
              width: double.infinity,
              child: ElevatedButton(
                onPressed: notifier.loading ? null : () => _doSearch(context),
                child: const Text('搜索'),
              ),
            ),
            if (notifier.error != null)
              Padding(
                padding: const EdgeInsets.only(top: 12),
                child: Text(notifier.error!.message,
                    style: const TextStyle(color: AppColors.error)),
              ),
            const SizedBox(height: 16),
            Expanded(child: _buildResults(notifier)),
          ],
        ),
      ),
    );
  }

  Future<void> _doSearch(BuildContext context) async {
    final q = _controller.text.trim();
    if (q.isEmpty) return;
    await context.read<FriendNotifier>().search(q);
  }

  Widget _buildResults(FriendNotifier notifier) {
    if (notifier.loading) {
      return const Center(child: CircularProgressIndicator());
    }
    if (notifier.searchResults.isEmpty) {
      return const Center(
        child: Text('通过手机号或用户 ID 添加好友', style: AppTypography.caption),
      );
    }
    return ListView.separated(
      itemCount: notifier.searchResults.length,
      separatorBuilder: (_, __) => const Divider(height: 1),
      itemBuilder: (_, i) {
        final u = notifier.searchResults[i];
        return _SearchResultTile(user: u);
      },
    );
  }
}

class _SearchResultTile extends StatelessWidget {
  const _SearchResultTile({required this.user});
  final UserSummary user;

  @override
  Widget build(BuildContext context) {
    final name =
        user.nickname.isNotEmpty ? user.nickname : user.username;
    return ListTile(
      leading: CircleAvatar(
        backgroundColor: AppColors.primaryLight,
        child:
            Text(name.isNotEmpty ? name[0] : '?', style: const TextStyle(color: AppColors.primary)),
      ),
      title: Text(name, style: AppTypography.subtitle),
      subtitle: Text('@${user.username}', style: AppTypography.caption),
      trailing: _AddButton(user: user),
    );
  }
}

class _AddButton extends StatelessWidget {
  const _AddButton({required this.user});
  final UserSummary user;

  @override
  Widget build(BuildContext context) {
    final notifier = context.watch<FriendNotifier>();
    return ElevatedButton(
      onPressed: notifier.loading
          ? null
          : () async {
              final ok = await notifier.sendRequest(user.username);
              if (ok && context.mounted) {
                ScaffoldMessenger.of(context).showSnackBar(
                  SnackBar(content: Text('已向 ${user.username} 发送好友请求')),
                );
              }
            },
      child: const Text('添加'),
    );
  }
}
