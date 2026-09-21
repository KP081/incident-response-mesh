"""Minimal Streamlit UI for the Incident Response Mesh.

Left: pick + trigger a scenario. Right: artifacts (triage, hypothesis,
critic verdict) and a two-phase HITL approval flow for high-risk actions
(see core/callbacks.py for why this is two phases, not a blocking prompt).

Run:
    HITL_CAPTURE_ONLY=true uv run streamlit run streamlit_app.py
"""

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

from google.adk.runners import Runner
from google.adk.sessions import DatabaseSessionService

from app import APP_NAME, SCENARIOS_DIR, _run_debug_with_retry
from core.agent import root_agent
from core.parsing import parse_agent_json
from tools.report_tools import create_remediation_draft, render_postmortem

st.set_page_config(page_title="Incident Response Mesh", layout="wide")

for key in ("state", "run_id", "postmortem_written"):
    if key not in st.session_state:
        st.session_state[key] = None


def get_event_loop():
    if "event_loop" not in st.session_state:
        st.session_state.event_loop = asyncio.new_event_loop()
    return st.session_state.event_loop


async def run_incident_for_ui(scenario_id: str) -> tuple[dict, str]:
    scenario = json.loads((SCENARIOS_DIR / f"{scenario_id}.json").read_text())
    session_service = DatabaseSessionService(db_url="sqlite+aiosqlite:///incidents.db")
    run_id = (
        f"{scenario_id}_ui_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')}"
    )
    session = await session_service.create_session(
        app_name=APP_NAME, user_id="ui_user", session_id=run_id
    )
    runner = Runner(
        agent=root_agent, app_name=APP_NAME, session_service=session_service
    )
    await _run_debug_with_retry(
        runner, json.dumps(scenario["trigger_alert"]), "ui_user", session.id
    )
    final = await session_service.get_session(
        app_name=APP_NAME, user_id="ui_user", session_id=session.id
    )
    return dict(final.state), run_id


def write_postmortem(state: dict, run_id: str, action: str, details: str) -> str:
    hypothesis = (
        parse_agent_json(state["hypothesis"]) if state.get("hypothesis") else {}
    )
    triage = state.get("triage_result", {})
    md = render_postmortem(
        {
            "session_id": run_id,
            "service_name": triage.get("service_name", "unknown-service"),
            "root_cause": hypothesis.get("root_cause", "not diagnosed"),
            "cited_log_lines": hypothesis.get("cited_log_lines", []),
            "action": action,
            "details": details,
        }
    )
    Path(f"postmortem_incident_{run_id}.md").write_text(md)
    return md


st.title("🚨 Incident Response Mesh")

left, right = st.columns(2)

with left:
    st.header("Trigger")
    scenario_ids = sorted(p.stem for p in SCENARIOS_DIR.glob("*.json"))
    selected = st.selectbox("Scenario", scenario_ids)

    if st.button("🚀 Trigger Incident", type="primary"):
        with st.spinner("Running Triage → Diagnosis Loop → Fix Advisor..."):
            loop = get_event_loop()
            asyncio.set_event_loop(loop)
            state, run_id = loop.run_until_complete(run_incident_for_ui(selected))
        st.session_state.state = state
        st.session_state.run_id = run_id
        st.session_state.postmortem_written = None
        st.rerun()

with right:
    st.header("Artifacts")
    state = st.session_state.state

    if not state:
        st.info("Trigger a scenario to see results here.")
    else:
        with st.expander("Triage Result", expanded=True):
            st.json(state.get("triage_result", {}))

        with st.expander("Hypothesis", expanded=True):
            hyp = state.get("hypothesis")
            st.json(parse_agent_json(hyp) if hyp else {})

        with st.expander("Critic Verdict", expanded=True):
            st.json(state.get("critic_verdict", {}))

        pending = state.get("pending_high_risk_action")
        if pending and not st.session_state.postmortem_written:
            st.warning(
                f"⚠️ Pending approval: **{pending.get('action')}** on "
                f"**{pending.get('service_name')}**"
            )
            st.caption(pending.get("details", ""))
            c1, c2 = st.columns(2)
            if c1.button("✅ Approve & Execute"):
                result = create_remediation_draft(**pending)
                md = write_postmortem(
                    state, st.session_state.run_id, result["action"], result["details"]
                )
                st.session_state.postmortem_written = md
                st.rerun()
            if c2.button("❌ Deny"):
                md = write_postmortem(
                    state,
                    st.session_state.run_id,
                    f"{pending.get('action')} (BLOCKED -- human denied approval)",
                    "[NOT EXECUTED -- a human denied approval for this action]",
                )
                st.session_state.postmortem_written = md
                st.rerun()
        elif state.get("remediation_plan") and not pending:
            with st.expander("Remediation Plan", expanded=True):
                st.json(parse_agent_json(state["remediation_plan"]))

        if st.session_state.postmortem_written:
            st.subheader("Postmortem")
            st.markdown(st.session_state.postmortem_written)
