"""Domain-specific evaluation harness.

Runs every scenario fixture through the full agent mesh (N trials each) and
scores it against that scenario's embedded ground_truth.

Each run is scored twice: on the hypothesis LogParser produced FIRST (before
the Critic saw it) and on the FINAL one. Comparing the two inside the same
run measures what the Critic actually changed.

Run (isolated sqlite so the live DB isn't touched):
    DATABASE_URL="sqlite+aiosqlite:///eval.db" HITL_AUTO_APPROVE=true \
        uv run python evals/run_business_metrics.py --trials 3
"""

import argparse
import asyncio
import json
import os
import sys
import traceback
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# Evals must never open real PRs on the sandbox repo.
os.environ.setdefault("EVAL_DRY_RUN", "true")

from app import SCENARIOS_DIR, run_incident
from core.parsing import parse_agent_json

from google.genai.errors import APIError
from core.config import MODEL_NAME


def _parse_hyp(raw) -> dict:
    try:
        return parse_agent_json(raw) if raw else {}
    except ValueError:
        return {}


def _hit(hyp: dict, faulty_line: str) -> bool:
    """Did the hypothesis cite the line that is the real root cause?"""
    return any(
        c and (c in faulty_line or faulty_line in c)
        for c in hyp.get("cited_log_lines", [])
    )


def _grounded(hyp: dict, logs: list[dict]) -> bool:
    """Is every cited line really present in the logs (no fabrication)?"""
    known = [l["msg"] for l in logs] + [f"{l['level']} {l['msg']}" for l in logs]
    cited = hyp.get("cited_log_lines", [])
    return bool(cited) and all(any(c in k for k in known) for c in cited)


def score_run(state: dict, scenario: dict) -> dict:
    faulty_line = scenario["ground_truth"]["faulty_line"]
    history = state.get("critic_history") or []
    final = _parse_hyp(state.get("hypothesis"))
    first = _parse_hyp(history[0].get("hypothesis")) if history else final

    return {
        "first_pass_correct": _hit(first, faulty_line),
        "citation_correct": _hit(final, faulty_line),
        "first_pass_grounded": _grounded(first, scenario["logs"]),
        "final_grounded": _grounded(final, scenario["logs"]),
        "critic_rejections": sum(1 for v in history if not v.get("approved")),
        "critic_approved": bool((state.get("critic_verdict") or {}).get("approved")),
        "safety_adherence": state.get("hitl_approved") is not False,
    }


async def main():
    if os.environ.get("HITL_AUTO_APPROVE") is None:
        print(
            "Set HITL_AUTO_APPROVE=true (or false) first -- otherwise "
            "high-risk actions will block on input()."
        )
        sys.exit(1)

    parser = argparse.ArgumentParser()
    parser.add_argument("--trials", type=int, default=1)
    parser.add_argument("--difficulty", choices=["easy", "hard", "all"], default="all")
    parser.add_argument(
        "--resume",
        action="store_true",
        help="keep the successful runs already in results.json, retry only the rest",
    )
    args = parser.parse_args()

    results_path = Path("evals/results.json")
    results = []
    if args.resume and results_path.exists():
        # keep successes only; errored runs get retried
        results = [r for r in json.loads(results_path.read_text()) if "error" not in r]
    done = {(r["scenario_id"], r["trial"]) for r in results}

    scenarios = []
    for path in sorted(SCENARIOS_DIR.glob("*.json")):
        s = json.loads(path.read_text())
        if args.difficulty in ("all", s.get("difficulty", "easy")):
            scenarios.append(s)

    jobs = [(s, t) for s in scenarios for t in range(1, args.trials + 1)]
    consecutive_api_errors = 0

    for scenario, trial in jobs:
        if (scenario["id"], trial) in done:
            continue
        print(f"Running {scenario['id']} (trial {trial}/{args.trials})...")
        meta = {
            "scenario_id": scenario["id"],
            "category": scenario["category"],
            "difficulty": scenario.get("difficulty", "easy"),
            "trial": trial,
            "model": MODEL_NAME,
        }
        try:
            state = await run_incident(scenario["id"])
            results.append({**meta, **score_run(state, scenario)})
            consecutive_api_errors = 0
        except Exception as e:
            is_api = isinstance(e, APIError)
            entry = {**meta, "error": str(e)[:200], "infra_error": is_api}
            if not is_api:  # a real bug deserves its traceback, an API blip doesn't
                entry["traceback"] = traceback.format_exc()
            results.append(entry)
            consecutive_api_errors = consecutive_api_errors + 1 if is_api else 0
        results_path.write_text(json.dumps(results, indent=2))

        if consecutive_api_errors >= 3:
            print(
                "\n3 API errors in a row -- Gemini looks down/overloaded. Stopping early.\n"
                "Re-run the same command with --resume to continue from here."
            )
            break

    valid = [r for r in results if "error" not in r]
    print(f"\n=== Summary (model={MODEL_NAME}) ===")
    groups = defaultdict(list)
    for r in valid:
        groups[r["difficulty"]].append(r)
    for name, rs in sorted(groups.items()):
        n = len(rs)

        def total(key):
            return sum(r[key] for r in rs)

        print(
            f"[{name}] runs={n}  first_pass={total('first_pass_correct')}/{n}  "
            f"final={total('citation_correct')}/{n}  "
            f"grounded {total('first_pass_grounded')}->{total('final_grounded')}/{n}  "
            f"critic_rejections={total('critic_rejections')}"
        )
    errors = [r for r in results if "error" in r]
    if errors:
        infra = sum(1 for r in errors if r.get("infra_error"))
        print(
            f"{len(errors)} run(s) errored ({infra} API/infra, {len(errors) - infra} other) "
            "-- excluded from the numbers above"
        )
    print("\nWritten to evals/results.json")


if __name__ == "__main__":
    asyncio.run(main())
