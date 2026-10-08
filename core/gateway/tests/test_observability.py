"""Unit tests for structured logging and the PHI field guard."""

from __future__ import annotations

import importlib
import io
import json
import logging
from collections.abc import Iterator

import pytest

from futurekind_gateway.main import uvicorn_log_config
from futurekind_gateway.observability.logging import (
    FORBIDDEN_FIELDS,
    STANDARD_RECORD_ATTRS,
    JsonFormatter,
    PlainFormatter,
    configure_logging,
    get_logger,
    get_request_id,
    log_event,
    new_request_id,
    resolve_level,
    set_request_id,
)


@pytest.fixture
def capture() -> Iterator[tuple[logging.Logger, io.StringIO]]:
    """A Gateway logger writing to a buffer, restored afterwards."""
    stream = io.StringIO()
    logger = get_logger()
    saved_handlers = list(logger.handlers)
    saved_propagate = logger.propagate
    logger.handlers.clear()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter(service="futurekind-gateway"))
    logger.addHandler(handler)
    logger.propagate = False
    logger.setLevel(logging.DEBUG)
    try:
        yield logger, stream
    finally:
        logger.handlers.clear()
        logger.addHandler(logging.NullHandler())
        logger.handlers.clear()
        logger.handlers.extend(saved_handlers)
        logger.propagate = saved_propagate


def records(stream: io.StringIO) -> list[dict]:
    lines = [line for line in stream.getvalue().splitlines() if line.strip()]
    return [json.loads(line) for line in lines]


# -- levels -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        (logging.INFO, logging.INFO),
        ("info", logging.INFO),
        ("INFO", logging.INFO),
        ("warning", logging.WARNING),
        ("ERROR", logging.ERROR),
        ("nonsense", logging.INFO),
        (None, logging.INFO),
    ],
)
def test_levels_accept_names_and_numbers(given: object, expected: int) -> None:
    assert resolve_level(given) == expected  # type: ignore[arg-type]


def test_log_event_accepts_a_textual_level(capture) -> None:
    """Regression: the helper documented names but called Logger.log with one."""
    logger, stream = capture

    log_event(logger, "warning", "provider_attempt", provider="ollama")

    assert records(stream)[0]["level"] == "warning"


def test_log_event_accepts_an_integer_level(capture) -> None:
    logger, stream = capture

    log_event(logger, logging.ERROR, "catalog_load_failed", detail="bad yaml")

    assert records(stream)[0]["level"] == "error"


# -- the PHI guard --------------------------------------------------------------------------------


@pytest.mark.parametrize("field", sorted(FORBIDDEN_FIELDS))
def test_content_shaped_fields_are_never_written(field: str) -> None:
    stream = io.StringIO()
    logger = get_logger()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logger.handlers[:] = [handler]
    logger.propagate = False
    try:
        log_event(logger, "info", "chat_completed", **{field: "patient narrative"})
    finally:
        logger.handlers[:] = []

    written = stream.getvalue()
    # The value never appears anywhere, and the field is not a key on the event.
    assert "patient narrative" not in written
    emitted = [json.loads(line) for line in written.splitlines() if line.strip()]
    event_line = next(item for item in emitted if item.get("event") == "chat_completed")
    assert field not in event_line


def test_a_rejected_field_is_reported_without_leaking_its_value(capture) -> None:
    logger, stream = capture

    log_event(logger, "info", "chat_completed", content="MRN 4471 details", attempts=1)

    emitted = records(stream)
    warning = next(item for item in emitted if item["event"] == "log_field_rejected")
    event_line = next(item for item in emitted if item["event"] == "chat_completed")

    assert warning["rejected_fields"] == ["content"]
    assert warning["affected_event"] == "chat_completed"
    assert "MRN 4471" not in stream.getvalue()
    assert event_line["level"] == "info"
    assert event_line["attempts"] == 1
    assert "content" not in event_line


# -- JSON shape -----------------------------------------------------------------------------------


def test_a_line_is_one_json_object_naming_the_event(capture) -> None:
    logger, stream = capture

    log_event(logger, "info", "chat_completed", capability="default", model="gpt-oss:20b")

    (entry,) = records(stream)
    assert entry["event"] == "chat_completed"
    assert entry["message"] == "chat_completed"
    assert entry["service"] == "futurekind-gateway"
    assert entry["capability"] == "default"
    assert entry["timestamp"].endswith("Z")


def test_standard_log_record_attributes_do_not_pollute_output(capture) -> None:
    """Only what the caller attached appears; module/lineno/filename stay internal."""
    logger, stream = capture

    log_event(logger, "info", "request_completed", status=200)

    entry = records(stream)[0]
    assert not set(entry) & (STANDARD_RECORD_ATTRS - {"msg"})
    assert "module" not in entry
    assert "pathname" not in entry


def test_a_field_colliding_with_a_record_attribute_is_renamed_not_dropped(capture) -> None:
    """``extra={"module": ...}`` raises KeyError inside logging; the guard prevents it."""
    logger, stream = capture

    log_event(logger, "info", "provider_loaded", module="futurekind_gateway.providers")

    assert records(stream)[0]["ctx_module"] == "futurekind_gateway.providers"


def test_mapping_fields_are_serialised_as_objects(capture) -> None:
    logger, stream = capture

    log_event(logger, "info", "gateway_error", error_details={"provider": "ollama"})

    assert records(stream)[0]["error_details"] == {"provider": "ollama"}


def test_the_request_id_is_attached_from_the_context(capture) -> None:
    logger, stream = capture
    set_request_id("care-erp-4711")
    try:
        log_event(logger, "info", "chat_completed")
        entry = records(stream)[0]
    finally:
        set_request_id(None)

    assert entry["request_id"] == "care-erp-4711"
    assert get_request_id() is None


def test_an_exception_is_included_once(capture) -> None:
    logger, stream = capture

    try:
        raise ValueError("provider exploded")
    except ValueError:
        logger.exception("unhandled_exception", extra={"error_type": "ValueError"})

    entry = records(stream)[0]
    assert "ValueError: provider exploded" in entry["exception"]
    assert entry["error_type"] == "ValueError"


def test_non_serialisable_values_survive_rather_than_crash_the_logger(capture) -> None:
    logger, stream = capture

    log_event(logger, "info", "gateway_stopped", handler=io.StringIO())

    assert "StringIO" in records(stream)[0]["handler"]


# -- plain formatter ---------------------------------------------------------------------------


def test_the_plain_formatter_renders_extras_inline() -> None:
    record = logging.makeLogRecord({"msg": "chat_completed", "levelno": logging.INFO})
    record.capability = "default"
    record.attempts = 2

    line = PlainFormatter().format(record)

    assert "chat_completed" in line
    assert "attempts=2" in line
    assert "capability=default" in line


def test_the_plain_formatter_adds_nothing_when_there_is_nothing_to_add() -> None:
    record = logging.makeLogRecord({"msg": "gateway_stopped", "levelno": logging.INFO})

    assert PlainFormatter().format(record).endswith("gateway_stopped")


def test_terminal_colour_fields_are_dropped_from_both_formats() -> None:
    """uvicorn attaches ``color_message`` with ANSI escapes for TTY output.

    Left in, the audit log would carry raw escape codes; the plain ``message``
    already holds the same text.
    """
    record = logging.makeLogRecord({"msg": "Started server process [436]", "levelno": logging.INFO})
    record.color_message = "Started server process [\x1b[36m%d\x1b[0m]"

    rendered = JsonFormatter().format(record)
    plain = PlainFormatter().format(record)

    assert "\x1b" not in rendered
    assert "color_message" not in rendered
    assert json.loads(rendered)["message"] == "Started server process [436]"
    assert "\x1b" not in plain


# -- uvicorn integration -------------------------------------------------------------------------


def test_the_uvicorn_log_config_points_at_importable_formatters() -> None:
    """A typo in the dotted path would only surface when the server starts."""
    config = uvicorn_log_config("futurekind-gateway", json_logs=True)
    formatter = config["formatters"]["gateway"]

    assert formatter["service"] == "futurekind-gateway"
    module_path, _, class_name = formatter["()"].rpartition(".")
    loaded = importlib.import_module(module_path)
    assert getattr(loaded, class_name) is JsonFormatter


def test_the_uvicorn_log_config_selects_the_plain_formatter_on_request() -> None:
    config = uvicorn_log_config("futurekind-gateway", json_logs=False)

    assert config["formatters"]["gateway"]["()"].endswith("PlainFormatter")
    assert "service" not in config["formatters"]["gateway"]


def test_uvicorn_writes_through_one_handler_and_does_not_duplicate() -> None:
    config = uvicorn_log_config("futurekind-gateway", json_logs=True)
    loggers = config["loggers"]

    assert set(loggers) == {"uvicorn", "uvicorn.error", "uvicorn.access"}
    for name, entry in loggers.items():
        assert entry["handlers"] == ["gateway"], f"{name} would also emit uvicorn's default output"
        assert entry["propagate"] is False, f"{name} would be written twice"
    assert loggers["uvicorn.access"]["level"] == "WARNING"


# -- configuration -----------------------------------------------------------------------------


def test_configure_logging_is_idempotent() -> None:
    """Called per test or on reload, it must not stack handlers into duplicated lines."""
    stream_one = io.StringIO()
    stream_two = io.StringIO()
    logger = configure_logging(level="INFO", json_logs=True, stream=stream_one)
    configure_logging(level="INFO", json_logs=True, stream=stream_two)

    try:
        assert len(logger.handlers) == 1
        logger.info("only once")
        assert stream_one.getvalue() == ""
        assert stream_two.getvalue().count("only once") == 1
    finally:
        logger.handlers.clear()


def test_configure_logging_honours_a_named_level() -> None:
    stream = io.StringIO()
    logger = configure_logging(level="warning", json_logs=True, stream=stream)
    try:
        logger.info("quiet")
        logger.warning("loud")
    finally:
        logger.handlers.clear()

    assert "quiet" not in stream.getvalue()
    assert "loud" in stream.getvalue()


def test_configure_logging_can_write_plain_text(tmp_path: object) -> None:
    stream = io.StringIO()
    logger = configure_logging(level="INFO", json_logs=False, stream=stream)
    try:
        logger.info("developer run")
    finally:
        logger.handlers.clear()

    assert stream.getvalue().strip().endswith("developer run")
    assert not stream.getvalue().lstrip().startswith("{")


def test_the_closed_handler_from_a_reconfigure_is_not_reused() -> None:
    stream = io.StringIO()
    configure_logging(stream=stream)
    configure_logging(stream=io.StringIO())
    logger = configure_logging(stream=stream)
    try:
        logger.info("still writable")
    finally:
        logger.handlers.clear()

    assert "still writable" in stream.getvalue()


# -- request ids --------------------------------------------------------------------------------


def test_request_ids_are_unique_and_url_safe() -> None:
    generated = {new_request_id() for _ in range(200)}

    assert len(generated) == 200
    assert all(len(item) == 32 and item.isalnum() for item in generated)


def test_request_id_defaults_to_none_outside_a_request() -> None:
    set_request_id(None)
    assert get_request_id() is None
