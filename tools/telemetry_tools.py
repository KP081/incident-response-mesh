"""
Pure-function mock telemetry tools.

Instead of hitting Prometheus/Datadog, these read from data/scenarios/*.json.
"""

import json
from pathlib import Path

SCENARIOS_DIR = Path(__file__).resolve().parent.parent / "data" / "scenarios"


def _load_all_scenarios() -> list[dict]:
    """
    Load all scenarios from data/scenarios/*.json.
    """
    scenarios = []
    for path in sorted(SCENARIOS_DIR.glob("*.json")):
        with open(path) as f:
            scenarios.append(json.load(f))
    return scenarios


def _find_scenario_for_service(service_name: str) -> dict | None:
    """
    Find the scenario for a given service name.
    """
    for scenario in _load_all_scenarios():
        if scenario["service"] == service_name:
            return scenario
    return None


def query_metrics(service_name: str, metric: str, window_minutes: int) -> dict:
    """
    Query a metric time series for a service over a recent time window.

    Args:
        service_name: The service to query metrics for, e.g. "checkout-service".
        metric: The metric name, e.g. "memory_usage_pct".
        window_minutes: How many minutes of history to return.
    """
    scenario = _find_scenario_for_service(service_name)
    if not scenario:
        return {
            "service_name": service_name,
            "metric": metric,
            "values": [],
            "found": False,
        }

    metrics = scenario.get("metrics", {})
    if metric not in metrics:
        available = [k for k in metrics if k != "window_minutes"]
        if not available:
            return {
                "service_name": service_name,
                "metric": metric,
                "values": [],
                "found": False,
            }
        metric = available[0]

    return {
        "service_name": service_name,
        "metric": metric,
        "values": metrics[metric],
        "window_minutes": min(
            window_minutes, metrics.get("window_minutes", window_minutes)
        ),
        "found": True,
    }


def fetch_logs(service_name: str, severity: str, limit: int) -> list[dict]:
    """
    Fetch recent log lines for a service, optionally filtered by severity.

    Args:
        service_name: The service to fetch logs for.
        severity: Minimum severity ("WARNING", "ERROR", "FATAL"), or "ALL".
        limit: Maximum number of log lines to return, most recent first.
    """
    scenario = _find_scenario_for_service(service_name)
    if not scenario:
        return []

    logs = scenario.get("logs", [])
    if severity != "ALL":
        order = {"INFO": -1, "WARNING": 0, "ERROR": 1, "FATAL": 2}
        min_rank = order.get(severity.upper(), 0)
        logs = [l for l in logs if order.get(l["level"].upper(), -1) >= min_rank]

    return logs[-limit:]
