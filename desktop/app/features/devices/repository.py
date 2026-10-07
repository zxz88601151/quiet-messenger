"""Device repository — real API implementation (Desktop / PySide6).

Wires devices feature to ApiClient. Endpoints follow shared/API_CONTRACT §5:
- GET /devices
- DELETE /devices/{id}
"""

from __future__ import annotations

from ...api.api_client import ApiClient
from .models import Device


class DeviceRepository:
    def __init__(self, client: ApiClient) -> None:
        self._client = client

    def list(self) -> list[Device]:
        resp = self._client.get("/devices")
        data = resp.json()
        if isinstance(data, dict):
            # Some backends wrap in {"devices": [...]}
            data = data.get("devices", [])
        return [Device.from_json(d) for d in data]

    def revoke(self, device_id: str) -> None:
        self._client.delete(f"/devices/{device_id}")
