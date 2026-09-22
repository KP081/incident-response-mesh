"""Minimal Streamlit UI for the Incident Response Mesh.

Designed so a first-time visitor who has never seen this project can
understand what's happening without reading the code: readable scenario
labels, a plain-English caption on each agent step, and a ground-truth
comparison for anyone who wants to sanity-check the result.

Left: pick + trigger a scenario. Right: what each agent did, and a
two-phase HITL approval flow for high-risk actions (see core/callbacks.py
for why this is two phases, not a blocking prompt).

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

from core.config import DATABASE_URL, get_session_service_kwargs

st.set_page_config(page_title="Incident Response Mesh", layout="wide")

CATEGORY_META = {
    "oom": ("🔥", "Memory Leak (OOM)"),
    "deadlock": ("🔒", "Database Deadlock"),
    "auth_regression": ("🔑", "Auth Regression"),
    "network_timeout": ("🌐", "Network Timeout"),
    "bad_deploy": ("🚀", "Bad Deploy"),
    "disk_full": ("💾", "Disk Full"),
    "rate_limit_misconfig": ("🚦", "Rate Limit Misconfig"),
    "db_write_failure": ("🗄️", "DB Write Failure"),
}

for key in (
    "state",
    "run_id",
    "postmortem_written",
    "triggered_scenario_id",
    "pending_scenario_id",
):
    if key not in st.session_state:
        st.session_state[key] = None


@st.cache_data
def load_scenarios() -> dict:
    scenarios = {}
    for path in sorted(SCENARIOS_DIR.glob("*.json")):
        s = json.loads(path.read_text())
        scenarios[s["id"]] = s
    return scenarios


def scenario_label(scenario_id: str, scenarios: dict) -> str:
    s = scenarios[scenario_id]
    emoji, name = CATEGORY_META.get(
        s["category"], ("⚙️", s["category"].replace("_", " ").title())
    )
    return f"{emoji} {name} — {s['service']}"


def get_event_loop():
    if "event_loop" not in st.session_state:
        st.session_state.event_loop = asyncio.new_event_loop()
    return st.session_state.event_loop


async def run_incident_for_ui(scenario_id: str) -> tuple[dict, str]:
    scenario = json.loads((SCENARIOS_DIR / f"{scenario_id}.json").read_text())
    session_service = DatabaseSessionService(db_url=DATABASE_URL, **get_session_service_kwargs())
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
st.markdown(
    "A demo of 4 AI agents handling a production incident end-to-end: "
    "**Triage → Diagnose → Verify → Remediate**, with a human-approval gate "
    "before any risky action runs. Pick a simulated incident below."
)

with st.expander("ℹ️ How this works"):
    st.markdown("""
1. **Trigger** -- you pick a simulated incident and click Trigger. The system receives just the raw alert (like a real PagerDuty payload) -- nothing else, no hints.
2. **Triage** -- an agent extracts which service is affected and how urgent it is.
3. **Diagnose** -- a second agent investigates logs and metrics, then proposes a root cause, citing the exact log line as evidence.
4. **Critic Review** -- a third agent independently re-checks that evidence against the raw logs. If a citation doesn't hold up, it's sent back to step 3 with feedback (up to 3 tries) before anything proceeds.
5. **Remediate** -- once a diagnosis is verified, a fourth agent proposes a fix. Risky actions (like rolling back a deployment) pause here for human approval before they'd actually run.
6. **Postmortem** -- a written record of the whole incident is generated automatically.
""")

scenarios = load_scenarios()
left, right = st.columns(2)

with left:
    st.header("1. Trigger an Incident")
    scenario_ids = list(scenarios.keys())
    selected = st.selectbox(
        "Choose a simulated incident",
        scenario_ids,
        format_func=lambda sid: scenario_label(sid, scenarios),
    )
    alert = scenarios[selected]["trigger_alert"]
    st.info(f"📟 **Alert:** {alert['summary']}  \n**Severity:** {alert['severity']}")

    with st.expander("📋 Raw incident data fed to the agents", expanded=True):
        st.caption(
            "Exactly what the agents receive and can query -- the alert, "
            "metrics, and logs. (The expected answer is hidden until after "
            "you trigger the run, so the diagnosis below is a real result, "
            "not a lookup.)"
        )
        preview = {k: v for k, v in scenarios[selected].items() if k != "ground_truth"}
        st.json(preview)

    if st.button("🚀 Trigger Incident", type="primary"):
        st.session_state.state = None
        st.session_state.postmortem_written = None
        st.session_state.pending_scenario_id = selected
        st.rerun()

    if st.session_state.get("pending_scenario_id"):
        pending_id = st.session_state.pending_scenario_id
        with st.spinner(
            f"Running agents on {scenario_label(pending_id, scenarios)}..."
        ):
            loop = get_event_loop()
            asyncio.set_event_loop(loop)
            state, run_id = loop.run_until_complete(run_incident_for_ui(pending_id))
        st.session_state.state = state
        st.session_state.run_id = run_id
        st.session_state.triggered_scenario_id = pending_id
        st.session_state.pending_scenario_id = None
        st.rerun()

with right:
    st.header("2. What the Agents Did")
    state = st.session_state.state

    if st.session_state.get("pending_scenario_id"):
        st.info("⏳ Agents are working on this incident... (usually 10-30 seconds)")
    elif not state:
        st.info(
            "Select an incident on the left and click **Trigger Incident** "
            "to watch the agents diagnose and respond to it."
        )
    else:
        triage = state.get("triage_result", {})
        with st.expander(f"🔍 Step 1 — Triage", expanded=True):
            st.caption(
                "Identifies which service is affected and how urgent the alert is. "
                "Doesn't diagnose anything yet."
            )
            st.write(f"**Service:** {triage.get('service_name', 'n/a')}")
            st.write(f"**Severity:** {triage.get('severity', 'n/a')}")
            if st.checkbox("Show raw JSON", key="raw_triage"):
                st.json(triage)

        hyp = parse_agent_json(state["hypothesis"]) if state.get("hypothesis") else {}
        with st.expander("🕵️ Step 2 — Diagnosis", expanded=True):
            st.caption(
                "Investigates logs and metrics, proposes a root cause with "
                "evidence quoted verbatim from the logs."
            )
            st.write(f"**Root cause:** {hyp.get('root_cause', 'n/a')}")
            if hyp.get("cited_log_lines"):
                st.write("**Evidence:**")
                for line in hyp["cited_log_lines"]:
                    st.code(line, language=None)
            if st.checkbox("Show raw JSON", key="raw_hypothesis"):
                st.json(hyp)

        critic = state.get("critic_verdict") or {}
        with st.expander("⚖️ Step 3 — Critic Review", expanded=True):
            st.caption(
                "Independently re-checks the diagnosis against the raw logs "
                "before it's trusted -- catches a citation that isn't real, "
                "or a minor warning being blamed while a bigger error was ignored."
            )
            if critic.get("approved"):
                st.success(f"✅ Approved — {critic.get('reason', '')}")
            elif critic:
                st.error(f"❌ Rejected — {critic.get('reason', '')}")
            else:
                st.warning("No verdict recorded.")
            if st.checkbox("Show raw JSON", key="raw_critic"):
                st.json(critic)

        pending = state.get("pending_high_risk_action")
        remediation = state.get("remediation_plan")

        st.subheader("3. Remediation")
        if pending and not st.session_state.postmortem_written:
            st.warning(
                f"⚠️ **Pending approval:** {pending.get('action')} on "
                f"{pending.get('service_name')}"
            )
            st.caption(pending.get("details", ""))
            st.caption(
                "This is a high-risk action -- a human must approve it before "
                "it actually runs."
            )
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
        elif remediation:
            r = parse_agent_json(remediation)
            st.write(f"**Action:** {r.get('action', 'n/a')}")
            st.write(r.get("details", ""))
            if st.checkbox("Show raw JSON", key="raw_remediation"):
                st.json(r)

            if not pending and not st.session_state.postmortem_written:
                st.session_state.postmortem_written = write_postmortem(
                    state,
                    st.session_state.run_id,
                    r.get("action", "n/a"),
                    r.get("details", ""),
                )

        if st.session_state.postmortem_written:
            with st.expander("📄 Full Postmortem"):
                st.markdown(st.session_state.postmortem_written)

        if st.session_state.triggered_scenario_id:
            with st.expander(
                "🎯 Ground Truth (what this incident was designed to test)"
            ):
                st.caption(
                    "For sanity-checking the agents' diagnosis above -- "
                    "not shown to the agents themselves."
                )
                gt = scenarios[st.session_state.triggered_scenario_id]["ground_truth"]
                st.write(f"**Expected root cause:** {gt['root_cause']}")
                st.write(f"**Expected action:** {gt['correct_action']}")
