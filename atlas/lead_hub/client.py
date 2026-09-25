from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from atlas.lead_hub.models import LeadCaptureRequest


@dataclass(frozen=True)
class LeadHubClientConfig:
    base_url: str
    token: str = "dev-lead-hub-token"
    timeout_seconds: float = 20.0

    @classmethod
    def from_env(cls) -> "LeadHubClientConfig":
        return cls(
            base_url=os.getenv("ATLAS_LEAD_HUB_URL", "http://127.0.0.1:5055").rstrip("/"),
            token=os.getenv("NEXYRA_LEAD_HUB_TOKEN", "dev-lead-hub-token"),
            timeout_seconds=float(os.getenv("ATLAS_LEAD_HUB_TIMEOUT", "20")),
        )


class LeadHubClient:
    def __init__(self, config: LeadHubClientConfig | None = None) -> None:
        self.config = config or LeadHubClientConfig.from_env()

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/api/v1/lead-hub/health")

    def pull(self, request: LeadCaptureRequest) -> dict[str, Any]:
        return self._request("POST", "/api/v1/lead-hub/pull", request.to_payload())

    def intake_batch(self, request: LeadCaptureRequest) -> dict[str, Any]:
        return self._request("POST", "/api/v1/lead-hub/intake/batch", request.to_payload())

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url=f"{self.config.base_url}{path}",
            data=body,
            method=method,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "X-Lead-Hub-Token": self.config.token,
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.config.timeout_seconds) as response:
                data = response.read().decode("utf-8")
                return json.loads(data) if data else {"ok": True}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            return {
                "ok": False,
                "error": "http_error",
                "status": exc.code,
                "detail": detail,
            }
        except urllib.error.URLError as exc:
            return {
                "ok": False,
                "error": "connection_error",
                "detail": str(exc.reason),
            }
        except TimeoutError as exc:
            return {
                "ok": False,
                "error": "timeout",
                "detail": str(exc),
            }
