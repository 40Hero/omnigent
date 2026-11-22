# Bet: grok-acp-gate

- **Home:** hero/projects/omnigent-grok-native
- **Work repo:** /Users/trent/Documents/40hero-os-github/omnigent (fork; branch `grok-acp-harness` already holds slice 01)
- **Status:** framed
- **Created:** 2026-07-14
- **Parent:** reshaped from `grok-native-harness` after its governance premise was falsified at build time.

## Grill

### Answered (from the grok-native-harness build, 2026-07-14)
- **Q:** Why doesn't the generic ACP path gate grok? -> **A:** Proven live — over `grok agent stdio` grok auto-executes tools and never emits `session/request_permission`; the `AcpExecutor` policy evaluator is consulted 0 times and the tool runs. A `~/.grok/hooks` deny hook did not block it either.
- **Q:** What's the most promising gate route? -> **A:** Grok's ACP `initialize` advertises `x.ai/hooks: {blockingEvents:["pre_tool_use"], decisions:["deny"]}`. Likely grok will route blocking `pre_tool_use` to the client IF the client advertises the matching capability in `initialize.clientCapabilities`. Unverified — that is the spike.
- **Q:** What's the fallback? -> **A:** A grok command-hook (codex-native-style, `native_policy_hook.py` plumbing) written into grok's env, if the ACP-capability route fails.
- **Q:** Does grok even run inside Omnigent? -> **A:** Yes — slice 01 SHIPPED; `acp:grok` runs a real governed-turn (ungoverned tools). This bet only adds the gate.

### N/A
- Data / migration / multi-tenancy: none; single-operator laptop harness.

### Proposed risk flags
auth: n | multi_tenant: n | durable: n | external: y | ui: n | high_stakes_ui: n
- **external: y** — the deliverable IS the egress gate on a coding agent's tool calls; correctness is the bet.

## Problem + the win

Grok now runs inside Omnigent via `acp:grok` (parent bet, slice 01 shipped), but ungoverned: over `grok agent stdio` grok auto-executes tools and never asks permission, so Omnigent's CEL policy engine never sees the tool call. Proven live — a DENY policy failed to stop a `touch` shell command; policy consulted 0 times; the file was created. Ungoverned, grok cannot be pointed at autonomous or consequential work under Omnigent's policy envelope, which is the entire reason to run a coding agent through Omnigent rather than by hand. This bet makes grok's tool calls dynamically gatable by the same CEL engine that governs claude-native and codex-native.

**Win:** When this ships, a CEL policy DENY provably blocks a grok tool call before it executes over the Omnigent-driven path, verified by `tests/e2e/test_grok_acp_e2e.py::test_grok_acp_deny_blocks_tool` flipping from its current `xfail` to PASS (the sentinel file is NOT created and the policy evaluator is consulted).

## Budget

- **Calendar:** 3 days (investigation-first: a spike to confirm the gate route precedes any build).
- **Hours (Trent):** ~2-3h — review the spike verdict + one live deny-gate proof, sign off. (guess)
- **$LLM:** $40 cap on build inference. (guess — grok turns ride the grok.com sub.)

## In

- **Spike first (gate before build):** confirm whether a grok-specific ACP client advertising the `x.ai/hooks` capability in `initialize.clientCapabilities` makes grok route blocking `pre_tool_use` to the client mid-turn. Timebox to ~half a day; a clear yes/no gates the rest.
- If viable: a thin grok-specific ACP executor (or minimal `AcpExecutor` glue) that handles grok's `pre_tool_use` request and routes it to Omnigent's `/policies/evaluate` (reuse `native_policy_hook.py` conversion), returning ALLOW/DENY/ASK.
- Fallback if the ACP-capability route fails: the grok command-hook route (write a PreToolUse command hook into grok's env pointing at the CEL endpoint), confirming whether `agent stdio` honors it.
- Flip the parent's `xfail` deny test to a real PASS; add the ALLOW + ASK cases.

## Out

- **The full native-TUI tile** — still the separate deferred bet.
- **Upstreaming to omnigent-ai**, model tuning, cross-session memory / plan-mode features.
- **Re-proving slice 01** — the governed-turn path is done; this bet is only the gate.

## Kill trigger + response

- **Trigger:** neither the `x.ai/hooks` ACP-capability route nor the command-hook route yields a dynamic per-call gate within the spike + one build day.
- **Response:** kill. Grok stays ungoverned-only in Omnigent (documented in the parent bet), usable for interactive/read-mostly work but never pointed at autonomous tool execution. A static `[permission]` deny-rule gate could be logged as a coarse partial in a future bet, but is explicitly not this one.
