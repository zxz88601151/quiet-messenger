"""Desktop router — simple stacked-widget navigation (Desktop / PySide6).

Maps sidebar items to pages. Profile is accessible via Settings → 个人资料
but not shown in the sidebar directly.

Phase 2: Profile page added, Settings page functionalized with navigation.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from PySide6.QtWidgets import QStackedWidget

from ..features.chat.chat_page import ChatPage
from ..features.chat.message_repository import MessageRepository
from ..features.chat.repository import ConversationRepository
from ..features.friends.friends_page import FriendsPage
from ..features.friends.state import FriendController
from ..features.devices.devices_page import DevicesPage
from ..features.devices.repository import DeviceRepository
from ..features.settings.settings_page import SettingsPage
from ..features.profile.profile_page import ProfilePage

if TYPE_CHECKING:
    from ..features.auth.repository import AuthRepository
    from ..features.auth.state import AuthController
    from ..realtime.realtime_client import RealtimeClient


class Router:
    # Sidebar navigation indices
    CHAT = 0
    FRIENDS = 1
    DEVICES = 2
    SETTINGS = 3

    def __init__(
        self,
        controller: "AuthController | None" = None,
        auth_repo: "AuthRepository | None" = None,
        friend_controller: FriendController | None = None,
        conversation_repo: ConversationRepository | None = None,
        message_repo: MessageRepository | None = None,
        device_repo: DeviceRepository | None = None,
        presence_controller: Optional[object] = None,
        realtime: "RealtimeClient | None" = None,
        current_user_id: str = "",
    ) -> None:
        self.controller = controller
        self.stack = QStackedWidget()

        # Build pages
        self.chat_page = ChatPage(
            conversation_repo=conversation_repo,
            message_repo=message_repo,
            realtime=realtime,
            current_user_id=current_user_id,
            presence_controller=presence_controller,
        )
        self.friends_page = (
            FriendsPage(friend_controller) if friend_controller else FriendsPage()
        )
        self.devices_page = DevicesPage(repository=device_repo)
        self.profile_page = ProfilePage(controller=controller, repository=auth_repo)
        self.settings_page = SettingsPage(on_navigate=self._on_settings_navigate)

        # Add to stack in sidebar order, then profile (accessible via settings)
        self._pages = [
            self.chat_page,       # 0 CHAT
            self.friends_page,    # 1 FRIENDS
            self.devices_page,    # 2 DEVICES
            self.settings_page,   # 3 SETTINGS
            self.profile_page,    # 4 PROFILE (not in sidebar)
        ]
        for p in self._pages:
            self.stack.addWidget(p)

    def navigate(self, index: int) -> None:
        if 0 <= index < len(self._pages):
            self.stack.setCurrentIndex(index)

    def navigate_to_profile(self) -> None:
        self.stack.setCurrentWidget(self.profile_page)

    def _on_settings_navigate(self, item_index: int) -> None:
        """SettingsPage navigation callback.
        item_index: 0=个人资料, 1=登录设备, 2=关于(handled internally)
        """
        if item_index == SettingsPage.PROFILE:
            self.navigate_to_profile()
        elif item_index == SettingsPage.DEVICES:
            self.navigate(self.DEVICES)
