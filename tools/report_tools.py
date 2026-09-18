"""
Remediation drafting and postmortem markdown generation tools.
"""

from datetime import datetime, timezone


def create_remediation_draft(service_name: str, action: str, details: str) -> dict:
    """Draft a remediation action for a diagnosed incident."""
    return {
        "service_name": service_name,
        "action": action,
        "details": details,
        "drafted_at": datetime.now(timezone.utc).isoformat(),
    }


def render_postmortem(incident: dict) -> str:
    """Render a structured incident record as a markdown postmortem."""
    lines = [
        f"# Postmortem: {incident.get('service_name', 'unknown-service')}",
        "",
        f"**Session ID:** {incident.get('session_id', 'n/a')}",
        f"**Generated:** {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Root Cause",
        incident.get("root_cause", "_not diagnosed_"),
        "",
        "## Evidence",
    ]
    for line in incident.get("cited_log_lines", []):
        lines.append(f"- `{line}`")

    lines += [
        "",
        "## Remediation",
        f"**Action:** {incident.get('action', 'n/a')}",
        "",
        incident.get("details", "_no details provided_"),
    ]
    return "\n".join(lines)
