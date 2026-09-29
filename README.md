# Incident Response Mesh

A 4-agent incident-response system built on Google ADK (Gemini) that triages
a raw alert, investigates logs/metrics, verifies its own diagnosis before
acting, and drafts a human-gated remediation plan with a full postmortem.

**Live demo:** https://incident-response-mesh-hdh5swb7jvgnefsgxy25eh.streamlit.app/
_(free tier -- sleeps after 12h idle, first load may take a few seconds to wake)_

## Architecture

```
                 [ Alert (PagerDuty-style JSON) ]
                              │
                              ▼
                     ┌─────────────────┐
                     │   TriageAgent   │  extracts service/severity/window
                     └────────┬────────┘
                              │
                              ▼
                  ┌─────────────────────┐
                  │   DiagnosisLoop     │  (LoopAgent, max 3 iterations)
                  │  ┌───────────────┐  │
                  │  │LogParserAgent │  │  proposes root cause + citations
                  │  └──────┬────────┘  │
                  │         ▼           │
                  │  ┌───────────────┐  │
                  │  │  CriticAgent  │──┼──► reject: loop retries with feedback
                  │  └──────┬────────┘  │
                  └─────────┼───────────┘
                            │ approve (exit_loop)
                            ▼
                  ┌─────────────────┐
                  │ FixAdvisorAgent │  drafts remediation + postmortem
                  └────────┬────────┘
                           │
                           ▼
              [ HITL gate on high-risk actions ]
```

- **TriageAgent** -- pure extraction, no diagnosis, no tools.
- **LogParserAgent** -- calls mock telemetry tools, proposes a hypothesis with verbatim log-line citations.
- **CriticAgent** -- independently re-fetches raw logs and rejects any hypothesis whose citation isn't verbatim, or that cites a `WARNING` while an unaddressed `FATAL`/`ERROR` exists.
- **FixAdvisorAgent** -- drafts a remediation action; high-risk actions (`rollback_deployment`, `apply_hotfix`, `restart_database`) are gated by a human-in-the-loop callback before they can "execute."

## Tech stack

- Google ADK 2.9.1 (`LlmAgent`, `SequentialAgent`, `LoopAgent`, `DatabaseSessionService`, `before_tool_callback`)
- Gemini 3.5 Flash-Lite
- Postgres (Neon, via `DatabaseSessionService` + `asyncpg`) for session/audit persistence
- Git integration — PyGithub, real commits/diffs/PRs on a sandbox repo.
- Streamlit for the UI
- Docker for containerization
- `tenacity` for retry/backoff on transient API errors and malformed-output retries

## Setup

```bash
git clone https://github.com/YOUR_USERNAME/incident-response-mesh.git
cd incident-response-mesh
uv sync
cp .env.example .env   # fill in GOOGLE_API_KEY
```

## Usage

```bash
# Single scenario via CLI
uv run app.py scenario_01_oom

# Isolated test of the Critic's rejection logic
uv run tests/manual_critic_check.py

# Full domain eval across all scenarios (auto-approves HITL so it doesn't hang)
HITL_AUTO_APPROVE=true uv run python3 evals/run_business_metrics.py

# Ablation: same eval, CriticAgent removed entirely
HITL_AUTO_APPROVE=true uv run python3 evals/ablation_no_critic.py

# Streamlit UI
HITL_CAPTURE_ONLY=true uv run streamlit run streamlit_app.py

# Tests (pure-function tools + agent-mesh construction, no API calls)
uv run pytest -v
```

## Docker

```bash
docker build -t incident-mesh .
docker run -p 8080:8080 -e GOOGLE_API_KEY=your_key incident-mesh
```

## Project structure

```
incident-response-mesh/
├── agents/           # TriageAgent, LogParserAgent, CriticAgent, FixAdvisorAgent
├── core/             # agent composition, HITL callback, config, JSON parsing
├── tools/            # mock telemetry, git, and postmortem-generation tools
├── data/scenarios/   # 15 synthetic incident fixtures
├── evals/            # business-metric harness + Critic ablation study
├── tests/            # pure-function tests + isolated Critic test
├── app.py            # CLI entrypoint
└── streamlit_app.py  # web UI
```

## Eval results

15 synthetic incident scenarios spanning OOM, DB deadlocks, auth
regressions, network timeouts, bad deploys, disk-full, and rate-limit
misconfigurations.

| Metric            | With Critic  | Without Critic (ablation) |
| ----------------- | ------------ | ------------------------- |
| Citation accuracy | 15/15 (100%) | 15/15 (100%)              |

The ablation shows no measurable lift on this benchmark --
`LogParserAgent`'s own severity-prioritization instruction was sufficient
for these 15 cases. The Critic's rejection logic is separately verified in
isolation by `tests/manual_critic_check.py`, which feeds it a hypothesis
that cites a `WARNING` over an unaddressed `FATAL` and confirms it rejects.

## Critic Loop in Action

The eval harness (`evals/run_business_metrics.py`) scores every run twice:
on LogParserAgent's *first* hypothesis (before the Critic sees it) and on
the *final* one, so the Critic's actual contribution is measured inside
each run rather than assumed.

**Original 15 scenarios** ("easy"): first-pass accuracy was already 15/15.
The Critic never had a real error to catch here -- correctly diagnosing
this, 3 harder scenarios were added specifically to stress it.

**3 "hard" scenarios**, designed to break the "cite the highest-severity
log line" heuristic (e.g. a WARNING is the true root cause, a later FATAL
is just its downstream symptom):

| | first pass | after Critic loop |
|---|---|---|
| Correct root cause | 6/9 (3 trials × 3 scenarios) | **9/9** |

Example (`scenario_16_stale_cache`, a real run):

> **Attempt 1** -- cites only `assertion failed: price mismatch...` (the
> FATAL symptom). **Critic: rejected** -- "cites only a downstream/symptom
> line while an earlier line names a specific configuration defect
> (`cache TTL misconfigured: ttl_seconds=0`) that the hypothesis never
> cites."
>
> **Attempt 2** -- cites the TTL misconfiguration line and traces it
> through to the price-mismatch failure. **Critic: approved.**

Getting here took two iterations on the Critic's own rules: an initial
version over-corrected and started rejecting valid diagnoses on the
original 15 (rejections went 1 -> 7, with malformed-output crashes on
2 scenarios). The fix was narrowing the rule to specific configuration
defects ("misconfigured", "expired", "rotated", ...) rather than any
earlier log line, and making FixAdvisorAgent always emit valid JSON
(`action: "escalate_to_human"`) when the Critic can't confirm a
hypothesis, instead of replying in free text.

Run it yourself: `evals/results.json` and `evals/explain_run.py
<scenario_id>` show the full transcript for any run.

## Known limitations

- The eval harness scores citation correctness and safety adherence; it
  does not score exact remediation-action-label match, since
  "apply_hotfix" vs. "rollback_deployment" is left as a choice the model
  can reasonably make either way.

---

See [`docs/INTERVIEW_NOTES.md`](docs/INTERVIEW_NOTES.md) for a detailed
write-up of the engineering issues hit during development and the ablation
study's findings.
