"""Structured, per-step logging for the agent mesh.

Emits one JSON line per agent turn and per tool call to stdout. This is
deliberately plain structured logging, not OpenTelemetry -- for a
project this size it answers the same question ("what happened, how
long did it take, what failed") without needing a collector/exporter
running anywhere. Swapping this for real OTel spans later means the
callback shape stays the same; only what runs inside them changes.
"""

import json
import logging
import time
from datetime import datetime, timezone

logger = logging.getLogger("incident_mesh")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)

_REDACT_KEYS = {"token", "pat", "password", "secret", "api_key"}


def log_event(event: str, **fields) -> None:
    record = {"ts": datetime.now(timezone.utc).isoformat(), "event": event, **fields}
    logger.info(json.dumps(record, default=str))


def _redact(args: dict) -> dict:
    return {k: ("***" if k.lower() in _REDACT_KEYS else v) for k, v in args.items()}


def before_agent_logging_callback(callback_context):
    callback_context.state["_agent_start_ts"] = time.monotonic()
    log_event("agent_start", agent=callback_context.agent_name)
    return None


def after_agent_logging_callback(callback_context):
    start = callback_context.state.get("_agent_start_ts")
    duration_ms = round((time.monotonic() - start) * 1000, 1) if start else None
    log_event("agent_end", agent=callback_context.agent_name, duration_ms=duration_ms)
    return None


def before_tool_logging_callback(tool, args, tool_context):
    tool_context.state[f"_tool_start_{tool.name}"] = time.monotonic()
    log_event("tool_call", tool=tool.name, args=_redact(dict(args)))
    return None


def after_tool_logging_callback(tool, args, tool_context, tool_response):
    start = tool_context.state.get(f"_tool_start_{tool.name}")
    duration_ms = round((time.monotonic() - start) * 1000, 1) if start else None
    ok = not (isinstance(tool_response, dict) and tool_response.get("status") == "error")
    log_event("tool_result", tool=tool.name, duration_ms=duration_ms, ok=ok)
    return None