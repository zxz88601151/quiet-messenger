/// Conversation repository — REAL API implementation (Phase 3D).
///
/// Wires the chat feature to the existing [ApiClient] (Dio) from Phase 3A.
/// NO second HTTP client. Endpoints follow shared/API_CONTRACT.md §4.
///
/// Scope (Phase 3D only): list conversations + get a single conversation.
/// The "Get/Create Direct Conversation" step is fulfilled by the backend at
/// friend-accept time (API_CONTRACT §3 returns `{friendship, conversation}`),
/// so the client only needs read access here. Message send/list belongs to
/// Phase 3E — this repository deliberately exposes NO send() method.
///
/// Layering: UI → Provider/Notifier → ConversationRepository → ApiClient.
import '../../../core/api/api_client.dart';
import '../models/conversation.dart';

abstract class ConversationRepository {
  /// GET /conversations — list, newest first, with peer + optional preview.
  Future<List<Conversation>> getConversations();

  /// GET /conversations/{id} — single conversation (403 if not a member).
  Future<Conversation> getConversation(String conversationId);
}

class ApiConversationRepository implements ConversationRepository {
  const ApiConversationRepository(this._client);

  final ApiClient _client;

  @override
  Future<List<Conversation>> getConversations() async {
    final resp = await _client.get('/conversations');
    final list = (resp.data as List?) ?? [];
    return list
        .map((e) => Conversation.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  @override
  Future<Conversation> getConversation(String conversationId) async {
    final resp = await _client.get('/conversations/$conversationId');
    return Conversation.fromJson(resp.data as Map<String, dynamic>);
  }
}
