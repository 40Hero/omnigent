# Grok gate — Slice 01: gate route spike + deny enforcement

**Type:** walking-skeleton (spike)
**Crosses layers:** ACP client (AcpExecutor) -> policy(DENY) -> grok agent stdio
**Depends on:** none
**Model plan:** implementer frontier · reviewer frontier (from shape.md)

This slice is a genuine spike: it first *confirms* grok's undocumented `x.ai/hooks` ACP behavior, then wires it to the policy gate. There is a real chance the route is dead (see the STOP rule).

## Frozen contracts

### AcpExecutor initialize -> grok (advertise the capability)
- **Input:** the `initialize` handshake gains `clientCapabilities._meta["x.ai/hooks"] = {"blockingEvents":["pre_tool_use"], "decisions":["deny"]}` (mirroring what grok advertises in its own initialize `_meta`). Sent ONLY when about to drive an agent; harmless to agents that ignore unknown `_meta`.
- **Gate:** the new inbound-request handling activates ONLY if the agent's `initialize` RESULT advertised `_meta["x.ai/hooks"]` (grok does; gemini/goose/qwen do not). Detected once at handshake, stored as `self._xai_hooks_supported: bool`.
- **Errors:** if the agent rejects the extra `_meta`, fall back to no advertisement (log + continue ungated) — never break the handshake.

### grok pre_tool_use request -> policy -> decision (the gate)
- **Inbound (from grok, TBD-by-spike):** a JSON-RPC REQUEST from grok to the client carrying the pending tool call. Exact method name + params shape are DISCOVERED by the spike (Unit 0/1) and pinned here before Unit 2. Expected: a method under the `x.ai` hooks namespace with `{sessionId, toolName, toolInput}`-shaped params and an `id` expecting a client response.
- **Handling:** convert to a `PHASE_TOOL_CALL` evaluation, run the existing `_decide_permission` (the same ALLOW/DENY/ASK machinery `session/request_permission` uses), and answer grok's request with its deny/allow decision shape (`{"decision":"deny"|"allow", ...}` per grok's advertised `decisions`).
- **Response to grok:** DENY -> grok must NOT execute the tool. ALLOW -> grok proceeds. The load-bearing observable is the tool's side effect being absent under DENY.
- **Errors / fail-closed:** if the handler cannot produce a verdict on a governed session, answer DENY (fail-closed — a gate that fails open is worse than none).

## Real vs stubbed

- **Real (this slice):** the capability advertisement, the inbound `pre_tool_use` handler, the `_decide_permission` DENY path, and grok actually blocking the tool. The policy is the in-process `_policy_evaluator` (as in the parent e2e), not a live HTTP endpoint.
- **Stubbed:** ALLOW-proceeds and ASK-elicitation are exercised only enough to prove DENY; full ALLOW/ASK coverage is slice 02. Route B (command-hook) is NOT built here.

## DONE

**Given** an `AcpExecutor` driving real `grok agent stdio`, advertising the `x.ai/hooks` client capability, with a `_policy_evaluator` that returns DENY for the shell tool,
**When** grok is prompted to run `touch <sentinel>` via the shell,
**Then** grok routes a blocking `pre_tool_use` request to the client, the policy evaluator is consulted (>0 times), the answer is DENY, and the tool does NOT execute — the sentinel file is NOT created.

**Verify:** `OMNIGENT_E2E_GROK=1 .venv/bin/python -m pytest tests/e2e/test_grok_acp_e2e.py::test_grok_acp_deny_blocks_tool -v` PASSES (the parent's `xfail(strict)` marker is removed as part of this slice; a strict-xfail that starts passing would otherwise error).

**STOP condition (spike may fail):** if Unit 1 shows grok does NOT route `pre_tool_use` to the client even with the capability advertised, this done-test cannot pass via route A. Do NOT build route B. Queue "route A dead — route B or kill?" to `DECISIONS-NEEDED.md`, leave the test `xfail`, and stop the run for the owner.

## Non-goals

- No route B (command-hook / HTTP policy) build.
- No new harness, no `GrokAcpExecutor` subclass, no registration changes.
- No behavior change for gemini/goose/qwen or any agent not advertising `x.ai/hooks`.
- No ALLOW/ASK completeness (slice 02).

## Layers / files touched

- `omnigent/inner/acp_executor.py`: advertise `x.ai/hooks` in `initialize`; detect `self._xai_hooks_supported`; handle the inbound `pre_tool_use` request through `_decide_permission`.
- `tests/e2e/test_grok_acp_e2e.py`: remove the `xfail` from `test_grok_acp_deny_blocks_tool`.
- `tests/inner/test_acp_executor.py`: unit coverage for the new handler (fake agent sending a `pre_tool_use` request).

## Build units

- [S] **Unit 0: author the spike diagnostic + confirm the target is RED** — a raw-ACP script (fix the parent spike's `session/new` handling: read `result.sessionId` correctly, correct `session/prompt` param shape) that advertises `x.ai/hooks` and logs any grok->client request. Confirm the parent deny test is currently xfail/failing.
- [S] **Unit 1 (SPIKE GATE): does grok route pre_tool_use to the client?** Run the diagnostic. If YES, pin the exact method + params in the Frozen contract and proceed. If NO, execute the STOP condition (queue + halt).
- [S] **Unit 2: advertise + detect** — add the capability to `initialize`; set `self._xai_hooks_supported` from the agent's initialize result; against contract: AcpExecutor initialize -> grok.
- [S] **Unit 3: handle + gate** — route grok's `pre_tool_use` request through `_decide_permission`, answer DENY, fail-closed on no-verdict; against contract: grok pre_tool_use -> policy -> decision.
- [S] **Unit 4: unit test the handler** — fake-agent test that a `pre_tool_use` request + a DENY verdict yields grok's deny response and no execution.
- [S] **Final: remove the xfail, run the done-test, confirm GREEN.**
