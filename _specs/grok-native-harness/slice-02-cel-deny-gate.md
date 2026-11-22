# Grok harness — Slice 02: CEL deny gate

**Type:** thickening
**Crosses layers:** policy -> AcpExecutor -> grok agent stdio
**Depends on:** 01
**Model plan:** implementer default · reviewer frontier (from shape.md)

This is the value proof: the whole reason to run grok inside Omnigent instead of by hand.

## Frozen contracts

### session/request_permission -> CEL policy -> decision (reused AcpExecutor path)
- **Request:** grok emits ACP `session/request_permission {sessionId, toolCall:{name, rawInput/arguments}, options}` when a tool needs approval under permission-mode `default`.
- **Omnigent handling (existing):** AcpExecutor converts it to a TOOL_CALL policy evaluation -> `POST /v1/sessions/{id}/policies/evaluate` -> the CEL engine returns ALLOW / DENY / ASK.
- **Response back to grok:** DENY -> the `request_permission` result selects the reject/deny option (grok does NOT run the tool); ALLOW -> the approve option; ASK -> a human-consent elicitation card is raised and its resolution is returned.
- **Errors / fail-closed:** if the round trip yields no usable verdict on a governed session, the tool is denied (fail-closed), matching `native_policy_hook.fail_closed_hook_output` semantics.

## Real vs stubbed

- **Real (this slice):** a session CEL policy that denies the shell tool; grok's shell-tool attempt is intercepted and blocked with no execution; ALLOW lets a read tool proceed; ASK raises an elicitation.
- **Stubbed:** nothing — this exercises the real policy engine on real grok tool calls. (If slice 01 found grok does NOT emit `session/request_permission` and the Decision-5 fallback was taken, this slice gates via grok's native `x.ai/hooks pre_tool_use` instead; the done-test outcome is identical.)

## DONE

**Given** the acp:grok governed session from slice 01, and a session CEL policy that DENIES the shell tool (`run_terminal_cmd`),
**When** grok is prompted to run a shell command it would otherwise execute (e.g. "run `echo hello` in the shell"),
**Then** the tool call is blocked before execution — no `echo` runs on the host — grok receives the denial, and the transcript honestly shows the tool was denied by policy (not silently dropped).

**Verify:** with a deny-shell policy attached, `omni run --harness acp:grok "run the shell command: echo omnigent-gate-proof"` completes with NO `omnigent-gate-proof` appearing in any shell output / no side effect on disk, and the session transcript + policy log show a DENY for `run_terminal_cmd`. (Exact policy-attachment + assertion path pinned in Unit 0, mirroring how codex-native's deny is tested.)

## Non-goals

- No new policy-engine features — reuse the existing TOOL_CALL policy + `/policies/evaluate`.
- No exhaustive tool-matrix; one clearly-destructive tool (shell) proves the gate.
- ASK is observed, not fully productized (no new elicitation UI).

## Layers / files touched

- Policy: session CEL policy fixture denying `run_terminal_cmd` (test-scoped).
- Executor: `omnigent/inner/acp_executor.py` — only if grok's `session/request_permission` shape needs a grok-guarded adapter to map cleanly to the deny/allow options.
- Tests: integration test attaching the deny policy and asserting no side effect + a DENY verdict.

## Build units

- [S] **Unit 0: write the done-test + confirm RED** — before the deny wiring is proven, prompting grok to shell-out executes `echo` (side effect present); pin the policy-attach + side-effect-absence assertion.
- [S] **Unit 1: DENY blocks** — attach the deny-shell policy, run grok's shell attempt, assert the tool never executes and grok gets the denial; against contract: request_permission -> CEL -> decision.
- [S] **Unit 2: ALLOW proceeds** — a read tool under an allow/empty policy runs normally (regression guard that the gate is not blanket-blocking).
- [S] **Unit 3: ASK raises an elicitation** — a policy set to ASK surfaces a human-consent card; resolving it approve/reject flows back to grok.
- [S] **Final: run the done-test, confirm GREEN.**
