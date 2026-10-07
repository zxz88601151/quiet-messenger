"""Realtime WebSocket Client (Desktop / PySide6, Phase 3C).

分层：UI → Controller/Repository → RealtimeClient → WebSocket。
禁止 QWidget 直接持有 WebSocket 连接。

特性（仅基础设施，不含聊天/好友等业务）：
- Bearer 头鉴权（Authorization: Bearer <access_token>），token 不入 URL（§8）。
- 收到 connection.ready → ConnectionState.CONNECTED。
- 收到 connection.ping → 回 connection.pong（§16 心跳）。
- 指数退避重连（1/2/4/8/16s 上限），杜绝无限高速重连（§17）。
- Access Token 失效：经注入的 refresh callback 取新 token 后重连（§18），
  不自行签发 token。
- 状态变更通过 on_state_change 回调广播（UI 最小展示 Connected/Connecting/Offline）。

token 提供方：传入 get_token() 回调（从 TokenStorage 读）；refresh 提供方：
传入 on_token_expired() 回调（调 AuthRepository.refresh，更新 TokenStorage）。
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Awaitable, Callable, Optional

from .connection_state import ConnectionState
from .event_envelope import EventEnvelope
from .realtime_error import AuthFailedError, ConnectionLostError, RealtimeError

logger = logging.getLogger("liaotian.realtime")

# 指数退避序列（秒），封顶 16s（§17）。
_BACKOFF_SCHEDULE = [1, 2, 4, 8, 16]
_DEFAULT_WS_PATH = "/ws/v1"


class RealtimeClient:
    def __init__(
        self,
        base_url: str,
        get_token: Callable[[], Optional[str]],
        on_token_expired: Callable[[], Awaitable[bool]],
        on_state_change: Callable[[ConnectionState], None] | None = None,
        on_event: Callable[[EventEnvelope], None] | None = None,
        ws_path: str = _DEFAULT_WS_PATH,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._ws_path = ws_path
        self._get_token = get_token
        self._on_token_expired = on_token_expired
        self._on_state_change = on_state_change
        self.on_event = on_event  # legacy single-callback; prefer add_event_listener

        # Multicast event listeners (DEF-RT-001): multiple subscribers can
        # receive WS events simultaneously without overwriting each other.
        self._event_listeners: list[Callable[[EventEnvelope], None]] = []

        # Multicast state listeners (DEF-RT-010): subscribers can react to
        # connection state changes, e.g. trigger REST reconciliation on reconnect.
        self._state_listeners: list[Callable[[ConnectionState], None]] = []

        self._state = ConnectionState.DISCONNECTED
        self._running = False
        self._ws: object | None = None
        self._task: asyncio.Task | None = None
        self._reconnect_attempts = 0
        self._current_conn_id: str | None = None

    # --- 公共 API ---
    @property
    def state(self) -> ConnectionState:
        return self._state

    def connect(self) -> None:
        """启动连接循环（幂等）。在事件循环内调用。"""
        if self._running:
            return
        self._running = True
        try:
            self._task = asyncio.ensure_future(self._run())
        except RuntimeError:
            # 无运行事件循环（如测试）：交给调用方调度。
            self._task = None
            self._running = False

    def disconnect(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            self._task = None
        self._set_state(ConnectionState.DISCONNECTED)

    def add_event_listener(
        self, cb: Callable[[EventEnvelope], None]
    ) -> Callable[[], None]:
        """Register a multicast event listener. Returns an unsubscribe callback.

        Multiple listeners can coexist; one listener crashing does not block
        others. Always call the returned unsubscribe when the subscriber is
        destroyed to avoid leaks (DEF-RT-001).
        """
        if cb not in self._event_listeners:
            self._event_listeners.append(cb)

        def _unsubscribe() -> None:
            if cb in self._event_listeners:
                self._event_listeners.remove(cb)

        return _unsubscribe

    def remove_event_listener(self, cb: Callable[[EventEnvelope], None]) -> None:
        if cb in self._event_listeners:
            self._event_listeners.remove(cb)

    def add_state_listener(
        self, cb: Callable[[ConnectionState], None]
    ) -> Callable[[], None]:
        """Register a multicast state listener. Returns an unsubscribe callback.

        Used for REST reconciliation on reconnect (DEF-RT-010): when the
        connection transitions disconnected→connected after a prior drop,
        subscribers can refresh state from REST APIs.
        """
        if cb not in self._state_listeners:
            self._state_listeners.append(cb)

        def _unsubscribe() -> None:
            if cb in self._state_listeners:
                self._state_listeners.remove(cb)

        return _unsubscribe

    def remove_state_listener(self, cb: Callable[[ConnectionState], None]) -> None:
        if cb in self._state_listeners:
            self._state_listeners.remove(cb)

    def send(self, event: dict) -> None:
        """发送客户端事件（connection.pong / connection.close）。"""
        if self._ws is None:
            return
        try:
            asyncio.ensure_future(self._ws.send(json.dumps(event)))  # type: ignore[attr-defined]
        except Exception as e:  # noqa: BLE001
            logger.warning("realtime send failed: %s", e)

    # --- 内部 ---
    def _set_state(self, state: ConnectionState) -> None:
        if state == self._state:
            return
        self._state = state
        if self._on_state_change:
            try:
                self._on_state_change(state)
            except Exception:  # noqa: BLE001
                pass
        for cb in list(self._state_listeners):
            try:
                cb(state)
            except Exception:  # noqa: BLE001
                pass

    def _ws_uri(self) -> str:
        http = self._base_url
        if http.startswith("https://"):
            ws = "wss://" + http[len("https://") :]
        elif http.startswith("http://"):
            ws = "ws://" + http[len("http://") :]
        else:
            ws = "ws://" + http
        return f"{ws}{self._ws_path}"

    async def _run(self) -> None:
        import websockets  # 延迟导入，测试可 mock

        while self._running:
            token = self._get_token()
            if not token:
                self._set_state(ConnectionState.ERROR)
                await asyncio.sleep(self._backoff())
                continue
            self._set_state(
                ConnectionState.RECONNECTING
                if self._reconnect_attempts > 0
                else ConnectionState.CONNECTING
            )
            try:
                headers = {"Authorization": f"Bearer {token}"}
                async with websockets.connect(
                    self._ws_uri(), additional_headers=headers
                ) as ws:
                    self._ws = ws
                    self._reconnect_attempts = 0
                    self._set_state(ConnectionState.AUTHENTICATING)
                    await self._loop(ws)
            except AuthFailedError:
                # 鉴权失败：尝试 refresh 后重连一次；仍失败则等待退避。
                if await self._try_refresh():
                    continue
                self._set_state(ConnectionState.ERROR)
                await asyncio.sleep(self._backoff())
            except Exception as e:  # noqa: BLE001
                logger.info("realtime disconnected: %s", e)
                self._set_state(ConnectionState.DISCONNECTED)
                if self._running:
                    await asyncio.sleep(self._backoff())
        self._ws = None

    async def _loop(self, ws) -> None:
        import websockets  # type: ignore

        try:
            async for raw in ws:
                try:
                    data = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    continue
                # EventEnvelope.from_json validates field types (DEF-RT-007).
                # Malformed frames are logged and discarded — must not crash the
                # WS loop or pollute business state.
                try:
                    evt = EventEnvelope.from_json(data)
                except ValueError as e:
                    logger.warning("realtime malformed event discarded: %s", e)
                    continue
                # Legacy single callback (kept for backward compat).
                if self.on_event:
                    try:
                        self.on_event(evt)
                    except Exception:  # noqa: BLE001
                        pass
                # Multicast listeners (DEF-RT-001): each listener isolated;
                # one crashing must not block others.
                for cb in list(self._event_listeners):
                    try:
                        cb(evt)
                    except Exception:  # noqa: BLE001
                        logger.exception("realtime event listener crashed")
                if evt.type == "connection.ready":
                    self._current_conn_id = evt.payload.get("connection_id")
                    self._set_state(ConnectionState.CONNECTED)
                elif evt.type == "connection.error":
                    if evt.payload.get("code") == "WS_AUTH_FAILED":
                        raise AuthFailedError()
                elif evt.type == "connection.ping":
                    # 心跳回应（§16）。
                    await ws.send(json.dumps(EventEnvelope.pong()))
        except websockets.ConnectionClosed:  # type: ignore[attr-defined]
            raise ConnectionLostError()
        finally:
            self._current_conn_id = None

    async def _try_refresh(self) -> bool:
        try:
            return await self._on_token_expired()
        except Exception:  # noqa: BLE001
            return False

    def _backoff(self) -> float:
        if self._reconnect_attempts < len(_BACKOFF_SCHEDULE):
            delay = _BACKOFF_SCHEDULE[self._reconnect_attempts]
        else:
            delay = _BACKOFF_SCHEDULE[-1]
        self._reconnect_attempts += 1
        return float(delay)
