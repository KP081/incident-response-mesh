"""HITL execution gate for high-risk remediation actions.

Wired via before_tool_callback on FixAdvisorAgent. When it returns a dict,
ADK skips the real tool call entirely and uses that dict as the result --
verified against the ADK source (_tool_caller.py Step 3) before relying on
this behavior.
"""

from google.adk.tools.tool_context import ToolContext

HIGH_RISK_ACTIONS = {"apply_hotfix", "restart_database", "rollback_deployment"}


def execution_guardrail_callback(tool, args: dict, tool_context: ToolContext):
    if (
        tool.name == "create_remediation_draft"
        and args.get("action") in HIGH_RISK_ACTIONS
    ):
        print(
            f"\n[ALERT] High-risk action detected: {tool.name}(action={args.get('action')!r})"
        )
        approved = input("Approve execution? (yes/no): ").strip().lower() == "yes"
        tool_context.state["hitl_approved"] = approved
        if not approved:
            return {"status": "blocked", "reason": "human denied execution"}
    return None
