---
slug: grok-native-harness
bet: ./bet.md
status: shaping
---

# Shape: Grok as a governed Omnigent harness (via ACP)

Work repo: `/Users/trent/Documents/40hero-os-github/omnigent` (fork; remotes origin=40Hero, upstream=omnigent-ai). Shape docs live here in ai-ws; the build branches + runs in the fork.

## Problem (recap)

Grok Build is installed and authed but can only be run by hand, ungoverned, outside Omnigent. Recon proved `grok agent stdio` speaks ACP protocolVersion 1 and Omnigent's existing `AcpExecutor` already routes ACP `session/request_permission` through the CEL policy engine. So a governed grok is reachable as an `acp:grok` config agent on the generic `acp` harness, plus whatever thin glue grok's ACP dialect needs. The full native-TUI tile is a deferred ~15-file follow-on bet, not this work.

## Layers in play

- **Config layer** — the `acp:grok` agent entry in Omnigent's global `acp:` config block (`{"acp":{"agents":[...]}}`).
- **Harness layer** — the generic `acp` harness (`omnigent/inner/acp_harness.py`) resolving `acp:grok` -> `HARNESS_ACP_COMMAND="grok agent stdio"` via `_build_acp_spawn_env` (`omnigent/runtime/workflow.py:1460`).
- **Executor layer** — `AcpExecutor` (`omnigent/inner/acp_executor.py`): ACP JSON-RPC client (initialize / session/new / session/prompt / session/update / session/request_permission) mapping to Omnigent `ExecutorEvent`s.
- **Policy layer** — the CEL engine at `POST /v1/sessions/{id}/policies/evaluate`, reached from `AcpExecutor`'s `session/request_permission` handler (TOOL_CALL policy + elicitation).
- **Agent process** — `grok agent stdio` (external, xAI).

## Feedback-loop readiness

| Layer | Test command | Type/lint | Smoke / run path |
|-------|-------------|-----------|------------------|
| ACP handshake | `echo '{...initialize...}' \| grok agent stdio` (verified green this session) | n/a | live stdio |
| Harness / executor | `MISSING — slice 01 establishes` the exact governed-run command (`omni run --harness acp:grok` vs session API) | `ruff` / repo typecheck | `omni run --harness acp:grok` |
| Bench matrix | `python -m tests.harness_bench --harness acp --live` (acp config pointed at grok) | n/a | conformance probes |
| Policy gate | exercised via a session CEL policy in slice 02 (no standalone unit) | n/a | live governed turn |

## Decision table

| # | Question | Recommended | If instead... | Resolved |
|---|----------|-------------|---------------|----------|
| 1 | How is `acp:grok` registered? | Add via the existing Omnigent ACP-agent config path (`omnigent` CLI / `acp_agents_settings`) writing `{slug:"grok", name:"Grok Build", command:"grok agent stdio"}` to the global `acp:` block. Zero repo change if the path exists. | Hand-editing config risks a malformed `acp:` block; the catalog code already guards against that but the CLI path is the blessed seam. | pending |
| 2 | Which permission mode does grok run under so tools route through Omnigent (not grok's own prompt)? | `default` (grok emits `session/request_permission` -> Omnigent's TOOL_CALL policy decides). NOT `--yolo`/bypassPermissions. | `--yolo` self-approves inside grok and Omnigent never sees the tool to gate it — breaks the governance premise. | pending |
| 3 | If grok's ACP dialect diverges from `AcpExecutor` (permission-request shape, session/prompt fields, model in session/new)? | Write minimal glue in `acp_executor.py` guarded to grok (or the `acp:` config knobs: `send_model`, `session_id_mode`); do NOT fork a grok-specific executor. | A forked executor re-opens the subsystem-scale build the ACP path exists to avoid. | pending |
| 4 | How is the formal bench run against grok when `acp` is a single generic profile? | Point the `acp:` config at grok as the sole/selected agent, run `--harness acp --live`, record the matrix as the cross-check. Primary gates stay the live `omni run` done-tests (unambiguous). | Treating the bench as the sole gate risks blocking on per-slug-profile plumbing the bench may not have. | pending |
| 5 | Fallback if ACP `session/request_permission` does NOT gate (grok self-executes tools)? | Fall back to grok's native `x.ai/hooks` blocking `pre_tool_use` (advertised in initialize `_meta`) as an HTTP hook to the CEL `/policies/evaluate` endpoint — reusing `native_policy_hook.py`. | No gate at all = ungovernable = kill. This fallback is the kill-trigger's escape hatch. | pending |
| 6 | Monitoring slice (receipts + sweep + canary)? | No. Ships nothing long-running — a local dev harness, not a service. | Adds a monitoring subsystem to a laptop harness that has no cron/uptime surface. | pending |

## Autonomy envelope

### Decision rules
- If `acp:grok` config can be written via the CLI path, use it; if that path is missing, write the global config JSON directly (idempotent, single agent entry), never hand-merge.
- If a governed turn completes but grok's `session/request_permission` shape differs from `AcpExecutor`'s expectation, add the smallest grok-guarded adapter in `acp_executor.py`; do NOT restructure the executor.
- If grok never emits `session/request_permission` for a tool (self-executes), STOP the ALLOW-path assumption and switch to the Decision-5 fallback (native `x.ai/hooks`), recording the pivot in DECISIONS-NEEDED.md.
- Model default = grok-4.5. Do not tune model selection beyond proving override works.
- Any change that would touch the native-tile subsystem files (`grok_native*.py`, launch wirings, capability/native_agents entries) is OUT — that is the follow-on bet.
- **This build session runs inside the live Omnigent instance.** Validate every done-test against an ISOLATED server — the harness-bench full-server transport (`spawn_omnigent_server` on a free port, runs the freshly-edited repo code) or a separate dev `omni` server — NEVER by restarting the live host. The live host keeps old code loaded and untouched; new `acp_executor.py` glue is exercised only in the ephemeral server. The `acp:grok` config write is an additive shallow-merge to `~/.omnigent/config.yaml` (one agent entry) and is safe against the running instance.

### Decide-alone vs queue
- **Build decides alone:** the `acp:grok` config contents, grok-dialect glue in `acp_executor.py`, test wiring, the exact governed-run command — all validated against an isolated server.
- **Queue to `DECISIONS-NEEDED.md` and work around:** whether to add a Grok model family / catalog label polish; whether to record the bench matrix as a committed fixture; the Decision-5 fallback pivot (queue it, keep building other slices).
- **Hard stop (never proceed):** restarting/booting-out the Omnigent server or host (kills this build's own runner mid-run), external mutations (pushing the fork, opening a PR upstream), destructive ops, real scope change (building any native-tile file).

### Evidence contract
- Slice 01: transcript/stdout of a real grok reply through `acp:grok` + a policy-engine log line showing the ALLOW evaluation fired; the exact run command recorded.
- Slice 02: transcript showing a grok shell-tool attempt BLOCKED under a DENY policy (no execution), plus the ALLOW and ASK observations.
- Slice 03: model-override before/after responding model, an interrupted turn stopping, a usage/cost surface, and the `acp` bench matrix output.

## Model plan

| # | Slice | Implementer | Reviewer | Notes |
|---|-------|-------------|----------|-------|
| 01 | acp:grok governed turn (skeleton) | default | frontier | ACP dialect integration seam — reviewer checks the mapping is real, not stubbed. |
| 02 | CEL deny gate (governance) | default | frontier | external:y security path — the value proof; reviewer is adversarial about bypass. |
| 03 | override + interrupt + cost + bench | default | default | mechanical thickening over the proven seam. |

Final whole-branch review: most capable available tier. Because `external: y` and the whole point is a governed egress boundary, escalate to `/spine:review-deep` (cross-vendor lanes as finders) on the whole diff; feed findings to one fix subagent.

## Risk flags

```yaml
auth: n
multi_tenant: n
durable: n
external: y
ui: n
high_stakes_ui: n
```

- **external: y** — drives the `grok` CLI to xAI and gates a coding agent's tool egress; the gate correctness is the bet.

## Blast radius

- **Environments touched:** local only.
- **In-scope paths:** Omnigent global `acp:` config (user config, not repo); `omnigent/inner/acp_executor.py` and/or `omnigent/inner/acp_harness.py` (grok-dialect glue only, if needed); test files under `tests/` for the new done-tests.
- **Out-of-scope paths (must NOT change):** any `omnigent/*grok_native*.py`, `omnigent/codex_native*`, `omnigent/claude_native*`, the launch wirings (`cli.py`, `resume_dispatch.py`, `chat.py`), `harness_plugins.py` capability/native_agents entries, `web/` frontend. All native-tile subsystem = follow-on bet.
- **External services touched:** xAI (via `grok agent stdio`), on Trent's grok.com subscription.
- **Destructive operations allowed:** none.
- **Data migrations:** no.
- **Live-instance safety:** the build runs inside the live Omnigent. It must NOT restart the server/host. Tests run against an isolated ephemeral server (own free port); the `acp:grok` config write is an additive shallow-merge; code edits do not affect the already-loaded live process.

## Slice index

| # | Slice | Type | Crosses | Depends on | Done-test (one line) |
|---|-------|------|---------|-----------|----------------------|
| 01 | acp:grok governed turn | skeleton | config -> harness -> executor -> policy(ALLOW) -> grok | none | A real grok reply comes back through `acp:grok` and a tool call is seen + allowed by the CEL policy path. |
| 02 | CEL deny gate | thickening | policy -> executor -> grok | 01 | Under a DENY policy, grok's shell-tool attempt is blocked before execution; ALLOW proceeds; ASK raises an elicitation. |
| 03 | override + interrupt + cost + bench | thickening | config -> executor -> grok; bench | 01 | Model override changes the responder, interrupt stops a running turn, usage surfaces, and the `acp` bench matrix is recorded against grok. |

## Approval

Approved when: decision table resolved, contracts frozen, every slice has an end-to-end done-test, autonomy envelope + model plan + risk flags + blast radius complete. On go, the unattended build runs all slices, queues non-blocking decisions to `DECISIONS-NEEDED.md`, and ends with the evidence-contract report.

**Approval:** pending
