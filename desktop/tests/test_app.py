"""Desktop foundation + Auth tests (PySide6, Phase 3A + 3B).

Phase 3A: (1) imports resolve, (2) app constructs + shows under offscreen
platform, (3) pages build without raising, (4) token storage round-trips.
Phase 3B: (5) AuthController login success/failure, (6) logout clears
tokens, (7) session restore, (8) error mapping. All auth logic is exercised
against an in-memory fake repository so tests need NO network/backend.

Run: pytest tests/
"""

from __future__ import annotations

import os
import sys

import pytest

from app.features.auth.state import AuthController, AuthStatus
from app.features.auth.models import Session, User, AuthTokens, DeviceInfo
from app.features.auth.error_mapper import map_auth_error
from app.errors.api_exception import ApiException


# --- In-memory fake repository (no network) -------------------------------
class FakeAuthRepository:
    """Stand-in for AuthRepository; drives AuthController without backend."""

    def __init__(self, fail_login: bool = False) -> None:
        self.fail_login = fail_login
        self.logged_out = False
        self.restored = False
        self._refresh = "refresh-token"

    def login(self, identifier: str, password: str, device=None) -> Session:
        if self.fail_login or not password:
            raise ApiException(code="INVALID_CREDENTIALS", message="bad")
        return Session(
            user=User(id="u1", username=identifier, phone="123456", nickname="n"),
            tokens=AuthTokens(access_token="a", refresh_token=self._refresh),
        )

    def register(self, username, phone, password, nickname, device=None) -> Session:
        return Session(
            user=User(id="u1", username=username, phone=phone, nickname=nickname),
            tokens=AuthTokens(access_token="a", refresh_token=self._refresh),
        )

    def logout(self) -> None:
        self.logged_out = True

    def restore_session(self):
        self.restored = True
        return None  # simulate no saved session

    def refresh(self) -> AuthTokens:
        return AuthTokens(access_token="a2", refresh_token="r2")

    def get_current_user(self) -> User:
        return User(id="u1", username="x", phone="1", nickname="n")

    def forgot_password(self, phone: str) -> None:
        pass

    def reset_password(self, phone, code, new_password) -> None:
        pass


def _qt_app():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication(sys.argv)


def _fake_controller(fail_login: bool = False) -> AuthController:
    return AuthController(FakeAuthRepository(fail_login=fail_login))


def test_imports():
    from app.main import MainWindow, LoginWindow
    from app.router.router import Router
    from app.api.api_client import ApiClient
    from app.storage.token_storage import TokenStorage
    from app.features.auth.repository import AuthRepository
    from app.features.auth.state import AuthController

    assert MainWindow is not None
    assert LoginWindow is not None
    assert Router is not None
    assert ApiClient is not None
    assert TokenStorage is not None
    assert AuthRepository is not None
    assert AuthController is not None


def test_main_window_builds():
    _qt_app()
    from app.main import MainWindow

    ctrl = _fake_controller()
    win = MainWindow(ctrl)
    win.show()
    assert win.router.stack.count() == 5  # chat/friends/devices/settings/profile


def test_login_window_builds():
    _qt_app()
    from app.main import LoginWindow

    ctrl = _fake_controller()
    win = LoginWindow(ctrl)
    win.show()
    assert win._page is not None


def test_pages_build():
    _qt_app()
    from app.features.auth.login_page import LoginPage
    from app.features.chat.chat_page import ChatPage
    from app.features.friends.friends_page import FriendsPage
    from app.features.devices.devices_page import DevicesPage
    from app.features.settings.settings_page import SettingsPage

    ctrl = _fake_controller()
    for cls, *args in (
        (LoginPage, ctrl),
        (ChatPage,),
        (FriendsPage,),
        (DevicesPage,),
        (SettingsPage,),
    ):
        page = cls(*args)
        assert page is not None


def test_token_storage_roundtrip():
    from app.storage.token_storage import TokenStorage

    ts = TokenStorage()
    ts.set_tokens(access="a", refresh="r")
    assert ts.get_access_token() == "a"
    assert ts.get_refresh_token() == "r"
    ts.clear()
    assert ts.get_access_token() is None


# --- Phase 3B auth logic (no network) --------------------------------------
def test_auth_login_success():
    ctrl = _fake_controller()
    ctrl.login("alice", "secret")
    assert ctrl.state.status == AuthStatus.AUTHENTICATED
    assert ctrl.state.session is not None
    assert ctrl.state.error is None


def test_auth_login_failure_maps_error():
    ctrl = _fake_controller(fail_login=True)
    ctrl.login("alice", "wrong")
    assert ctrl.state.status == AuthStatus.UNAUTHENTICATED
    assert ctrl.state.error is not None
    assert ctrl.state.error.code == "INVALID_CREDENTIALS"


def test_auth_logout_clears_session():
    ctrl = _fake_controller()
    ctrl.login("alice", "secret")
    assert ctrl.state.status == AuthStatus.AUTHENTICATED
    ctrl.logout()
    assert ctrl.state.status == AuthStatus.UNAUTHENTICATED
    assert ctrl.state.session is None
    # repository received logout call (best-effort backend revoke)
    assert ctrl.repo.logged_out is True


def test_auth_restore_no_session():
    ctrl = _fake_controller()
    ctrl.restore()
    assert ctrl.state.status == AuthStatus.UNAUTHENTICATED
    assert ctrl.repo.restored is True


def test_error_mapping_user_facing():
    err = map_auth_error(ApiException(code="INVALID_CREDENTIALS", message="x"))
    assert "密码" in err.message
    assert "DioException" not in err.message
    net = map_auth_error(ApiException(code="NETWORK_ERROR", message="boom"))
    assert "网络" in net.message
