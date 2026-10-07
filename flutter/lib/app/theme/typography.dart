/// Design Tokens — Typography
///
/// Source of truth: `index.html` font-size scale (extracted from prototype CSS).
/// Prototype uses a single system font stack (`--font`), so we map to
/// Flutter's default text theme and apply the prototype's px sizes + weights.
import 'package:flutter/material.dart';

class AppTypography {
  AppTypography._();

  /// Prototype base body size: 13px on mobile frames, 12px on desktop.
  /// We standardize on a 4-tier scale lifted from the prototype.
  static const TextStyle h1 = TextStyle(
    fontSize: 24,
    fontWeight: FontWeight.w700,
    letterSpacing: -0.3,
    color: AppColorsRef.text,
  );

  static const TextStyle h2 = TextStyle(
    fontSize: 22,
    fontWeight: FontWeight.w700,
    letterSpacing: -0.3,
    color: AppColorsRef.text,
  );

  static const TextStyle title = TextStyle(
    fontSize: 17,
    fontWeight: FontWeight.w700,
    color: AppColorsRef.text,
  );

  static const TextStyle subtitle = TextStyle(
    fontSize: 15,
    fontWeight: FontWeight.w600,
    color: AppColorsRef.text,
  );

  static const TextStyle body = TextStyle(
    fontSize: 13,
    fontWeight: FontWeight.w400,
    height: 1.5,
    color: AppColorsRef.text,
  );

  static const TextStyle body2 = TextStyle(
    fontSize: 12,
    fontWeight: FontWeight.w400,
    color: AppColorsRef.text2,
  );

  static const TextStyle caption = TextStyle(
    fontSize: 11,
    fontWeight: FontWeight.w400,
    color: AppColorsRef.text3,
  );

  static const TextStyle label = TextStyle(
    fontSize: 12,
    fontWeight: FontWeight.w500,
    color: AppColorsRef.text2,
  );

  static const TextStyle button = TextStyle(
    fontSize: 14,
    fontWeight: FontWeight.w500,
  );
}

/// Local reference to avoid a circular import with [AppColors].
/// [AppTypography] only reads color constants at theme-build time.
class AppColorsRef {
  const AppColorsRef._();
  static const Color text = Color(0xFF111827);
  static const Color text2 = Color(0xFF6B7280);
  static const Color text3 = Color(0xFF9CA3AF);
}
