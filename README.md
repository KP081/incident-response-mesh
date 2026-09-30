# Incident Response Mesh

![Tests](https://github.com/KP081/incident-response-mesh/actions/workflows/tests.yml/badge.svg)

A 4-agent incident-response system built on Google ADK (Gemini) that triages
a raw alert, investigates logs/metrics, verifies its own diagnosis before
acting, and drafts a human-gated remediation plan with a full postmortem.

**Live demo:** https://incident-response-mesh-hdh5swb7jvgnefsgxy25eh.streamlit.app/
_(free tier -- sleeps after 12h idle, first load may take a few seconds to wake)_

## Architecture

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
              │ FixAdvisorAgent │  drafts remediation + postmortem + PR
              └────────┬────────┘
                       │
                       ▼
          [ HITL gate on high-risk actions ]

- **TriageAgent** -- pure extraction, no diagnosis, no tools.
- **LogParserAgent** -- queries real Postgres-backed logs/metrics tables (seeded fresh per run, see [Telemetry](#telemetry--git-data) below), proposes a hypothesis with verbatim log-line citations.
- **CriticAgent** -- independently re-fetches the same raw logs and rejects any hypothesis whose citation isn't verbatim, that cites a `WARNING` while an unaddressed `FATAL`/`ERROR` exists, or that cites only a downstream symptom while an earlier line names the actual root-cause defect.
- **FixAdvisorAgent** -- fetches the real git diff for the affected service, drafts a remediation action, and opens a real PR on a sandbox repo once approved. High-risk actions (`rollback_deployment`, `apply_hotfix`, `restart_database`, opening the PR itself) are gated by a human-in-the-loop callback -- enforced twice: once on the drafted action, once again on the PR tool call itself, so a model that ignores its own "don't proceed" instruction still can't open a real PR.

Every agent turn and tool call is logged as a structured JSON line (`core/observability.py`) -- agent name, duration, tool args (secrets redacted), and success/failure.

## Tech stack

- Google ADK 2.9.1 (`LlmAgent`, `SequentialAgent`, `LoopAgent`, `DatabaseSessionService`, agent/tool callbacks)
- Gemini 3.5 Flash-Lite
- Postgres (Neon, via `DatabaseSessionService` + SQLAlchemy async core) for session/audit persistence _and_ for real telemetry (logs/metrics), swappable to local SQLite in dev via one env var
- Git integration -- PyGithub, real commits/diffs/PRs on a sandbox repo
- Structured JSON logging per agent/tool step
- Streamlit for the UI
- Docker for containerization
- GitHub Actions CI running the test suite on every push
- `tenacity` for retry/backoff on transient API errors and malformed-output retries

## Telemetry & git data

Logs and metrics are **not** read from static JSON fixtures at query time.
`seed_telemetry()` ingests each scenario's data into real Postgres tables
(`service_logs`, `service_metrics`) with timestamps re-anchored to "now"
right before a run, and `LogParserAgent`'s tools run real SQL queries
against them -- same code path locally (SQLite) and in production (Neon).

Git diffs are real too: `scripts/seed_git_history.py` seeds two commits
per service (before/after) on a sandbox GitHub repo, and `fetch_git_diff()`
fetches the actual latest commit diff via the GitHub API.

What's still synthetic: the underlying incident data itself (no real
service is actually failing) -- this is a scenario-driven demo, not a
live production integration.

## Setup

```bash
git clone https://github.com/KP081/incident-response-mesh.git
cd incident-response-mesh
uv sync
cp .env.example .env   # fill in GOOGLE_API_KEY, DATABASE_URL, GITHUB_PAT, GITHUB_SANDBOX_REPO
uv run python scripts/seed_git_history.py   # one-time: seeds the sandbox repo's commit history
```

See the comments in `.env.example` for exactly how to get each value
(Neon connection string format, GitHub fine-grained PAT scopes, etc).

## Usage

```bash
# Single scenario via CLI
uv run python app.py scenario_01_oom

# Full domain eval across all scenarios (paired first-pass vs final scoring)
# Use an isolated DB so eval runs never touch live demo data, and
# EVAL_DRY_RUN so it never opens real PRs on the sandbox repo
DATABASE_URL="sqlite+aiosqlite:///eval.db" HITL_AUTO_APPROVE=true \
    uv run python evals/run_business_metrics.py --trials 3 --difficulty all

# Print the full diagnosis-loop transcript for one scenario
DATABASE_URL="sqlite+aiosqlite:///eval.db" HITL_AUTO_APPROVE=true \
    uv run python evals/explain_run.py scenario_16_stale_cache

# Ablation: same eval, CriticAgent removed entirely
DATABASE_URL="sqlite+aiosqlite:///eval.db" HITL_AUTO_APPROVE=true \
    uv run python evals/ablation_no_critic.py

# Streamlit UI
HITL_CAPTURE_ONLY=true uv run streamlit run streamlit_app.py

# Tests -- tool/telemetry tests run against an isolated local SQLite DB
# (see tests/conftest.py); GitHub integration tests hit the real API and
# auto-skip if GITHUB_PAT isn't set
uv run pytest tests/ -v
```

## Docker

```bash
docker build -t incident-mesh .
docker run -p 8080:8080 \
    -e GOOGLE_API_KEY=your_key \
    -e DATABASE_URL=your_postgres_url \
    -e GITHUB_PAT=your_pat \
    -e GITHUB_SANDBOX_REPO=your-username/repo \
    incident-mesh
```

## Project structure

incident-response-mesh/
├── .github/workflows/ # CI: runs the test suite on every push
├── agents/ # TriageAgent, LogParserAgent, CriticAgent, FixAdvisorAgent
├── core/ # agent composition, HITL callback, DB engine, observability, config
├── tools/ # real Postgres-backed telemetry, real GitHub diff/PR tools, postmortem generation
├── scripts/ # one-time setup (seeds the sandbox repo's commit history)
├── data/scenarios/ # 18 synthetic incident fixtures (15 original + 3 designed to stress the Critic)
├── evals/ # business-metric harness, Critic ablation, transcript viewer
├── tests/ # tool tests (isolated DB) + real-GitHub integration tests + manual Critic check
├── app.py # CLI entrypoint
└── streamlit_app.py # web UI

## Critic Loop in Action

The eval harness (`evals/run_business_metrics.py`) scores every run twice:
on LogParserAgent's _first_ hypothesis (before the Critic sees it) and on
the _final_ one, so the Critic's actual contribution is measured inside
each run rather than assumed.

**Original 15 scenarios:** first-pass accuracy was already 15/15 -- the
Critic never had a real error to catch here. 3 harder scenarios were then
added specifically to stress the "cite the highest-severity log line"
heuristic (e.g. a WARNING is the true root cause, a later FATAL is just
its downstream symptom):

|                                  | first pass | after Critic loop |
| -------------------------------- | ---------- | ----------------- |
| Original 15 scenarios            | 15/15      | 15/15             |
| 3 hard scenarios (3 trials each) | 6/9        | **9/9**           |

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
<scenario_id>` show the full transcript for any run. The Critic's
rejection logic is also verified in isolation by
`tests/manual_critic_check.py`.

## Known limitations

- The eval harness scores citation correctness and safety adherence; it
  does not score exact remediation-action-label match, since
  "apply_hotfix" vs. "rollback_deployment" is a choice the model can
  reasonably make either way.
- FixAdvisorAgent's final JSON output occasionally comes back truncated/
  malformed (intermittent, not yet root-caused) after otherwise-successful
  tool calls; `app.py` retries the whole run when this happens.
  `open_remediation_pr()` is idempotent against this (skips instead of
  duplicating a PR if one was already opened for the same service in the
  last 10 minutes), so the retry is safe, just not fully explained yet.
  `core/observability.py` now logs each agent's raw final output, so the
  next occurrence will have a full transcript instead of a fragment.
- Session/telemetry data lives in a single shared Postgres instance with
  no per-user isolation -- fine for a single-operator demo, not for a
  real multi-tenant deployment.

---

See [`docs/INTERVIEW_NOTES.md`](docs/INTERVIEW_NOTES.md) for a detailed
write-up of the engineering issues hit during development.
