"""Shared UI primitives (Desktop / PySide6).

Small helpers that mirror the prototype's button/input/card vocabulary so
feature pages stay consistent. Keeps raw Qt styling in one place.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLineEdit,
    QLabel,
    QFrame,
)
from ..theme import colors as C
from ..theme import typography as T


def primary_button(text: str) -> QPushButton:
    b = QPushButton(text)
    b.setMinimumHeight(36)
    b.setStyleSheet(
        f"QPushButton{{background:{C.PRIMARY};color:#fff;border:none;"
        f"border-radius:{T.R_MD}px;font-size:{T.SIZE_BODY}px;"
        f"font-weight:{T.WEIGHT_MEDIUM};padding:0 16px;}}"
        f"QPushButton:disabled{{background:{C.BORDER};}}"
        f"QPushButton:hover{{background:{C.PRIMARY_HOVER};}}"
    )
    return b


def text_field(placeholder: str = "") -> QLineEdit:
    e = QLineEdit()
    e.setPlaceholderText(placeholder)
    e.setMinimumHeight(38)
    e.setStyleSheet(
        f"QLineEdit{{border:1px solid {C.BORDER};border-radius:{T.R_MD}px;"
        f"padding:0 12px;font-size:{T.SIZE_BODY}px;background:{C.BG};"
        f"color:{C.TEXT};}}"
        f"QLineEdit:focus{{border:1.5px solid {C.PRIMARY};}}"
    )
    return e


def section_title(text: str) -> QLabel:
    l = QLabel(text)
    l.setStyleSheet(
        f"font-size:{T.SIZE_H2}px;font-weight:{T.WEIGHT_BOLD};color:{C.TEXT};"
    )
    return l


def card() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.StyledPanel)
    f.setStyleSheet(
        f"QFrame{{background:{C.BG};border:1px solid {C.BORDER};"
        f"border-radius:{T.R_LG}px;}}"
    )
    return f


class Page(QWidget):
    """Base page with a centered max-width column (matches prototype frames)."""

    def __init__(self) -> None:
        super().__init__()
        self.setStyleSheet(f"background:{C.CANVAS};")
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(24, 24, 24, 24)
        self.layout.setSpacing(12)
