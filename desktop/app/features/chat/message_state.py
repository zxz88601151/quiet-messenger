"""Message controller (Desktop / PySide6, Phase 3E).

Orchestrates the message flow for ONE conversation (UI ≠ Controller ≠ Repository):
- load history (GET)
- send (POST) with optimistic insert + server-confirm replacement
- subscribe to RealtimeClient `message.created` events → dedup insert by id
  (REST response + WS event never double-render; §8)
- minimal UI state: sending / sent / failed (no status machine bloat)

Out of scope (NOT implemented): typing, read receipt, reaction, reply, edit,
recall, file/image/voice/video, group, AI, push.
"""
from __future__ import annotations

import uuid
from typing import Callable, Optional

from ...realtime.event_envelope import EventEnvelope
from ...realtime.realtime_client import RealtimeClient
from .message_models import Message, MessageUiState
from .message_repository import MessageRepository


class MessageController:
    def __init__(
        self,
        repository: MessageRepository,
        realtime: RealtimeClient,
        current_user_id: str,
        conversation_id: str,
    ) -> None:
        self._repo = repository
        self._realtime = realtime
        self._current_user_id = current_user_id
        self.conversation_id = conversation_id

        self.messages: list[Message] = []
        self.loading = True
        self.loading_more = False
        self.error: Optional[str] = None
        self.has_more = False

        self._subscribers: list[Callable[[], None]] = []
        # Multicast WS subscription (DEF-RT-001): use add_event_listener
        # instead of overwriting realtime.on_event, so Friend/Presence and
        # other conversations can also receive events.
        self._unsubscribe_ws = self._realtime.add_event_listener(self._on_event)
        # Offline message catch-up (DEF-RT-010 parity): reload history on
        # disconnected→connected transition to recover messages received while
        # the client was offline.
        self._unsubscribe_state = self._realtime.add_state_listener(self._on_connection_state)
        self._has_been_connected = False
        self._was_disconnected = False
        self._reconciling = False

    # ---订阅（UI 监听状态变化）---
    def subscribe(self, fn: Callable[[], None]) -> None:
        if fn not in self._subscribers:
            self._subscribers.append(fn)

    def unsubscribe(self, fn: Callable[[], None]) -> None:
        if fn in self._subscribers:
            self._subscribers.remove(fn)

    def _notify(self) -> None:
        for fn in list(self._subscribers):
            try:
                fn()
            except Exception:  # noqa: BLE001
                pass

    # ---加载历史---
    def load(self) -> None:
        self.loading = True
        self.error = None
        self._notify()
        try:
            self.messages = self._repo.get_messages(self.conversation_id, limit=50)
            self.has_more = len(self.messages) >= 50
            self.error = None
        except Exception as e:  # noqa: BLE001
            self.error = str(e)
        finally:
            self.loading = False
            self._notify()

    # ---重连 catch-up（离线消息同步）---
    def _on_connection_state(self, state) -> None:
        """RealtimeClient state listener for offline message catch-up.

        On disconnected→connected transition, reload history to recover
        messages that arrived while offline. Same guard pattern as
        FriendController (DEF-RT-010): initial connect does NOT reconcile.
        """
        state_name = getattr(state, "name", str(state)).lower()
        if state_name == "connected":
            if self._has_been_connected and self._was_disconnected and not self._reconciling:
                self._reconcile()
            self._has_been_connected = True
            self._was_disconnected = False
        elif state_name in ("disconnected", "reconnecting"):
            self._was_disconnected = True

    def _reconcile(self) -> None:
        """Fetch latest history and merge with local state.

        Preserves failed messages (not on server) and sending messages
        (in-flight). Dedup by message.id ensures no duplicates from
        REST + WS overlap.
        """
        if self._reconciling:
            return
        self._reconciling = True
        try:
            failed = [m for m in self.messages if m.ui_state == MessageUiState.FAILED]
            sending = [m for m in self.messages if m.ui_state == MessageUiState.SENDING]

            page = self._repo.get_messages(self.conversation_id, limit=50)
            self.messages = list(page)

            for m in failed + sending:
                if not any(existing.id == m.id for existing in self.messages):
                    self.messages.append(m)

            self.messages.sort(key=lambda m: m.created_at or "")
            self.error = None
            self._notify()
        except Exception as e:  # noqa: BLE001
            self.error = str(e)
            self._notify()
        finally:
            self._reconciling = False

    # ---发送---
    def send(self, content: str) -> None:
        text = (content or "").strip()
        if not text:
            return
        client_id = f"c_{uuid.uuid4().hex[:24]}"
        optimistic = Message.optimistic(
            conversation_id=self.conversation_id,
            sender_id=self._current_user_id,
            content=text,
            client_message_id=client_id,
        )
        self.messages.append(optimistic)
        self._notify()
        try:
            confirmed = self._repo.send_message(self.conversation_id, text, client_id)
            self._replace_by_id(optimistic.id, confirmed.copy_with(MessageUiState.SENT))
            self.error = None
        except Exception as e:  # noqa: BLE001
            self._replace_by_id(optimistic.id, optimistic.copy_with(MessageUiState.FAILED))
            self.error = str(e)
            self._notify()

    def retry(self, failed: Message) -> None:
        if not failed.client_message_id:
            return
        self._replace_by_id(failed.id, failed.copy_with(MessageUiState.SENDING))
        try:
            confirmed = self._repo.send_message(
                self.conversation_id, failed.content, failed.client_message_id
            )
            self._replace_by_id(failed.id, confirmed.copy_with(MessageUiState.SENT))
            self.error = None
        except Exception as e:  # noqa: BLE001
            self._replace_by_id(failed.id, failed.copy_with(MessageUiState.FAILED))
            self.error = str(e)
            self._notify()

    # ---WS 事件---
    def _on_event(self, evt: EventEnvelope) -> None:
        if evt.type != "message.created":
            return
        payload = evt.payload or {}
        if payload.get("conversation_id") != self.conversation_id:
            return
        msg = Message.from_json(payload)
        # DEF-RT-008: exclude own messages from sound; play new_message for
        # incoming messages only. Dedup by message.id is handled by _upsert.
        if msg.sender_id != self._current_user_id:
            try:
                from ...core.sound_service import SoundService
                SoundService().play_new_message()
            except Exception:  # noqa: BLE001
                pass
        self._upsert(msg)

    def _upsert(self, msg: Message) -> None:
        for i, m in enumerate(self.messages):
            if m.id == msg.id:
                self.messages[i] = msg.copy_with(MessageUiState.SENT)
                self._notify()
                return
        self.messages.append(msg)
        self._notify()

    def _replace_by_id(self, old_id: str, next_msg: Message) -> None:
        for i, m in enumerate(self.messages):
            if m.id == old_id:
                self.messages[i] = next_msg
                self._notify()
                return
        self.messages.append(next_msg)
        self._notify()

    def dispose(self) -> None:
        """Unsubscribe from WS events and clear listeners (DEF-RT-001)."""
        if hasattr(self, "_unsubscribe_ws"):
            self._unsubscribe_ws()
        if hasattr(self, "_unsubscribe_state"):
            self._unsubscribe_state()
        self._subscribers.clear()
