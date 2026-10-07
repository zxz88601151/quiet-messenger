/// Design Tokens — Spacing & Radius
///
/// Source of truth: `index.html` spacing/radius scale.
/// Prototype radii: `--r-sm:6px --r-md:8px --r-lg:12px --r-xl:16px --r-full:9999px`
/// Shadows: `--sh-sm/md/lg` are mapped to Flutter [BoxShadow] hints.
import 'package:flutter/material.dart';

class AppSpacing {
  AppSpacing._();

  static const double xs = 4;
  static const double sm = 8;
  static const double md = 12;
  static const double lg = 16;
  static const double xl = 20;
  static const double xxl = 24;

  // ---- Radius ----
  static const double rSm = 6;
  static const double rMd = 8;
  static const double rLg = 12;
  static const double rXl = 16;
  static const double rFull = 9999;
}

class AppShadows {
  AppShadows._();

  /// Prototype `--sh-sm: 0 1px 2px rgba(0,0,0,.05)`
  static const List<BoxShadow> sm = [
    BoxShadow(
      color: Color(0x0D000000),
      blurRadius: 2,
      offset: Offset(0, 1),
    ),
  ];

  /// Prototype `--sh-md: 0 4px 12px rgba(0,0,0,.08)`
  static const List<BoxShadow> md = [
    BoxShadow(
      color: Color(0x14000000),
      blurRadius: 12,
      offset: Offset(0, 4),
    ),
  ];

  /// Prototype `--sh-lg: 0 12px 32px rgba(0,0,0,.12)`
  static const List<BoxShadow> lg = [
    BoxShadow(
      color: Color(0x1F000000),
      blurRadius: 32,
      offset: Offset(0, 12),
    ),
  ];
}
