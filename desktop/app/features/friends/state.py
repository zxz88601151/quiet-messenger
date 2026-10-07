"""Friend state (Desktop / PySide6, Phase 3D).

A tiny observable state holder. To keep it testable without a QApplication, we
do NOT inherit QObject; the UI layer reads attributes and subscribes via
``on_change`` callbacks. ``loading`` and ``error`` drive UI feedback. UI never
calls ApiClient directly (UI → Controller → Repository → API).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional

from .error_mapper import FriendError
from .models import AcceptResult, FriendRequest, Friendship, UserSummary
from .repository import FriendRepository


class FriendStatus(str, Enum):
    IDLE = "idle"
    LOADING = "loading"
    ERROR = "error"


@dataclass
class FriendState:
    status: FriendStatus = FriendStatus.IDLE
    search_results: list[UserSummary] = field(default_factory=list)
    requests: list[FriendRequest] = field(default_factory=list)
    friends: list[Friendship] = field(default_factory=list)
    error: Optional[FriendError] = None
    last_accepted_conversation_id: Optional[str] = None
    _listeners: list[Callable[["FriendState"], None]] = field(default_factory=list)

    def subscribe(self, cb: Callable[["FriendState"], None]) -> None:
        self._listeners.append(cb)

    def _emit(self) -> None:
        for cb in self._listeners:
            cb(self)

    def _set(self, **kwargs) -> None:
        for k, v in kwargs.items():
            object.__setattr__(self, k, v)
        self._emit()


class FriendController:
    """Orchestrates [FriendRepository] + [FriendState]. UI calls the actions."""

    def __init__(
        self,
        repo: FriendRepository,
        realtime=None,
        current_user_id: str = "",
    ) -> None:
        self.repo = repo
        self.state = FriendState()
        self._realtime = realtime
        self._current_user_id = current_user_id
        # Dedup + initial-sync exclusion (DEF-RT-004, aligns Android).
        self._seen_request_ids: set[str] = set()
        self._requests_initialized = False
        # Reconciliation tracking (DEF-RT-010): distinguish initial connect
        # from reconnect after a prior drop.
        self._has_been_connected = False
        self._was_disconnected = False
        self._unsubscribe_ws = None
        self._unsubscribe_state = None
        if realtime is not None:
            self._unsubscribe_ws = realtime.add_event_listener(self._on_realtime_event)
            self._unsubscribe_state = realtime.add_state_listener(self._on_connection_state)

    def _on_connection_state(self, state) -> None:
        """REST reconciliation on reconnect (DEF-RT-010).

        Initial connect (first time reaching CONNECTED) does NOT trigger
        reconciliation — the UI loads data on page open. Only a reconnect
        (DISCONNECTED → CONNECTED after a prior drop) triggers a refresh.
        """
        from ...realtime.connection_state import ConnectionState
        if state == ConnectionState.CONNECTED:
            if not self._has_been_connected:
                self._has_been_connected = True
                return
            if self._was_disconnected:
                self._was_disconnected = False
                # Reconnect detected — refresh pending requests to catch missed events.
                try:
                    self.load_requests()
                except Exception:  # noqa: BLE001
                    pass
        elif state == ConnectionState.DISCONNECTED:
            self._was_disconnected = True

    def _on_realtime_event(self, evt) -> None:
        """Handle friend.request.created WS events (DEF-RT-004)."""
        if evt.type != "friend.request.created":
            return
        payload = evt.payload or {}
        req_id = payload.get("id")
        if not req_id or req_id in self._seen_request_ids:
            return
        self._seen_request_ids.add(req_id)
        # Parse and prepend (newest first). The event is pushed to the receiver.
        try:
            from .models import FriendRequest
            req = FriendRequest.from_json(payload, self._current_user_id)
            self.state._set(requests=[req, *self.state.requests])
        except Exception:  # noqa: BLE001
            pass  # malformed payload: still dedup the ID
        # Play sound only after initial sync (first REST load does not play).
        if self._requests_initialized:
            try:
                from ...core.sound_service import SoundService
                SoundService().play_friend_added()
            except Exception:  # noqa: BLE001
                pass

    def dispose(self) -> None:
        if self._unsubscribe_ws:
            self._unsubscribe_ws()
        if self._unsubscribe_state:
            self._unsubscribe_state()
        self.state._listeners.clear()

    def _fail(self, e: Exception) -> None:
        from ...errors.api_exception import ApiException

        if isinstance(e, ApiException):
            err = map_friend_error_safe(e)
        else:
            err = FriendError(message=str(e), code="UNKNOWN")
        self.state._set(status=FriendStatus.ERROR, error=err)

    def search(self, query: str) -> None:
        self.state._set(status=FriendStatus.LOADING, error=None)
        try:
            results = self.repo.search_users(query)
            self.state._set(
                status=FriendStatus.IDLE,
                search_results=results,
                error=None,
            )
        except Exception as e:  # noqa: BLE001
            self._fail(e)

    def load_requests(self, req_type: str = "all") -> None:
        self.state._set(status=FriendStatus.LOADING, error=None)
        try:
            reqs = self.repo.get_requests(req_type=req_type)
            self.state._set(status=FriendStatus.IDLE, requests=reqs, error=None)
            # Initial sync: record all IDs, do NOT play sound. Subsequent WS
            # events for unseen IDs will trigger sound (DEF-RT-004).
            current_ids = {r.id for r in reqs}
            if not self._requests_initialized:
                self._seen_request_ids.update(current_ids)
                self._requests_initialized = True
            else:
                # Subsequent REST refresh: detect new incoming pending requests.
                has_new = any(
                    r.is_incoming and r.status == "pending" and r.id not in self._seen_request_ids
                    for r in reqs
                )
                if has_new:
                    try:
                        from ...core.sound_service import SoundService
                        SoundService().play_friend_added()
                    except Exception:  # noqa: BLE001
                        pass
                self._seen_request_ids.update(current_ids)
        except Exception as e:  # noqa: BLE001
            self._fail(e)

    def load_friends(self) -> None:
        self.state._set(status=FriendStatus.LOADING, error=None)
        try:
            friends = self.repo.get_friends()
            self.state._set(status=FriendStatus.IDLE, friends=friends, error=None)
        except Exception as e:  # noqa: BLE001
            self._fail(e)

    def send_request(self, target: str) -> bool:
        self.state._set(status=FriendStatus.LOADING, error=None)
        try:
            self.repo.send_friend_request(target)
            self.state._set(status=FriendStatus.IDLE, error=None)
            return True
        except Exception as e:  # noqa: BLE001
            self._fail(e)
            return False

    def accept(self, request_id: str) -> bool:
        self.state._set(status=FriendStatus.LOADING, error=None)
        try:
            result: AcceptResult = self.repo.accept_friend_request(request_id)
            self.state._set(
                status=FriendStatus.IDLE,
                error=None,
                last_accepted_conversation_id=result.conversation_id,
            )
            return True
        except Exception as e:  # noqa: BLE001
            self._fail(e)
            return False

    def reject(self, request_id: str) -> bool:
        self.state._set(status=FriendStatus.LOADING, error=None)
        try:
            self.repo.reject_friend_request(request_id)
            self.state._set(status=FriendStatus.IDLE, error=None)
            return True
        except Exception as e:  # noqa: BLE001
            self._fail(e)
            return False

    def delete_friend(self, friend_id: str) -> bool:
        self.state._set(status=FriendStatus.LOADING, error=None)
        try:
            self.repo.delete_friend(friend_id)
            self.state._set(status=FriendStatus.IDLE, error=None)
            return True
        except Exception as e:  # noqa: BLE001
            self._fail(e)
            return False

    def clear_error(self) -> None:
        self.state._set(error=None)


def map_friend_error_safe(e: "ApiException") -> FriendError:
    from .error_mapper import map_friend_error

    return map_friend_error(e)
