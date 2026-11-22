# DECISIONS-NEEDED — grok-native-harness

## BLOCKING (circuit breaker fired) — the governance premise is falsified

**What the build proved (live, on branch `grok-acp-harness` in the omnigent fork):**

- **Slice 01 GREEN.** Grok runs a real turn through Omnigent via `acp:grok` on the generic `AcpExecutor`, **zero glue** — `tests/e2e/test_grok_acp_e2e.py::test_grok_acp_streams_and_completes` PASSES against real grok (streams reasoning + text, completes). Grok is usable in Omnigent right now.
- **Slice 02 RED — root cause found.** Over `grok agent stdio`, grok **auto-executes tools and never emits `session/request_permission`**. Diagnostic: for a `touch <file>` shell request, events were `ToolCallRequest -> ToolCallComplete`, the policy evaluator was **consulted 0 times**, and the file **was created**. A naive `~/.grok/hooks` PreToolUse deny hook (via isolated `GROK_HOME`) did **not** block it either.
- **Why:** the generic `AcpExecutor` gate depends on the agent volunteering `session/request_permission` (gemini/goose do). Grok in ACP mode does not — its per-call approval is an interactive-TUI prompt it auto-approves headlessly. Grok's only non-interactive gates are **static** `[permission]` deny rules / `--deny`, not Omnigent's **dynamic per-call** CEL evaluation.

**Consequence:** the bet as framed (governed grok ≈ config + thin glue, ~1 day) is dead. A dynamic CEL gate for grok is real grok-specific code. Reshape or kill — do not extend this bet's appetite.

## The fork in the road (owner decision)

1. **Ship slice 01 as-is: "grok in Omnigent, UNGOVERNED."** `acp:grok` for interactive / read-mostly use; explicitly NOT safe to point at autonomous tool work. Zero further build. Honest and limited.
2. **New bet — grok ACP `x.ai/hooks` gate (recommended path to investigate).** Grok's initialize advertises `x.ai/hooks: {blockingEvents:["pre_tool_use"], decisions:["deny"]}`. A thin **grok-specific** ACP executor that advertises the matching client capability in `initialize` and routes grok's blocking `pre_tool_use` -> Omnigent's `/policies/evaluate` may give the dynamic gate. Unverified protocol; ~1-2 days; its own bet.
3. **New bet — grok native command-hook gate.** The codex-native-style PreToolUse command-hook + `native_policy_hook.py` plumbing, written into grok's env. Heavier; my quick probe suggests `agent stdio` may not run those hooks — needs confirmation. Overlaps the deferred native-tile bet's hook half.
4. **Static deny-rules gate (partial).** Translate Omnigent policy -> grok `[permission]` deny rules per session. Coarse (static, not per-call); loses dynamic CEL evaluation.

## Non-blocking (queued, not worked)
- Slices 02 + 03 done-tests are parked pending the governance decision above (both depend on a working gate).
- Whether to record the `acp` bench matrix against grok.
