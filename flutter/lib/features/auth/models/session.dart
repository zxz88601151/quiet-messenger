/// Auth domain model — Session.
///
/// A session is the combination of the authenticated [user] and the
/// [tokens] used to make authorized requests. Built after login / register
/// or restored from secure storage on app start.
import 'auth_tokens.dart';
import 'user.dart';

class Session {
  const Session({required this.user, required this.tokens});

  final User user;
  final AuthTokens tokens;
}
