"""Composes the incident-response agent mesh.

Topology:
    TriageAgent -> DiagnosisLoop[LogParserAgent, CriticAgent] -> FixAdvisorAgent
"""

from google.adk.agents import SequentialAgent, LoopAgent

from agents.triage_agent import triage_agent
from agents.log_parser_agent import log_parser_agent
from agents.critic_agent import critic_agent
from agents.fix_advisor_agent import fix_advisor_agent

MAX_DIAGNOSIS_ITERATIONS = 3

diagnosis_loop = LoopAgent(
    name="DiagnosisLoop",
    sub_agents=[log_parser_agent, critic_agent],
    max_iterations=MAX_DIAGNOSIS_ITERATIONS,
)

root_agent = SequentialAgent(
    name="IncidentResponseMesh",
    sub_agents=[triage_agent, diagnosis_loop, fix_advisor_agent],
)
