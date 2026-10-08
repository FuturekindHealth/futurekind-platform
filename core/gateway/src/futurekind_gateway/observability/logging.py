"""Structured logging for the Gateway.

Two rules are enforced here rather than left to convention:

1. **Logs are JSON lines.**  A hospital box is monitored by tooling, not by
   someone tailing a file.
2. **Prompts and completions are never logged.**  A request log that records
   *which clinician asked which capability, how large the payload was, how long
   the model took and how many tokens it cost* supports audit, debugging and
   capacity planning without turning the log file into an unmanaged copy of
   patient narrative.  Content must be logged deliberately, elsewhere, under a
   retention policy — not by accident in an access log.
"""

from __future__ import annotations

import json
import logging
import sys
from collections.abc import Mapping
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

LOGGER_NAME = "futurekind.gateway"
REQUEST_ID_HEADER = "X-Request-Id"

#: Field names callers must never pass to :func:`log_event`.
#: Content is checked by name because a mis-named log field is a PHI leak.
FORBIDDEN_FIELDS = frozenset(
    {
        "content",
        "messages",
        "prompt",
        "prompts",
        "completion",
        "completions",
        "response_text",
        "text",
        "system_prompt",
        "input",
        "output",
    }
)

_request_id: ContextVar[str | None] = ContextVar("fk_gateway_request_id", default=None)

#: Attributes every ``LogRecord`` carries anyway. Used twice: the formatters skip
#: them so JSON output holds only what the caller chose to attach, and
#: :func:`log_event` renames any field that would collide, because
#: ``Logger.log(extra=...)`` raises KeyError rather than overwriting ``module``.
STANDARD_RECORD_ATTRS = frozenset(vars(logging.makeLogRecord({"msg": ""}))) | {"extra"}

#: Fields dropped from the rendered line. ``color_message`` is how uvicorn carries
#: ANSI escapes for terminal output; kept verbatim in a JSON stream it would put
#: raw escape codes into the audit log, and the plain ``message`` already says it.
SUPPRESSED_FIELDS = frozenset({"color_message"})


def _safe_field_name(name: str) -> str:
    return f"ctx_{name}" if name in STANDARD_RECORD_ATTRS else name


def new_request_id() -> str:
    """Return a fresh opaque request id."""
    return uuid4().hex


def set_request_id(value: str | None) -> None:
    _request_id.set(value)


def get_request_id() -> str | None:
    """The current request id, when one is bound to this task."""
    return _request_id.get()


def get_logger(name: str = LOGGER_NAME) -> logging.Logger:
    return logging.getLogger(name)


class JsonFormatter(logging.Formatter):
    """Render one log record per JSON line, folding ``record.extra`` fields in."""

    def __init__(self, *, service: str = "futurekind-gateway") -> None:
        super().__init__()
        self._service = service

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(timespec="milliseconds").replace(
                "+00:00", "Z"
            ),
            "level": record.levelname.lower(),
            "logger": record.name,
            "service": self._service,
            "message": record.getMessage(),
        }
        request_id = getattr(record, "request_id", None) or _request_id.get()
        if request_id:
            payload["request_id"] = request_id
        for key, value in record.__dict__.items():
            if key in STANDARD_RECORD_ATTRS or key.startswith("_") or key in payload:
                continue
            if key in SUPPRESSED_FIELDS:
                continue
            payload[key] = value
        if record.exc_info and record.exc_info[0] is not None:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, ensure_ascii=False)


class PlainFormatter(logging.Formatter):
    """Human-readable fallback for developers running the Gateway in a terminal."""

    def __init__(self) -> None:
        super().__init__(
            fmt="%(asctime)s %(levelname)-7s %(name)s %(message)s",
            datefmt="%H:%M:%S",
        )

    def format(self, record: logging.LogRecord) -> str:
        extras = {
            key: value
            for key, value in record.__dict__.items()
            if key not in STANDARD_RECORD_ATTRS
            and key not in SUPPRESSED_FIELDS
            and not key.startswith("_")
        }
        base = super().format(record)
        if not extras:
            return base
        rendered = " ".join(f"{key}={value}" for key, value in sorted(extras.items()))
        return f"{base} {rendered}"


def configure_logging(
    *,
    level: str = "INFO",
    json_logs: bool = True,
    service: str = "futurekind-gateway",
    stream: Any | None = None,
) -> logging.Logger:
    """Attach one handler to the Gateway logger and return it.

    Idempotent: repeated calls replace this logger's own handlers instead of
    stacking duplicates, so tests and reloads do not multiply log lines.
    """
    logger = get_logger()
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.propagate = False

    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    handler = logging.StreamHandler(stream or sys.stdout)
    handler.setLevel(logging.NOTSET)
    handler.setFormatter(JsonFormatter(service=service) if json_logs else PlainFormatter())
    logger.addHandler(handler)
    return logger


def resolve_level(level: int | str) -> int:
    """Accept either ``logging.INFO`` or ``"info"``.

    Call sites read better with names, and ``Logger.log`` only takes integers,
    so the conversion happens in exactly one place.
    """
    if isinstance(level, int):
        return level
    resolved = getattr(logging, str(level).upper(), None)
    return resolved if isinstance(resolved, int) else logging.INFO


def log_event(
    logger: logging.Logger,
    level: int | str,
    event: str,
    **fields: Any,
) -> None:
    """Emit a named event with structured fields, rejecting PHI-shaped fields.

    ``event`` is a stable identifier (``chat_completed``, ``provider_attempt``)
    so log queries match on it instead of on human prose.
    """
    unsafe = sorted(key for key in fields if key.lower() in FORBIDDEN_FIELDS)
    if unsafe:
        # Log the refusal, not the value: the field names are safe, the content is not.
        # This gets its own event name so an operator can alert on rejections.
        logger.warning(
            "log_event rejected PHI-shaped field(s): %s",
            ", ".join(unsafe),
            extra={
                "event": "log_field_rejected",
                "rejected_fields": unsafe,
                "affected_event": event,
            },
        )
        fields = {
            key: value for key, value in fields.items() if key.lower() not in FORBIDDEN_FIELDS
        }

    extra: dict[str, Any] = {"event": event}
    for key, value in fields.items():
        extra[_safe_field_name(key)] = dict(value) if isinstance(value, Mapping) else value
    logger.log(resolve_level(level), event, extra=extra)


__all__ = [
    "FORBIDDEN_FIELDS",
    "LOGGER_NAME",
    "REQUEST_ID_HEADER",
    "STANDARD_RECORD_ATTRS",
    "SUPPRESSED_FIELDS",
    "JsonFormatter",
    "PlainFormatter",
    "configure_logging",
    "get_logger",
    "get_request_id",
    "log_event",
    "new_request_id",
    "resolve_level",
    "set_request_id",
]
