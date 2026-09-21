"""Lifecycle state-machine tests (pure unit tests, no DB).

Source of truth: docs/KNOWLEDGE_MODEL.md section 2 (active chain, terminal
states, no skipping, absorbing terminals, per-transition audit) and the
``mkc.core.lifecycle`` docstring (``unknown`` classification, human gate).

Security note (T-P1, already tracked in docs/THREAT_MODEL.md): the human
gate checks a client-attested ``actor`` string, not the authenticated
identity. These tests pin the gate behaviour AS DOCUMENTED (automated
identities denied for human-required states, anything else accepted);
they are not the place for new expectations about actor identity.
"""

from __future__ import annotations

import pytest

from mkc.core.lifecycle import (
    AUTOMATED_ACTORS,
    HAPPY_PATH,
    HUMAN_REQUIRED_STATES,
    LIFECYCLE_TRANSITIONS,
    TERMINAL_FROM_STATES,
    TERMINAL_STATES,
    InvalidTransition,
    allowed_next_states,
    can_transition,
    enforce_transition,
    validate_transition,
)

HUMAN = "qa-human"

EXPECTED_TRANSITIONS: dict[str, frozenset[str]] = {}
for _i, _state in enumerate(HAPPY_PATH):
    _next = frozenset({HAPPY_PATH[_i + 1]}) if _i + 1 < len(HAPPY_PATH) else frozenset()
    if _state in TERMINAL_FROM_STATES:
        _next = _next | TERMINAL_STATES
    EXPECTED_TRANSITIONS[_state] = _next
EXPECTED_TRANSITIONS["unknown"] = frozenset(HAPPY_PATH)
for _state in TERMINAL_STATES:
    EXPECTED_TRANSITIONS[_state] = frozenset()

ALL_STATES = frozenset(EXPECTED_TRANSITIONS)

LEGAL_EDGES = [(f, t) for f, targets in EXPECTED_TRANSITIONS.items() for t in targets]

ILLEGAL_EDGES = [
    ("idea", "hypothesis"),
    ("idea", "production"),
    ("question", "experiment"),
    ("hypothesis", "validated"),
    ("hypothesis", "production"),
    ("researching", "hypothesis"),
    ("validated", "validating"),
    ("production", "validated"),
    ("contradicted", "idea"),
    ("rejected", "hypothesis"),
    ("deprecated", "production"),
    ("superseded", "idea"),
    ("unknown", "contradicted"),
    ("idea", "idea"),
    ("hypothesis", "hypothesis"),
    ("bogus", "idea"),
    ("idea", "bogus"),
]


def test_transition_matrix_matches_documented_edges() -> None:
    assert set(LIFECYCLE_TRANSITIONS) == ALL_STATES
    for state in ALL_STATES:
        assert LIFECYCLE_TRANSITIONS[state] == EXPECTED_TRANSITIONS[state], (
            f"edge set for {state!r} drifted from the documented lifecycle"
        )


@pytest.mark.parametrize(("from_state", "to_state"), LEGAL_EDGES, ids=lambda v: v or "n/a")
def test_legal_edges_are_allowed(from_state: str, to_state: str) -> None:
    actor = HUMAN if to_state in HUMAN_REQUIRED_STATES else "auto"
    result = validate_transition(from_state, to_state, actor=actor)
    assert result.allowed, f"{from_state} -> {to_state} should be legal (actor={actor})"
    enforce_transition(from_state, to_state, actor=actor)
    assert can_transition(from_state, to_state, actor=actor)


@pytest.mark.parametrize(("from_state", "to_state"), ILLEGAL_EDGES, ids=lambda v: v or "n/a")
def test_illegal_edges_raise_invalid_transition(from_state: str, to_state: str) -> None:
    with pytest.raises(InvalidTransition) as excinfo:
        enforce_transition(from_state, to_state, actor=HUMAN)
    err = excinfo.value
    assert err.from_state == from_state
    assert err.to_state == to_state
    assert not validate_transition(from_state, to_state, actor=HUMAN).allowed


def test_invalid_transition_carries_allowed_next_states() -> None:
    with pytest.raises(InvalidTransition) as excinfo:
        enforce_transition("hypothesis", "production", actor=HUMAN)
    assert sorted(excinfo.value.allowed) == sorted(allowed_next_states("hypothesis"))
    assert excinfo.value.reason


def test_can_transition_mirrors_validate_transition() -> None:
    assert can_transition("hypothesis", "validated", actor=HUMAN) is False
    assert can_transition("hypothesis", "researching", actor="auto") is True
    assert can_transition("validated", "implemented", actor="auto") is False
    assert can_transition("validated", "implemented", actor=HUMAN) is True


@pytest.mark.parametrize(
    ("from_state", "to_state"),
    [
        ("validating", "validated"),
        ("validated", "implemented"),
        ("implemented", "production"),
        ("unknown", "production"),
    ],
)
def test_human_required_states_accept_human_actor(from_state: str, to_state: str) -> None:
    for actor in (HUMAN, "alice", "Alice Chen", "ops"):
        result = validate_transition(from_state, to_state, actor=actor)
        assert result.allowed, f"{actor!r} should be treated as human for {to_state}"


@pytest.mark.parametrize("actor", sorted(AUTOMATED_ACTORS) + ["AUTO", " Auto ", "Pipeline"])
@pytest.mark.parametrize(
    ("from_state", "to_state"),
    [
        ("validating", "validated"),
        ("validated", "implemented"),
        ("implemented", "production"),
    ],
)
def test_automated_actor_rejected_for_human_required_states(
    from_state: str, to_state: str, actor: str
) -> None:
    result = validate_transition(from_state, to_state, actor=actor)
    assert not result.allowed
    assert "human" in result.reason
    with pytest.raises(InvalidTransition):
        enforce_transition(from_state, to_state, actor=actor)


@pytest.mark.parametrize("actor", sorted(AUTOMATED_ACTORS))
def test_automated_actor_allowed_below_human_gate(actor: str) -> None:
    assert validate_transition("idea", "question", actor=actor).allowed
    assert validate_transition("hypothesis", "researching", actor=actor).allowed
    assert validate_transition("unknown", "idea", actor=actor).allowed


def test_terminal_states_are_reachable() -> None:
    for target in ("contradicted", "rejected", "deprecated", "superseded"):
        result = validate_transition("hypothesis", target, actor="auto")
        assert result.allowed, f"hypothesis -> {target} must be reachable"
        enforce_transition("hypothesis", target, actor="auto")


def test_terminal_states_have_no_outgoing_transitions() -> None:
    for terminal in sorted(TERMINAL_STATES):
        assert allowed_next_states(terminal) == []
        for target in sorted(ALL_STATES - {terminal}):
            result = validate_transition(terminal, target, actor=HUMAN)
            assert not result.allowed, f"{terminal} is absorbing; {target} must be unreachable"


def test_unknown_classifies_into_any_happy_path_state() -> None:
    for target in HAPPY_PATH:
        actor = HUMAN if target in HUMAN_REQUIRED_STATES else "auto"
        assert validate_transition("unknown", target, actor=actor).allowed


def test_unknown_state_lists_all_happy_path_as_allowed() -> None:
    assert allowed_next_states("unknown") == sorted(HAPPY_PATH)
    assert allowed_next_states("not-a-state") == []


def test_validate_transition_reports_unknown_states() -> None:
    result = validate_transition("not-a-state", "idea", actor=HUMAN)
    assert not result.allowed and "unknown from-state" in result.reason
    result = validate_transition("idea", "not-a-state", actor=HUMAN)
    assert not result.allowed and "unknown to-state" in result.reason


def test_transition_is_audit_logged_by_api_layer() -> None:
    """KNOWLEDGE_MODEL: 'every transition is audit-logged'.

    The state machine itself never writes audit rows (documented: 'the API
    layer does this'); the API-level wiring is verified in test_api.py.
    This test pins that the module layer adds no audit side effect of its own,
    i.e. enforce_transition is pure.
    """
    enforce_transition("hypothesis", "researching", actor=HUMAN)
