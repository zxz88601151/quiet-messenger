/// Friends list — real data (Phase 3D).
///
/// Shows the current user's friend list + an entry to add/search friends and
/// to view pending requests. Driven by [FriendNotifier] (UI ≠ Repository).
/// Conversation entry is wired via the accept flow (see FriendRequestsPage).
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';

import '../../../app/theme/colors.dart';
import '../../../app/theme/typography.dart';
import '../../chat/repositories/conversation_repository.dart';
import '../friend_notifier.dart';
import '../models/friendship.dart';

class FriendsPage extends StatefulWidget {
  const FriendsPage({super.key});

  @override
  State<FriendsPage> createState() => _FriendsPageState();
}

class _FriendsPageState extends State<FriendsPage> {
  @override
  void initState() {
    super.initState();
    // Load after first frame so the provider is available.
    Future.microtask(() => context.read<FriendNotifier>().loadFriends());
  }

  @override
  Widget build(BuildContext context) {
    final notifier = context.watch<FriendNotifier>();
    return Scaffold(
      appBar: AppBar(
        title: const Text('好友'),
        actions: [
          IconButton(
            icon: const Icon(Icons.person_add_outlined),
            onPressed: () => context.push('/friends/add'),
            tooltip: '添加好友',
          ),
          IconButton(
            icon: const Icon(Icons.mail_outlined),
            onPressed: () => context.push('/friends/requests'),
            tooltip: '好友请求',
          ),
        ],
      ),
      body: _buildBody(notifier),
    );
  }

  Widget _buildBody(FriendNotifier notifier) {
    if (notifier.loading && notifier.friends.isEmpty) {
      return const Center(child: CircularProgressIndicator());
    }
    if (notifier.error != null) {
      return Center(
        child: Text(notifier.error!.message, style: AppTypography.caption),
      );
    }
    if (notifier.friends.isEmpty) {
      return const Center(
        child: Text('还没有好友，点击右上角添加', style: AppTypography.caption),
      );
    }
    return ListView.separated(
      itemCount: notifier.friends.length,
      separatorBuilder: (_, __) => const Divider(height: 1),
      itemBuilder: (_, i) {
        final f = notifier.friends[i];
        return _FriendTile(friend: f, onTap: () => _openConversation(f));
      },
    );
  }

  /// Find the direct conversation for this friend (created at accept time)
  /// and navigate to it. If not found, show a message.
  Future<void> _openConversation(Friendship friend) async {
    try {
      final repo = context.read<ConversationRepository>();
      final convs = await repo.getConversations();
      final match = convs.where(
        (c) => c.peer.id == friend.user.id,
      );
      if (match.isNotEmpty && mounted) {
        context.push('/chat/${match.first.id}');
      } else if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('会话尚未创建，请稍后重试')),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('打开会话失败: ${e.toString().split('\n').first}')),
        );
      }
    }
  }
}

class _FriendTile extends StatelessWidget {
  const _FriendTile({required this.friend, this.onTap});
  final Friendship friend;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final name = friend.user.nickname.isNotEmpty
        ? friend.user.nickname
        : friend.user.username;
    return ListTile(
      leading: CircleAvatar(
        backgroundColor: AppColors.primaryLight,
        backgroundImage: friend.user.avatar != null && friend.user.avatar!.isNotEmpty
            ? NetworkImage(friend.user.avatar!)
            : null,
        child: friend.user.avatar != null && friend.user.avatar!.isNotEmpty
            ? null
            : Text(name.isNotEmpty ? name[0] : '?',
                style: const TextStyle(color: AppColors.primary)),
      ),
      title: Text(name, style: AppTypography.subtitle),
      subtitle: Text('@${friend.user.username}',
          style: const TextStyle(fontSize: 11, color: AppColors.text2)),
      onTap: onTap,
    );
  }
}
