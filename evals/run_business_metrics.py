"""Domain-specific evaluation harness.

Runs every scenario fixture through the full agent mesh and scores it
against that scenario's embedded ground_truth.

Run:
    HITL_AUTO_APPROVE=true python evals/run_business_metrics.py
"""

import asyncio
import json
import os
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app import SCENARIOS_DIR, run_incident
from core.parsing import parse_agent_json


def score_run(state: dict, ground_truth: dict) -> dict:
    hypothesis_raw = state.get("hypothesis")
    hypothesis = parse_agent_json(hypothesis_raw) if hypothesis_raw else {}
    critic = state.get("critic_verdict") or {}

    cited = hypothesis.get("cited_log_lines", [])
    faulty_line = ground_truth["faulty_line"]
    citation_correct = any(c in faulty_line or faulty_line in c for c in cited)

    return {
        "citation_correct": citation_correct,
        "critic_approved": bool(critic.get("approved")),
        "safety_adherence": state.get("hitl_approved") is not False,
    }


async def main():
    if os.environ.get("HITL_AUTO_APPROVE") is None:
        print(
            "Set HITL_AUTO_APPROVE=true (or false) first -- otherwise "
            "high-risk actions will block on input()."
        )
        sys.exit(1)

    results = []
    for scenario_path in sorted(SCENARIOS_DIR.glob("*.json")):
        scenario = json.loads(scenario_path.read_text())
        scenario_id = scenario["id"]
        print(f"Running {scenario_id}...")
        try:
            state = await run_incident(scenario_id)
            scores = score_run(state, scenario["ground_truth"])
        except (ValueError, RuntimeError) as e:
            scores = {"error": str(e), "traceback": traceback.format_exc()}
        results.append({"scenario_id": scenario_id, **scores})

    print("\n=== Results ===")
    for r in results:
        print(r)

    valid = [r for r in results if "error" not in r]
    if valid:
        acc = sum(r["citation_correct"] for r in valid) / len(valid)
        print(
            f"\nCitation accuracy: {acc:.0%} ({sum(r['citation_correct'] for r in valid)}/{len(valid)})"
        )

    Path("evals/results.json").write_text(json.dumps(results, indent=2))
    print("\nWritten to evals/results.json")


if __name__ == "__main__":
    asyncio.run(main())
