"""API Client foundation — thin requests wrapper (Desktop / PySide6).

Phase 3A scope: infrastructure only. GET/POST/PATCH/DELETE + Authorization
header from stored access token + unified error parsing of the backend
envelope ``{error:{code,message,status}}`` (shared/API_CONTRACT.md §7).

Business flows (Auth/Friend/Message) are intentionally NOT implemented —
deferred to Phase 3D/3E. Repository stubs live in features/.
"""

from __future__ import annotations

import requests

from .api_config import ApiConfig
from ..storage.token_storage import TokenStorage
from ..errors.api_exception import ApiException


class ApiClient:
    def __init__(self, token_storage: TokenStorage | None = None) -> None:
        self._token_storage = token_storage or TokenStorage()
        self._session = requests.Session()
        self._session.headers.update({"Content-Type": "application/json"})

    def _auth(self) -> dict[str, str]:
        token = self._token_storage.get_access_token()
        return {"Authorization": f"Bearer {token}"} if token else {}

    def _request(self, method: str, path: str, json=None, params=None):
        url = f"{ApiConfig.api_base_url()}{path}"
        try:
            resp = self._session.request(
                method, url, json=json, params=params, headers=self._auth(),
                timeout=10,
            )
        except requests.RequestException as e:  # network-level failure
            raise ApiException(code="NETWORK_ERROR", message=str(e))
        if not resp.ok:
            code, message = self._parse_error(resp)
            raise ApiException(code=code, message=message, status=resp.status_code)
        return resp

    @staticmethod
    def _parse_error(resp) -> tuple[str, str]:
        try:
            data = resp.json()
            err = data.get("error", {})
            return err.get("code", "UNKNOWN"), err.get("message", resp.text)
        except Exception:
            return "UNKNOWN", resp.text

    def get(self, path: str, params=None):
        return self._request("GET", path, params=params)

    def post(self, path: str, json=None):
        return self._request("POST", path, json=json)

    def patch(self, path: str, json=None):
        return self._request("PATCH", path, json=json)

    def delete(self, path: str):
        return self._request("DELETE", path)
