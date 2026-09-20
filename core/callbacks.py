"""HITL execution gate for high-risk remediation actions."""

import os

from google.adk.tools.tool_context import ToolContext

HIGH_RISK_ACTIONS = {"apply_hotfix", "restart_database", "rollback_deployment"}


def execution_guardrail_callback(tool, args: dict, tool_context: ToolContext):
    if (
        tool.name == "create_remediation_draft"
        and args.get("action") in HIGH_RISK_ACTIONS
    ):
        auto = os.environ.get("HITL_AUTO_APPROVE")
        if auto is not None:
            approved = auto.strip().lower() == "true"
            print(
                f"\n[ALERT] {tool.name}(action={args.get('action')!r}) "
                f"-- auto-{'approved' if approved else 'denied'} (HITL_AUTO_APPROVE set)"
            )
        else:
            print(
                f"\n[ALERT] High-risk action detected: {tool.name}(action={args.get('action')!r})"
            )
            approved = input("Approve execution? (yes/no): ").strip().lower() == "yes"
        tool_context.state["hitl_approved"] = approved
        if not approved:
            return {"status": "blocked", "reason": "human denied execution"}
    return None
