# Grok gate — Slice 02: allow + ask + regression + bench

**Type:** thickening
**Crosses layers:** ACP client (AcpExecutor) -> policy(ALLOW/ASK) -> grok agent stdio; harness-bench
**Depends on:** 01 (only runnable if slice 01's route A succeeded)
**Model plan:** implementer default · reviewer frontier (from shape.md)

If slice 01 hit its STOP condition (route A dead), this slice does not run — it is gated on a working gate.

## Frozen contracts

### policy ALLOW/ASK -> grok pre_tool_use response (extends slice 01)
- **ALLOW:** `_decide_permission` returns allow -> the handler answers grok's `pre_tool_use` request with its allow decision -> grok executes the tool normally.
- **ASK:** `_decide_permission` defers to elicitation -> the existing human-consent elicitation handler is invoked -> its resolution maps to grok's allow/deny decision.
- **Errors:** unchanged from slice 01 (fail-closed to DENY on no verdict).

### acp bench profile -> grok
- **Input:** the `acp` bench profile with the `acp:` config pointed at grok.
- **Output:** a probe matrix (basic_turn, streaming, tool_calling, policy_deny, interrupt, cost_tracking) recorded as the formal cross-check. policy_deny now reflects the working gate.

## Real vs stubbed

- **Real:** ALLOW lets a real read tool run; ASK raises a real elicitation and its answer flows back to grok; the deny regression stays green; a real bench run.
- **Stubbed:** none.

## DONE

**Given** the working grok gate from slice 01,
**When** (a) a read tool runs under an ALLOW policy, (b) a tool runs under an ASK policy, and (c) the `acp` bench profile is run against grok,
**Then** (a) the read tool executes and its result reaches the turn, (b) the ASK raises an elicitation whose approval lets the tool run and whose rejection blocks it, (c) the deny regression test still passes, and (d) the bench matrix is produced with policy_deny reflecting the gate.

**Verify:** `OMNIGENT_E2E_GROK=1 .venv/bin/python -m pytest tests/e2e/test_grok_acp_e2e.py -v` shows deny (regression) + allow + ask all green; and `python -m tests.harness_bench --harness acp --live` (acp config = grok) prints a matrix with no DRIFT and policy_deny at least PARTIAL.

## Non-goals

- No route B, no new harness, no native-tile files.
- No model tuning; grok-4.5 default.
- No committed bench fixture unless the queued decision says so.

## Layers / files touched

- `omnigent/inner/acp_executor.py`: ALLOW/ASK branches of the `pre_tool_use` handler (mostly reuse of `_decide_permission` + the elicitation handler from slice 01).
- `tests/e2e/test_grok_acp_e2e.py`: add allow-proceeds and ask-elicitation e2e cases.
- bench invocation wiring for the matrix record.

## Build units

- [S] **Unit 0: write the allow + ask done-tests, confirm RED** — before the ALLOW/ASK branches, an ALLOW read tool is blocked (fail-closed) or an ASK is not surfaced; pin the assertions.
- [S] **Unit 1: ALLOW proceeds** — allow branch answers grok's request with allow; a read tool runs; against contract: policy ALLOW.
- [S] **Unit 2: ASK -> elicitation** — ask branch invokes the elicitation handler; approve runs, reject blocks; against contract: policy ASK.
- [S] **Unit 3: bench matrix** — run `--harness acp --live` against grok, record the matrix.
- [S] **Final: run the full done-test (deny regression + allow + ask + bench), confirm GREEN.**
