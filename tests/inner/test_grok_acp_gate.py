"""Unit tests for the grok tool-egress gate (no real grok needed).

Covers the loopback bridge in isolation: a POSTed tool payload is mapped to a
permission-params dict, run through a fake decider, and answered allow/deny —
and the bridge fails CLOSED (deny) when the decider raises. Also covers the
payload mapping and the hook's no-URL fail-closed path.
"""

from __future__ import annotations

import asyncio
import json
import urllib.error
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


def _post(url: str, payload: dict, token: str | None = None) -> dict:
    headers = {"Content-Type": "application/json"}
    if token is not None:
        headers["X-Omnigent-Gate-Token"] = token
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:  # 403 unauthorized still returns a deny body
        return json.loads(exc.read().decode())


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
        url, tok = _gate_url(gate), gate._token  # type: ignore[attr-defined]
        payload = {"toolName": "run_terminal_command", "toolInput": {"command": "x"}}

        verdict["allow"] = True
        assert (await asyncio.to_thread(_post, url, payload, tok))["decision"] == "allow"

        verdict["allow"] = False
        assert (await asyncio.to_thread(_post, url, payload, tok))["decision"] == "deny"
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
        out = await asyncio.to_thread(_post, _gate_url(gate), {"toolName": "x"}, gate._token)  # type: ignore[attr-defined]
        assert out["decision"] == "deny"
    finally:
        gate.close()


@pytest.mark.asyncio
async def test_gate_rejects_untokened_request(tmp_path) -> None:
    """A request without the per-session token is denied (no local spoofing)."""
    allowed = {"n": 0}

    async def decide(params: dict) -> bool:
        allowed["n"] += 1
        return True

    gate = GrokAcpGate(decide, asyncio.get_running_loop())
    gate.start(real_grok_home=tmp_path)
    try:
        out = await asyncio.to_thread(_post, _gate_url(gate), {"toolName": "x"}, None)
        assert out["decision"] == "deny"
        assert allowed["n"] == 0, "decider must not run for an untokened request"
        # wrong token also rejected
        out2 = await asyncio.to_thread(_post, _gate_url(gate), {"toolName": "x"}, "wrong")
        assert out2["decision"] == "deny"
    finally:
        gate.close()


@pytest.mark.asyncio
async def test_gate_denies_truncated_input(tmp_path) -> None:
    """A truncated tool input is unjudgeable -> deny before the decider runs."""
    ran = {"n": 0}

    async def decide(params: dict) -> bool:
        ran["n"] += 1
        return True

    gate = GrokAcpGate(decide, asyncio.get_running_loop())
    gate.start(real_grok_home=tmp_path)
    try:
        payload = {
            "toolName": "run_terminal_command",
            "toolInput": {"command": "rm"},
            "toolInputTruncated": True,
        }
        out = await asyncio.to_thread(_post, _gate_url(gate), payload, gate._token)  # type: ignore[attr-defined]
        assert out["decision"] == "deny"
        assert ran["n"] == 0, "decider must not run on truncated input"
    finally:
        gate.close()


def test_gate_provisions_hook_by_absolute_path_with_token(tmp_path) -> None:
    """start() writes an unmatched PreToolUse hook run by absolute path (not -m)."""

    async def decide(params: dict) -> bool:
        return True

    async def run() -> None:
        gate = GrokAcpGate(decide, asyncio.get_running_loop())
        gate.start(real_grok_home=tmp_path)
        try:
            home = gate._home  # type: ignore[attr-defined]
            hook_file = json.loads((home / "hooks" / "omnigent-gate.json").read_text())
            pre = hook_file["hooks"]["PreToolUse"][0]["hooks"][0]
            # invoked by absolute path to a copied script, never `-m` (no cwd shadow)
            assert " -m " not in pre["command"]
            assert str(home / "omnigent_grok_hook.py") in pre["command"]
            assert (home / "omnigent_grok_hook.py").exists()
            assert pre["env"]["OMNIGENT_GROK_GATE_URL"].startswith("http://127.0.0.1:")
            assert pre["env"]["OMNIGENT_GROK_GATE_TOKEN"] == gate._token  # type: ignore[attr-defined]
            assert "matcher" not in hook_file["hooks"]["PreToolUse"][0]
        finally:
            gate.close()

    asyncio.run(run())
