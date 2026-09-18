"""CLI entrypoint: run one scenario through the full agent mesh."""

import asyncio
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai.errors import APIError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

from core.agent import root_agent

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

    session_service = InMemorySessionService()
    session = await session_service.create_session(
        app_name=APP_NAME, user_id="cli_user", session_id=scenario_id
    )

    runner = Runner(
        agent=root_agent, app_name=APP_NAME, session_service=session_service
    )

    alert_message = json.dumps(scenario["trigger_alert"])
    await _run_debug_with_retry(runner, alert_message, "cli_user", session.id)

    final_session = await session_service.get_session(
        app_name=APP_NAME, user_id="cli_user", session_id=session.id
    )
    return dict(final_session.state)


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
