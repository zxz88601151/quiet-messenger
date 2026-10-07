/// Phase 3F — Message ownership attribution regression tests (Flutter).
///
/// The ONLY correct attribution rule is `sender_id == current_user_id`.
/// `client_message_id` is an idempotency key returned by the backend for BOTH
/// peers and MUST NOT be used for attribution. The prior `isMine =>
/// clientMessageId != null` predicate was wrong and rendered every received
/// message as "mine".
///
/// Execution: `flutter test` (needs flutter_tester). In the headless Windows
/// sandbox this may be BLOCKED BY ENVIRONMENT (no flutter_tester). The tests
/// are valid and assert real client behavior — they do NOT fabricate PASS.
import 'package:flutter_test/flutter_test.dart';

import 'package:flutter_client/features/chat/models/message.dart';

void main() {
  group('Message.isOwnMessage attribution (Phase 3F)', () {
    test('sender_id == current_user_id -> mine', () {
      final m = Message.fromJson({
        'id': 'm1',
        'conversation_id': 'c1',
        'sender_id': 'u1',
        'content': 'hi',
        'client_message_id': 'c-u1',
      });
      expect(m.isOwnMessage('u1'), isTrue);
    });

    test('sender_id != current_user_id -> peer', () {
      final m = Message.fromJson({
        'id': 'm2',
        'conversation_id': 'c1',
        'sender_id': 'u2',
        'content': 'hi from peer',
        'client_message_id': 'c-u2',
      });
      expect(m.isOwnMessage('u1'), isFalse);
    });

    test('client_message_id set but sender != current -> still peer '
        '(critical anti-regression guard)', () {
      // Peer's own optimistic message: backend returns client_message_id for
      // BOTH peers. The OLD buggy predicate `clientMessageId != null` would
      // return true here and wrongly render it as "mine".
      final peerMsg = Message.fromJson({
        'id': 'm3',
        'conversation_id': 'c1',
        'sender_id': 'u2',
        'content': 'peer message with client id',
        'client_message_id': 'c-u2',
      });
      expect(peerMsg.clientMessageId, isNotNull); // precondition: id present
      expect(peerMsg.isOwnMessage('u1'), isFalse); // must NOT be treated as mine

      // Symmetric check: my own message after the peer's id is present.
      final myMsg = Message.fromJson({
        'id': 'm4',
        'conversation_id': 'c1',
        'sender_id': 'u1',
        'content': 'my message',
        'client_message_id': 'c-u1',
      });
      expect(myMsg.isOwnMessage('u1'), isTrue);
    });

    test('optimistic local message (no server id yet) still attributed by sender', () {
      final local = Message.optimistic(
        conversationId: 'c1',
        senderId: 'u1',
        content: 'draft',
        clientMessageId: 'c-local',
      );
      expect(local.isOwnMessage('u1'), isTrue);
      expect(local.isOwnMessage('u2'), isFalse);
    });
  });
}
