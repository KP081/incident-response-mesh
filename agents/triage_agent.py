"""TriageAgent: extracts service/severity/timeframe from a raw alert.

Deliberately forbidden from diagnosing anything -- that's LogParserAgent's
job. Keeping this stage narrow makes it cheap (a smaller model is fine).
"""

from google.adk.agents import LlmAgent

from core.config import MODEL_NAME

triage_agent = LlmAgent(
    name="TriageAgent",
    model=MODEL_NAME,
    instruction=(
        "You are an incident triage agent. You will receive a raw alert "
        "payload (source, summary, severity, timestamp).\n\n"
        "Extract and output ONLY the following, as JSON:\n"
        '  {"service_name": ..., "severity": ..., "window_minutes": ..., '
        '"alert_summary": ...}\n\n'
        "Infer service_name from the alert summary (e.g. a summary "
        "mentioning 'checkout-service' means service_name is "
        "'checkout-service'). Default window_minutes to 15 if the alert "
        "doesn't specify a timeframe.\n\n"
        "Do NOT diagnose a root cause. Do NOT call any tools. Your only job "
        "is structured extraction."
    ),
    output_key="triage_result",
)
