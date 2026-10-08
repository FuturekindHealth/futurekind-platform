"""Configuration the operator sets, read from the environment.

Deliberately small: this application has no catalogue, no policy file and no
routing table, because all three belong to the Gateway (``ADR-0002``). What is
left is where to find the Gateway and how long to wait for it.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

ENV_PREFIX = "FK_RADIOLOGY_"

#: The Gateway's loopback port in ``compose.yaml``. A default that points at the
#: platform's own door, so an installation works before anyone writes a variable.
DEFAULT_GATEWAY_BASE_URL = "http://127.0.0.1:8100"

#: ``radiology-report`` declares a 90 second policy timeout, and a clinical draft
#: is legitimately slow. Waiting less than the Gateway does would make this
#: application the thing that breaks a request it did not answer.
DEFAULT_REQUEST_TIMEOUT_SECONDS = 120.0


@dataclass(frozen=True)
class CopilotSettings:
    gateway_base_url: str = DEFAULT_GATEWAY_BASE_URL
    gateway_api_key: str | None = None
    request_timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS
    host: str = "127.0.0.1"
    port: int = 8200

    @classmethod
    def from_env(cls, environ: dict[str, str] | None = None) -> CopilotSettings:
        env = os.environ if environ is None else environ

        def get(name: str, fallback: str = "") -> str:
            return env.get(f"{ENV_PREFIX}{name}", fallback).strip()

        timeout_raw = get("REQUEST_TIMEOUT_SECONDS")
        timeout = float(timeout_raw) if timeout_raw else DEFAULT_REQUEST_TIMEOUT_SECONDS
        port_raw = get("PORT")
        return cls(
            gateway_base_url=(get("GATEWAY_BASE_URL") or DEFAULT_GATEWAY_BASE_URL).rstrip("/"),
            gateway_api_key=get("GATEWAY_API_KEY") or None,
            request_timeout_seconds=timeout,
            host=get("HOST") or "127.0.0.1",
            port=int(port_raw) if port_raw else 8200,
        )

    def redacted(self) -> dict[str, Any]:
        """What may be printed. The credential is named, never shown."""
        return {
            "gateway_base_url": self.gateway_base_url,
            "gateway_api_key_configured": bool(self.gateway_api_key),
            "request_timeout_seconds": self.request_timeout_seconds,
            "host": self.host,
            "port": self.port,
        }


__all__ = ["DEFAULT_GATEWAY_BASE_URL", "ENV_PREFIX", "CopilotSettings"]
