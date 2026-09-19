"""CLI entrypoint: run one scenario through the full agent mesh."""

import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()

from google.adk.runners import Runner
from google.adk.sessions import DatabaseSessionService
from google.genai.errors import APIError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

from core.agent import root_agent

from core.parsing import parse_agent_json
from tools.report_tools import render_postmortem

RETRYABLE_CODES = {429, 503}

APP_NAME = "incident_mesh"
SCENARIOS_DIR = Path(__file__).parent / "data" / "scenarios"


def _is_retryable(exc: BaseException) -> bool:
    return isinstance(exc, APIError) and getattr(exc, "code", None) in RETRYABLE_CODES


@retry(
    stop=stop_after_attempt(8),
    wait=wait_exponential(multiplier=2, min=10, max=60),
    retry=retry_if_exception(_is_retryable),
    reraise=True,
)
async def _run_debug_with_retry(runner, message, user_id, session_id):
    return await runner.run_debug(
        message, user_id=user_id, session_id=session_id, quiet=True
    )


async def run_incident(scenario_id: str) -> dict:
    scenario_path = SCENARIOS_DIR / f"{scenario_id}.json"
    scenario = json.loads(scenario_path.read_text())

    session_service = DatabaseSessionService(db_url="sqlite+aiosqlite:///incidents.db")

    run_id = f"{scenario_id}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}"
    session = await session_service.create_session(
        app_name=APP_NAME, user_id="cli_user", session_id=run_id
    )

    runner = Runner(
        agent=root_agent, app_name=APP_NAME, session_service=session_service
    )

    alert_message = json.dumps(scenario["trigger_alert"])
    await _run_debug_with_retry(runner, alert_message, "cli_user", session.id)

    final_session = await session_service.get_session(
        app_name=APP_NAME, user_id="cli_user", session_id=session.id
    )
    state = dict(final_session.state)

    remediation = state.get("remediation_plan")
    if remediation:
        remediation = parse_agent_json(remediation)
        hypothesis = (
            parse_agent_json(state.get("hypothesis", {}))
            if state.get("hypothesis")
            else {}
        )
        triage = state.get("triage_result", {})

        postmortem_md = render_postmortem(
            {
                "session_id": run_id,
                "service_name": triage.get("service_name", "unknown-service"),
                "root_cause": hypothesis.get("root_cause", "not diagnosed"),
                "cited_log_lines": hypothesis.get("cited_log_lines", []),
                "action": remediation.get("action", "n/a"),
                "details": remediation.get("details", ""),
            }
        )
        out_path = Path(f"postmortem_incident_{run_id}.md")
        out_path.write_text(postmortem_md)
        print(f"\nPostmortem written to {out_path}")

    return state


def main():
    if len(sys.argv) != 2:
        print("Usage: python app.py <scenario_id>  (e.g. scenario_01_oom)")
        sys.exit(1)

    scenario_id = sys.argv[1]
    state = asyncio.run(run_incident(scenario_id))

    print("\n=== Final session state ===")
    for key in ("triage_result", "hypothesis", "critic_verdict", "remediation_plan"):
        print(f"\n--- {key} ---")
        print(
            state.get(
                key, "<not set -- check DiagnosisLoop iteration cap / escalation>"
            )
        )


if __name__ == "__main__":
    main()
