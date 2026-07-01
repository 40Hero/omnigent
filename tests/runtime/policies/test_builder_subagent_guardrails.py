"""Tests that a sub-agent session is governed by its OWN guardrails.

Regression coverage for the nested-sub-agent guardrail gap: when a
parent delegates to a named sub-agent (an inline ``sub_agents`` entry
sharing the parent's ``agent_id``), the policy engine built for the
child session must resolve the sub-agent's own ``guardrails:`` block —
not silently fall back to the parent's top-level guardrails.

Root-conversation *session* policies (set via ``sys_add_policy``) still
inherit downward; that inheritance is covered in
``test_builder_session_policies``. This file covers the orthogonal
concern: the sub-agent's *spec-declared* guardrails.
"""

from __future__ import annotations

from omnigent.runtime.policies.builder import build_policy_engine
from omnigent.spec.types import (
    AgentSpec,
    FunctionPolicySpec,
    FunctionRef,
    GuardrailsSpec,
)
from omnigent.stores.conversation_store.sqlalchemy_store import (
    SqlAlchemyConversationStore,
)

_HANDLER = "tests.resources.examples._shared.tool_functions.block_long_sleep"


def _policy(name: str) -> FunctionPolicySpec:
    """A minimal always-loadable function policy spec named ``name``."""
    return FunctionPolicySpec(name=name, on=None, function=FunctionRef(path=_HANDLER))


def _spec_with_subagent() -> AgentSpec:
    """Parent spec whose top-level guardrails differ from its sub-agent's.

    Top-level declares ``parent_guard``; the ``worker`` sub-agent
    declares its own ``worker_guard``.
    """
    worker = AgentSpec(
        spec_version=1,
        name="worker",
        guardrails=GuardrailsSpec(policies=[_policy("worker_guard")]),
    )
    return AgentSpec(
        spec_version=1,
        name="orchestrator",
        guardrails=GuardrailsSpec(policies=[_policy("parent_guard")]),
        sub_agents=[worker],
    )


def test_subagent_session_uses_own_guardrails(db_uri: str) -> None:
    """A ``sub_agent`` session resolves the sub-agent's declared guardrails.

    The engine for a child session bound to ``sub_agent_name="worker"``
    must include the sub-agent's ``worker_guard`` and must NOT inherit
    the parent's top-level ``parent_guard``.

    :param db_uri: Per-test SQLite URI.
    """
    conv_store = SqlAlchemyConversationStore(db_uri)
    root_conv = conv_store.create_conversation()
    child_conv = conv_store.create_conversation(
        parent_conversation_id=root_conv.id,
        kind="sub_agent",
        sub_agent_name="worker",
    )

    engine = build_policy_engine(
        spec=_spec_with_subagent(),
        conversation_id=child_conv.id,
        conversation_store=conv_store,
    )

    names = [p.spec.name for p in engine.policies]
    assert "worker_guard" in names, f"sub-agent's own guardrails not resolved; got {names}"
    assert "parent_guard" not in names, (
        f"sub-agent wrongly inherited the parent's top-level guardrails; got {names}"
    )


def test_top_level_session_still_uses_top_level_guardrails(db_uri: str) -> None:
    """A normal (non-sub-agent) session keeps the top-level guardrails.

    Guards against the fix over-reaching: a session with no
    ``sub_agent_name`` must still resolve ``parent_guard`` and must not
    pick up any sub-agent policy.

    :param db_uri: Per-test SQLite URI.
    """
    conv_store = SqlAlchemyConversationStore(db_uri)
    conv = conv_store.create_conversation()

    engine = build_policy_engine(
        spec=_spec_with_subagent(),
        conversation_id=conv.id,
        conversation_store=conv_store,
    )

    names = [p.spec.name for p in engine.policies]
    assert "parent_guard" in names, f"top-level guardrails dropped; got {names}"
    assert "worker_guard" not in names, (
        f"top-level session wrongly picked up a sub-agent policy; got {names}"
    )
