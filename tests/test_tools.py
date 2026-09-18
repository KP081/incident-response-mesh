import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.telemetry_tools import fetch_logs, query_metrics, SCENARIOS_DIR
from tools.git_tools import fetch_git_diff
from tools.report_tools import create_remediation_draft, render_postmortem


def _all_scenarios():
    return [json.loads(p.read_text()) for p in sorted(SCENARIOS_DIR.glob("*.json"))]


def test_scenario_fixtures_have_required_keys():
    scenarios = _all_scenarios()
    assert len(scenarios) >= 3
    required_top = {
        "id",
        "service",
        "category",
        "trigger_alert",
        "metrics",
        "logs",
        "ground_truth",
    }
    for s in scenarios:
        assert required_top <= s.keys(), f"{s.get('id')} missing keys"


def test_fetch_logs_returns_the_fatal_line_for_every_scenario():
    for s in _all_scenarios():
        logs = fetch_logs(s["service"], severity="ALL", limit=50)
        joined = " | ".join(f"{l['ts']} {l['level']} {l['msg']}" for l in logs)
        assert s["ground_truth"]["faulty_line"] in joined


def test_fetch_logs_severity_filter_excludes_info():
    logs = fetch_logs("checkout-service", severity="WARNING", limit=50)
    assert not any(l["level"] == "INFO" for l in logs)


def test_query_metrics_returns_series_for_known_service():
    result = query_metrics("checkout-service", "memory_usage_pct", window_minutes=15)
    assert result["found"] is True


def test_fetch_git_diff_known_and_unknown_service():
    assert "max_size" in fetch_git_diff("checkout-service", "abc123")
    assert fetch_git_diff("totally-unknown-service", "abc123") == ""


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
