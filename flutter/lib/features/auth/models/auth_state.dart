/// Auth state enumeration for the auth state machine.
///
/// Drives router redirects (Shared concept from STATE_MACHINES.md, modeled
/// minimally for Phase 3B):
/// - [unknown]    : app booting, session restore in progress
/// - [authenticated]   : valid session, route to home
/// - [unauthenticated] : no session, route to login
/// - [loading]    : transient (login/register/refresh in flight)
enum AuthState {
  unknown,
  authenticated,
  unauthenticated,
  loading,
}
