/// Friendship status machine (V1.1, minimal direction).
///
/// Per Phase 3D §7 only the following states are permitted. We deliberately
/// do NOT introduce FOLLOWING / FOLLOWER / MUTUAL / CLOSE_FRIEND / BEST_FRIEND
/// (those belong to other social models, not this minimal private-comms app).
enum FriendStatus {
  none,
  pendingOutgoing,
  pendingIncoming,
  friends,
  blocked,
}
