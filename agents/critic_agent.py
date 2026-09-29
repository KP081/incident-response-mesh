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

    # Keep every verdict + the hypothesis it judged, so evals can compare the
    # FIRST pass against the final one inside the same run. Assign a new list
    # instead of appending in place so ADK registers it as a state change.
    history = list(tool_context.state.get("critic_history", []))
    history.append({**verdict, "hypothesis": tool_context.state.get("hypothesis")})
    tool_context.state["critic_history"] = history
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
        "4. Reject the hypothesis if it cites only a downstream/symptom "
        "line (a crash, assertion failure, or resource exhaustion) while "
        "an EARLIER line in the same window names a specific "
        "configuration, setting, or deployment defect (containing words "
        "like 'misconfigured', 'disabled', 'expired', 'rotated', 'wrong', "
        "'nonexistent') that the hypothesis never cites. Do NOT apply "
        "this rule to earlier lines that are just resource-usage trends "
        "or performance symptoms (e.g. 'GC pause', 'slow heartbeat', "
        "'queue growing') -- those are secondary symptoms, not root "
        "causes, and citing only the final FATAL for those is correct.\n"
        "5. Otherwise, approve it.\n\n"
        "6. Keep `reason` to ONE plain sentence stating which rule "
        "applied and why -- never include step-by-step deliberation.\n"
        "7. ALWAYS call record_verdict with your decision and reason -- "
        "do this every time, approved or not.\n"
        "8. ONLY if you approved, call exit_loop right after record_verdict."
    ),
    tools=[fetch_logs, record_verdict, exit_loop],
)
