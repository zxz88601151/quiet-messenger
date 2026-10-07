/// Message repository — REAL API implementation (Phase 3E).
///
/// Wires the chat message flow to the existing [ApiClient] (Dio) from Phase 3A.
/// NO second HTTP client. Endpoints follow shared/API_CONTRACT.md §4:
///   GET  /conversations/{id}/messages?cursor=&limit=
///   POST /conversations/{id}/messages  { content, client_message_id }
///
/// Layering: UI → Provider/Notifier → MessageRepository → ApiClient.
import '../../../core/api/api_client.dart';
import '../models/message.dart';

abstract class MessageRepository {
  /// GET history, cursor-paginated ascending by created_at.
  Future<List<Message>> getMessages(
    String conversationId, {
    String? cursor,
    int limit = 50,
  });

  /// POST a new message. Returns the server-confirmed [Message].
  Future<Message> sendMessage(
    String conversationId,
    String content,
    String clientMessageId,
  );
}

class ApiMessageRepository implements MessageRepository {
  const ApiMessageRepository(this._client);

  final ApiClient _client;

  @override
  Future<List<Message>> getMessages(
    String conversationId, {
    String? cursor,
    int limit = 50,
  }) async {
    final query = <String, dynamic>{
      'limit': limit,
      if (cursor != null && cursor.isNotEmpty) 'cursor': cursor,
    };
    final resp = await _client.get(
      '/conversations/$conversationId/messages',
      query: query,
    );
    final data = resp.data as Map<String, dynamic>? ?? {};
    final items = (data['items'] as List?) ?? [];
    return items
        .map((e) => Message.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  @override
  Future<Message> sendMessage(
    String conversationId,
    String content,
    String clientMessageId,
  ) async {
    final resp = await _client.post(
      '/conversations/$conversationId/messages',
      data: {
        'content': content,
        'client_message_id': clientMessageId,
      },
    );
    return Message.fromJson(resp.data as Map<String, dynamic>);
  }
}
