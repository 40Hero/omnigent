"""End-to-end tests: the generic ``acp`` harness drives ``grok agent stdio``.

Grok Build (xAI) speaks the Agent Client Protocol via ``grok agent stdio``. Unlike
Goose (which has a dedicated ``GooseExecutor``), Grok rides the *generic*
:class:`omnigent.inner.acp_executor.AcpExecutor` straight from an ``acp:grok``
config entry — no vendor-specific executor. This test drives that generic executor
against a *real* ``grok agent stdio`` process and asserts the full round-trip:
streaming agent text and a completed turn (slice 01), then a mid-turn
``session/request_permission`` gated by Omnigent's TOOL_CALL policy — DENY blocks
the tool, ASK routes to elicitation (slice 02).

Environment requirements (why this is opt-in, not pure-CI)
----------------------------------------------------------
* **Opt-in only**: set ``OMNIGENT_E2E_GROK=1`` to run. Needs the ``grok`` binary on
  PATH and a logged-in Grok (``grok models`` shows an account; auth is grok's own
  cached token in ``~/.grok/auth.json`` or ``XAI_API_KEY``). The agent subprocess
  runs in an isolated temp ``cwd`` so its file tools never touch the repo; grok's
  own auth/session dirs are left as-is (additive, harmless).

    OMNIGENT_E2E_GROK=1 .venv/bin/python -m pytest tests/e2e/test_grok_acp_e2e.py -v
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from omnigent.inner.acp_executor import AcpAgentConfig, AcpExecutor
from omnigent.inner.executor import ExecutorError, TextChunk, TurnComplete

pytestmark = pytest.mark.skipif(
    os.environ.get("OMNIGENT_E2E_GROK") != "1" or shutil.which("grok") is None,
    reason=(
        "grok ACP e2e is opt-in: set OMNIGENT_E2E_GROK=1 with the `grok` binary on "
        "PATH and a logged-in Grok (grok models shows an account)."
    ),
)

_GROK_COMMAND = "grok agent stdio"


class _AskVerdict:
    """A TOOL_CALL policy verdict that always defers to elicitation."""

    action = "POLICY_ACTION_ASK"


class _DenyVerdict:
    """A TOOL_CALL policy verdict that denies the tool outright."""

    action = "POLICY_ACTION_DENY"
    reason = "blocked by test policy"


def _grok_executor(cwd: Path) -> AcpExecutor:
    """Construct the generic ACP executor pointed at real ``grok agent stdio``."""
    return AcpExecutor(
        AcpAgentConfig(command=_GROK_COMMAND, name="Grok"),
        cwd=str(cwd),
    )


@pytest.mark.asyncio
async def test_grok_acp_streams_and_completes(tmp_path: Path) -> None:
    """Slice 01 skeleton: a plain prose turn streams agent text and completes."""
    executor = _grok_executor(tmp_path)
    chunks: list[str] = []
    final: TurnComplete | None = None
    try:
        async for ev in executor.run_turn(
            [{"role": "user", "content": "Reply with exactly the word PONG and nothing else."}],
            tools=[],
            system_prompt="You are a terse assistant.",
        ):
            if isinstance(ev, TextChunk):
                chunks.append(ev.text)
            elif isinstance(ev, TurnComplete):
                final = ev
            elif isinstance(ev, ExecutorError):
                pytest.fail(f"executor error: {ev.message}")
    finally:
        await executor.close()

    assert final is not None, "expected a TurnComplete"
    assert "PONG" in ("".join(chunks) + (final.response or "")), (
        f"grok reply did not contain PONG; chunks={chunks!r} response={final.response!r}"
    )


@pytest.mark.asyncio
async def test_grok_acp_deny_blocks_tool(tmp_path: Path) -> None:
    """A CEL DENY blocks grok's shell tool before it runs (grok-acp-gate).

    A sentinel file is the side-effect probe: grok is asked to create it via the
    shell. Grok auto-executes tools over ACP, so the gate is enforced by a
    provisioned PreToolUse hook (omnigent.grok_acp_gate) that bridges every tool
    call back to _decide_permission; under a DENY policy the tool never executes
    and the file must NOT exist afterward.
    """
    sentinel = tmp_path / "grok-gate-proof.txt"
    denied: list[dict] = []

    async def _policy(phase: str, tool: dict) -> _DenyVerdict:
        denied.append({"phase": phase, "tool": tool})
        return _DenyVerdict()

    executor = _grok_executor(tmp_path)
    executor._policy_evaluator = _policy  # type: ignore[attr-defined]

    try:
        async for ev in executor.run_turn(
            [
                {
                    "role": "user",
                    "content": (
                        f"Use the shell tool to run exactly: touch {sentinel}. "
                        "Do not do anything else."
                    ),
                }
            ],
            tools=[],
            system_prompt="You are a helpful coding agent. Use the shell tool when asked.",
        ):
            if isinstance(ev, ExecutorError):
                # An error is acceptable (grok may surface the denial as an error);
                # the load-bearing assertion is the absence of the side effect.
                break
    finally:
        await executor.close()

    assert not sentinel.exists(), (
        "DENY policy failed to block grok's shell tool — the sentinel file was created"
    )
    assert denied, "policy evaluator was never consulted — the tool was not gated"


class _AllowVerdict:
    """A TOOL_CALL policy verdict that allows the tool outright."""

    action = "POLICY_ACTION_ALLOW"


async def _run_touch(executor: AcpExecutor, sentinel: Path) -> None:
    """Drive one grok turn that asks for a shell `touch <sentinel>`."""
    try:
        async for ev in executor.run_turn(
            [
                {
                    "role": "user",
                    "content": (
                        f"Use the shell tool to run exactly: touch {sentinel}. "
                        "Do not do anything else."
                    ),
                }
            ],
            tools=[],
            system_prompt="You are a helpful coding agent. Use the shell tool when asked.",
        ):
            if isinstance(ev, ExecutorError):
                break
    finally:
        await executor.close()


@pytest.mark.asyncio
async def test_grok_acp_allow_runs_tool(tmp_path: Path) -> None:
    """ALLOW lets grok's shell tool run — the gate is not a blanket block."""
    sentinel = tmp_path / "grok-allow-proof.txt"
    seen: list[dict] = []

    async def _policy(phase: str, tool: dict) -> _AllowVerdict:
        seen.append({"phase": phase, "tool": tool})
        return _AllowVerdict()

    executor = _grok_executor(tmp_path)
    executor._policy_evaluator = _policy  # type: ignore[attr-defined]
    await _run_touch(executor, sentinel)

    assert seen, "policy evaluator was never consulted — the gate did not fire"
    assert sentinel.exists(), "ALLOW policy wrongly blocked grok's shell tool"


@pytest.mark.asyncio
async def test_grok_acp_ask_approve_runs(tmp_path: Path) -> None:
    """ASK routes to elicitation; on approval the tool runs."""
    sentinel = tmp_path / "grok-ask-approve.txt"
    elicited: list[tuple[str, dict]] = []

    async def _policy(phase: str, tool: dict) -> _AskVerdict:
        return _AskVerdict()

    async def _elicit(tool_name: str, tool_input: dict) -> bool:
        elicited.append((tool_name, tool_input))
        return True  # user approves

    executor = _grok_executor(tmp_path)
    executor._policy_evaluator = _policy  # type: ignore[attr-defined]
    executor._elicitation_handler = _elicit  # type: ignore[attr-defined]
    await _run_touch(executor, sentinel)

    assert elicited, "ASK verdict did not raise an elicitation"
    assert sentinel.exists(), "approved ASK wrongly blocked grok's shell tool"


@pytest.mark.asyncio
async def test_grok_acp_ask_reject_blocks(tmp_path: Path) -> None:
    """ASK routes to elicitation; on rejection the tool is blocked."""
    sentinel = tmp_path / "grok-ask-reject.txt"
    elicited: list[tuple[str, dict]] = []

    async def _policy(phase: str, tool: dict) -> _AskVerdict:
        return _AskVerdict()

    async def _elicit(tool_name: str, tool_input: dict) -> bool:
        elicited.append((tool_name, tool_input))
        return False  # user rejects

    executor = _grok_executor(tmp_path)
    executor._policy_evaluator = _policy  # type: ignore[attr-defined]
    executor._elicitation_handler = _elicit  # type: ignore[attr-defined]
    await _run_touch(executor, sentinel)

    assert elicited, "ASK verdict did not raise an elicitation"
    assert not sentinel.exists(), "rejected ASK failed to block grok's shell tool"
