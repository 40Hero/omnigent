"""Grok PreToolUse hook that gates tool calls through Omnigent's policy.

Grok Build (over ``grok agent stdio``) does not surface tool calls to the ACP
client as ``session/request_permission`` — it auto-executes them. But grok DOES
honor a configured ``PreToolUse`` hook that can block a tool with a ``deny``
decision (verified live). :class:`omnigent.inner.acp_executor.AcpExecutor`
provisions a per-session grok ``GROK_HOME`` whose ``PreToolUse`` hook runs a COPY
of this module for every tool call.

**Self-contained on purpose.** This module imports only the stdlib. The gate
copies it into ``GROK_HOME`` and invokes it by ABSOLUTE PATH — never
``-m omnigent.grok_acp_hook`` — so a malicious repo cannot shadow it via cwd
module resolution, and it does not need the ``omnigent`` package on the path
(so it can run inside a confined sandbox that excludes site-packages).

It reads grok's event envelope from stdin, POSTs it to the executor's in-process
loopback gate (URL + token in the env the gate sets), and emits grok's allow/deny
decision on stdout. The gate endpoint calls the executor's ``_decide_permission``.

**Fail closed.** A gate on a coding agent's tool egress that fails open is worse
than no gate. Any error here — missing URL, unreachable gate, malformed reply,
timeout, a stdin that never closes — emits an explicit ``deny``. Only a clean
``allow`` from the gate lets the tool run.
"""

from __future__ import annotations

import json
import os
import signal
import sys
import urllib.error
import urllib.request

# Env vars the gate sets in the hook's `env` (see omnigent.grok_acp_gate).
_GATE_URL_ENV = "OMNIGENT_GROK_GATE_URL"
_GATE_TOKEN_ENV = "OMNIGENT_GROK_GATE_TOKEN"

# HTTP deadline for the policy round trip. Kept comfortably below grok's own
# PreToolUse hook timeout (60s) so a slow/blocked decider makes THIS process
# emit `deny` and exit before grok kills the hook (which would fail open).
_HTTP_TIMEOUT_S = 30.0
# Hard ceiling on the whole hook, including the stdin read (grok normally
# writes-then-closes, but a stuck stdin must not outlive grok's 60s kill).
_WALL_DEADLINE_S = 40


def _deny(reason: str) -> None:
    """Emit an explicit deny decision and exit. This is the fail-closed path."""
    print(json.dumps({"decision": "deny", "reason": reason}))
    # Exit 0: grok honors the stdout `deny` regardless of exit code, and a
    # non-zero "hook failure" would fail OPEN. We own the decision explicitly.
    sys.exit(0)


def _allow() -> None:
    print(json.dumps({"decision": "allow"}))
    sys.exit(0)


def _install_deadline() -> None:
    """Fail closed if the whole hook (incl. a stuck stdin) runs too long."""
    if not hasattr(signal, "SIGALRM"):  # non-Unix; grok targets Unix
        return

    def _on_alarm(_signum: int, _frame: object) -> None:
        _deny("hook deadline exceeded")

    signal.signal(signal.SIGALRM, _on_alarm)
    signal.alarm(_WALL_DEADLINE_S)


def main() -> None:
    _install_deadline()

    url = os.environ.get(_GATE_URL_ENV, "").strip()
    if not url:
        _deny("omnigent gate URL not configured")
    token = os.environ.get(_GATE_TOKEN_ENV, "")

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
            headers={"Content-Type": "application/json", "X-Omnigent-Gate-Token": token},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT_S) as resp:
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
