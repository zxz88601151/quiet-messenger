"""Profile — real current user data (Desktop / PySide6, Phase 2).

Displays the authenticated user's avatar/nickname/username/id and supports
nickname editing via PATCH /users/me. Data comes from AuthController.session
— no hardcoded users.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QLabel,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
    QLineEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QMessageBox,
    QWidget,
)

from ...widgets.common import Page, primary_button
from ...theme import colors as C
from ...theme import typography as T
from ...errors.api_exception import ApiException


class ProfilePage(Page):
    def __init__(self, controller=None, repository=None) -> None:
        super().__init__()
        self._controller = controller
        self._repo = repository

        # Avatar (circle with initial)
        self._avatar = QLabel("?")
        self._avatar.setFixedSize(72, 72)
        self._avatar.setAlignment(Qt.AlignCenter)
        self._avatar.setStyleSheet(
            f"background:{C.PRIMARY_LIGHT};color:{C.PRIMARY};"
            f"border-radius:36px;font-size:28px;font-weight:{T.WEIGHT_BOLD};"
        )
        avatar_row = QHBoxLayout()
        avatar_row.addStretch()
        avatar_row.addWidget(self._avatar)
        avatar_row.addStretch()
        self.layout.addLayout(avatar_row)

        # Nickname
        self._nickname = QLabel("")
        self._nickname.setAlignment(Qt.AlignCenter)
        self._nickname.setStyleSheet(
            f"font-size:{T.SIZE_H2}px;font-weight:{T.WEIGHT_BOLD};color:{C.TEXT};"
        )
        self.layout.addWidget(self._nickname)

        # Username
        self._username = QLabel("")
        self._username.setAlignment(Qt.AlignCenter)
        self._username.setStyleSheet(f"color:{C.TEXT_2};font-size:{T.SIZE_BODY}px;")
        self.layout.addWidget(self._username)

        # User ID
        self._user_id = QLabel("")
        self._user_id.setAlignment(Qt.AlignCenter)
        self._user_id.setStyleSheet(f"color:{C.TEXT_3};font-size:{T.SIZE_CAPTION}px;")
        self.layout.addWidget(self._user_id)

        self.layout.addSpacing(16)

        # Edit nickname button
        self._edit_btn = primary_button("编辑昵称")
        self._edit_btn.clicked.connect(self._edit_nickname)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(self._edit_btn)
        btn_row.addStretch()
        self.layout.addLayout(btn_row)

        self.layout.addStretch()

        # Subscribe to auth state changes
        if self._controller is not None:
            self._controller.state.subscribe(lambda _s: self._refresh())

        self._refresh()

    def _refresh(self) -> None:
        if self._controller is None or self._controller.state.session is None:
            self._nickname.setText("未登录")
            self._username.setText("")
            self._user_id.setText("")
            self._avatar.setText("?")
            self._edit_btn.setEnabled(False)
            return
        user = self._controller.state.session.user
        display = user.nickname if user.nickname else user.username
        self._nickname.setText(display)
        self._username.setText(f"@{user.username}")
        self._user_id.setText(f"ID: {user.id}")
        initial = display[0].upper() if display else "?"
        self._avatar.setText(initial)
        self._edit_btn.setEnabled(True)

    def _edit_nickname(self) -> None:
        if self._controller is None or self._controller.state.session is None:
            return
        current = self._controller.state.session.user.nickname
        dialog = _NicknameDialog(self, current)
        if dialog.exec() != QDialog.Accepted:
            return
        new_nick = dialog.value().strip()
        if not new_nick or new_nick == current:
            return
        try:
            updated = self._repo.patch_me({"nickname": new_nick})
            self._controller.update_current_user(updated)
            self._refresh()
            QMessageBox.information(self, "已更新", "昵称已更新。")
        except ApiException as e:
            QMessageBox.warning(self, "更新失败", e.message)
        except Exception as e:
            QMessageBox.warning(self, "更新失败", str(e))


class _NicknameDialog(QDialog):
    def __init__(self, parent, current: str) -> None:
        super().__init__(parent)
        self.setWindowTitle("编辑昵称")
        self.setMinimumWidth(320)
        form = QFormLayout(self)
        self._input = QLineEdit(current)
        self._input.setMaxLength(30)
        form.addRow("新昵称：", self._input)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def value(self) -> str:
        return self._input.text()
