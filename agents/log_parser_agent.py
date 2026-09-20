"""LogParserAgent: queries metrics/logs and proposes a root-cause hypothesis.

Every claim it makes must be traceable to a verbatim log line -- that's what
lets CriticAgent mechanically check the hypothesis instead of just
re-reading it and trusting it.
"""

from google.adk.agents import LlmAgent

from tools.telemetry_tools import fetch_logs, query_metrics

from core.config import MODEL_NAME


def build_log_parser_agent() -> LlmAgent:
    return LlmAgent(
        name="LogParserAgent",
        model=MODEL_NAME,
        instruction=(
            "You are a log analysis agent investigating an incident.\n\n"
            "Triage result (JSON): {triage_result}\n\n"
            "If this is a retry after a rejected hypothesis, the previous "
            "verdict is here: {critic_verdict?}\n\n"
            "Use the query_metrics and fetch_logs tools to gather evidence for "
            "the service named in triage_result. Then output a hypothesis as "
            "JSON:\n"
            '  {"root_cause": ..., "cited_log_lines": [...], "confidence": 0.0-1.0}\n\n'
            "Rules:\n"
            "- Every string in cited_log_lines MUST be copied verbatim from a "
            "fetch_logs result -- do not paraphrase or invent a log line.\n"
            "- Prefer the highest-severity unaddressed log line (FATAL over "
            "ERROR over WARNING) as your primary citation. Do not build a "
            "hypothesis around a WARNING if an unexplained FATAL exists in the "
            "same window.\n"
            "- If a previous verdict rejected your hypothesis, address its "
            "stated reason directly rather than repeating the same claim."
        ),
        tools=[query_metrics, fetch_logs],
        output_key="hypothesis",
    )


log_parser_agent = build_log_parser_agent()
