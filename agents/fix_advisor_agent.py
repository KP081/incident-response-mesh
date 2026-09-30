"""FixAdvisorAgent: drafts a remediation action and postmortem.

Only runs after DiagnosisLoop exits with an approved hypothesis.
"""

from google.adk.agents import LlmAgent

from tools.git_tools import fetch_git_diff, open_remediation_pr
from tools.report_tools import create_remediation_draft, render_postmortem

from core.config import MODEL_NAME
from core.callbacks import fix_advisor_tool_callback
from core.observability import (
    before_agent_logging_callback,
    after_agent_logging_callback,
    after_tool_logging_callback,
)


def build_fix_advisor_agent() -> LlmAgent:
    return LlmAgent(
        name="FixAdvisorAgent",
        model=MODEL_NAME,
        instruction=(
            "You are a remediation advisor. An approved diagnosis is ready:\n\n"
            "Hypothesis (JSON): {hypothesis}\n"
            "Critic verdict (JSON): {critic_verdict?}\n"
            "Triage result (JSON): {triage_result}\n\n"
            "1. Call fetch_git_diff for the affected service to check for a "
            "recent suspect commit.\n"
            "2. Decide on ONE action: rollback_deployment, apply_hotfix, "
            "restart_database, or config_adjustment.\n"
            "3. Call create_remediation_draft with that action and a clear "
            "explanation tied to the cited log evidence.\n"
            'If create_remediation_draft\'s result has status "blocked", clearly say '
            "in your output that the action was NOT executed and a human denied it -- "
            "do not describe it as completed.\n"
            "4. If create_remediation_draft succeeded (not blocked), call "
            "open_remediation_pr with the same service name, action, and details "
            'to record it as a real PR. If its result has status "error", say in '
            "your output that the PR could not be opened and include the reason -- "
            "do not treat this as a failure of the remediation itself.\n"
            "5. Call render_postmortem with a dict combining the service name, "
            "root cause, cited log lines, action, and details.\n"
            "6. Output the final remediation plan as JSON: "
            '{"action": ..., "details": ..., "postmortem_md": ...}.\n'
            "If critic_verdict shows approved: false, this JSON is still "
            'required -- set "action" to "escalate_to_human", and make '
            '"details" state plainly that the diagnosis loop could not '
            "confirm a hypothesis within its retry limit, so no "
            "remediation was attempted. Do not skip the JSON or reply in "
            "plain prose for this case."
        ),
        tools=[
            fetch_git_diff,
            open_remediation_pr,
            create_remediation_draft,
            render_postmortem,
        ],
        output_key="remediation_plan",
        before_agent_callback=before_agent_logging_callback,
        after_agent_callback=after_agent_logging_callback,
        before_tool_callback=fix_advisor_tool_callback,
        after_tool_callback=after_tool_logging_callback,
    )


fix_advisor_agent = build_fix_advisor_agent()
