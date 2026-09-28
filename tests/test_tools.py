import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from app import SCENARIOS_DIR
from tools.telemetry_tools import fetch_logs, query_metrics, seed_telemetry
from tools.report_tools import render_postmortem


def _all_scenarios():
    return [json.loads(p.read_text()) for p in sorted(SCENARIOS_DIR.glob("*.json"))]


def test_scenario_fixtures_have_required_keys():
    scenarios = _all_scenarios()
    assert len(scenarios) >= 3
    required_top = {
        "id", "service", "category", "trigger_alert", "metrics", "logs", "ground_truth",
    }
    for s in scenarios:
        assert required_top <= s.keys(), f"{s.get('id')} missing keys"


async def test_fetch_logs_returns_the_fatal_line_for_every_scenario():
    for s in _all_scenarios():
        await seed_telemetry(s)
        logs = await fetch_logs(s["service"], severity="ALL", limit=50)
        joined = " | ".join(f"{l['level']} {l['msg']}" for l in logs)
        # ts is re-anchored to real time at seed, so compare level + msg only
        expected = s["ground_truth"]["faulty_line"].split(" ", 1)[1]
        assert expected in joined


async def test_fetch_logs_severity_filter_excludes_info():
    scenario = next(s for s in _all_scenarios() if s["service"] == "checkout-service")
    await seed_telemetry(scenario)
    logs = await fetch_logs("checkout-service", severity="WARNING", limit=50)
    assert not any(l["level"] == "INFO" for l in logs)


async def test_query_metrics_returns_series_for_known_service():
    scenario = next(s for s in _all_scenarios() if s["service"] == "checkout-service")
    await seed_telemetry(scenario)
    result = await query_metrics("checkout-service", "memory_usage_pct", window_minutes=15)
    assert result["found"] is True


def test_render_postmortem_includes_evidence_and_action():
    md = render_postmortem(
        {
            "service_name": "checkout-service",
            "root_cause": "memory leak",
            "cited_log_lines": ["04:12:01 FATAL OOMKilled: exit code 137"],
            "action": "rollback_deployment",
            "details": "revert the cache change",
        }
    )
    assert "memory leak" in md and "OOMKilled" in md