"""Unified API error type (Desktop / PySide6)."""

from __future__ import annotations


class ApiException(Exception):
    def __init__(self, code: str, message: str, status: int | None = None) -> None:
        super().__init__(f"{code} ({status}): {message}")
        self.code = code
        self.message = message
        self.status = status
