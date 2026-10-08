"""The one place this application talks to the Gateway.

It is a *client of the wire contract*, not of the Gateway package: nothing here
imports ``futurekind_gateway``. The dependency an application is allowed to have
is on a documented HTTP interface (``docs/ARCHITECTURE.md``: "Applications never
communicate directly with AI models"), and importing the Gateway's classes would
let a refactor there become a break here.

The fields this client tolerates are the ones ``POST /chat`` documents. Tolerant
of additions, strict about the ones a draft cannot be built without — a Gateway
that answers with something else is a version mismatch, and saying so is better
than drafting a report from a shape nobody agreed to.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

from .errors import GatewayRequestError

CHAT_PATH = "/chat"

#: The skill this application runs, spelled once. A second copy in a request body
#: is a second thing to forget when the skill is renamed.
RADIOLOGY_SKILL = "radiology-report"


class GatewayCompletion(BaseModel):
    """One completion, as ``POST /chat`` reports it."""

    model_config = ConfigDict(protected_namespaces=(), extra="ignore")

    request_id: str
    skill: str | None = None
    capability: str
    model: str
    provider: str
    selected_by: str
    policy: dict[str, Any]
    attempts: int
    degraded: bool
    content: str
    finish_reason: str | None = None
    usage: dict[str, int] = {}
    latency_ms: int

    @property
    def ran_out_of_tokens(self) -> bool:
        """True when the provider stopped because its budget was reached.

        ``length`` is the only finish reason that means "this answer was cut off".
        ``content_filter`` is reported separately by the renderer, because a
        refusal by the deployment is a different clinical event from a truncation.
        """
        return self.finish_reason == "length"


def _problem_list(exc: ValueError) -> list[dict[str, Any]]:
    """The structural part of a validation failure, with the values removed.

    ``ValidationError`` derives from ``ValueError``, so catching the latter also
    catches a 200 whose body is not JSON at all. Pydantic's error entries carry an
    ``input`` key holding the offending value — here, a slice of a completion that
    may quote the patient — and a refusal is exactly the text most likely to be
    logged, printed and forwarded. So the values go, the field names stay.
    """
    if not isinstance(exc, ValidationError):
        return [{"msg": type(exc).__name__}]
    return [
        {key: value for key, value in item.items() if key not in {"input", "ctx"}}
        for item in exc.errors()[:3]
    ]


class GatewayClient:
    """Calls the Gateway. Never calls a model, an alias or a provider directly."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None = None,
        timeout_seconds: float = 120.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not base_url.startswith(("http://", "https://")):
            raise ValueError(
                "Gateway base_url must be an absolute http(s) URL, e.g. http://127.0.0.1:8100"
            )
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout_seconds
        self._transport = transport

    def _headers(self) -> dict[str, str]:
        if not self._api_key:
            return {}
        return {"Authorization": f"Bearer {self._api_key}"}

    async def complete(
        self,
        *,
        skill: str,
        messages: Sequence[dict[str, str]],
        temperature: float | None = None,
    ) -> GatewayCompletion:
        """Ask for one completion by skill, and return it typed.

        No field here can name a model, a provider or an endpoint, because the
        Gateway refuses a body that does (ADR-0002) — and an application that
        could not ask is an application that cannot drift into breaking it.
        """
        body: dict[str, Any] = {"skill": skill, "messages": list(messages)}
        if temperature is not None:
            body["temperature"] = temperature

        try:
            async with httpx.AsyncClient(
                timeout=self._timeout, transport=self._transport
            ) as client:
                response = await client.post(
                    f"{self._base_url}{CHAT_PATH}", json=body, headers=self._headers()
                )
        except httpx.TimeoutException as exc:
            raise GatewayRequestError(
                "The Gateway did not answer within the application's wait limit.",
                details={"base_url": self._base_url, "timeout_seconds": self._timeout},
                status_code=504,
                retryable=True,
            ) from exc
        except httpx.HTTPError as exc:
            raise GatewayRequestError(
                "The Gateway could not be reached. Is it running, and is "
                "FK_RADIOLOGY_GATEWAY_BASE_URL correct?",
                details={"base_url": self._base_url, "transport_error": type(exc).__name__},
                status_code=503,
                retryable=True,
            ) from exc

        if response.status_code != 200:
            raise self._upstream_error(response)

        try:
            return GatewayCompletion.model_validate(response.json())
        except ValueError as exc:
            raise GatewayRequestError(
                "The Gateway's answer did not match the documented completion shape, "
                "so this application stopped rather than guess at it.",
                details={"problem": _problem_list(exc)},
                status_code=502,
            ) from exc

    def _upstream_error(self, response: httpx.Response) -> GatewayRequestError:
        """Carry the Gateway's own refusal through, without dressing it up.

        The Gateway's error message is operator-facing and, by its contract,
        carries no patient text — so it is safe to surface. The clinical
        consequence stays visible either way: this is a refusal, not a warning.
        """
        code: str | None = None
        message = f"The Gateway refused the request (HTTP {response.status_code})."
        retryable: bool | None = None
        request_id: str | None = None
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict):
                code = str(error["code"]) if error.get("code") is not None else None
                if error.get("message"):
                    message = str(error["message"])[:500]
                if isinstance(error.get("retryable"), bool):
                    retryable = error["retryable"]
                # Correlation survives the translation: the Gateway recorded this
                # request in its own log, and its id is the only thing that joins
                # a clinician's "it failed" to that line.
                if error.get("request_id"):
                    request_id = str(error["request_id"])[:64]
        return GatewayRequestError(
            message,
            upstream_code=code,
            status_code=502,
            retryable=retryable,
            request_id=request_id,
            details={"http_status": response.status_code},
        )


__all__ = ["CHAT_PATH", "RADIOLOGY_SKILL", "GatewayClient", "GatewayCompletion"]
