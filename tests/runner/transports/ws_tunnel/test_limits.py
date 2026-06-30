"""Tests for the WS tunnel size limits + keepalive budget constants."""

from __future__ import annotations

from omnigent.runner.transports.ws_tunnel.limits import (
    RUNNER_TUNNEL_MAX_MESSAGE_BYTES,
    TUNNEL_KEEPALIVE_PING_INTERVAL_S,
    TUNNEL_KEEPALIVE_PING_TIMEOUT_S,
)


def test_max_message_bytes_is_100mb() -> None:
    """The tunnel message size limit matches the design spec: 100 MiB."""
    assert RUNNER_TUNNEL_MAX_MESSAGE_BYTES == 100 * 1024 * 1024


def test_max_message_bytes_is_positive_int() -> None:
    """The constant is a positive integer, not a float or zero."""
    assert isinstance(RUNNER_TUNNEL_MAX_MESSAGE_BYTES, int)
    assert RUNNER_TUNNEL_MAX_MESSAGE_BYTES > 0


def test_keepalive_constants_are_positive_floats() -> None:
    """Ping interval/timeout are positive floats (passed straight to websockets/uvicorn)."""
    assert isinstance(TUNNEL_KEEPALIVE_PING_INTERVAL_S, float)
    assert isinstance(TUNNEL_KEEPALIVE_PING_TIMEOUT_S, float)
    assert TUNNEL_KEEPALIVE_PING_INTERVAL_S > 0
    assert TUNNEL_KEEPALIVE_PING_TIMEOUT_S > 0


def test_keepalive_not_stricter_than_app_level_budget() -> None:
    """The protocol keepalive MUST NOT pre-empt the app-level liveness budget (#1116).

    The server's app-level ``_ping_loop`` declares a peer dead after
    ``PING_INTERVAL_S * PING_MISS_THRESHOLD`` seconds of silence. If the
    websockets/uvicorn protocol keepalive timeout is tighter than that, it drops a
    healthy-but-busy tunnel (event loop stalled) with ``1011`` before the
    deliberate app-level policy ever applies — the regression this guards. Checked
    against BOTH tunnels, which share the same budget.
    """
    from omnigent.server.routes import host_tunnel, runner_tunnel

    for module in (runner_tunnel, host_tunnel):
        app_level_dead_after_s = module.PING_INTERVAL_S * module.PING_MISS_THRESHOLD
        assert app_level_dead_after_s <= TUNNEL_KEEPALIVE_PING_TIMEOUT_S, (
            f"protocol ping_timeout ({TUNNEL_KEEPALIVE_PING_TIMEOUT_S}s) is stricter "
            f"than {module.__name__}'s {app_level_dead_after_s}s app-level budget; it "
            "would drop a busy-but-healthy tunnel with 1011 before the app-level "
            "keepalive fires (issue #1116)."
        )
