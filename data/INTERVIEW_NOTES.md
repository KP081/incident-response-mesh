# Interview Notes -- Incident Response Mesh

Reference material for talking about this project in interviews. Not part
of the project's README -- this is personal prep material, not
documentation for someone trying to use the repo.

---

## Engineering challenges actually hit and fixed

Not a hypothetical list -- every one of these was a real failure
encountered while building this, in the order they happened.

**1. Model deprecation mid-build.**
`gemini-2.5-flash` returned a live `404` ("no longer available to new
users") partway through development. Fixed by switching to
`gemini-3.6-flash`, then switching again to `gemini-3.5-flash-lite` once
free-tier daily quota (20 req/day vs. 500 req/day) made the flagship model
impractical for iterative testing with a multi-agent pipeline that makes
8-10 calls per run.

**2. A "deprecated" framework class was still the correct choice.**
`LoopAgent`/`SequentialAgent` are deprecated in ADK in favor of a newer
graph-based `Workflow` class -- but that class's own deprecation notice
states it can't yet be used the way this project composes agents. Verified
directly against the installed package (`LlmAgent.model_fields`,
`inspect.getsource`) rather than trusting a stale tutorial or an LLM's
suggested migration code, which turned out to reference a module
(`google.adk.workflows.Step`/`LoopStep`) that doesn't exist in the
installed version at all.

**3. A framework internal silently dropped agent output on one code path.**
`exit_loop()` sets `skip_summarization=True` internally, which skips the
model's final text-generation turn -- so `output_key` alone lost the
Critic's verdict specifically on the _approval_ path (it worked fine on
rejection, which is what made the bug intermittent and confusing at first).
Fixed by writing the verdict directly via a dedicated tool
(`record_verdict`) that writes to session state, instead of relying on the
model's final text turn.

**4. A model that "denies" honestly in prose but not reliably in state.**
The HITL callback correctly blocked the real tool call on denial, but
`FixAdvisorAgent`'s own summary of what happened couldn't be trusted --
in one run it described a blocked `rollback_deployment` as completed.
Fixed by treating the callback's own `tool_context.state["hitl_approved"]`
write as ground truth in the application layer, and overriding the
displayed action/details whenever it disagreed with the model's narrative.

**5. A silent data-integrity bug from a fixture naming collision.**
Two scenario fixtures accidentally shared the same `service` name. The
mock telemetry tool's lookup returned the _first_ match every time, so one
scenario silently ran against another scenario's logs -- no error, just
wrong data. Caught by a test asserting each scenario's `ground_truth`
fault line appears in its own fetched logs, not by code review.

**6. An asyncio lifecycle bug that only appeared on the second run.**
`asyncio.run()` closes its event loop after each call -- correct for a
short-lived CLI script, wrong inside a long-lived Streamlit server process.
The underlying HTTP client's connection pool stayed bound to the first
(now-closed) loop, so the second button click crashed with `RuntimeError:
Event loop is closed`. Fixed by creating one event loop per Streamlit
session and reusing it via `loop.run_until_complete()` instead of
`asyncio.run()`.

**7. A CLI-style blocking HITL gate doesn't translate to a web request/response model.**
A server can't pause mid-request waiting for a button click across page
reloads the way a CLI's `input()` can block a terminal. Solved by
splitting HITL into two phases for the web UI: the agent _proposes_ an
action (captured into session state via the callback, never executed), and
a separate UI action _executes_ the plain tool function directly once a
human clicks Approve -- decision and execution are no longer coupled to a
single agent turn.

---

## Ablation study -- what it found and why that's still a good answer

Ran the same 15 scenarios with `CriticAgent` removed entirely
(`evals/ablation_no_critic.py`) and compared citation accuracy against the
full pipeline.

|                | Citation accuracy |
| -------------- | ----------------- |
| With Critic    | 15/15 (100%)      |
| Without Critic | 15/15 (100%)      |

**If asked "so the Critic doesn't do anything?":** No measurable lift on
_this_ benchmark -- `LogParserAgent`'s own severity-prioritization
instruction was strong enough for these 15 cases on its own. That's
separate from whether the Critic's rejection mechanism works, which is
proven independently by `tests/manual_critic_check.py`: fed a hypothesis
that cites a `WARNING` while an unaddressed `FATAL` exists, the Critic
rejects it with a specific, correct reason. The honest claim is: the
mechanism works, and this particular benchmark wasn't adversarial enough
to need it in practice. A harder or noisier benchmark would likely show a
real gap -- that's a natural next experiment, not a claim to fake now.
