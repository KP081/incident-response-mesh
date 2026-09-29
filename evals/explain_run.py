"""Prints the full diagnosis-loop transcript for one scenario -- every
hypothesis LogParser proposed and Critic's verdict on each, in order.
Turns an eval result into a documented case study.

Run:
    DATABASE_URL="sqlite+aiosqlite:///eval.db" HITL_AUTO_APPROVE=true \
        uv run python evals/explain_run.py scenario_16_stale_cache
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app import run_incident
from core.parsing import parse_agent_json


async def main():
    scenario_id = sys.argv[1]
    state = await run_incident(scenario_id)

    for i, entry in enumerate(state.get("critic_history", []), 1):
        hyp = parse_agent_json(entry["hypothesis"]) if entry.get("hypothesis") else {}
        print(f"\n--- Attempt {i} ---")
        print("Root cause:", hyp.get("root_cause"))
        print("Cited lines:", hyp.get("cited_log_lines"))
        print("Critic approved:", entry.get("approved"))
        print("Critic reason:", entry.get("reason"))


if __name__ == "__main__":
    asyncio.run(main())
