# DECISIONS-NEEDED — grok-acp-gate

## RESOLVED — route B built, hardened, all tests green

- **Spike verdict:** route A (grok routes `pre_tool_use` to the ACP client) is DEAD; route B (grok command-hook via `GROK_HOME`) WORKS. Owner chose route B.
- **Built (branch `grok-acp-gate`, commits `02f7a7fc` + `843099f3`):** when the ACP command is grok, the executor provisions a throwaway `GROK_HOME` with an unmatched `PreToolUse` hook that POSTs every tool call to an in-process loopback bridge running `_decide_permission` (strict, fail-closed). DENY blocks, ALLOW runs, ASK elicits.
- **Proven:** 5 live e2e (`OMNIGENT_E2E_GROK=1`) — deny blocks, allow runs, ask-approve runs, ask-reject blocks, streaming unaffected — plus gate/executor unit tests. All green.
- **Reviewed:** deep tier, codex cross-vendor + a frontier adversarial lane. 7 confirmed findings all fixed/mitigated (see `review-report.md`). Both lanes confirmed the timeout chain fails closed.

## OWED (residuals from review — not blocking, but do before pointing grok at autonomous work)

1. **Subagent tool coverage (frontier#2) — the key verification.** Whether grok's up-to-8 subagents' INTERNAL tool calls fire the parent-session `PreToolUse` hook is UNVERIFIED (hard to force deterministically in a test). If they bypass the hook, a subagent gets ungated egress. Before trusting grok for autonomous multi-agent work: verify with a live subagent run, OR conservatively have the policy DENY `spawn_subagent` for gated grok.
2. **Sandbox read-root coverage (frontier#1).** The gate currently REFUSES to run grok under an active OS sandbox (fail-closed) because the hook interpreter may be outside the read roots. To run sandboxed grok gated, extend the sandbox read roots to cover `sys.executable` + `GROK_HOME`.
3. **Live acp bench matrix against grok** (non-blocking cross-check; the 5 e2e are the real conformance proof).
4. **`GROK_HOME` config.toml copy** imports the user's `[permission]`/hooks. Confirmed benign (a hook `deny` is authoritative; user allow-rules cannot override), but consider copying only `auth.json` for a fully deterministic gated env.
