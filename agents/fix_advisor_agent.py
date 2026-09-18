"""FixAdvisorAgent: drafts a remediation action and postmortem.

Only runs after DiagnosisLoop exits with an approved hypothesis.
"""

from google.adk.agents import LlmAgent

from tools.git_tools import fetch_git_diff
from tools.report_tools import create_remediation_draft, render_postmortem

from core.config import MODEL_NAME

fix_advisor_agent = LlmAgent(
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
        "4. Call render_postmortem with a dict combining the service name, "
        "root cause, cited log lines, action, and details.\n"
        "5. Output the final remediation plan as JSON: "
        '{"action": ..., "details": ..., "postmortem_md": ...}.'
        "If critic_verdict shows approved: false, say so clearly instead of "
        "confidently recommending an action — this means the diagnosis loop "
        "could not confirm a hypothesis within its retry limit."
    ),
    tools=[fetch_git_diff, create_remediation_draft, render_postmortem],
    output_key="remediation_plan",
)
