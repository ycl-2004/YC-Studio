"""Verify the Stage 7 structured logging contract in an isolated subprocess.

Run from ``backend/`` with ``uv run python scripts/check_logging.py``.
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any
from uuid import UUID

BACKEND_DIR = Path(__file__).resolve().parents[1]


def run_probe() -> list[dict[str, Any]]:
    """Run the production-mode probe and parse every stdout line as JSON."""

    environment = os.environ.copy()
    environment["ENVIRONMENT"] = "production"
    result = subprocess.run(
        [sys.executable, "scripts/log_probe.py"],
        cwd=BACKEND_DIR,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"logging probe failed with exit {result.returncode}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )

    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert lines, "logging probe produced no stdout"
    try:
        events = [json.loads(line) for line in lines]
    except json.JSONDecodeError as error:
        raise AssertionError(f"non-JSON production log line: {error.doc!r}") from error

    assert all(isinstance(event, dict) for event in events)
    print(f"PASS all {len(events)} production log lines are valid JSON objects")
    return events


def verify_request_contract(events: list[dict[str, Any]]) -> None:
    """Verify context isolation, headers, timing, foreign logs, and SQL logs."""

    summary = _one(events, event="probe.summary")
    responses = summary["normal_responses"]
    request_ids = {response["marker"]: response["request_id"] for response in responses}

    assert set(request_ids) == {"alpha", "beta"}
    assert len(set(request_ids.values())) == 2
    for request_id in request_ids.values():
        UUID(request_id)
    print("PASS concurrent requests received distinct UUID request IDs")

    for marker, request_id in request_ids.items():
        application_event = _one(events, event="probe.application", probe_marker=marker)
        assert application_event["request_id"] == request_id

        uvicorn_event = _one(
            events,
            event="probe.uvicorn_inside_request",
            probe_marker=marker,
        )
        assert uvicorn_event["request_id"] == request_id
        assert uvicorn_event["logger"] == "uvicorn.error"

        sql_events = [
            event
            for event in events
            if event.get("logger", "").startswith("sqlalchemy.engine")
            and event.get("probe_marker") == marker
            and "SELECT 1" in event.get("event", "")
        ]
        assert sql_events
        assert all(event["request_id"] == request_id for event in sql_events)

        hidden_parameter_events = [
            event
            for event in events
            if event.get("logger", "").startswith("sqlalchemy.engine")
            and event.get("probe_marker") == marker
            and "SQL parameters hidden due to hide_parameters=True" in event.get("event", "")
        ]
        assert hidden_parameter_events

        completed_event = _one(
            events,
            event="request.completed",
            probe_marker=marker,
        )
        assert completed_event["request_id"] == request_id
        assert completed_event["status_code"] == 200
        assert completed_event["duration_ms"] >= 0
        assert completed_event["http_method"] == "GET"

    print("PASS app, Uvicorn, SQLAlchemy, and completion logs share each response request ID")
    print("PASS SQLAlchemy logs hide parameter values")

    outside_uvicorn_event = _one(events, event="probe.uvicorn_outside_request")
    assert outside_uvicorn_event["logger"] == "uvicorn.error"
    print("PASS Uvicorn standard-library logs use the shared structured renderer")


def verify_failure_contract(events: list[dict[str, Any]]) -> None:
    """Verify an unhandled exception carries its request context and traceback."""

    summary = _one(events, event="probe.summary")
    assert summary["error_status_code"] == 500

    failed_event = _one(events, event="request.failed", probe_marker="error")
    request_id = failed_event["request_id"]
    UUID(request_id)
    assert failed_event["status_code"] == 500
    assert failed_event["duration_ms"] >= 0
    assert "RuntimeError" in failed_event["exception"]
    assert "intentional Step 7 logging probe failure" in failed_event["exception"]
    assert summary["error_request_id"] == request_id
    assert summary["error_body_request_id"] == request_id
    print("PASS failure log, response header/body, status, duration, and traceback share one ID")


def _one(events: list[dict[str, Any]], **expected: Any) -> dict[str, Any]:
    matches = [
        event for event in events if all(event.get(key) == value for key, value in expected.items())
    ]
    assert len(matches) == 1, f"expected one event matching {expected}, got {len(matches)}"
    return matches[0]


def main() -> None:
    """Run all Step 7 logging checks."""

    events = run_probe()
    verify_request_contract(events)
    verify_failure_contract(events)
    print("PASS Stage 0 Step 7 structured logging check completed")


if __name__ == "__main__":
    main()
