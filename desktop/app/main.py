"""Desktop application entrypoint (Desktop / PySide6, Phase 3B).

Flow: show [LoginWindow] first; on successful auth (AuthController emits
AUTHENTICATED) swap to [MainWindow]. Logout returns to login. UI ≠ API ≠
Domain: all network calls live in AuthRepository / AuthController.

Runs headless under QT_QPA_PLATFORM=offscreen for tests.
"""

from __future__ import annotations

import os
import sys

from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QListWidget,
    QListWidgetItem,
    QHBoxLayout,
    QLabel,
)
from PySide6.QtCore import Qt

from .router.router import Router
from .theme import colors as C
from .theme import typography as T
from .api.api_client import ApiClient
from .api.api_config import ApiConfig
from .storage.token_storage import TokenStorage
from .features.auth.repository import AuthRepository
from .features.auth.state import AuthController, AuthStatus
from .features.friends.state import FriendController
from .features.presence import PresenceController
from .features.chat.repository import ConversationRepository
from .features.chat.message_repository import MessageRepository
from .features.auth.login_page import LoginPage
from .features.friends.repository import FriendRepository
from .features.devices.repository import DeviceRepository
from .realtime.realtime_client import RealtimeClient


class LoginWindow(QMainWindow):
    def __init__(self, controller: AuthController) -> None:
        super().__init__()
        self.setWindowTitle("极简私人通讯 · 登录")
        self.resize(920, 620)
        self.setStyleSheet(f"background:{C.CANVAS};")
        self._controller = controller
        self._page = LoginPage(controller)
        self.setCentralWidget(self._page)
        # When auth succeeds, signal the app to open the main window.
        controller.state.subscribe(self._on_state)

    def _on_state(self, state) -> None:
        if state.status == AuthStatus.AUTHENTICATED:
            self.authenticated = True
            self.close()


class MainWindow(QMainWindow):
    def __init__(
        self,
        controller: AuthController,
        auth_repo: "AuthRepository | None" = None,
        friend_controller: FriendController | None = None,
        conversation_repo: ConversationRepository | None = None,
        message_repo: MessageRepository | None = None,
        device_repo: "DeviceRepository | None" = None,
        presence_controller: "PresenceController | None" = None,
        realtime: "RealtimeClient | None" = None,
        current_user_id: str = "",
    ) -> None:
        super().__init__()
        self.setWindowTitle("极简私人通讯")
        self.resize(1000, 680)
        self.setStyleSheet(f"background:{C.CANVAS};")
        self._controller = controller

        root = QWidget()
        self.setCentralWidget(root)
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ---- Sidebar ----
        sidebar = QListWidget()
        sidebar.setFixedWidth(200)
        sidebar.setStyleSheet(
            f"QListWidget{{background:{C.SURFACE};border:none;"
            f"border-right:1px solid {C.BORDER};}}"
            f"QListWidget::item{{padding:12px 16px;color:{C.TEXT_2};"
            f"font-size:{T.SIZE_BODY}px;}}"
            f"QListWidget::item:selected{{background:{C.PRIMARY_LIGHT};"
            f"color:{C.PRIMARY};font-weight:{T.WEIGHT_MEDIUM};}}"
        )
        for label in ("聊天", "好友", "设备", "设置", "退出登录"):
            sidebar.addItem(QListWidgetItem(label))
        sidebar.setCurrentRow(0)
        layout.addWidget(sidebar)

        # ---- Router (central) ----
        self.router = Router(
            controller,
            auth_repo=auth_repo,
            friend_controller=friend_controller,
            conversation_repo=conversation_repo,
            message_repo=message_repo,
            device_repo=device_repo,
            presence_controller=presence_controller,
            realtime=realtime,
            current_user_id=current_user_id,
        )
        layout.addWidget(self.router.stack, 1)

        sidebar.currentRowChanged.connect(self._on_nav)

    def _on_nav(self, index: int) -> None:
        # Last item (index 4) is "退出登录".
        if index == 4:
            self._confirm_logout()
            return
        self.router.navigate(index)

    def _confirm_logout(self) -> None:
        from PySide6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self,
            "退出登录",
            "确定要退出当前账号吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self._controller.logout()
            self.close()


def main() -> int:
    # NOTE: QT_QPA_PLATFORM=offscreen must be set explicitly by the test
    # runner (e.g. pytest conftest or CI env). Do NOT default to offscreen
    # here — it would hide the GUI on normal desktop launches.
    app = QApplication(sys.argv)
    app.setStyleSheet("QWidget{font-family:'Segoe UI',system-ui;}")

    token_storage = TokenStorage()
    api = ApiClient(token_storage=token_storage)
    repo = AuthRepository(api, token_storage)
    controller = AuthController(repo)
    controller.restore()  # restore session from secure storage on start

    # Phase 3D: build friends/chat repositories + controllers from the same
    # ApiClient/TokenStorage. current_user_id comes from the restored session.
    current_user_id = ""
    if controller.state.session and controller.state.session.user:
        current_user_id = controller.state.session.user.id
    friend_repo = FriendRepository(api, token_storage, current_user_id=current_user_id)
    conversation_repo = ConversationRepository(api)
    message_repo = MessageRepository(api)
    device_repo = DeviceRepository(api)
    realtime = RealtimeClient(
        base_url=ApiConfig.base_url(),
        get_token=lambda: token_storage.get_access_token(),  # type: ignore[arg-type]
        on_token_expired=lambda: controller.refresh_and_return(),  # type: ignore[arg-type]
        on_event=lambda _evt: None,
    )
    # Controllers that subscribe to realtime must be created AFTER realtime.
    friend_controller = FriendController(friend_repo, realtime=realtime, current_user_id=current_user_id)
    presence_controller = PresenceController(realtime=realtime, current_user_id=current_user_id)

    # DEF-RT-003: Drive RealtimeClient lifecycle from AuthState.
    # - Logout (UNAUTHENTICATED): disconnect WS, cancel reconnect timers.
    # - Re-login (AUTHENTICATED): open a NEW WS connection.
    _last_auth_status = controller.state.status

    def _on_auth_state(state) -> None:
        nonlocal _last_auth_status
        if state.status == _last_auth_status:
            return
        if state.status == AuthStatus.UNAUTHENTICATED:
            realtime.disconnect()
            presence_controller.current_user_id = ""
        elif state.status == AuthStatus.AUTHENTICATED:
            realtime.connect()
            if state.session and state.session.user:
                presence_controller.current_user_id = state.session.user.id
        _last_auth_status = state.status

    controller.state.subscribe(_on_auth_state)

    if controller.state.status == AuthStatus.AUTHENTICATED:
        realtime.connect()

    if controller.state.status == AuthStatus.AUTHENTICATED:
        win = MainWindow(
            controller,
            auth_repo=repo,
            friend_controller=friend_controller,
            conversation_repo=conversation_repo,
            message_repo=message_repo,
            device_repo=device_repo,
            presence_controller=presence_controller,
            realtime=realtime,
            current_user_id=current_user_id,
        )
    else:
        win = LoginWindow(controller)

    win.show()

    # On login success, swap to main window.
    def _maybe_swap() -> None:
        if isinstance(win, LoginWindow) and win.authenticated:
            main_win = MainWindow(
                controller,
                auth_repo=repo,
                friend_controller=friend_controller,
                conversation_repo=conversation_repo,
                message_repo=message_repo,
                device_repo=device_repo,
                presence_controller=presence_controller,
                realtime=realtime,
                current_user_id=current_user_id,
            )
            main_win.show()

    # Use a single-shot timer to check after the event loop processes close.
    from PySide6.QtCore import QTimer

    timer = QTimer()
    timer.setInterval(50)
    timer.timeout.connect(_maybe_swap)
    timer.start()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
