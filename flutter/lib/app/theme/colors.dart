/// Design Tokens — Colors
///
/// Source of truth: `index.html` CSS custom properties (V1.1 UI Prototype).
/// These map the prototype's visual language into Flutter semantic tokens.
/// Per V1.1_SCOPE §6 (Dark Mode POSTPONE), we use semantic names so a future
/// theme switch is non-breaking. Values reflect the prototype's light palette.
import 'package:flutter/material.dart';

class AppColors {
  AppColors._();

  // ---- Brand / Accent ----
  /// Prototype `--primary: #2563EB`
  static const Color primary = Color(0xFF2563EB);
  /// Prototype `--primary-hover: #1D4ED8`
  static const Color primaryHover = Color(0xFF1D4ED8);
  /// Prototype `--primary-light: #EFF6FF`
  static const Color primaryLight = Color(0xFFEFF6FF);

  // ---- Text ----
  /// Prototype `--text: #111827`
  static const Color text = Color(0xFF111827);
  /// Prototype `--text-2: #6B7280`
  static const Color text2 = Color(0xFF6B7280);
  /// Prototype `--text-3: #9CA3AF`
  static const Color text3 = Color(0xFF9CA3AF);

  // ---- Surface / Background ----
  /// Prototype `--bg: #FFFFFF`
  static const Color bg = Color(0xFFFFFFFF);
  /// Prototype `--surface: #F7F8FA`
  static const Color surface = Color(0xFFF7F8FA);
  /// Prototype `--surface-2: #F3F4F6`
  static const Color surface2 = Color(0xFFF3F4F6);

  // ---- Border ----
  /// Prototype `--border: #E5E7EB`
  static const Color border = Color(0xFFE5E7EB);
  /// Prototype `--border-light: #F3F4F6`
  static const Color borderLight = Color(0xFFF3F4F6);

  // ---- Semantic states ----
  /// Prototype `--success: #10B981` / `--online: #10B981`
  static const Color success = Color(0xFF10B981);
  /// Prototype `--error: #EF4444` / `--busy: #EF4444`
  static const Color error = Color(0xFFEF4444);
  /// Prototype `--warning: #F59E0B`
  static const Color warning = Color(0xFFF59E0B);
  /// Prototype `--offline: #9CA3AF`
  static const Color offline = Color(0xFF9CA3AF);

  // ---- App canvas (mobile/desktop root) ----
  /// Prototype `body { background: #EEF1F5 }`
  static const Color canvas = Color(0xFFEEF1F5);
}
