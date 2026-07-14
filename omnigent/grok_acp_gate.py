"""Per-session tool-egress gate for grok driven over ``grok agent stdio``.

Grok auto-executes tools over ACP (it never sends ``session/request_permission``
to the client), so :class:`omnigent.inner.acp_executor.AcpExecutor`'s normal
policy path never sees them. Grok DOES honor a configured ``PreToolUse`` hook
that can block a tool with a ``deny`` decision. This module provisions that hook
for a grok session and bridges it back to the executor's in-process policy.

Shape:

- A throwaway ``GROK_HOME`` (grok's config dir, set via the subprocess env) that
  carries a copy of the real ``auth.json`` (so grok stays authenticated) plus a
  ``hooks/`` dir with one unmatched ``PreToolUse`` hook — it fires for EVERY
  tool call.
- A loopback HTTP server (``127.0.0.1:<ephemeral>``) whose ``/evaluate`` endpoint
  runs the executor's ``_decide_permission`` (Omnigent's TOOL_CALL policy +
  elicitation) on the executor's event loop and answers allow/deny.
- The hook (:mod:`omnigent.grok_acp_hook`) POSTs each pending tool call to that
  endpoint and emits grok's decision. It fails closed (deny) on any error.

Only a real ``grok`` command gets this — see ``AcpExecutor`` gate wiring — so no
other ACP agent's behavior changes.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import shutil
import sys
import tempfile
import threading
from collections.abc import Awaitable, Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# The env var the hook reads to find the loopback gate (see grok_acp_hook.py).
GATE_URL_ENV = "OMNIGENT_GROK_GATE_URL"

# Decider: given a synthesized session/request_permission-shaped params dict,
# return True to allow the tool, False to deny. This is AcpExecutor._decide_permission.
Decider = Callable[[dict[str, Any]], Awaitable[bool]]


class GrokAcpGate:
    """Owns a grok session's throwaway GROK_HOME + loopback policy bridge."""

    def __init__(self, decide: Decider, loop: asyncio.AbstractEventLoop) -> None:
        """
        :param decide: the executor's ``_decide_permission`` coroutine.
        :param loop: the executor's running event loop (the decider runs on it).
        """
        self._decide = decide
        self._loop = loop
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._home: Path | None = None

    @property
    def grok_home(self) -> str:
        """The provisioned ``GROK_HOME`` path (only valid after :meth:`start`)."""
        assert self._home is not None, "GrokAcpGate.start() not called"
        return str(self._home)

    def start(self, real_grok_home: Path | None = None) -> None:
        """Provision the GROK_HOME + hook and start the loopback gate server.

        :param real_grok_home: source of ``auth.json`` (defaults to ``~/.grok``).
            Its ``auth.json`` (and ``config.toml`` if present) are copied so the
            gated grok stays authenticated.
        """
        self._start_server()
        assert self._server is not None
        host, port = self._server.server_address[0], self._server.server_address[1]
        gate_url = f"http://{host}:{port}/evaluate"

        home = Path(tempfile.mkdtemp(prefix="omnigent-grok-gate-"))
        src = real_grok_home or (Path.home() / ".grok")
        for name in ("auth.json", "config.toml"):
            s = src / name
            if s.exists():
                shutil.copy2(s, home / name)

        hooks = home / "hooks"
        hooks.mkdir(parents=True, exist_ok=True)
        # One PreToolUse hook, no matcher -> fires for every tool. It runs this
        # interpreter's grok_acp_hook module and is handed the loopback URL.
        hook_config = {
            "hooks": {
                "PreToolUse": [
                    {
                        "hooks": [
                            {
                                "type": "command",
                                "command": f'"{sys.executable}" -m omnigent.grok_acp_hook',
                                "timeout": 60,
                                "env": {GATE_URL_ENV: gate_url},
                            }
                        ]
                    }
                ]
            }
        }
        (hooks / "omnigent-gate.json").write_text(json.dumps(hook_config, indent=2))
        self._home = home
        logger.info("grok gate provisioned: GROK_HOME=%s gate=%s", home, gate_url)

    def _start_server(self) -> None:
        decide = self._decide
        loop = self._loop

        class _Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args: Any) -> None:  # silence default logging
                return

            def do_POST(self) -> None:
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    raw = self.rfile.read(length) if length else b"{}"
                    payload = json.loads(raw.decode("utf-8") or "{}")
                    params = _payload_to_permission_params(payload)
                    fut = asyncio.run_coroutine_threadsafe(decide(params), loop)
                    allow = bool(fut.result(timeout=120))
                    decision = "allow" if allow else "deny"
                except Exception as exc:  # noqa: BLE001 — bridge must fail closed
                    logger.warning("grok gate evaluation error (deny): %s", exc)
                    decision = "deny"
                body = json.dumps({"decision": decision}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def close(self) -> None:
        """Stop the gate server and remove the throwaway GROK_HOME."""
        if self._server is not None:
            with contextlib.suppress(Exception):
                self._server.shutdown()
                self._server.server_close()
            self._server = None
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
        if self._home is not None:
            with contextlib.suppress(Exception):
                shutil.rmtree(self._home, ignore_errors=True)
            self._home = None


def _payload_to_permission_params(payload: dict[str, Any]) -> dict[str, Any]:
    """Map grok's PreToolUse envelope to a session/request_permission params dict.

    Grok sends ``{toolName, toolInput, ...}``; ``AcpExecutor._extract_tool_call``
    reads ``params["toolCall"]{title, rawInput}``. Bridge the two.
    """
    tool_name = payload.get("toolName") or payload.get("tool_name") or "tool"
    tool_input = payload.get("toolInput") or payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        tool_input = {"value": tool_input}
    return {"toolCall": {"title": str(tool_name), "rawInput": tool_input}, "options": []}
