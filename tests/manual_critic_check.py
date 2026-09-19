"""Manually run CriticAgent in isolation against a deliberately bad
hypothesis -- proves the rejection logic works without hoping the real
model makes a mistake on its own.

Run manually (uses real API quota, not part of the pytest suite):
    python tests/manual_critic_check.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv()

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService

from agents.critic_agent import critic_agent

APP_NAME = "critic_isolated_test"

# Deliberately bad: cites the WARNING, ignores the unaddressed FATAL.
BAD_HYPOTHESIS = {
    "root_cause": "cache warm-up delay caused elevated login latency",
    "cited_log_lines": ["cache miss rate elevated after deploy"],
    "confidence": 0.8,
}
TRIAGE_RESULT = {
    "service_name": "auth-service",
    "severity": "critical",
    "window_minutes": 15,
    "alert_summary": "Spike in login failures on auth-service",
}


async def main():
    session_service = InMemorySessionService()
    session = await session_service.create_session(
        app_name=APP_NAME,
        user_id="test_user",
        state={"hypothesis": BAD_HYPOTHESIS, "triage_result": TRIAGE_RESULT},
    )
    runner = Runner(
        agent=critic_agent, app_name=APP_NAME, session_service=session_service
    )
    await runner.run_debug(
        "Review this hypothesis.",
        user_id="test_user",
        session_id=session.id,
        quiet=True,
    )
    final = await session_service.get_session(
        app_name=APP_NAME, user_id="test_user", session_id=session.id
    )
    verdict = final.state.get("critic_verdict")
    print("Verdict:", verdict)
    assert verdict is not None, "critic_verdict was never written"
    assert verdict["approved"] is False, (
        "Critic approved a hallucinated citation -- rejection rule needs work"
    )
    print("\n✅ CriticAgent correctly rejected the WARNING-not-FATAL hypothesis.")


if __name__ == "__main__":
    asyncio.run(main())
