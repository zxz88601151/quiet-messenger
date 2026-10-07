"""Auth state (Desktop / PySide6, Phase 3B).

A tiny observable-ish state holder. To keep it testable without a QApplication,
we do NOT inherit QObject here; the UI layer (LoginPage / MainWindow) reads
``status`` and subscribes by calling ``on_change`` callbacks. ``loading`` and
``error`` drive UI feedback.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

from .error_mapper import AuthError
from .models import Session
from .repository import AuthRepository


class AuthStatus(str, Enum):
    UNKNOWN = "unknown"
    AUTHENTICATED = "authenticated"
    UNAUTHENTICATED = "unauthenticated"
    LOADING = "loading"


@dataclass
class AuthState:
    status: AuthStatus = AuthStatus.UNKNOWN
    session: Session | None = None
    loading: bool = False
    error: AuthError | None = None
    _listeners: list[Callable[["AuthState"], None]] = field(default_factory=list)

    def subscribe(self, cb: Callable[["AuthState"], None]) -> None:
        self._listeners.append(cb)

    def _emit(self) -> None:
        for cb in self._listeners:
            cb(self)

    def _set(self, **kwargs) -> None:
        for k, v in kwargs.items():
            object.__setattr__(self, k, v)
        self._emit()


class AuthController:
    """Orchestrates [AuthRepository] + [AuthState]. UI calls the actions."""

    def __init__(self, repo: AuthRepository) -> None:
        self.repo = repo
        self.state = AuthState()

    def restore(self) -> None:
        self.state._set(status=AuthStatus.UNKNOWN, error=None)
        restored = self.repo.restore_session()
        if restored is not None:
            self.state._set(session=restored, status=AuthStatus.AUTHENTICATED)
        else:
            self.state._set(session=None, status=AuthStatus.UNAUTHENTICATED)

    def login(self, identifier: str, password: str) -> None:
        self.state._set(loading=True, error=None)
        try:
            session = self.repo.login(identifier=identifier, password=password)
            self.state._set(
                session=session, status=AuthStatus.AUTHENTICATED, loading=False
            )
        except Exception as e:  # noqa: BLE001 - map any repo error
            self._fail(e)

    def register(
        self, username: str, phone: str, password: str, nickname: str
    ) -> None:
        self.state._set(loading=True, error=None)
        try:
            session = self.repo.register(
                username=username, phone=phone, password=password, nickname=nickname
            )
            self.state._set(
                session=session, status=AuthStatus.AUTHENTICATED, loading=False
            )
        except Exception as e:  # noqa: BLE001
            self._fail(e)

    def logout(self) -> None:
        self.state._set(loading=True)
        try:
            self.repo.logout()
        except Exception:  # noqa: BLE001 - clear locally regardless
            pass
        self.state._set(session=None, status=AuthStatus.UNAUTHENTICATED, loading=False)

    def clear_error(self) -> None:
        self.state._set(error=None)

    def update_current_user(self, user) -> None:
        """Replace the current user in the session (e.g. after PATCH /users/me)."""
        if self.state.session is not None:
            from .models import Session
            new_session = Session(user=user, tokens=self.state.session.tokens)
            self.state._set(session=new_session)

    async def refresh_and_return(self) -> bool:
        """WS token-expiry hook: try ONE refresh, return success (bool)."""
        try:
            self.repo.refresh()
            return True
        except Exception:  # noqa: BLE001
            return False

    def _fail(self, e: Exception) -> None:
        from ...errors.api_exception import ApiException
        from .error_mapper import map_auth_error

        if isinstance(e, ApiException):
            err = map_auth_error(e)
        else:
            err = AuthError(message=str(e), code="UNKNOWN")
        self.state._set(error=err, status=AuthStatus.UNAUTHENTICATED, loading=False)
