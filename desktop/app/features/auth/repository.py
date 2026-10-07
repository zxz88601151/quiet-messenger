"""Auth repository — real API implementation (Desktop / PySide6, Phase 3B).

Wires the auth feature to the existing ``ApiClient`` (requests) +
``TokenStorage`` (keyring/in-memory) from Phase 3A. NO second HTTP client.
Endpoints follow shared/API_CONTRACT.md §1 exactly.

Scope (Phase 3B only): register / login / refresh / logout / restore /
current user / forgot / reset. No friend / message / websocket / QR logic.
"""

from __future__ import annotations

from ...api.api_client import ApiClient
from ...storage.token_storage import TokenStorage
from ...errors.api_exception import ApiException
from .models import AuthTokens, DeviceInfo, Session, User


class AuthRepository:
    def __init__(self, client: ApiClient, token_storage: TokenStorage) -> None:
        self._client = client
        self._tokens = token_storage

    def register(
        self,
        username: str,
        phone: str,
        password: str,
        nickname: str,
        device: DeviceInfo | None = None,
    ) -> Session:
        device = device or DeviceInfo()
        resp = self._client.post(
            "/auth/register",
            json={
                "username": username,
                "phone": phone,
                "password": password,
                "nickname": nickname,
                "device": device.to_json(),
            },
        )
        return self._session_from_response(resp.json())

    def login(
        self, identifier: str, password: str, device: DeviceInfo | None = None
    ) -> Session:
        device = device or DeviceInfo()
        resp = self._client.post(
            "/auth/login",
            json={
                "identifier": identifier,
                "password": password,
                "device": device.to_json(),
            },
        )
        return self._session_from_response(resp.json())

    def refresh(self) -> AuthTokens:
        refresh_token = self._tokens.get_refresh_token()
        if not refresh_token:
            raise ApiException(code="UNAUTHENTICATED", message="无刷新令牌")
        resp = self._client.post(
            "/auth/refresh", json={"refresh_token": refresh_token}
        )
        tokens = AuthTokens.from_json(resp.json())
        self._tokens.set_tokens(access=tokens.access_token, refresh=tokens.refresh_token)
        return tokens

    def logout(self) -> None:
        refresh_token = self._tokens.get_refresh_token()
        if refresh_token:
            try:
                self._client.post("/auth/logout", json={"refresh_token": refresh_token})
            except ApiException:
                # Best-effort: clear local state regardless.
                pass
        self._tokens.clear()

    def restore_session(self) -> Session | None:
        refresh_token = self._tokens.get_refresh_token()
        if not refresh_token:
            return None
        try:
            tokens = self.refresh()
            user = self.get_current_user()
            return Session(user=user, tokens=tokens)
        except ApiException:
            self._tokens.clear()
            return None

    def get_current_user(self) -> User:
        resp = self._client.get("/users/me")
        return User.from_json(resp.json())

    def patch_me(self, payload: dict) -> User:
        """PATCH /users/me — update nickname/avatar/privacy etc."""
        resp = self._client.patch("/users/me", json=payload)
        return User.from_json(resp.json())

    def forgot_password(self, phone: str) -> None:
        self._client.post("/auth/forgot-password", json={"phone": phone})

    def reset_password(self, phone: str, code: str, new_password: str) -> None:
        self._client.post(
            "/auth/reset-password",
            json={"phone": phone, "code": code, "new_password": new_password},
        )

    def _session_from_response(self, data: dict) -> Session:
        tokens = AuthTokens.from_json(data)
        user = User.from_json(data["user"])
        self._tokens.set_tokens(
            access=tokens.access_token, refresh=tokens.refresh_token
        )
        return Session(user=user, tokens=tokens)
