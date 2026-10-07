"""Desktop SoundService (PySide6 / DEF-RT-006).

Plays application notification sounds. Business interface mirrors the Android
SoundService (enabled / volume / playFriendAdded / playNewMessage / playOnline
/ throttle / dispose). The actual audio backend is pluggable.

Sound playback is fire-and-forget: audio errors never affect business logic.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import Optional

logger = logging.getLogger("liaotian.sound")

_ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "sounds")
_FRIEND_ADDED = os.path.join(_ASSETS_DIR, "friend_added.mp3")
_NEW_MESSAGE = os.path.join(_ASSETS_DIR, "new_message.mp3")
_ONLINE = os.path.join(_ASSETS_DIR, "online.mp3")
_FRIEND_THROTTLE_SECONDS = 3.0


class _AudioBackend:
    def play(self, path: str) -> bool:
        raise NotImplementedError

    def stop(self) -> None:
        pass

    def dispose(self) -> None:
        pass


class _ThreadedFileBackend(_AudioBackend):
    def __init__(self) -> None:
        self._mode = "startfile"
        self._qsound = None
        self._qurl_cls = None
        self._init_backend()

    def _init_backend(self) -> None:
        try:
            from PySide6.QtMultimedia import QSoundEffect  # type: ignore
            from PySide6.QtCore import QUrl  # type: ignore
            self._qsound = QSoundEffect()
            self._qurl_cls = QUrl
            self._mode = "qsound"
            logger.info("sound backend: QSoundEffect")
            return
        except Exception:
            pass
        self._mode = "startfile"
        logger.info("sound backend: os.startfile (fallback)")

    def play(self, path: str) -> bool:
        if not os.path.exists(path):
            logger.warning("sound file not found: %s", path)
            return False
        try:
            if self._mode == "qsound":
                self._qsound.setSource(self._qurl_cls.fromLocalFile(path))
                self._qsound.setVolume(0.5)
                self._qsound.play()
                return True
            elif self._mode == "startfile":
                os.startfile(path)  # type: ignore[attr-defined]
                return True
        except Exception as e:
            logger.warning("sound play failed: %s", e)
        return False

    def stop(self) -> None:
        try:
            if self._mode == "qsound" and self._qsound:
                self._qsound.stop()
        except Exception:
            pass

    def dispose(self) -> None:
        self.stop()


class SoundService:
    _instance: Optional["SoundService"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "SoundService":
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._init()
            return cls._instance

    def _init(self) -> None:
        self._enabled = True
        self._volume = 0.5
        self._last_friend_play: float = 0.0
        self._backend = _ThreadedFileBackend()

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value
        if not value:
            self._backend.stop()

    @property
    def volume(self) -> float:
        return self._volume

    @volume.setter
    def volume(self, value: float) -> None:
        self._volume = max(0.0, min(1.0, value))

    def _play(self, path: str) -> None:
        if not self._enabled:
            return
        self._backend.play(path)

    def play_friend_added(self) -> None:
        now = time.monotonic()
        if now - self._last_friend_play < _FRIEND_THROTTLE_SECONDS:
            return
        self._last_friend_play = now
        self._play(_FRIEND_ADDED)

    def play_new_message(self) -> None:
        self._play(_NEW_MESSAGE)

    def play_online(self) -> None:
        if os.path.exists(_ONLINE):
            self._play(_ONLINE)

    def dispose(self) -> None:
        self._backend.dispose()
