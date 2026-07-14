"""Grok PreToolUse hook that gates tool calls through Omnigent's policy.

Grok Build (over ``grok agent stdio``) does not surface tool calls to the ACP
client as ``session/request_permission`` — it auto-executes them. But grok DOES
honor a configured ``PreToolUse`` hook that can block a tool with a ``deny``
decision (verified live). :class:`omnigent.inner.acp_executor.AcpExecutor`
provisions a per-session grok ``GROK_HOME`` whose ``PreToolUse`` hook runs THIS
module for every tool call.

The hook is a thin, dependency-free bridge: it reads grok's event envelope from
stdin, POSTs it to the executor's in-process loopback gate (URL in
``OMNIGENT_GROK_GATE_URL``), and emits grok's allow/deny decision on stdout. The
gate endpoint is where the real decision happens — it calls the executor's
``_decide_permission`` (Omnigent's TOOL_CALL policy + elicitation).

**Fail closed.** A gate on a coding agent's tool egress that fails open is worse
than no gate. Any error here — missing URL, unreachable gate, malformed reply,
timeout — emits an explicit ``deny`` so grok blocks the tool. Only a clean
``allow`` from the gate lets the tool run.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

# Env var the executor sets in the hook's `env` (see AcpExecutor gate provisioning).
_GATE_URL_ENV = "OMNIGENT_GROK_GATE_URL"
_TIMEOUT_S = 30.0


def _deny(reason: str) -> None:
    """Emit an explicit deny decision and exit. This is the fail-closed path."""
    print(json.dumps({"decision": "deny", "reason": reason}))
    # Exit 0: grok honors the stdout `deny` regardless of exit code, and a
    # non-zero "hook failure" would fail OPEN. We own the decision explicitly.
    sys.exit(0)


def _allow() -> None:
    print(json.dumps({"decision": "allow"}))
    sys.exit(0)


def main() -> None:
    url = os.environ.get(_GATE_URL_ENV, "").strip()
    if not url:
        _deny("omnigent gate URL not configured")

    raw = sys.stdin.read()
    # We forward grok's raw envelope; the gate does the tool extraction. If the
    # payload is unreadable we cannot evaluate it -> deny.
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except (ValueError, TypeError):
        _deny("unparseable tool payload")

    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as resp:
            body = resp.read().decode("utf-8")
        decision = json.loads(body).get("decision")
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
        _deny(f"omnigent gate unreachable: {exc}")

    if decision == "allow":
        _allow()
    # Anything that is not an explicit allow (deny, unknown, missing) -> deny.
    _deny("blocked by omnigent policy")


if __name__ == "__main__":
    main()
