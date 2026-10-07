"""API Client foundation — environment configuration (Desktop / PySide6).

Phase 3A scope: infrastructure only. Supports Development + Staging. Per §12,
Production MUST NOT be hardcoded. Default dev = localhost; staging uses the
verified Staging API root. Routes are mounted under ``/api/v1``.
"""

from enum import Enum


class ApiEnvironment(str, Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"


class ApiConfig:
    # Override via env var LIAOTIAN_ENV=staging for staging runs.
    environment: ApiEnvironment = ApiEnvironment.DEVELOPMENT

    _BASE_URLS = {
        ApiEnvironment.DEVELOPMENT: "http://127.0.0.1:8000",
        # Verified Staging API root (Nginx). Replace with real domain once
        # issued (certbot → real HTTPS). No forged HTTPS.
        ApiEnvironment.STAGING: "http://192.168.3.200:9080",
    }

    API_PREFIX = "/api/v1"

    @classmethod
    def base_url(cls) -> str:
        return cls._BASE_URLS[cls.environment]

    @classmethod
    def api_base_url(cls) -> str:
        return f"{cls.base_url()}{cls.API_PREFIX}"
