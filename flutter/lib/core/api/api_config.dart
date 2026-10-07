/// API Client foundation — environment configuration.
///
/// Phase 3A scope: infrastructure only. Supports Development + Staging.
/// Per §12, Production MUST NOT be hardcoded; it is supplied via build env
/// or runtime config. Default dev points at localhost; staging uses the
/// already-verified Staging API.
///
/// NOTE: The verified Staging API is served behind Nginx on
/// `https://<staging-host>` with routes under `/api/v1`. Until a real
/// domain is issued, [staging] may use the LAN IP over HTTP for local
/// verification — we do NOT forge HTTPS.
import 'package:flutter/foundation.dart';

enum ApiEnvironment { development, staging }

class ApiConfig {
  const ApiConfig._();

  /// Active environment. Override via `flutter run --dart-define=ENV=staging`.
  static const ApiEnvironment environment = kDebugMode
      ? ApiEnvironment.development
      : ApiEnvironment.staging;

  /// Base URL per environment. No hardcoded production.
  static const Map<ApiEnvironment, String> _baseUrls = {
    // Local backend (docker-compose / run-backend-staging.sh)
    ApiEnvironment.development: 'http://127.0.0.1:8000',
    // Verified Staging API host (M1 DNS PASS: api-staging.ycqinnan.cn →
    // 111.229.225.123). Real device cannot use LAN IP / localhost, so the
    // approved Staging domain is used. HTTPS is the production intent
    // (M4 will provision Nginx + Let's Encrypt cert for this subdomain).
    // Until M4 completes, real-device E2E against this host is NOT VERIFIED.
    ApiEnvironment.staging: 'https://api-staging.ycqinnan.cn',
  };

  static String get baseUrl => _baseUrls[environment]!;

  /// API path prefix used by the backend routers (shared/API_CONTRACT.md).
  static const String apiPrefix = '/api/v1';

  static String get apiBaseUrl => '$baseUrl$apiPrefix';
}
