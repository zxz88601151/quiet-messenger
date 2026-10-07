"""Login page — real auth flow (Desktop / PySide6, Phase 3B).

Wires the credentials form to [AuthController.login]. Shows loading + mapped
errors (never raw exceptions). QR Desktop Login (D1/D2/D3) stays PHASE 6
POSTPONE — rendered as a disabled placeholder. UI ≠ API ≠ Domain.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QLabel,
    QHBoxLayout,
    QVBoxLayout,
    QFrame,
    QLineEdit,
    QPushButton,
)
from PySide6.QtCore import Qt

from ...widgets.common import Page, primary_button, text_field, section_title
from ...theme import colors as C
from ...theme import typography as T
from .state import AuthController, AuthStatus


class LoginPage(Page):
    def __init__(self, controller: AuthController) -> None:
        super().__init__()
        self._controller = controller
        self.setFixedWidth(880)

        title = section_title("登录")
        self.layout.addWidget(title)
        sub = QLabel("安静、可靠的私人通讯")
        sub.setStyleSheet(f"color:{C.TEXT_2};font-size:{T.SIZE_BODY_2}px;")
        self.layout.addWidget(sub)
        self.layout.addSpacing(16)

        # Credentials column
        col = QVBoxLayout()
        self.identifier = text_field("用户名 / 手机号")
        self.password = text_field("密码")
        self.password.setEchoMode(QLineEdit.EchoMode.Password)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet(
            f"color:{C.ERROR};font-size:{T.SIZE_CAPTION}px;"
        )
        self.error_label.setWordWrap(True)

        col.addWidget(QLabel("用户名 / 手机号"))
        col.addWidget(self.identifier)
        col.addWidget(QLabel("密码"))
        col.addWidget(self.password)
        col.addWidget(self.error_label)
        self.login_btn = primary_button("登录")
        self.login_btn.clicked.connect(self._on_login)
        col.addWidget(self.login_btn)
        col.addStretch(1)

        # QR placeholder (Phase 6 — visual only, disabled)
        qr = QFrame()
        qr.setFixedSize(180, 180)
        qr.setStyleSheet(
            f"QFrame{{background:{C.SURFACE_2};border:1px dashed {C.BORDER};"
            f"border-radius:{T.R_LG}px;}}"
        )
        qr_label = QLabel("扫码登录\n（即将上线）")
        qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        qr_label.setStyleSheet(f"color:{C.TEXT_3};font-size:{T.SIZE_CAPTION}px;")
        ql = QVBoxLayout(qr)
        ql.addWidget(qr_label)

        row = QHBoxLayout()
        row.addLayout(col, 1)
        row.addWidget(qr)
        self.layout.addLayout(row)
        self.layout.addStretch(1)

        # Subscribe to auth state changes for loading/error feedback.
        self._controller.state.subscribe(self._on_state)

    def _on_login(self) -> None:
        identifier = self.identifier.text().strip()
        password = self.password.text()
        if not identifier or not password:
            self.error_label.setText("请输入用户名和密码")
            return
        # Run in background to avoid blocking the UI thread on network I/O.
        from PySide6.QtCore import QThreadPool, QRunnable

        class _LoginTask(QRunnable):
            def __init__(self, ctrl, ident, pw) -> None:
                super().__init__()
                self._ctrl = ctrl
                self._ident = ident
                self._pw = pw

            def run(self) -> None:
                self._ctrl.login(self._ident, self._pw)

        QThreadPool.globalInstance().start(_LoginTask(self._controller, identifier, password))

    def _on_state(self, state) -> None:
        self.login_btn.setEnabled(state.status != AuthStatus.LOADING)
        if state.error is not None:
            self.error_label.setText(state.error.message)
        else:
            self.error_label.setText("")
