"""CriticAgent: verifies LogParserAgent's hypothesis against raw logs.

IMPORTANT: exit_loop() sets skip_summarization=True internally, which means
the agent's final text response (and therefore its output_key) never fires
on the turn where it approves. So the verdict is written directly via the
record_verdict tool instead -- this works reliably whether the hypothesis
is approved or rejected.
"""

from google.adk.agents import LlmAgent
from google.adk.tools import exit_loop
from google.adk.tools.tool_context import ToolContext

from core.config import MODEL_NAME
from tools.telemetry_tools import fetch_logs


def record_verdict(approved: bool, reason: str, tool_context: ToolContext) -> dict:
    """Record the critic's verdict directly into session state.

    Always call this BEFORE exit_loop -- exit_loop skips the model's final
    text response, so output_key alone cannot be trusted to save the verdict.
    """
    verdict = {"approved": approved, "reason": reason}
    tool_context.state["critic_verdict"] = verdict
    return verdict


critic_agent = LlmAgent(
    name="CriticAgent",
    model=MODEL_NAME,
    instruction=(
        "You are a skeptical reviewer checking a root-cause hypothesis "
        "before it's acted on.\n\n"
        "Hypothesis under review (JSON): {hypothesis}\n"
        "Triage result (JSON): {triage_result}\n\n"
        "Steps:\n"
        '1. Call fetch_logs (severity="ALL") for the service in '
        "triage_result to get the ground-truth raw logs yourself.\n"
        "2. Reject the hypothesis if ANY cited_log_lines entry is not a "
        "verbatim substring of a raw log line you fetched.\n"
        "3. Reject the hypothesis if it cites a WARNING while an "
        "unaddressed FATAL or ERROR exists in the same raw logs.\n"
        "4. Otherwise, approve it.\n\n"
        "5. ALWAYS call record_verdict with your decision and reason -- "
        "do this every time, approved or not.\n"
        "6. ONLY if you approved, call exit_loop right after record_verdict."
    ),
    tools=[fetch_logs, record_verdict, exit_loop],
)
