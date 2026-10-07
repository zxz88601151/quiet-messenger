/// App Theme — composes the design tokens into a Flutter [ThemeData].
///
/// Per V1.1_SCOPE §6, Dark Mode is POSTPONE; we keep semantic tokens so a
/// future [ThemeMode.dark] swap is non-breaking. This file only assembles
/// light theme from [AppColors]/[AppTypography]/[AppSpacing].
import 'package:flutter/material.dart';

import 'colors.dart';
import 'typography.dart';

class AppTheme {
  AppTheme._();

  static ThemeData get light => ThemeData(
        useMaterial3: true,
        brightness: Brightness.light,
        scaffoldBackgroundColor: AppColors.canvas,
        primaryColor: AppColors.primary,
        colorScheme: const ColorScheme.light(
          primary: AppColors.primary,
          onPrimary: Colors.white,
          surface: AppColors.surface,
          onSurface: AppColors.text,
          error: AppColors.error,
          onError: Colors.white,
          secondary: AppColors.success,
        ),
        textTheme: const TextTheme(
          displaySmall: AppTypography.h1,
          headlineMedium: AppTypography.h2,
          titleLarge: AppTypography.title,
          titleMedium: AppTypography.subtitle,
          bodyMedium: AppTypography.body,
          bodySmall: AppTypography.body2,
          labelSmall: AppTypography.caption,
          labelMedium: AppTypography.label,
        ),
        appBarTheme: const AppBarTheme(
          backgroundColor: AppColors.bg,
          foregroundColor: AppColors.text,
          elevation: 0,
          centerTitle: false,
        ),
        inputDecorationTheme: InputDecorationTheme(
          filled: true,
          fillColor: AppColors.bg,
          contentPadding:
              const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
          border: OutlineInputBorder(
            borderRadius: BorderRadius.circular(8),
            borderSide: const BorderSide(color: AppColors.border),
          ),
          enabledBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(8),
            borderSide: const BorderSide(color: AppColors.border),
          ),
          focusedBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(8),
            borderSide: const BorderSide(color: AppColors.primary, width: 1.5),
          ),
          labelStyle: AppTypography.label,
          hintStyle: AppTypography.caption,
        ),
        elevatedButtonTheme: ElevatedButtonThemeData(
          style: ElevatedButton.styleFrom(
            backgroundColor: AppColors.primary,
            foregroundColor: Colors.white,
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(8),
            ),
            textStyle: AppTypography.button,
          ),
        ),
        dividerColor: AppColors.border,
        cardColor: AppColors.bg,
      );
}
