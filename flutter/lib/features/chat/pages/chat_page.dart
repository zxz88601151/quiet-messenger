/// Chat window — Professionalized V1.1 Chat Detail (Phase Core Completion).
///
/// Implements P0 core UX:
/// - Header: avatar + nickname + online indicator (PresenceNotifier) + more menu
/// - Date grouping: 今天/昨天/MM月dd日, message HH:mm timestamp
/// - Empty state: icon + "你们已经是好友，开始聊天吧"
/// - Bubble refinement: multiline, long text, emoji, selectable, timestamp
/// - Long press: copy to clipboard (delete = BLOCKED, no backend API)
/// - New message indicator: ScrollController + bottom detection + counter + tap to bottom
/// - Scroll behavior: auto-scroll at bottom, never steal when reading history
/// - Realtime connection state: reconnecting banner + connected recovery
///
/// NOT implemented (out of scope / blocked):
/// - Typing indicator, read receipt, reaction, reply, edit, recall
/// - Image/file/voice/video (backend has no media storage — BLOCKED)
/// - Delete message (backend has no DELETE endpoint — BLOCKED)
/// - Group chat, AI, push
import 'package:flutter/material.dart' hide ConnectionState;
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import '../../../app/theme/colors.dart';
import '../../../app/theme/typography.dart';
import '../../auth/auth_notifier.dart';
import '../../friends/models/user_summary.dart';
import '../../presence/presence_notifier.dart';
import '../message_notifier.dart';
import '../models/conversation.dart';
import '../models/message.dart';
import '../repositories/conversation_repository.dart';
import '../repositories/message_repository.dart';
import '../../../core/realtime/connection_state.dart';
import '../../../core/realtime/realtime_client.dart';

class ChatPage extends StatefulWidget {
  const ChatPage({super.key, this.conversationId});

  final String? conversationId;

  @override
  State<ChatPage> createState() => _ChatPageState();
}

class _ChatPageState extends State<ChatPage> {
  Conversation? _conversation;
  bool _loadingConv = true;
  String? _convError;

  @override
  void initState() {
    super.initState();
    if (widget.conversationId != null) _loadConversation();
  }

  Future<void> _loadConversation() async {
    try {
      final repo = context.read<ConversationRepository>();
      _conversation = await repo.getConversation(widget.conversationId!);
      _convError = null;
    } catch (e) {
      _convError = e.toString();
    } finally {
      if (mounted) setState(() => _loadingConv = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_loadingConv) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }
    if (_convError != null || _conversation == null) {
      return Scaffold(
        appBar: AppBar(title: const Text('会话')),
        body: Center(
          child: Text(_convError ?? '会话不存在', style: AppTypography.caption),
        ),
      );
    }
    return _ChatBody(conversation: _conversation!);
  }
}

// ---------------------------------------------------------------------------
// Chat body — stateful for ScrollController / new-message counter / banner
// ---------------------------------------------------------------------------
class _ChatBody extends StatefulWidget {
  const _ChatBody({required this.conversation});

  final Conversation conversation;

  @override
  State<_ChatBody> createState() => _ChatBodyState();
}

class _ChatBodyState extends State<_ChatBody> {
  final ScrollController _scrollController = ScrollController();
  bool _isAtBottom = true;
  int _newMessageCount = 0;

  // Realtime connection state for reconnect banner
  ConnectionState _connState = ConnectionState.connected;
  bool _showConnectedFlash = false;
  void Function()? _unsubscribeConnState;

  @override
  void initState() {
    super.initState();
    _scrollController.addListener(_onScroll);
    // Subscribe to RealtimeClient state changes for reconnect banner
    final realtime = context.read<RealtimeClient>();
    _connState = realtime.state;
    _unsubscribeConnState = realtime.addStateListener(_onConnectionState);
  }

  @override
  void dispose() {
    _scrollController.removeListener(_onScroll);
    _scrollController.dispose();
    _unsubscribeConnState?.call();
    super.dispose();
  }

  void _onScroll() {
    if (!_scrollController.hasClients) return;
    final atBottom = _scrollController.position.pixels >=
        _scrollController.position.maxScrollExtent - 24;
    if (atBottom != _isAtBottom) {
      setState(() {
        _isAtBottom = atBottom;
        if (atBottom) _newMessageCount = 0;
      });
    }
  }

  void _onConnectionState(ConnectionState state) {
    if (!mounted) return;
    final prev = _connState;
    setState(() => _connState = state);
    // Show brief "已连接" flash when recovering from disconnect/reconnect
    if (state == ConnectionState.connected &&
        (prev == ConnectionState.disconnected || prev == ConnectionState.reconnecting)) {
      setState(() => _showConnectedFlash = true);
      Future.delayed(const Duration(seconds: 2), () {
        if (mounted) setState(() => _showConnectedFlash = false);
      });
    }
  }

  /// Called after build when new messages arrive — auto-scroll if at bottom,
  /// otherwise increment the unread counter.
  void _handleNewMessages(int prevCount, int newCount) {
    if (newCount <= prevCount) return;
    if (_isAtBottom) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (_scrollController.hasClients) {
          _scrollController.animateTo(
            _scrollController.position.maxScrollExtent,
            duration: const Duration(milliseconds: 200),
            curve: Curves.easeOut,
          );
        }
      });
    } else {
      setState(() => _newMessageCount += newCount - prevCount);
    }
  }

  void _scrollToBottom() {
    if (_scrollController.hasClients) {
      _scrollController.animateTo(
        _scrollController.position.maxScrollExtent,
        duration: const Duration(milliseconds: 250),
        curve: Curves.easeOut,
      );
    }
    setState(() {
      _newMessageCount = 0;
      _isAtBottom = true;
    });
  }

  @override
  Widget build(BuildContext context) {
    final api = context.read<MessageRepository>();
    final realtime = context.read<RealtimeClient>();
    final currentUser = context.read<AuthNotifier>().currentUser;

    return ChangeNotifierProvider<MessageNotifier>(
      create: (_) => MessageNotifier(
        repository: api,
        realtime: realtime,
        currentUserId: currentUser?.id ?? '',
        conversationId: widget.conversation.id,
      )..load(),
      child: _ChatScaffold(
        conversation: widget.conversation,
        scrollController: _scrollController,
        isAtBottom: _isAtBottom,
        newMessageCount: _newMessageCount,
        connState: _connState,
        showConnectedFlash: _showConnectedFlash,
        onNewMessages: _handleNewMessages,
        onScrollToBottom: _scrollToBottom,
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Scaffold — separates MessageNotifier consumer from scroll state
// ---------------------------------------------------------------------------
class _ChatScaffold extends StatelessWidget {
  const _ChatScaffold({
    required this.conversation,
    required this.scrollController,
    required this.isAtBottom,
    required this.newMessageCount,
    required this.connState,
    required this.showConnectedFlash,
    required this.onNewMessages,
    required this.onScrollToBottom,
  });

  final Conversation conversation;
  final ScrollController scrollController;
  final bool isAtBottom;
  final int newMessageCount;
  final ConnectionState connState;
  final bool showConnectedFlash;
  final void Function(int prev, int next) onNewMessages;
  final VoidCallback onScrollToBottom;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: _ChatHeader(conversation: conversation),
      body: Stack(
        children: [
          Column(
            children: [
              // Reconnect banner
              if (connState == ConnectionState.reconnecting ||
                  connState == ConnectionState.disconnected)
                _ReconnectBanner(state: connState)
              else if (showConnectedFlash)
                const _ConnectedFlash(),
              Expanded(
                child: _MessageList(
                  conversation: conversation,
                  scrollController: scrollController,
                  onNewMessages: onNewMessages,
                ),
              ),
              _Composer(onSent: onScrollToBottom),
            ],
          ),
          // New message indicator FAB (positioned above composer)
          if (newMessageCount > 0)
            Positioned(
              bottom: 72,
              left: 0,
              right: 0,
              child: _NewMessageButton(
                count: newMessageCount,
                onTap: onScrollToBottom,
              ),
            ),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Header — avatar + nickname + online indicator + more menu
// ---------------------------------------------------------------------------
class _ChatHeader extends StatelessWidget implements PreferredSizeWidget {
  const _ChatHeader({required this.conversation});

  final Conversation conversation;

  @override
  Size get preferredSize => const Size.fromHeight(kToolbarHeight);

  @override
  Widget build(BuildContext context) {
    final peer = conversation.peer;
    final presence = context.watch<PresenceNotifier>();
    final isOnline = presence.isOnline(peer.id);
    final displayName = peer.nickname.isNotEmpty ? peer.nickname : peer.username;

    return AppBar(
      titleSpacing: 0,
      title: InkWell(
        onTap: () {
          // Navigate to friend profile if available
          // TODO: navigate to FriendProfilePage(peer) when implemented
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text('$displayName 的资料页'), duration: const Duration(seconds: 1)),
          );
        },
        child: Row(
          children: [
            Stack(
              children: [
                CircleAvatar(
                  radius: 18,
                  backgroundImage: peer.avatar != null && peer.avatar!.isNotEmpty
                      ? NetworkImage(peer.avatar!)
                      : null,
                  backgroundColor: AppColors.primaryLight,
                  child: peer.avatar == null || peer.avatar!.isEmpty
                      ? Text(
                          displayName.isNotEmpty ? displayName[0].toUpperCase() : '?',
                          style: AppTypography.body.copyWith(color: AppColors.primary, fontWeight: FontWeight.w600),
                        )
                      : null,
                ),
                // Online indicator dot
                Positioned(
                  right: 0,
                  bottom: 0,
                  child: Container(
                    width: 10,
                    height: 10,
                    decoration: BoxDecoration(
                      color: isOnline ? Colors.green : Colors.grey[400],
                      shape: BoxShape.circle,
                      border: Border.all(color: Colors.white, width: 1.5),
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(width: 10),
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  displayName,
                  style: AppTypography.body.copyWith(fontWeight: FontWeight.w600),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
                Text(
                  isOnline ? '在线' : '离线',
                  style: AppTypography.caption.copyWith(
                    color: isOnline ? Colors.green[700] : AppColors.text3,
                    fontSize: 11,
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
      actions: [
        PopupMenuButton<String>(
          icon: const Icon(Icons.more_vert),
          onSelected: (value) {
            if (value == 'profile') {
              ScaffoldMessenger.of(context).showSnackBar(
                SnackBar(content: Text('$displayName 的资料页'), duration: const Duration(seconds: 1)),
              );
            }
          },
          itemBuilder: (context) => [
            const PopupMenuItem(value: 'profile', child: Text('查看资料')),
            const PopupMenuItem(
              value: 'block',
              enabled: false,
              child: Text('拉黑（暂不可用）'),
            ),
          ],
        ),
      ],
    );
  }
}

// ---------------------------------------------------------------------------
// Reconnect banner
// ---------------------------------------------------------------------------
class _ReconnectBanner extends StatelessWidget {
  const _ReconnectBanner({required this.state});

  final ConnectionState state;

  @override
  Widget build(BuildContext context) {
    final text = state == ConnectionState.reconnecting ? '正在重新连接…' : '连接已断开';
    final color = state == ConnectionState.reconnecting ? Colors.orange : Colors.red;
    return Container(
      width: double.infinity,
      color: color.withValues(alpha: 0.1),
      padding: const EdgeInsets.symmetric(vertical: 6, horizontal: 16),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          if (state == ConnectionState.reconnecting)
            const SizedBox(
              width: 12,
              height: 12,
              child: CircularProgressIndicator(strokeWidth: 2),
            ),
          if (state == ConnectionState.reconnecting) const SizedBox(width: 8),
          Text(text, style: AppTypography.caption.copyWith(color: color)),
        ],
      ),
    );
  }
}

class _ConnectedFlash extends StatelessWidget {
  const _ConnectedFlash();

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      color: Colors.green.withValues(alpha: 0.1),
      padding: const EdgeInsets.symmetric(vertical: 6, horizontal: 16),
      child: Center(
        child: Text('已连接', style: AppTypography.caption.copyWith(color: Colors.green[700])),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Message list — date grouping + bubbles + empty state
// ---------------------------------------------------------------------------
class _MessageList extends StatefulWidget {
  const _MessageList({
    required this.conversation,
    required this.scrollController,
    required this.onNewMessages,
  });

  final Conversation conversation;
  final ScrollController scrollController;
  final void Function(int prev, int next) onNewMessages;

  @override
  State<_MessageList> createState() => _MessageListState();
}

class _MessageListState extends State<_MessageList> {
  int _prevMessageCount = 0;

  @override
  Widget build(BuildContext context) {
    final notifier = context.watch<MessageNotifier>();
    final messages = notifier.messages;

    // Detect new messages and notify parent for auto-scroll / counter
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (messages.length != _prevMessageCount) {
        widget.onNewMessages(_prevMessageCount, messages.length);
        _prevMessageCount = messages.length;
      }
    });

    if (notifier.loading) {
      return const Center(child: CircularProgressIndicator());
    }
    if (notifier.error != null && messages.isEmpty) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.error_outline, size: 40, color: AppColors.text3),
              const SizedBox(height: 12),
              Text(notifier.error!, style: AppTypography.caption, textAlign: TextAlign.center),
            ],
          ),
        ),
      );
    }
    if (messages.isEmpty) {
      return const _EmptyChatState();
    }

    // Build list with date separators
    final children = <Widget>[];
    DateTime? prevDate;
    for (var i = 0; i < messages.length; i++) {
      final m = messages[i];
      final msgDate = m.createdAt;
      // Date separator
      if (msgDate != null && (prevDate == null || !_isSameDay(prevDate!, msgDate))) {
        children.add(_DateSeparator(date: msgDate));
      }
      if (msgDate != null) prevDate = msgDate;
      children.add(_Bubble(message: m));
    }
    children.add(const SizedBox(height: 8));

    return ListView.builder(
      controller: widget.scrollController,
      padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 12),
      itemCount: children.length,
      itemBuilder: (ctx, i) => children[i],
    );
  }

  bool _isSameDay(DateTime a, DateTime b) =>
      a.year == b.year && a.month == b.month && a.day == b.day;
}

// ---------------------------------------------------------------------------
// Date separator
// ---------------------------------------------------------------------------
class _DateSeparator extends StatelessWidget {
  const _DateSeparator({required this.date});

  final DateTime date;

  @override
  Widget build(BuildContext context) {
    final now = DateTime.now();
    final yesterday = now.subtract(const Duration(days: 1));
    String label;
    if (date.year == now.year && date.month == now.month && date.day == now.day) {
      label = '今天';
    } else if (date.year == yesterday.year && date.month == yesterday.month && date.day == yesterday.day) {
      label = '昨天';
    } else if (date.year == now.year) {
      label = '${date.month}月${date.day}日';
    } else {
      label = '${date.year}年${date.month}月${date.day}日';
    }
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 12),
      child: Center(
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
          decoration: BoxDecoration(
            color: AppColors.bg,
            borderRadius: BorderRadius.circular(10),
          ),
          child: Text(label, style: AppTypography.caption.copyWith(color: AppColors.text3, fontSize: 11)),
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Empty chat state
// ---------------------------------------------------------------------------
class _EmptyChatState extends StatelessWidget {
  const _EmptyChatState();

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.chat_bubble_outline, size: 56, color: AppColors.text3.withValues(alpha: 0.5)),
          const SizedBox(height: 16),
          Text('你们已经是好友', style: AppTypography.body.copyWith(color: AppColors.text2)),
          const SizedBox(height: 4),
          Text('开始聊天吧', style: AppTypography.caption.copyWith(color: AppColors.text3)),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Message bubble — own/peer, timestamp, long-press copy
// ---------------------------------------------------------------------------
class _Bubble extends StatelessWidget {
  const _Bubble({required this.message});

  final Message message;

  @override
  Widget build(BuildContext context) {
    final currentUserId = context.read<AuthNotifier>().currentUser?.id ?? '';
    final mine = message.isOwnMessage(currentUserId);
    final alignment = mine ? CrossAxisAlignment.end : CrossAxisAlignment.start;
    final bubbleColor = mine ? AppColors.primary : AppColors.bg;
    final textColor = mine ? Colors.white : AppColors.text;
    final borderColor = mine ? Colors.transparent : AppColors.border;
    final time = message.createdAt != null
        ? '${message.createdAt!.hour.toString().padLeft(2, '0')}:${message.createdAt!.minute.toString().padLeft(2, '0')}'
        : '';

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Column(
        crossAxisAlignment: alignment,
        children: [
          GestureDetector(
            onLongPress: () => _showMessageMenu(context, message.content),
            child: Container(
              constraints: BoxConstraints(
                maxWidth: MediaQuery.of(context).size.width * 0.72,
              ),
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 9),
              decoration: BoxDecoration(
                color: bubbleColor,
                borderRadius: BorderRadius.circular(14),
                border: Border.all(color: borderColor),
              ),
              child: SelectableText(
                message.content,
                style: AppTypography.body.copyWith(color: textColor, height: 1.35),
                cursorColor: mine ? Colors.white70 : AppColors.primary,
                toolbarOptions: const ToolbarOptions(copy: true, selectAll: true),
              ),
            ),
          ),
          const SizedBox(height: 2),
          // Timestamp + status
          Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (time.isNotEmpty)
                Text(time, style: AppTypography.caption.copyWith(color: AppColors.text3, fontSize: 10)),
              if (mine && message.uiState == MessageUiState.sending) ...[
                const SizedBox(width: 4),
                Text('发送中…', style: AppTypography.caption.copyWith(color: AppColors.text3, fontSize: 10)),
              ],
              if (mine && message.uiState == MessageUiState.failed) ...[
                const SizedBox(width: 4),
                GestureDetector(
                  onTap: () => context.read<MessageNotifier>().retry(message),
                  child: Text('失败·点击重试', style: AppTypography.caption.copyWith(color: AppColors.error, fontSize: 10)),
                ),
              ],
            ],
          ),
        ],
      ),
    );
  }

  void _showMessageMenu(BuildContext context, String content) {
    showModalBottomSheet(
      context: context,
      builder: (ctx) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            ListTile(
              leading: const Icon(Icons.copy),
              title: const Text('复制'),
              onTap: () {
                Clipboard.setData(ClipboardData(text: content));
                Navigator.pop(ctx);
                ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(content: Text('已复制'), duration: Duration(seconds: 1)),
                );
              },
            ),
            ListTile(
              leading: const Icon(Icons.delete_outline, color: Colors.grey),
              title: const Text('删除（暂不可用）', style: TextStyle(color: Colors.grey)),
              enabled: false,
              onTap: null,
            ),
          ],
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// New message indicator button
// ---------------------------------------------------------------------------
class _NewMessageButton extends StatelessWidget {
  const _NewMessageButton({required this.count, required this.onTap});

  final int count;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Align(
        alignment: Alignment.bottomCenter,
        child: GestureDetector(
          onTap: onTap,
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(20),
              boxShadow: [
                BoxShadow(color: Colors.black.withValues(alpha: 0.15), blurRadius: 8, offset: const Offset(0, 2)),
              ],
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(Icons.arrow_downward, size: 16, color: AppColors.primary),
                const SizedBox(width: 4),
                Text('$count 条新消息', style: AppTypography.caption.copyWith(color: AppColors.primary, fontSize: 12)),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Composer — input + send + media placeholder (BLOCKED)
// ---------------------------------------------------------------------------
class _Composer extends StatefulWidget {
  const _Composer({required this.onSent});

  final VoidCallback onSent;

  @override
  State<_Composer> createState() => _ComposerState();
}

class _ComposerState extends State<_Composer> {
  final TextEditingController _controller = TextEditingController();
  bool _hasText = false;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _send() {
    final text = _controller.text.trim();
    if (text.isEmpty) return;
    context.read<MessageNotifier>().send(text);
    _controller.clear();
    setState(() => _hasText = false);
    widget.onSent();
  }

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      top: false,
      child: Container(
        decoration: BoxDecoration(
          color: AppColors.bg,
          border: Border(top: BorderSide(color: AppColors.border, width: 0.5)),
        ),
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            // Media button — BLOCKED (backend has no media storage)
            IconButton(
              icon: const Icon(Icons.add_circle_outline),
              color: AppColors.text3,
              onPressed: () {
                ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(content: Text('图片/文件功能暂未开放'), duration: Duration(seconds: 1)),
                );
              },
            ),
            Expanded(
              child: TextField(
                controller: _controller,
                minLines: 1,
                maxLines: 4,
                textInputAction: TextInputAction.send,
                decoration: InputDecoration(
                  hintText: '发条消息…',
                  hintStyle: AppTypography.body.copyWith(color: AppColors.text3),
                  contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                  filled: true,
                  fillColor: AppColors.canvas,
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(20),
                    borderSide: BorderSide.none,
                  ),
                ),
                onChanged: (v) => setState(() => _hasText = v.trim().isNotEmpty),
                onSubmitted: (_) => _send(),
              ),
            ),
            const SizedBox(width: 4),
            // Send button
            IconButton(
              icon: Icon(_hasText ? Icons.send : Icons.send),
              color: _hasText ? AppColors.primary : AppColors.text3,
              onPressed: _hasText ? _send : null,
            ),
          ],
        ),
      ),
    );
  }
}
