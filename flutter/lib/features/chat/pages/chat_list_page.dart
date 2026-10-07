/// Chat List screen — real conversation list (Phase 3D).
///
/// Driven by a local [ConversationRepository] read. Phase 3A used LOCAL mock;
/// this wires GET /conversations. Message FLOW (sending/reading/typing) is
/// Phase 3E — tapping a conversation opens an empty-state [ChatPage] here.
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';

import '../../../app/theme/colors.dart';
import '../../../app/theme/typography.dart';
import '../models/conversation.dart';
import '../repositories/conversation_repository.dart';

class ChatListPage extends StatefulWidget {
  const ChatListPage({super.key});

  @override
  State<ChatListPage> createState() => _ChatListPageState();
}

class _ChatListPageState extends State<ChatListPage> {
  List<Conversation> _conversations = const [];
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    Future.microtask(_load);
  }

  Future<void> _load() async {
    try {
      final repo = context.read<ConversationRepository>();
      _conversations = await repo.getConversations();
      _error = null;
    } catch (e) {
      _error = e.toString();
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('聊天')),
      body: _buildBody(),
    );
  }

  Widget _buildBody() {
    if (_loading) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_error != null) {
      return Center(child: Text(_error!, style: AppTypography.caption));
    }
    if (_conversations.isEmpty) {
      return const Center(
        child: Text('还没有会话，去添加好友吧', style: AppTypography.caption),
      );
    }
    return ListView.separated(
      itemCount: _conversations.length,
      separatorBuilder: (_, _) => const Divider(height: 1),
      itemBuilder: (_, i) {
        final c = _conversations[i];
        final name = c.peer.nickname.isNotEmpty ? c.peer.nickname : c.peer.username;
        return ListTile(
          leading: CircleAvatar(
            backgroundColor: AppColors.primaryLight,
            child: Text(name.isNotEmpty ? name[0] : '?',
                style: const TextStyle(color: AppColors.primary)),
          ),
          title: Text(name, style: AppTypography.subtitle),
          subtitle: c.lastMessagePreview != null
              ? Text(c.lastMessagePreview!,
                  style: AppTypography.caption, maxLines: 1)
              : const Text('会话已建立',
                  style: TextStyle(fontSize: 11, color: AppColors.text2)),
          trailing: c.unreadCount > 0
              ? CircleAvatar(
                  radius: 10,
                  backgroundColor: AppColors.primary,
                  child: Text('${c.unreadCount}',
                      style: const TextStyle(color: Colors.white, fontSize: 10)),
                )
              : null,
          // Phase 3E: open ChatPage(conversationId). For now navigate to the
          // empty-state conversation entry (no message send in Phase 3D).
          onTap: () => context.push('/chat/${c.id}'),
        );
      },
    );
  }
}
