"""Secure token storage foundation (Desktop / PySide6).

Phase 3A scope: infrastructure only. Persists access + refresh tokens via
the OS keyring (keyring lib) with an in-memory fallback for headless test
runs. No auth-flow logic — just get/set/clear.

NOTE: ``keyring`` is optional; if unavailable we fall back to an in-memory
store so the desktop app + tests can run in CI without a keyring backend.
"""

from __future__ import annotations

import keyring
from keyring.errors import KeyringError

_ACCESS_KEY = "liaotian_access_token"
_REFRESH_KEY = "liaotian_refresh_token"
_SERVICE = "liaotian_desktop"


class TokenStorage:
    def __init__(self) -> None:
        self._mem: dict[str, str] = {}

    def get_access_token(self) -> str | None:
        return self._get(_ACCESS_KEY)

    def get_refresh_token(self) -> str | None:
        return self._get(_REFRESH_KEY)

    def set_tokens(self, access: str, refresh: str) -> None:
        self._set(_ACCESS_KEY, access)
        self._set(_REFRESH_KEY, refresh)

    def clear(self) -> None:
        for k in (_ACCESS_KEY, _REFRESH_KEY):
            try:
                keyring.delete_password(_SERVICE, k)
            except (KeyringError, Exception):
                pass
        self._mem.clear()

    def _get(self, key: str) -> str | None:
        try:
            v = keyring.get_password(_SERVICE, key)
            if v:
                return v
        except (KeyringError, Exception):
            pass
        return self._mem.get(key)

    def _set(self, key: str, value: str) -> None:
        self._mem[key] = value
        try:
            keyring.set_password(_SERVICE, key, value)
        except (KeyringError, Exception):
            pass
