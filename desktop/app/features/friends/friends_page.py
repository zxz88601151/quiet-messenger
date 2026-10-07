"""Friends list — real data (Desktop / PySide6, Phase 3D).

Shows the current user's friend list + search entry + pending requests. Driven
by [FriendController] (UI ≠ Repository). Conversation entry is wired via the
accept flow (see chat_page / request dialog). Keeps raw Qt styling in
widgets.common; no network calls here.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QSize
from PySide6.QtWidgets import (
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QHBoxLayout,
    QVBoxLayout,
    QMessageBox,
    QTabWidget,
    QFrame,
)

from ...widgets.common import Page, primary_button, text_field, section_title
from ...theme import colors as C
from ...theme import typography as T
from .state import FriendController, FriendStatus
from .models import FriendRequest, Friendship, UserSummary


class FriendsPage(Page):
    def __init__(self, controller: FriendController | None = None) -> None:
        super().__init__()
        self._controller = controller
        if controller is not None:
            self._controller.state.subscribe(self._on_state)

        self.layout.addWidget(section_title("好友"))

        # Search row
        self.search_input = text_field("手机号 / 用户 ID")
        self.search_btn = primary_button("搜索")
        self.search_btn.clicked.connect(self._on_search)
        search_row = QHBoxLayout()
        search_row.addWidget(self.search_input, 1)
        search_row.addWidget(self.search_btn)
        self.layout.addLayout(search_row)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet(f"color:{C.TEXT_3};font-size:{T.SIZE_CAPTION}px;")
        self.layout.addWidget(self.status_label)

        # Tabs: Friends / Requests
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(
            f"QTabWidget::pane{{border:1px solid {C.BORDER};border-radius:{T.R_LG}px;}}"
            f"QTabBar::tab{{padding:8px 16px;color:{C.TEXT_2};font-size:{T.SIZE_BODY}px;}}"
            f"QTabBar::tab:selected{{color:{C.PRIMARY};font-weight:{T.WEIGHT_MEDIUM};}}"
        )
        self.friend_list = QListWidget()
        self.request_list = QListWidget()
        self.tabs.addTab(self.friend_list, "好友")
        self.tabs.addTab(self.request_list, "请求")
        self.layout.addWidget(self.tabs, 1)

        # Initial load (requests + friends) only when wired to a controller.
        if self._controller is not None:
            self._controller.load_requests()
            self._controller.load_friends()

    def _on_state(self, state) -> None:
        self.status_label.setText(state.error.message if state.error else "")
        self._render_friends(state.friends)
        self._render_requests(state.requests)

    def _on_search(self) -> None:
        q = self.search_input.text().strip()
        if not q:
            return
        self._controller.search(q)
        state = self._controller.state
        # Search results shown in a transient message box (no dedicated panel).
        if state.error:
            QMessageBox.information(self, "搜索", state.error.message)
            return
        if not state.search_results:
            QMessageBox.information(self, "搜索", "未找到用户")
            return
        lines = "\n".join(
            f"{u.nickname or u.username} (@{u.username})" for u in state.search_results
        )
        reply = QMessageBox.question(
            self, "搜索结果", f"{lines}\n\n发送好友请求？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            target = state.search_results[0].username
            if self._controller.send_request(target):
                QMessageBox.information(self, "已发送", "好友请求已发送")
                self._controller.load_requests()

    def _render_friends(self, friends: list[Friendship]) -> None:
        self.friend_list.clear()
        if not friends:
            # Empty state with CTA
            empty_widget = QFrame()
            empty_layout = QVBoxLayout(empty_widget)
            empty_layout.setAlignment(Qt.AlignCenter)
            empty_layout.setSpacing(12)
            empty_label = QLabel("还没有好友")
            empty_label.setAlignment(Qt.AlignCenter)
            empty_label.setStyleSheet(f"color:{C.TEXT_3};font-size:{T.SIZE_BODY}px;")
            empty_layout.addWidget(empty_label)
            add_btn = primary_button("添加好友")
            add_btn.clicked.connect(self._focus_search)
            btn_row = QHBoxLayout()
            btn_row.addStretch()
            btn_row.addWidget(add_btn)
            btn_row.addStretch()
            empty_layout.addLayout(btn_row)
            item = QListWidgetItem(self.friend_list)
            item.setSizeHint(QSize(self.friend_list.width(), 140))
            self.friend_list.addItem(item)
            self.friend_list.setItemWidget(item, empty_widget)
            return
        for f in friends:
            name = f.user.nickname or f.user.username
            self.friend_list.addItem(QListWidgetItem(f"{name}  (@{f.user.username})"))

    def _focus_search(self) -> None:
        """Focus the search input to guide user to add a friend."""
        self.search_input.setFocus()
        self.search_input.selectAll()

    def _render_requests(self, requests: list[FriendRequest]) -> None:
        self.request_list.clear()
        for r in requests:
            name = (r.other_user.nickname if r.other_user and r.other_user.nickname
                    else (r.other_user.username if r.other_user else "用户"))
            if r.is_incoming:
                item = QListWidgetItem(f"{name}  → 请求添加你")
                self.request_list.addItem(item)
                # Accept / Reject buttons via item widget
                self._attach_request_actions(r, name)
            else:
                self.request_list.addItem(QListWidgetItem(f"你 → {name} (已发送)"))

    def _attach_request_actions(self, req: FriendRequest, name: str) -> None:
        row = QListWidgetItem()
        self.request_list.addItem(row)
        widget = QFrame()
        h = QHBoxLayout(widget)
        h.addWidget(QLabel(name))
        accept = QPushButton("接受")
        reject = QPushButton("拒绝")
        accept.clicked.connect(lambda: self._on_accept(req))
        reject.clicked.connect(lambda: self._on_reject(req))
        h.addWidget(accept)
        h.addWidget(reject)
        self.request_list.setItemWidget(row, widget)

    def _on_accept(self, req: FriendRequest) -> None:
        if self._controller.accept(req.id):
            conv_id = self._controller.state.last_accepted_conversation_id
            msg = "已添加为好友"
            if conv_id:
                msg += f"，可进入会话 {conv_id[:8]}…"
            QMessageBox.information(self, "已添加", msg)
            self._controller.load_friends()
            self._controller.load_requests()

    def _on_reject(self, req: FriendRequest) -> None:
        if self._controller.reject(req.id):
            QMessageBox.information(self, "已拒绝", "已拒绝该请求")
            self._controller.load_requests()
