---
slug: grok-acp-gate
bet: ./bet.md
status: shaping
---

# Shape: dynamic CEL gate for grok tool calls (over ACP)

Work repo: `/Users/trent/Documents/40hero-os-github/omnigent` (fork). Parent bet `grok-native-harness` shipped slice 01 (grok runs ungoverned via `acp:grok`). This bet adds the gate.

## Problem (recap)

Grok runs in Omnigent via `acp:grok` but auto-executes tools over `grok agent stdio` and never emits `session/request_permission`, so Omnigent's CEL policy is never consulted (proven live: policy consulted 0 times, tool ran). This bet makes grok's tool calls dynamically gatable by the same CEL engine that governs claude-native/codex-native. The core unknown: grok's `initialize` advertises `_meta.x.ai/hooks: {blockingEvents:["pre_tool_use"], decisions:["deny"]}` — does grok actually route a blocking `pre_tool_use` to an ACP client that advertises the matching capability? Slice 01 is the spike that decides it.

## Layers in play

- **ACP client layer** — `omnigent/inner/acp_executor.py` (`AcpExecutor`): the `initialize` handshake (advertise `x.ai/hooks`), the inbound-request loop (handle grok's `pre_tool_use` request), capability-gated so only x.ai/hooks-advertising agents get the new path.
- **Policy layer** — the in-process `_policy_evaluator` (e2e tests) and, in production, `POST /v1/sessions/{id}/policies/evaluate`. The existing `_decide_permission` path already maps ALLOW/DENY/ASK; slice 01 feeds grok's request into it.
- **Agent process** — `grok agent stdio` (external, xAI).

## Feedback-loop readiness

| Layer | Test command | Type/lint | Smoke / run path |
|-------|-------------|-----------|------------------|
| ACP client / gate | `OMNIGENT_E2E_GROK=1 .venv/bin/python -m pytest tests/e2e/test_grok_acp_e2e.py -v` (parent's deny test is the target; currently xfail) | `ruff` / repo typecheck | real `grok agent stdio` |
| Unit (dialect) | `.venv/bin/python -m pytest tests/inner/test_acp_executor.py -v` | as above | fake-ACP-agent double |
| Spike (route confirm) | a raw-ACP diagnostic driving `grok agent stdio` (slice 01 Unit 0 authors it) | n/a | live stdio |

## Decision table

| # | Question | Recommended | If instead... | Resolved |
|---|----------|-------------|---------------|----------|
| 1 | Which gate route? | **Route A first**: grok's `x.ai/hooks` over ACP — advertise the capability in `initialize`, handle grok's inbound `pre_tool_use` request, answer from the policy. Fits the in-process e2e evaluator cleanly. | Route B (command-hook -> HTTP `/policies/evaluate`) needs a live server + reuses `native_policy_hook.py`; heavier, and its e2e needs the full-server harness not the in-process evaluator. | pending |
| 2 | Where does route A live? | **Capability-gated glue in the generic `AcpExecutor`**: activate the `pre_tool_use` handler only when the agent's `initialize` result advertised `_meta.x.ai/hooks`. Gemini/goose (no x.ai/hooks) are unaffected; no new harness. | A dedicated `GrokAcpExecutor` subclass + harness registration drifts toward the ~15-file native footprint for no gain. | pending |
| 3 | If route A fails the spike (grok does NOT route pre_tool_use to the client)? | **Queue to DECISIONS-NEEDED, do NOT auto-build route B.** Route B changes the test harness (live HTTP policy) and the plumbing surface — a scope change. Surface it; let the owner decide route B vs kill. | Auto-building route B silently triples the bet and swaps its test model. | pending |
| 4 | ASK handling for grok? | Map policy ASK -> the existing human-consent elicitation path (as gemini/goose do), returning grok the deny/allow option accordingly. | Treating ASK as auto-deny loses the interactive-approval capability the gate should preserve. | pending |
| 5 | Record the `acp` bench matrix against grok? | Yes, as a cross-check in slice 02, non-blocking. | Skipping loses the formal conformance signal. | pending |
| 6 | Monitoring slice? | No — a client-side gate in a local dev harness, nothing long-running. | Monitoring subsystem on a laptop library change. | pending |

## Autonomy envelope

### Decision rules
- Spike route A first (Decision 1). Timebox the spike to ~half a day of build time.
- Route A lives as capability-gated glue in the generic `AcpExecutor`, activated only when the agent advertised `_meta.x.ai/hooks` at initialize (Decision 2) — never change behavior for agents that did not advertise it.
- If the spike shows grok DOES route `pre_tool_use` to the client: wire it into the existing `_decide_permission` (ALLOW/DENY/ASK) path and make the parent's `xfail` deny test PASS.
- If the spike shows grok does NOT route it (route A dead): STOP. Queue "route A failed, route B (command-hook) or kill?" to `DECISIONS-NEEDED.md` and do not build route B this run (Decision 3 — a scope change is a hard stop).
- Never restart the live Omnigent (:6767) — validate against the repo `.venv` / isolated grok subprocesses (this session runs inside Omnigent).
- Do not touch the native-tile subsystem files.

### Decide-alone vs queue
- **Build decides alone:** the capability-gated `AcpExecutor` glue, the spike diagnostic, wiring grok's request into `_decide_permission`, flipping the xfail test, all validated in isolation.
- **Queue to `DECISIONS-NEEDED.md` and work around:** route B (if route A fails); whether to commit a bench fixture; any grok ACP dialect quirk needing more than a localized adapter.
- **Hard stop (never proceed):** restarting the Omnigent server/host, external mutations (push/PR), destructive ops, building route B or a new harness (scope change).

### Evidence contract
- Slice 01: the spike diagnostic output (does grok route pre_tool_use? yes/no), and if yes, the parent deny test flipping xfail -> PASS (sentinel NOT created, policy consulted > 0).
- Slice 02: ALLOW-proceeds output, ASK-elicitation output, the parent deny test green, and the `acp` bench matrix.

## Model plan

| # | Slice | Implementer | Reviewer | Notes |
|---|-------|-------------|----------|-------|
| 01 | gate route spike + deny enforcement | frontier | frontier | protocol reverse-engineering + a security-critical gate; the hardest, least-specified slice. |
| 02 | allow + ask + regression + bench | default | frontier | mechanical once the route is proven; reviewer stays adversarial on the gate. |

Final whole-branch review: most capable available tier. `external: y` and the deliverable IS an egress gate, so escalate to `/spine:review-deep` (cross-vendor lanes) on the whole diff; one fix subagent applies findings.

## Risk flags

```yaml
auth: n
multi_tenant: n
durable: n
external: y
ui: n
high_stakes_ui: n
```

- **external: y** — the deliverable is the dynamic egress gate on grok's tool calls; a gate that fails open is worse than no gate.

## Blast radius

- **Environments touched:** local only.
- **In-scope paths:** `omnigent/inner/acp_executor.py` (capability-gated x.ai/hooks handling), `tests/e2e/test_grok_acp_e2e.py` (flip the xfail deny test, add allow/ask), possibly `tests/inner/test_acp_executor.py` (unit coverage for the new handler).
- **Out-of-scope paths (must NOT change):** all `*grok_native*` / `*codex_native*` / `*claude_native*` files, launch wirings, `harness_plugins.py` registration, `web/`. Behavior for non-x.ai/hooks ACP agents (gemini/goose/qwen) must NOT change.
- **External services touched:** xAI via `grok agent stdio` (grok.com sub).
- **Destructive operations allowed:** none.
- **Data migrations:** no.
- **Live-instance safety:** runs inside the live Omnigent; no server/host restart; isolated test subprocesses.

## Slice index

| # | Slice | Type | Crosses | Depends on | Done-test (one line) |
|---|-------|------|---------|-----------|----------------------|
| 01 | gate route spike + deny enforcement | skeleton | ACP client -> policy(DENY) -> grok | none | Driven by a client advertising x.ai/hooks, a CEL DENY blocks grok's shell tool (sentinel NOT created, policy consulted); the parent xfail deny test flips to PASS. |
| 02 | allow + ask + regression + bench | thickening | ACP client -> policy(ALLOW/ASK) -> grok | 01 | ALLOW lets a read tool run, ASK raises an elicitation, the deny regression stays green, and the `acp` bench matrix is recorded against grok. |

## Approval

Approved when: decision table resolved, contracts frozen, every slice has an end-to-end done-test, autonomy envelope + model plan + risk flags + blast radius complete. On go, the unattended build runs slice 01 (the spike) first; if route A is dead it STOPS and queues the route-B-or-kill decision rather than proceeding. Ends with the evidence-contract report.

**Approval:** pending
