"""Robust JSON extraction from LLM text output.

Agents that combine tool-calling with structured output can't fully
guarantee clean JSON -- ADK's own docs note the schema constraint becomes
"best-effort" when tools and output_schema are both set. Parsing
defensively here means we don't depend on that guarantee holding.
"""

import json
import re


def parse_agent_json(text) -> dict:
    """Extract a JSON object from LLM output that may have stray text
    around it (a bare 'json' word, a markdown fence, or both). If the
    input is already a dict (e.g. from an output_schema-enforced agent),
    return it unchanged.
    """
    if isinstance(text, dict):
        return text

    stripped = text.strip()

    fence_match = re.fullmatch(r"```\w*\s*(.*?)\s*```", stripped, re.DOTALL)
    if fence_match:
        stripped = fence_match.group(1).strip()

    stripped = re.sub(r"^_?json\s*\n", "", stripped, flags=re.IGNORECASE)

    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        start, end = stripped.find("{"), stripped.rfind("}")
        if start != -1 and end != -1:
            return json.loads(stripped[start : end + 1])
        raise
