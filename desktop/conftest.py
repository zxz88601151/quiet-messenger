"""Pytest config — ensure the ``app`` package is importable from repo root.

Also forces Qt offscreen platform so GUI tests run headless on CI/servers
without a display. The application itself must NOT default to offscreen —
that would hide the GUI on normal desktop launches.
"""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(__file__))
