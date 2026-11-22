# Grok harness — Slice 03: model override + interrupt + cost + bench matrix

**Type:** thickening
**Crosses layers:** config -> AcpExecutor -> grok agent stdio; harness-bench
**Depends on:** 01
**Model plan:** implementer default · reviewer default (from shape.md)

## Frozen contracts

### Model override (Omnigent model picker -> session/new)
- **Input:** a per-turn model override (`grok-4.5` <-> `grok-composer-2.5-fast`) via `ExecutorConfig.model` (the adapter stamps it from `request.model_override`).
- **Output:** AcpExecutor passes the model into `session/new` (or grok's model-set method); grok's response is produced by the requested model, reflected in its `modelState.currentModelId` / usage `modelUsage` key.
- **Errors:** unknown model id -> grok rejects at `session/new` -> `ExecutorError`.

### Interrupt (Omnigent interrupt -> ACP cancel)
- **Input:** an interrupt on a running turn.
- **Output:** AcpExecutor sends ACP `session/cancel` (the reused path); grok stops the turn; Omnigent emits `TurnCancelled`.

### Cost / usage (grok ACP `_meta.usage` -> Omnigent)
- **Input:** grok's end-of-turn usage (`_meta.usage` PromptUsage on `session/update`/stop, or the headless `usage`/`modelUsage` shape).
- **Output:** surfaced on `TurnComplete` as token usage; priced cost when grok stamps it (SUPPORTED), tokens-only otherwise (PARTIAL) — matching the bench's cost_tracking verdict semantics.

### Bench (`python -m tests.harness_bench --harness acp`)
- **Input:** the `acp` bench profile with the `acp:` config pointed at grok.
- **Output:** a probe matrix (basic_turn, streaming, tool_calling, policy_deny, model_override, interrupt, cost_tracking) recorded as the formal cross-check.

## Real vs stubbed

- **Real (this slice):** live model override, live interrupt, live usage surfacing, and a real bench run against grok.
- **Stubbed:** nothing. Cost may legitimately land PARTIAL (tokens-only) if grok's OAuth/pool path omits priced cost — that is an honest verdict, not a stub.

## DONE

**Given** the acp:grok governed session,
**When** (a) a turn is run with the model overridden to `grok-composer-2.5-fast`, (b) a long-running turn is interrupted, and (c) the `acp` bench profile is run against grok,
**Then** (a) the responder is the overridden model (visible in usage/model state), (b) the interrupted turn stops and emits a cancellation, (c) usage/cost surfaces on turn completion, and (d) the bench matrix is produced and recorded.

**Verify:** `python -m tests.harness_bench --harness acp --live` (acp config = grok) prints a matrix with basic_turn/streaming/tool_calling/policy_deny/model_override/interrupt at least SUPPORTED-or-PARTIAL and no DRIFT; plus a live `omni run --harness acp:grok -m grok-composer-2.5-fast "..."` whose usage names the composer model, and an interrupt test that yields `TurnCancelled`.

## Non-goals

- No model tuning / effort optimization beyond proving override switches the responder.
- No committed bench fixture unless Decision (queued) says so.
- No native-tile files.

## Layers / files touched

- Executor: `omnigent/inner/acp_executor.py` — grok-guarded glue for model-in-session/new and usage extraction, if the reused path does not already cover grok's shape.
- Tests: bench invocation wiring + interrupt/override integration assertions.

## Build units

- [S] **Unit 0: write the done-test + confirm RED** — before override wiring, both models respond identically / usage unlabeled; pin the bench + override + interrupt assertions.
- [S] **Unit 1: model override** — thread `ExecutorConfig.model` into grok's `session/new`; assert the responder model; against contract: Model override.
- [S] **Unit 2: interrupt** — wire/confirm `session/cancel` stops a turn -> `TurnCancelled`; against contract: Interrupt.
- [S] **Unit 3: cost/usage** — surface grok's `_meta.usage` on `TurnComplete`; against contract: Cost/usage.
- [S] **Unit 4: bench matrix** — run `--harness acp --live` against grok, record the matrix; against contract: Bench.
- [S] **Final: run the done-test, confirm GREEN.**
