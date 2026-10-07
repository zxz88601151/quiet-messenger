"""Design Tokens — Colors (Desktop / PySide6).

Source of truth: ``index.html`` CSS custom properties (V1.1 UI Prototype).
Maps the prototype's visual language into PySide6 color constants. Per
V1.1_SCOPE §6 (Dark Mode POSTPONE) we keep semantic names; values reflect
the prototype's light palette so a future theme swap is non-breaking.
"""

# Brand / Accent
PRIMARY = "#2563EB"
PRIMARY_HOVER = "#1D4ED8"
PRIMARY_LIGHT = "#EFF6FF"

# Text
TEXT = "#111827"
TEXT_2 = "#6B7280"
TEXT_3 = "#9CA3AF"

# Surface / Background
BG = "#FFFFFF"
SURFACE = "#F7F8FA"
SURFACE_2 = "#F3F4F6"
CANVAS = "#EEF1F5"

# Border
BORDER = "#E5E7EB"
BORDER_LIGHT = "#F3F4F6"

# Semantic states
SUCCESS = "#10B981"
ERROR = "#EF4444"
WARNING = "#F59E0B"
OFFLINE = "#9CA3AF"
