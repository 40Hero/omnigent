# Grok harness — Slice 01: acp:grok governed turn

**Type:** walking-skeleton
**Crosses layers:** config -> acp harness -> AcpExecutor -> policy(ALLOW) -> grok agent stdio
**Depends on:** none
**Model plan:** implementer default · reviewer frontier (from shape.md)

## Frozen contracts

### Config -> harness (`acp:` config block -> `_build_acp_spawn_env`)
- **Input:** one agent entry in the global `acp:` config: `{"slug":"grok","name":"Grok Build","command":"grok agent stdio","session_id_mode":"server","send_model":<bool>}` (knob names per `omnigent/runtime/workflow.py:1488-1511`).
- **Output:** selecting harness `acp:grok` sets spawn env `HARNESS_ACP_COMMAND="grok agent stdio"` (+ `HARNESS_ACP_NAME`, model/session knobs) consumed by `omnigent/inner/acp_harness.py`.
- **Errors:** no `grok` agent configured -> `HARNESS_ACP_COMMAND` unset -> harness request-time error (this is the RED state before config).

### AcpExecutor <-> grok (ACP JSON-RPC over stdio, protocolVersion 1)
- **Handshake:** `initialize` -> result advertises `protocolVersion:1`, `agentCapabilities.loadSession:true`, `session/request_permission` support, `authMethods:[cached_token,...]` (verified live).
- **Turn:** `session/new {cwd, mcpServers}` -> sessionId; `session/prompt {sessionId, prompt}` -> stream of `session/update` (agent_message_chunk text, tool_call, tool_call_update) -> stop.
- **Event mapping (in AcpExecutor, reused):** `session/update` text -> `TextChunk`; `tool_call` -> `ToolCallRequest`; `tool_call_update` -> `ToolCallComplete`; final -> `TurnComplete`; failure -> `ExecutorError`.
- **Errors:** ACP request error -> surfaced as `ExecutorError`; auth failure -> handshake error before any turn.

## Real vs stubbed

- **Real (this slice):** the full path — acp:grok config, ACP handshake, one `session/prompt` turn, grok's text response streamed as Omnigent events, and one tool call passing through the CEL policy evaluation in ALLOW mode.
- **Stubbed:** none of the transport. Governance is exercised only in ALLOW here (DENY/ASK is slice 02). Model override / interrupt / cost / bench are slice 03.

## DONE

**Given** a fresh Omnigent, grok installed + authed (`grok models` shows logged in), and an `acp:grok` agent written to the global `acp:` config,
**When** a governed session is run against harness `acp:grok` with a prompt that asks grok to read one file (e.g. "read ./README and reply with its first line"), under permission-mode `default`,
**Then** grok's reply comes back through Omnigent's event stream (a `TextChunk`/`TurnComplete` carrying the real answer), the file-read tool call surfaces as a `ToolCallRequest`, and the CEL policy path logs an ALLOW evaluation for it (the tool was seen by the gate, not self-executed invisibly).

**Verify:** `omni run --harness acp:grok "read ./README.md and reply with only its first line"` returns grok's answer through Omnigent, AND the session's policy-evaluation log shows one TOOL_CALL evaluation (ALLOW) for the read. (Slice 01 pins the exact run command + log-inspection path in Unit 0; if `omni run` lacks a headless assertion hook, the done-test is the equivalent `tests/` integration test driving the session API and asserting the streamed events + a policy-evaluate call.)

## Non-goals

- No DENY/ASK policy (slice 02).
- No model override, interrupt, or cost surfacing (slice 03).
- No native-tile files, no launch-wiring, no capability/native_agents edits.
- No grok-dialect glue beyond the minimum to make one turn complete.

## Layers / files touched

- Config: global `acp:` block (user config) — the `acp:grok` agent entry.
- Executor/harness: `omnigent/inner/acp_executor.py` / `acp_harness.py` — grok-dialect glue ONLY if the handshake/turn needs it.
- Tests: one integration test under `tests/` (or the pinned `omni run` invocation) exercising the governed turn.

## Build units

- [S] **Unit 0: write the done-test + confirm RED** — with no `acp:grok` configured, the run errors "no agent configured"; pin the exact governed-run + policy-log-inspection command here.
- [S] **Unit 1: register `acp:grok`** — write the agent entry via the Omnigent ACP-agent config path (Decision 1); against contract: Config -> harness.
- [S] **Unit 2: complete one governed turn** — run acp:grok, drive `initialize`/`session/new`/`session/prompt`; add grok-guarded glue in `acp_executor.py` only if a real divergence blocks the turn; against contract: AcpExecutor <-> grok.
- [S] **Unit 3: confirm the ALLOW gate fired** — assert the tool call routed through `/policies/evaluate` (ALLOW), proving the governance seam is live even on the happy path.
- [S] **Final: run the done-test, confirm GREEN.**
