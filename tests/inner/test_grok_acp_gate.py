"""Unit tests for the grok tool-egress gate (no real grok needed).

Covers the loopback bridge in isolation: a POSTed tool payload is mapped to a
permission-params dict, run through a fake decider, and answered allow/deny —
and the bridge fails CLOSED (deny) when the decider raises. Also covers the
payload mapping and the hook's no-URL fail-closed path.
"""

from __future__ import annotations

import asyncio
import json
import urllib.request

import pytest

from omnigent.grok_acp_gate import GrokAcpGate, _payload_to_permission_params


def test_payload_maps_toolname_and_input() -> None:
    params = _payload_to_permission_params(
        {"toolName": "run_terminal_command", "toolInput": {"command": "echo hi"}}
    )
    # AcpExecutor._extract_tool_call reads params["toolCall"]{title, rawInput}.
    assert params["toolCall"]["title"] == "run_terminal_command"
    assert params["toolCall"]["rawInput"] == {"command": "echo hi"}


def test_payload_defaults_when_fields_missing() -> None:
    params = _payload_to_permission_params({})
    assert params["toolCall"]["title"] == "tool"
    assert params["toolCall"]["rawInput"] == {}


def test_payload_non_dict_input_wrapped() -> None:
    params = _payload_to_permission_params({"toolName": "x", "toolInput": "raw-string"})
    assert params["toolCall"]["rawInput"] == {"value": "raw-string"}


def _post(url: str, payload: dict) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


def _gate_url(gate: GrokAcpGate) -> str:
    server = gate._server  # type: ignore[attr-defined]
    assert server is not None
    return f"http://127.0.0.1:{server.server_address[1]}/evaluate"


@pytest.mark.asyncio
async def test_gate_bridges_allow_and_deny(tmp_path) -> None:
    """The loopback bridge returns the decider's allow/deny verdict."""
    verdict = {"allow": True}

    async def decide(params: dict) -> bool:
        # confirm the mapping reached the decider intact
        assert params["toolCall"]["title"] == "run_terminal_command"
        return verdict["allow"]

    gate = GrokAcpGate(decide, asyncio.get_running_loop())
    gate.start(real_grok_home=tmp_path)  # empty source: no auth copy needed for this test
    try:
        url = _gate_url(gate)
        payload = {"toolName": "run_terminal_command", "toolInput": {"command": "x"}}

        verdict["allow"] = True
        assert (await asyncio.to_thread(_post, url, payload))["decision"] == "allow"

        verdict["allow"] = False
        assert (await asyncio.to_thread(_post, url, payload))["decision"] == "deny"
    finally:
        gate.close()


@pytest.mark.asyncio
async def test_gate_fails_closed_when_decider_raises(tmp_path) -> None:
    """A decider exception must yield DENY, never a silent allow."""

    async def boom(params: dict) -> bool:
        raise RuntimeError("policy backend down")

    gate = GrokAcpGate(boom, asyncio.get_running_loop())
    gate.start(real_grok_home=tmp_path)
    try:
        decision = (await asyncio.to_thread(_post, _gate_url(gate), {"toolName": "x"}))["decision"]
        assert decision == "deny"
    finally:
        gate.close()


def test_gate_provisions_hook_and_grok_home(tmp_path) -> None:
    """start() writes an unmatched PreToolUse hook carrying the gate URL."""

    async def decide(params: dict) -> bool:
        return True

    async def run() -> None:
        gate = GrokAcpGate(decide, asyncio.get_running_loop())
        gate.start(real_grok_home=tmp_path)
        try:
            hook_file = json.loads(
                (gate._home / "hooks" / "omnigent-gate.json").read_text()  # type: ignore[attr-defined]
            )
            pre = hook_file["hooks"]["PreToolUse"][0]["hooks"][0]
            assert "grok_acp_hook" in pre["command"]
            assert pre["env"]["OMNIGENT_GROK_GATE_URL"].startswith("http://127.0.0.1:")
            # no matcher -> fires for every tool
            assert "matcher" not in hook_file["hooks"]["PreToolUse"][0]
        finally:
            gate.close()

    asyncio.run(run())
