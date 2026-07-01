"""Tests for the OMNIGENT_DEFAULT_AGENTS packaged-seeder allowlist.

The env var lets a deployment trim which packaged default agents/harness
tiles (`claude`, `codex`, `pi`, …) get seeded at startup. Unset/empty
preserves the upstream behavior (seed all), so the gate is backward
compatible and safe to leave off.
"""

from __future__ import annotations

from omnigent.server.app import (
    _DEFAULT_AGENT_SEEDER_KEYS,
    _selected_default_agent_keys,
)


def test_none_means_all() -> None:
    """An unset env (None) returns None → caller seeds every default."""
    assert _selected_default_agent_keys(None) is None


def test_empty_and_whitespace_means_all() -> None:
    """An empty / whitespace value is treated as unset (seed all)."""
    assert _selected_default_agent_keys("") is None
    assert _selected_default_agent_keys("   ") is None
    assert _selected_default_agent_keys(" , , ") is None


def test_explicit_allowlist_is_parsed_and_normalized() -> None:
    """A comma list is split, trimmed, and lowercased."""
    assert _selected_default_agent_keys("claude,codex") == ["claude", "codex"]
    assert _selected_default_agent_keys("  Claude , CODEX ") == ["claude", "codex"]


def test_unknown_keys_are_dropped_not_kept() -> None:
    """Only recognized seeder keys survive; typos/unknowns are ignored.

    Prevents a misspelled entry (e.g. `claud`) from silently seeding
    nothing or, worse, being treated as a live key downstream.
    """
    assert _selected_default_agent_keys("claude,nope,codex") == ["claude", "codex"]
    assert _selected_default_agent_keys("bogus") == []


def test_seeder_keys_are_the_known_packaged_set() -> None:
    """Guard against drift: the key registry matches the packaged defaults."""
    assert _DEFAULT_AGENT_SEEDER_KEYS == (
        "claude",
        "codex",
        "pi",
        "opencode",
        "cursor",
        "kiro",
        "antigravity",
        "qwen",
        "kimi",
        "debby",
        "polly",
    )
