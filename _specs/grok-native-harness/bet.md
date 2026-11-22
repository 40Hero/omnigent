# Bet: grok-native-harness

- **Home:** hero/projects/omnigent-grok-native
- **Work repo:** /Users/trent/Documents/40hero-os-github/omnigent (fork of omnigent-ai/omnigent; remotes origin=40Hero, upstream=omnigent-ai)
- **Status:** SHIPPED AT BOUNDARY (slice 01 only). Slice 01 = grok usable in Omnigent via `acp:grok`, UNGOVERNED. Governance premise falsified at build (grok auto-executes tools over ACP, never emits `session/request_permission`); circuit breaker fired -> reshaped to a new bet `grok-acp-gate`. See DECISIONS-NEEDED.md.
- **Created:** 2026-07-14 · **Closed:** 2026-07-14

## Grill

### Answered
- **Q:** What's the fastest interface to drive Grok non-interactively? -> **A:** Not ACP (absent in installed 0.2.101). Headless `-p --output-format streaming-json` emits clean JSONL (`thought`/`text`/`end`, `end.usage` carries token counts). Same non-ACP headless+hooks shape codex-native already uses.
- **Q:** Can Omnigent's CEL policy actually gate a Grok tool call (the whole value question)? -> **A:** Yes. Grok's hook contract mirrors Claude Code: `PreToolUse` returns `{"decision":"deny","reason":...}`; `type:"http"` hooks POST the event envelope to a URL. That is exactly claude-native's gate mechanism.
- **Q:** Is auth a blocker? -> **A:** No. `grok 0.2.101` is installed and logged in via grok.com subscription (model grok-4.5), not the metered xAI API. Omnigent stores no credential (like goose/qwen).
- **Q:** What does "done" mean, measurably? -> **A:** grok-native passes the harness test bench (`tests/harness_bench`) on the same probes claude-native/codex-native pass.
- **Q:** Native TUI tile parity, or governed-via-ACP first? -> **A (revised at shape time):** Governed via ACP first. Shape recon found the native-TUI tile is a ~15-file port of the codex-native subsystem (3-5 days), not a 1.5-day file fork. Grok speaks genuine ACP (`grok agent stdio`, protocolVersion 1, live-verified handshake) and Omnigent's `AcpExecutor` already gates ACP `session/request_permission` through the CEL engine. So govern grok via `acp:grok` now (~1 day); the tile is a deferred follow-on bet.
- **Q:** Does grok's ACP handshake actually work with Omnigent's client? -> **A:** Yes, verified live this session: `echo '{...initialize...}' | grok agent stdio` returns `protocolVersion:1`, `agentCapabilities.loadSession:true`, `session/request_permission` support, cached-token auth, and models grok-4.5 / grok-composer-2.5-fast.

### N/A
- Data / migration: none. The harness is a session bridge, no store, nothing irreversible.
- Multi-tenancy: single operator on Trent's laptop; no per-tenant isolation surface.
- After-ship maintenance: Trent owns it in his fork; standard.

### Proposed risk flags
auth: n | multi_tenant: n | durable: n | external: y | ui: n | high_stakes_ui: n
- **external: y** — the harness drives the `grok` CLI, which calls xAI, and the entire point is a coding agent that can take tool actions; egress must be CEL-gated.
- **ui: n** — the ACP path builds NO new UI; grok's turns render through Omnigent's existing chat + tool-card surface (the generic `acp` harness path). The native-TUI tile (ui: y) is the deferred follow-on bet.

## Problem + the win

Omnigent can govern Claude Code and Codex as first-class harnesses (Omnigent CEL policy gates on every tool call), but Grok Build — xAI's terminal coding agent, already installed and authed on this machine — can only be run by hand, ungoverned, outside Omnigent. Recon this session proved the governance seam live: `grok agent stdio` handshakes ACP `protocolVersion 1` and its initialize response advertises `x.ai/hooks: {blockingEvents:["pre_tool_use"], decisions:["deny"]}` plus `session/request_permission`. Omnigent already ships `AcpExecutor`, which routes ACP `session/request_permission` through the CEL policy engine + human-consent elicitation. So a GOVERNED grok is reachable as mostly configuration — an `acp:grok` agent driven by the existing generic `acp` harness — not a new subsystem. It unlocks Grok as a cross-vendor review lane and a cheap parallel-subagent build harness inside the same policy envelope as the other two. (The full native-TUI tile, a ~15-file port of the codex-native stack, is a separate deferred bet.)

**Win:** When this ships, Grok runs as a governed harness inside Omnigent: a live turn completes end to end through `acp:grok` (initialize -> session/new -> session/prompt -> response streamed as Omnigent events) AND a CEL policy DENY provably blocks a grok tool call before it executes, both verified by the slice done-tests, with the generic `acp` bench profile run against grok recording the probe matrix.

## Budget

- **Calendar:** 1 day (ACP path: config + live verification + any grok-dialect glue in AcpExecutor).
- **Hours (Trent):** ~1-2h alignment — watch one live governed turn + one live deny-gate proof, sign off. (guess)
- **$LLM:** $20 cap on build inference. (guess — grok turns themselves ride the grok.com sub, so this is the Omnigent-side build agent, not grok usage.)

## In

- An `acp:grok` agent in the Omnigent global `acp:` config block (slug `grok`, command `grok agent stdio`, name, protocol knobs), added via the existing `omnigent` ACP-agent config path.
- Drive grok through the existing generic `acp` harness + `AcpExecutor` (reused unchanged where possible); write only the glue needed for grok's ACP dialect quirks (session/prompt shape, permission-request shape, model override via `session/new`).
- Live governance proof: a session CEL policy DENY intercepts grok's `session/request_permission` and blocks the tool before execution; ALLOW proceeds; ASK raises an elicitation card.
- Model override (grok-4.5 <-> grok-composer-2.5-fast), interrupt (session/cancel), and cost/usage surfacing verified live.
- Record the `acp` bench profile matrix run against grok as the formal cross-check.

## Out

- **The full native-TUI tile** — the ~15-file codex-native-style subsystem (`grok_native.py` + `_state`/`_bridge`/`_forwarder`/`_app_server`/`_hook` + inner executor/harness + 4 launch wirings + capability/native_agents entries) that renders grok's own fullscreen Plan-Mode TUI in a pane. DEFERRED to a separate follow-on bet, framed only after the ACP path proves grok-in-Omnigent earns its keep.
- **Upstreaming to omnigent-ai** — keep it in the 40Hero fork; a PR to upstream is a separate decision after it works.
- **The review-lane / build-harness wiring itself** — routing grok into a cross-vendor review or assigning it build slices is downstream *use* of the harness, not this build.
- **Model tuning** — grok-4.5 vs grok-composer selection/optimization beyond proving override works.
- **Cross-session memory / plan-mode / subagent-specific features.**

## Kill trigger + response

- **Trigger:** grok's ACP dialect diverges enough from `AcpExecutor`'s expectations that a governed turn can't complete without material new code (turning "config + glue" into a real build), OR the CEL gate can't actually block a grok tool call in practice (grok self-executes without emitting `session/request_permission`, or the deny is ignored).
- **Response:** internal replan — if the divergence is real code, re-scope to a thin grok-specific ACP executor as its own bet; if the gate fails at the ACP layer, fall back to grok's native `x.ai/hooks` blocking `pre_tool_use` (an HTTP PreToolUse hook to the CEL engine) as the gate. If neither governs, kill: an ungovernable harness is a demo toy, explicitly out of value scope.
