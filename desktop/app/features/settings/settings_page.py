"""Settings — functional navigation list (Desktop / PySide6, Phase 2).

Replaces static placeholder with real navigation entries:
- 个人资料 → Profile page
- 登录设备 → Devices page
- 关于 → About dialog
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtWidgets import (
    QListWidget,
    QListWidgetItem,
    QLabel,
    QMessageBox,
)

from ...widgets.common import Page
from ...theme import colors as C
from ...theme import typography as T


class SettingsPage(Page):
    # Navigation indices
    PROFILE = 0
    DEVICES = 1
    ABOUT = 2

    def __init__(self, on_navigate: Callable[[int], None] | None = None) -> None:
        super().__init__()
        self._on_navigate = on_navigate

        head = QLabel("设置")
        head.setStyleSheet(
            f"font-size:{T.SIZE_TITLE}px;font-weight:{T.WEIGHT_BOLD};"
        )
        self.layout.addWidget(head)

        self._list = QListWidget()
        self._list.setStyleSheet(
            f"QListWidget{{background:{C.BG};border:1px solid {C.BORDER};"
            f"border-radius:{T.R_LG}px;}}"
            f"QListWidget::item{{padding:14px 16px;border-bottom:1px solid {C.BORDER};"
            f"font-size:{T.SIZE_BODY}px;}}"
            f"QListWidget::item:hover{{background:{C.PRIMARY_LIGHT};}}"
        )
        for label in ("个人资料", "登录设备", "关于"):
            self._list.addItem(QListWidgetItem(label))
        self._list.itemClicked.connect(self._on_item_clicked)
        self.layout.addWidget(self._list, 1)

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        row = self._list.row(item)
        if row == self.ABOUT:
            self._show_about()
        elif self._on_navigate is not None:
            self._on_navigate(row)
        # Clear selection so the same item can be clicked again
        self._list.clearSelection()

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            "关于 Quiet Messenger",
            "Quiet Messenger v1.1\n\n"
            "极简私人通讯 · 安静、可靠、只属于你。\n\n"
            "支持 Android + Windows Desktop 跨端实时通信。",
        )
