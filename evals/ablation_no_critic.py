"""Ablation: same 15 scenarios, no CriticAgent -- LogParserAgent's first
guess goes straight to FixAdvisorAgent, unverified. Compares citation
accuracy against the full pipeline (with Critic) to measure the Critic's
actual lift, rather than assuming it helps.

Run:
    HITL_AUTO_APPROVE=true uv run python3 evals/ablation_no_critic.py
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from google.adk.agents import SequentialAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService

from agents.fix_advisor_agent import build_fix_advisor_agent
from agents.log_parser_agent import build_log_parser_agent
from agents.triage_agent import build_triage_agent
from app import SCENARIOS_DIR, _run_debug_with_retry
from evals.run_business_metrics import score_run

APP_NAME = "incident_mesh_baseline"


def build_baseline_agent() -> SequentialAgent:
    """Same pipeline, CriticAgent/DiagnosisLoop removed entirely --
    LogParserAgent's single unverified guess feeds straight into
    FixAdvisorAgent. Fresh agent instances every call: ADK forbids reusing
    an instance that already has a parent (see the real mesh in core/agent.py).
    """
    return SequentialAgent(
        name="IncidentResponseMeshBaseline",
        sub_agents=[
            build_triage_agent(),
            build_log_parser_agent(),
            build_fix_advisor_agent(),
        ],
    )


async def run_baseline_incident(scenario_id: str) -> dict:
    scenario = json.loads((SCENARIOS_DIR / f"{scenario_id}.json").read_text())
    session_service = InMemorySessionService()
    run_id = f"{scenario_id}_baseline_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')}"
    session = await session_service.create_session(
        app_name=APP_NAME, user_id="eval", session_id=run_id
    )
    runner = Runner(
        agent=build_baseline_agent(), app_name=APP_NAME, session_service=session_service
    )
    await _run_debug_with_retry(
        runner, json.dumps(scenario["trigger_alert"]), "eval", session.id
    )
    final = await session_service.get_session(
        app_name=APP_NAME, user_id="eval", session_id=session.id
    )
    return dict(final.state)


async def main():
    if os.environ.get("HITL_AUTO_APPROVE") is None:
        print(
            "Set HITL_AUTO_APPROVE=true first -- FixAdvisorAgent still has "
            "the HITL gate, it would otherwise block on input()."
        )
        sys.exit(1)

    results = []
    for scenario_path in sorted(SCENARIOS_DIR.glob("*.json")):
        scenario = json.loads(scenario_path.read_text())
        scenario_id = scenario["id"]
        print(f"[baseline] Running {scenario_id}...")
        try:
            state = await run_baseline_incident(scenario_id)
            scores = score_run(state, scenario["ground_truth"])
        except Exception as e:
            scores = {"error": str(e)}
        results.append({"scenario_id": scenario_id, **scores})

    print("\n=== Baseline (no Critic) Results ===")
    for r in results:
        print(r)

    valid = [r for r in results if "error" not in r]
    if valid:
        correct = sum(r["citation_correct"] for r in valid)
        print(
            f"\nBaseline citation accuracy: {correct}/{len(valid)} ({correct / len(valid):.0%})"
        )

    Path("evals/results_baseline.json").write_text(json.dumps(results, indent=2))
    print("\nWritten to evals/results_baseline.json")
    print(
        "\nCompare against evals/results.json (the with-Critic run) for the ablation delta."
    )


if __name__ == "__main__":
    asyncio.run(main())
