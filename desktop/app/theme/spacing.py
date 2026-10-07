"""Spacing system — unified spacing constants (Desktop / PySide6, Phase 2B).

Base unit = 4px. Use these constants instead of hardcoded margins/paddings
to keep the Desktop UI visually consistent. Only pages modified in Phase 2B
are migrated; do NOT do a project-wide refactor for spacing alone.
"""

from __future__ import annotations

# Base spacing scale (4px grid)
XS = 4
SM = 8
MD = 12
LG = 16
XL = 24
XXL = 32

# Common layout presets
PAGE_MARGINS = (LG, LG, LG, LG)  # left, top, right, bottom
CARD_PADDING = (MD, MD, MD, MD)
BUBBLE_PADDING = (LG, SM, LG, SM)

# Component-specific
HEADER_HEIGHT = 48
INPUT_MIN_HEIGHT = 36
INPUT_MAX_HEIGHT = 80
AVATAR_SM = 28
AVATAR_MD = 36
AVATAR_LG = 48
