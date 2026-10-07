/// Friend Requests — real accept/reject (Phase 3D).
///
/// Lists incoming + outgoing requests. Accepting an incoming request creates
/// the bidirectional friendship + a pre-created direct conversation (backend
/// returns both). On accept we surface [FriendNotifier.lastAcceptedConversationId]
/// so the caller can navigate into the conversation (Phase 3E chat entry).
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';

import '../../../app/theme/colors.dart';
import '../../../app/theme/typography.dart';
import '../friend_notifier.dart';
import '../models/friend_request.dart';

class FriendRequestsPage extends StatefulWidget {
  const FriendRequestsPage({super.key});

  @override
  State<FriendRequestsPage> createState() => _FriendRequestsPageState();
}

class _FriendRequestsPageState extends State<FriendRequestsPage> {
  @override
  void initState() {
    super.initState();
    Future.microtask(() => context.read<FriendNotifier>().loadRequests());
  }

  @override
  Widget build(BuildContext context) {
    final notifier = context.watch<FriendNotifier>();
    return Scaffold(
      appBar: AppBar(title: const Text('好友请求')),
      body: _buildBody(notifier),
    );
  }

  Widget _buildBody(FriendNotifier notifier) {
    if (notifier.loading && notifier.requests.isEmpty) {
      return const Center(child: CircularProgressIndicator());
    }
    if (notifier.error != null) {
      return Center(
        child: Text(notifier.error!.message, style: AppTypography.caption),
      );
    }
    if (notifier.requests.isEmpty) {
      return const Center(
        child: Text('暂无好友请求', style: AppTypography.caption),
      );
    }
    return ListView.separated(
      itemCount: notifier.requests.length,
      separatorBuilder: (_, __) => const Divider(height: 1),
      itemBuilder: (_, i) => _RequestTile(request: notifier.requests[i]),
    );
  }
}

class _RequestTile extends StatelessWidget {
  const _RequestTile({required this.request});
  final FriendRequest request;

  @override
  Widget build(BuildContext context) {
    final name = request.otherUser?.nickname.isNotEmpty == true
        ? request.otherUser!.nickname
        : (request.otherUser?.username ?? '用户');
    return ListTile(
      leading: CircleAvatar(
        backgroundColor: AppColors.primaryLight,
        child: Text(name.isNotEmpty ? name[0] : '?',
            style: const TextStyle(color: AppColors.primary)),
      ),
      title: Text(name, style: AppTypography.subtitle),
      subtitle: Text(
        request.isIncoming ? '请求添加你为好友' : '已发送请求',
        style: AppTypography.caption,
      ),
      trailing: request.isIncoming
          ? Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                TextButton(
                  onPressed: () => _accept(context, request),
                  child: const Text('接受'),
                ),
                TextButton(
                  onPressed: () => _reject(context, request),
                  child: const Text('拒绝'),
                ),
              ],
            )
          : null,
    );
  }

  Future<void> _accept(BuildContext context, FriendRequest request) async {
    final notifier = context.read<FriendNotifier>();
    final ok = await notifier.accept(request.id);
    if (ok && context.mounted) {
      // Phase 3E: navigate into the conversation. For now show a confirmation;
      // the conversation id is stored in notifier.lastAcceptedConversationId.
      final displayName = request.otherUser?.nickname.isNotEmpty == true
          ? request.otherUser!.nickname
          : (request.otherUser?.username ?? '用户');
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('已添加 $displayName 为好友，可进入会话'),
          action: notifier.lastAcceptedConversationId != null
              ? SnackBarAction(
                  label: '进入会话',
                  onPressed: () => context.push(
                    '/chat/${notifier.lastAcceptedConversationId}',
                  ),
                )
              : null,
        ),
      );
    }
  }

  Future<void> _reject(BuildContext context, FriendRequest request) async {
    await context.read<FriendNotifier>().reject(request.id);
  }
}
