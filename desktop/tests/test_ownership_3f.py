"""Phase 3F — Desktop message ownership attribution (PySide6-free).

Verifies the ONLY correct ownership rule: sender_id == current_user_id.
`client_message_id` is an idempotency key returned by the backend for BOTH
peers and MUST NOT be used for attribution (prior `Message.is_mine` relied on
`client_message_id is not None` and rendered every message as "mine").

This module imports ONLY `app.features.chat.message_models` (a pure dataclass
module) so it runs without PySide6 / display — isolating the attribution logic
from the GUI test environment.
"""
from app.features.chat.message_models import Message, is_own_message


def test_is_own_message_mine():
    m = Message(id="m1", conversation_id="c1", sender_id="u1",
                content="hi", client_message_id="c-u1")
    assert is_own_message(m, "u1") is True


def test_is_own_message_peer():
    m = Message(id="m2", conversation_id="c1", sender_id="u2",
                content="hey", client_message_id="c-u2")
    assert is_own_message(m, "u1") is False


def test_is_own_message_regression_client_id_ignored():
    """Critical anti-regression: peer's message carries a client_message_id,
    but must NOT be attributed as mine."""
    m = Message(id="m3", conversation_id="c1", sender_id="u2",
                content="x", client_message_id="c-u2")
    assert m.client_message_id is not None  # precondition: peer has a client id
    # OLD buggy predicate `client_message_id is not None` -> True (wrong).
    assert is_own_message(m, "u1") is False  # correct: still peer
