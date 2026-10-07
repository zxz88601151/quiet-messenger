"""Chat window — Phase 2B Desktop UX Refinement (Desktop / PySide6).

Improvements over Phase 3E minimum:
- Chat header: Avatar + Nickname + Presence online indicator
- Date grouping: Today / Yesterday / YYYY-MM-DD separators
- New message indicator: "↓ N new messages" when reading history
- Reconnect banner: connection state from RealtimeClient
- Message status: sending / sent / failed with explicit Retry button
- Scroll behavior: auto-scroll only when at bottom
- Right-click copy: context menu on message bubbles
- Empty state: refined
- Error state: retry button

NOT implemented (out of scope / blocked):
- Typing, read receipt, reaction, reply, edit, recall
- Image/file/voice/video (backend no media storage — BLOCKED)
- Delete message (backend no DELETE — BLOCKED)
- Group chat, AI, push
"""
from __future__ import annotations

from datetime import datetime, date
from typing import Optional

from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtGui import QFont, QAction
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ...realtime.connection_state import ConnectionState
from ...realtime.realtime_client import RealtimeClient
from ...theme import colors as C
from ...theme import spacing as S
from ...theme import typography as T
from ...widgets.common import Page, primary_button, section_title
from .message_models import Message, MessageUiState, is_own_message
from .message_repository import MessageRepository
from .message_state import MessageController


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _format_date_group(dt: datetime) -> str:
    """Return date group label: Today / Yesterday / YYYY-MM-DD."""
    today = date.today()
    msg_date = dt.date()
    if msg_date == today:
        return "Today"
    from datetime import timedelta
    if msg_date == today - timedelta(days=1):
        return "Yesterday"
    return msg_date.strftime("%Y-%m-%d")


def _avatar_widget(name: str, size: int = S.AVATAR_MD) -> QLabel:
    """Create a circular avatar with initial letter."""
    initial = name[0].upper() if name else "?"
    avatar = QLabel(initial)
    avatar.setFixedSize(size, size)
    avatar.setAlignment(Qt.AlignCenter)
    avatar.setStyleSheet(
        f"background:{C.PRIMARY_LIGHT};color:{C.PRIMARY};"
        f"border-radius:{size // 2}px;font-size:{size // 2}px;"
        f"font-weight:{T.WEIGHT_BOLD};"
    )
    return avatar


# ---------------------------------------------------------------------------
# Date separator
# ---------------------------------------------------------------------------

class _DateSeparator(QWidget):
    def __init__(self, label: str, parent=None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, S.SM, 0, S.SM)
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet(f"color:{C.BORDER};")
        text = QLabel(label)
        text.setStyleSheet(f"color:{C.TEXT_3};font-size:{T.SIZE_CAPTION}px;padding:0 8px;")
        layout.addWidget(line, 1)
        layout.addWidget(text)
        layout.addWidget(line, 1)


# ---------------------------------------------------------------------------
# Message bubble
# ---------------------------------------------------------------------------

class _BubbleWidget(QWidget):
    """A single message bubble with text + timestamp + status + retry."""

    def __init__(self, message: Message, current_user_id: str, on_retry=None, parent=None) -> None:
        super().__init__(parent)
        self.message = message
        self._on_retry = on_retry
        mine = is_own_message(message, current_user_id)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(S.SM, S.XS, S.SM, S.XS)
        layout.setSpacing(0)

        # Bubble container
        bubble = QFrame()
        bubble.setMaximumWidth(420)
        bubble_layout = QVBoxLayout(bubble)
        bubble_layout.setContentsMargins(S.LG, S.SM, S.LG, S.XS)
        bubble_layout.setSpacing(2)

        # Message text (selectable + right-click copy)
        text_label = QLabel(message.content)
        text_label.setWordWrap(True)
        text_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        text_label.setContextMenuPolicy(Qt.CustomContextMenu)
        text_label.customContextMenuRequested.connect(lambda pos: self._show_context_menu(text_label, pos))
        text_label.setStyleSheet(
            f"color:{'white' if mine else C.TEXT};font-size:{T.SIZE_BODY}px;"
            f"line-height:1.4;"
        )
        bubble_layout.addWidget(text_label)

        # Timestamp + status row
        status_row = QHBoxLayout()
        status_row.setSpacing(4)

        time_str = ""
        if message.created_at is not None:
            time_str = message.created_at.strftime("%H:%M")

        if mine and message.ui_state == MessageUiState.SENDING:
            status_label = QLabel(f"{time_str}  发送中…")
            status_label.setStyleSheet(f"color:{C.TEXT_3};font-size:{T.SIZE_CAPTION - 1}px;")
            status_row.addWidget(status_label)
        elif mine and message.ui_state == MessageUiState.FAILED:
            status_label = QLabel(f"{time_str}  失败")
            status_label.setStyleSheet(f"color:{C.ERROR};font-size:{T.SIZE_CAPTION - 1}px;")
            status_row.addWidget(status_label)
            retry_btn = QPushButton("重试")
            retry_btn.setFlat(True)
            retry_btn.setStyleSheet(
                f"QPushButton{{color:{C.PRIMARY};font-size:{T.SIZE_CAPTION}px;padding:0 4px;}}"
                f"QPushButton:hover{{text-decoration:underline;}}"
            )
            retry_btn.clicked.connect(lambda: self._on_retry and self._on_retry(message))
            status_row.addWidget(retry_btn)
        else:
            status_label = QLabel(time_str)
            status_label.setStyleSheet(f"color:{C.TEXT_3};font-size:{T.SIZE_CAPTION - 1}px;")
            status_row.addWidget(status_label)

        status_row.addStretch()
        bubble_layout.addLayout(status_row)

        # Bubble styling
        bg_color = C.PRIMARY if mine else C.BG
        border = f"1px solid {C.BORDER}" if not mine else "none"
        bubble.setStyleSheet(
            f"QFrame{{background:{bg_color};border-radius:12px;border:{border};}}"
        )

        # Alignment
        if mine:
            layout.addStretch()
            layout.addWidget(bubble)
        else:
            layout.addWidget(bubble)
            layout.addStretch()

        self.setMinimumHeight(bubble.sizeHint().height() + S.SM)

    def _show_context_menu(self, label: QLabel, pos) -> None:
        menu = QMenu(self)
        copy_action = QAction("复制", self)
        copy_action.triggered.connect(lambda: _copy_to_clipboard(label.text()))
        menu.addAction(copy_action)
        menu.exec(label.mapToGlobal(pos))


def _copy_to_clipboard(text: str) -> None:
    from PySide6.QtWidgets import QApplication
    QApplication.clipboard().setText(text)


# ---------------------------------------------------------------------------
# Chat header
# ---------------------------------------------------------------------------

class _ChatHeader(QWidget):
    """Chat header: Avatar + Nickname + Presence indicator."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(S.HEADER_HEIGHT)
        self.setStyleSheet(f"background:{C.BG};border-bottom:1px solid {C.BORDER};")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(S.MD, S.SM, S.MD, S.SM)
        layout.setSpacing(S.SM)

        self._avatar = _avatar_widget("?", S.AVATAR_MD)
        layout.addWidget(self._avatar)

        text_col = QVBoxLayout()
        text_col.setSpacing(0)
        self._name = QLabel("选择一个会话")
        self._name.setStyleSheet(f"font-size:{T.SIZE_BODY}px;font-weight:{T.WEIGHT_MEDIUM};color:{C.TEXT};")
        self._presence = QLabel("")
        self._presence.setStyleSheet(f"font-size:{T.SIZE_CAPTION}px;color:{C.TEXT_3};")
        text_col.addWidget(self._name)
        text_col.addWidget(self._presence)
        layout.addLayout(text_col, 1)

    def set_peer(self, name: str, avatar_url: Optional[str] = None) -> None:
        initial = name[0].upper() if name else "?"
        self._avatar.setText(initial)
        self._name.setText(name)

    def set_presence(self, online: bool) -> None:
        if online:
            self._presence.setText("● 在线")
            self._presence.setStyleSheet(f"font-size:{T.SIZE_CAPTION}px;color:{C.SUCCESS};")
        else:
            self._presence.setText("离线")
            self._presence.setStyleSheet(f"font-size:{T.SIZE_CAPTION}px;color:{C.TEXT_3};")


# ---------------------------------------------------------------------------
# Reconnect banner
# ---------------------------------------------------------------------------

class _ReconnectBanner(QFrame):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"background:{C.PRIMARY_LIGHT};border-bottom:1px solid {C.BORDER};")
        self.setVisible(False)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(S.MD, S.XS, S.MD, S.XS)
        self._label = QLabel("")
        self._label.setStyleSheet(f"color:{C.PRIMARY};font-size:{T.SIZE_CAPTION}px;")
        layout.addWidget(self._label)
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide)

    def show_reconnecting(self) -> None:
        self._label.setText("连接已断开，正在重连…")
        self.setVisible(True)
        self._hide_timer.stop()

    def show_connected(self) -> None:
        self._label.setText("已连接")
        self.setVisible(True)
        self._hide_timer.start(2000)  # auto-hide after 2s


# ---------------------------------------------------------------------------
# New message indicator
# ---------------------------------------------------------------------------

class _NewMessageIndicator(QPushButton):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setVisible(False)
        self.setStyleSheet(
            f"QPushButton{{background:{C.PRIMARY};color:white;border:none;"
            f"border-radius:16px;padding:6px 14px;font-size:{T.SIZE_CAPTION}px;}}"
            f"QPushButton:hover{{background:{C.PRIMARY_HOVER};}}"
        )

    def show_count(self, count: int) -> None:
        if count <= 0:
            self.setVisible(False)
            return
        self.setText(f"↓ {count} 条新消息")
        self.setVisible(True)


# ---------------------------------------------------------------------------
# Main ChatPage
# ---------------------------------------------------------------------------

class ChatPage(Page):
    def __init__(
        self,
        conversation_repo: Optional[object] = None,
        message_repo: Optional[MessageRepository] = None,
        realtime: Optional[RealtimeClient] = None,
        current_user_id: str = "",
        presence_controller: Optional[object] = None,
    ) -> None:
        super().__init__()
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        self._conv_repo = conversation_repo
        self._msg_repo = message_repo
        self._realtime = realtime
        self._current_user_id = current_user_id
        self._presence = presence_controller
        self._controller: Optional[MessageController] = None
        self._conversations: list = []
        self._current_peer_id: Optional[str] = None
        self._new_message_count = 0
        self._user_scrolled_up = False

        # --- Top bar: conversation picker ---
        top_bar = QWidget()
        top_bar.setStyleSheet(f"background:{C.CANVAS};")
        top_layout = QVBoxLayout(top_bar)
        top_layout.setContentsMargins(S.LG, S.SM, S.LG, S.SM)
        top_layout.setSpacing(S.XS)

        picker_label = QLabel("会话")
        picker_label.setStyleSheet(f"font-size:{T.SIZE_CAPTION}px;color:{C.TEXT_3};")
        top_layout.addWidget(picker_label)

        self.conv_list = QListWidget()
        self.conv_list.setMaximumHeight(100)
        self.conv_list.setStyleSheet(
            f"QListWidget{{background:{C.BG};border:1px solid {C.BORDER};"
            f"border-radius:{T.R_MD}px;}}"
            f"QListWidget::item{{padding:6px 10px;font-size:{T.SIZE_BODY}px;}}"
            f"QListWidget::item:selected{{background:{C.PRIMARY_LIGHT};color:{C.PRIMARY};}}"
        )
        self.conv_list.itemClicked.connect(self._on_open_conversation)
        top_layout.addWidget(self.conv_list)
        self.layout.addWidget(top_bar)

        # --- Chat header ---
        self.chat_header = _ChatHeader()
        self.layout.addWidget(self.chat_header)

        # --- Reconnect banner ---
        self.reconnect_banner = _ReconnectBanner()
        self.layout.addWidget(self.reconnect_banner)

        # --- Message area ---
        msg_container = QWidget()
        msg_layout = QVBoxLayout(msg_container)
        msg_layout.setContentsMargins(0, 0, 0, 0)
        msg_layout.setSpacing(0)

        self.msg_list = QListWidget()
        self.msg_list.setStyleSheet(
            f"QListWidget{{background:{C.CANVAS};border:none;}}"
        )
        self.msg_list.setSpacing(0)
        self.msg_list.verticalScrollBar().valueChanged.connect(self._on_scroll)
        msg_layout.addWidget(self.msg_list, 1)

        # New message indicator (floating)
        self.new_msg_indicator = _NewMessageIndicator(msg_container)
        self.new_msg_indicator.clicked.connect(self._scroll_to_bottom)
        # Position it above the composer
        self.new_msg_indicator.move(20, 0)  # will be repositioned on resize

        self.layout.addWidget(msg_container, 1)

        # --- Composer ---
        composer = QWidget()
        composer.setStyleSheet(f"background:{C.CANVAS};border-top:1px solid {C.BORDER};")
        bar = QHBoxLayout(composer)
        bar.setContentsMargins(S.MD, S.SM, S.MD, S.SM)
        bar.setSpacing(S.SM)

        self.input = QTextEdit()
        self.input.setPlaceholderText("发条消息…")
        self.input.setMaximumHeight(S.INPUT_MAX_HEIGHT)
        self.input.setMinimumHeight(S.INPUT_MIN_HEIGHT)
        self.input.setStyleSheet(
            f"QTextEdit{{border:1px solid {C.BORDER};border-radius:{T.R_MD}px;"
            f"padding:6px 10px;font-size:{T.SIZE_BODY}px;background:{C.BG};}}"
            f"QTextEdit:focus{{border:1.5px solid {C.PRIMARY};}}"
        )
        bar.addWidget(self.input, 1)

        self.send_btn = primary_button("发送")
        self.send_btn.clicked.connect(self._on_send)
        self.send_btn.setEnabled(False)
        bar.addWidget(self.send_btn)
        self.layout.addWidget(composer)

        self.input.textChanged.connect(self._update_send_enabled)

        # Subscribe to realtime connection state
        if self._realtime is not None:
            self._realtime.add_state_listener(self._on_connection_state)

        if self._conv_repo is not None:
            self._load_conversations()

    # --- Conversation loading ---
    def _load_conversations(self) -> None:
        try:
            self._conversations = self._conv_repo.get_conversations()
            self._render_conv_list()
        except Exception as e:  # noqa: BLE001
            self.conv_list.clear()
            self.conv_list.addItem(QListWidgetItem(f"加载会话失败：{str(e)[:50]}"))

    def _render_conv_list(self) -> None:
        self.conv_list.clear()
        if not self._conversations:
            self.conv_list.addItem(QListWidgetItem("还没有会话，去添加好友吧"))
            return
        for c in self._conversations:
            name = c.peer.nickname or c.peer.username
            preview = c.last_message_preview or "会话已建立"
            self.conv_list.addItem(QListWidgetItem(f"{name} — {preview}"))

    # --- Open conversation ---
    def _on_open_conversation(self, item: QListWidgetItem) -> None:
        idx = self.conv_list.row(item)
        if idx < 0 or idx >= len(self._conversations):
            return
        conv = self._conversations[idx]
        self._open_conversation(str(conv.id), conv)

    def _open_conversation(self, conversation_id: str, conv=None) -> None:
        if self._msg_repo is None or self._realtime is None:
            return
        if self._controller is not None:
            try:
                self._controller.unsubscribe(self._on_state)
                self._controller.dispose()
            except Exception:  # noqa: BLE001
                pass

        # Update header
        if conv is not None:
            name = conv.peer.nickname or conv.peer.username
            self._current_peer_id = str(conv.peer.id)
            self.chat_header.set_peer(name, conv.peer.avatar)
            # Try to get presence
            self._update_presence()

        self._new_message_count = 0
        self.new_msg_indicator.setVisible(False)

        self._controller = MessageController(
            repository=self._msg_repo,
            realtime=self._realtime,
            current_user_id=self._current_user_id,
            conversation_id=conversation_id,
        )
        self._controller.subscribe(self._on_state)
        self._controller.load()

    def _update_presence(self) -> None:
        if self._presence is None or self._current_peer_id is None:
            return
        try:
            online = self._presence.state.is_online(self._current_peer_id)
            self.chat_header.set_presence(online)
        except Exception:  # noqa: BLE001
            pass

    # --- Connection state ---
    def _on_connection_state(self, state) -> None:
        state_name = getattr(state, "name", str(state)).lower()
        if state_name in ("disconnected", "reconnecting"):
            self.reconnect_banner.show_reconnecting()
        elif state_name == "connected":
            self.reconnect_banner.show_connected()
            self._update_presence()

    # --- State callback ---
    def _on_state(self) -> None:
        self._render_messages()

    # --- Scroll detection ---
    def _on_scroll(self, value: int) -> None:
        scrollbar = self.msg_list.verticalScrollBar()
        at_bottom = value >= scrollbar.maximum() - 5
        if at_bottom:
            self._user_scrolled_up = False
            self._new_message_count = 0
            self.new_msg_indicator.setVisible(False)
        else:
            self._user_scrolled_up = True

    def _is_at_bottom(self) -> bool:
        scrollbar = self.msg_list.verticalScrollBar()
        return scrollbar.value() >= scrollbar.maximum() - 5

    def _scroll_to_bottom(self) -> None:
        self.msg_list.scrollToBottom()
        self._user_scrolled_up = False
        self._new_message_count = 0
        self.new_msg_indicator.setVisible(False)

    # --- Render messages ---
    def _render_messages(self) -> None:
        was_at_bottom = self._is_at_bottom()
        prev_count = self.msg_list.count()

        self.msg_list.clear()

        if self._controller is None:
            self.msg_list.addItem(QListWidgetItem("选择一个会话开始聊天"))
            return

        if self._controller.loading:
            self.msg_list.addItem(QListWidgetItem("加载中…"))
            return

        if self._controller.error and not self._controller.messages:
            # Error state with retry
            error_widget = QWidget()
            error_layout = QVBoxLayout(error_widget)
            error_layout.setAlignment(Qt.AlignCenter)
            error_label = QLabel(f"加载消息失败\n{self._controller.error[:80]}")
            error_label.setAlignment(Qt.AlignCenter)
            error_label.setStyleSheet(f"color:{C.ERROR};font-size:{T.SIZE_BODY}px;padding:20px;")
            error_layout.addWidget(error_label)
            retry_btn = primary_button("重试")
            retry_btn.clicked.connect(lambda: self._controller and self._controller.load())
            btn_row = QHBoxLayout()
            btn_row.addStretch()
            btn_row.addWidget(retry_btn)
            btn_row.addStretch()
            error_layout.addLayout(btn_row)
            item = QListWidgetItem(self.msg_list)
            item.setSizeHint(QSize(self.msg_list.width(), 160))
            self.msg_list.addItem(item)
            self.msg_list.setItemWidget(item, error_widget)
            return

        if not self._controller.messages:
            # Empty state
            empty_widget = QWidget()
            empty_layout = QVBoxLayout(empty_widget)
            empty_layout.setAlignment(Qt.AlignCenter)
            empty_label = QLabel("你们已经是好友，开始聊天吧")
            empty_label.setAlignment(Qt.AlignCenter)
            empty_label.setStyleSheet(f"color:{C.TEXT_3};font-size:{T.SIZE_BODY}px;padding:40px;")
            empty_layout.addWidget(empty_label)
            item = QListWidgetItem(self.msg_list)
            item.setSizeHint(QSize(self.msg_list.width(), 140))
            self.msg_list.addItem(item)
            self.msg_list.setItemWidget(item, empty_widget)
            return

        # Render with date grouping
        last_date_group = None
        for m in self._controller.messages:
            # Date separator
            if m.created_at is not None:
                group = _format_date_group(m.created_at)
                if group != last_date_group:
                    sep_item = QListWidgetItem(self.msg_list)
                    sep = _DateSeparator(group)
                    sep_item.setSizeHint(QSize(self.msg_list.width(), 28))
                    self.msg_list.addItem(sep_item)
                    self.msg_list.setItemWidget(sep_item, sep)
                    last_date_group = group

            # Message bubble
            item = QListWidgetItem(self.msg_list)
            bubble = _BubbleWidget(m, self._current_user_id, on_retry=self._on_retry)
            item.setSizeHint(QSize(self.msg_list.width(), bubble.sizeHint().height()))
            self.msg_list.addItem(item)
            self.msg_list.setItemWidget(item, bubble)

        # Scroll behavior
        new_count = self.msg_list.count()
        if was_at_bottom or not self._user_scrolled_up:
            QTimer.singleShot(0, self._scroll_to_bottom)
        elif new_count > prev_count:
            # New messages arrived while user was reading history
            self._new_message_count += (new_count - prev_count)
            self.new_msg_indicator.show_count(self._new_message_count)
            # Reposition indicator
            self._reposition_indicator()

    def _reposition_indicator(self) -> None:
        # Position above composer, centered horizontally
        parent = self.new_msg_indicator.parent()
        if parent is None:
            return
        x = (parent.width() - self.new_msg_indicator.width()) // 2
        y = parent.height() - 60
        self.new_msg_indicator.move(max(20, x), y)

    # --- Send ---
    def _update_send_enabled(self) -> None:
        enabled = bool(self.input.toPlainText().strip()) and self._controller is not None
        self.send_btn.setEnabled(enabled)

    def _on_send(self) -> None:
        text = self.input.toPlainText().strip()
        if not text or self._controller is None:
            return
        self._controller.send(text)
        self.input.clear()
        self._update_send_enabled()
        self._scroll_to_bottom()

    def _on_retry(self, message: Message) -> None:
        if self._controller is not None:
            self._controller.retry(message)
