"""Knowledge object lifecycle state machine.

The canonical path (epistemic maturity) is::

    idea -> question -> hypothesis -> researching -> experiment -> observed
        -> validating -> validated -> implemented -> production

Additionally, the terminal / cross-cutting states::

    contradicted, rejected, deprecated, superseded

are reachable from any of the active middle states
(:data:`TERMINAL_FROM_STATES`)::

    hypothesis, researching, experiment, observed, validating, validated

Special states:

- ``unknown`` (the default for newly ingested objects) may be classified into
  any happy-path state — classification is not itself a maturity claim.
- Terminal states have no outgoing transitions: a contradicted or rejected
  object is never "re-promoted" by a transition. If new evidence appears,
  a new knowledge object is created referencing the old one (provenance is
  immutable; history is not rewritten).

Rules enforced by :func:`validate_transition`:

1. Both states must be known lifecycle states.
2. The edge must exist in :data:`LIFECYCLE_TRANSITIONS`.
3. Self-transitions are rejected (they carry no information and would flood
   the audit log).
4. Entering ``validated``, ``implemented`` or ``production`` requires a human
   actor: an actor of ``"auto"`` (or any identity in :data:`AUTOMATED_ACTORS`)
   is rejected even though the state-machine edge exists.

Every accepted transition MUST be recorded in ``audit_log`` by the caller
(the API layer does this via :func:`mkc.api.app.audit`); rejected
transitions raise :class:`InvalidTransition` and the API layer answers 409
with the list of allowed next states.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from mkc.core.constants import LIFECYCLE_STATES

logger = logging.getLogger(__name__)

#: The canonical happy path, in order.
HAPPY_PATH: tuple[str, ...] = (
    "idea",
    "question",
    "hypothesis",
    "researching",
    "experiment",
    "observed",
    "validating",
    "validated",
    "implemented",
    "production",
)

#: States from which the terminal exits are permitted.
TERMINAL_FROM_STATES: frozenset[str] = frozenset(
    {"hypothesis", "researching", "experiment", "observed", "validating", "validated"}
)

#: Terminal / cross-cutting states (no outgoing transitions).
TERMINAL_STATES: frozenset[str] = frozenset({"contradicted", "rejected", "deprecated", "superseded"})

#: States that can only be entered by a human actor (never "auto").
HUMAN_REQUIRED_STATES: frozenset[str] = frozenset({"validated", "implemented", "production"})

#: Actors that count as automated for the human-required check.
AUTOMATED_ACTORS: frozenset[str] = frozenset({"auto", "bot", "system", "pipeline", "ingest"})


def _build_transitions() -> dict[str, frozenset[str]]:
    transitions: dict[str, frozenset[str]] = {}
    for i, state in enumerate(HAPPY_PATH):
        if i + 1 < len(HAPPY_PATH):
            transitions[state] = frozenset({HAPPY_PATH[i + 1]})
        else:
            transitions[state] = frozenset()
    for state in TERMINAL_FROM_STATES:
        transitions[state] = transitions[state] | TERMINAL_STATES
    # unclassified objects may be classified into any happy-path state
    transitions["unknown"] = frozenset(HAPPY_PATH)
    # terminal states are sinks
    for state in TERMINAL_STATES:
        transitions[state] = frozenset()
    return transitions


#: Allowed transitions: current state -> set of states it may move to.
LIFECYCLE_TRANSITIONS: dict[str, frozenset[str]] = _build_transitions()


class InvalidTransition(Exception):
    """Raised when a lifecycle transition is not permitted.

    Carries the list of allowed next states so the API layer can return a
    useful 409 body instead of a bare error message.
    """

    def __init__(self, from_state: str, to_state: str, reason: str, allowed: list[str]) -> None:
        self.from_state = from_state
        self.to_state = to_state
        self.reason = reason
        self.allowed = allowed
        super().__init__(f"Invalid lifecycle transition {from_state!r} -> {to_state!r}: {reason}")


@dataclass(frozen=True)
class TransitionResult:
    """Outcome of :func:`validate_transition`."""

    allowed: bool
    reason: str = ""
    allowed_next_states: tuple[str, ...] = field(default_factory=tuple)


def allowed_next_states(from_state: str) -> list[str]:
    """Sorted list of states reachable from ``from_state`` ([] if terminal)."""
    if from_state not in LIFECYCLE_STATES:
        return []
    return sorted(LIFECYCLE_TRANSITIONS.get(from_state, frozenset()))


def is_human_actor(actor: str) -> bool:
    """True when ``actor`` is not one of the known automated identities."""
    return actor.strip().lower() not in AUTOMATED_ACTORS


def can_transition(from_state: str, to_state: str, actor: str = "auto") -> bool:
    """Non-raising check used by clients/UIs; mirrors :func:`validate_transition`."""
    return validate_transition(from_state, to_state, actor).allowed


def validate_transition(from_state: str, to_state: str, actor: str = "human") -> TransitionResult:
    """Validate a lifecycle transition and return a structured result.

    Does not raise; use :func:`enforce_transition` for the raising variant.
    The ``actor`` matters: entering :data:`HUMAN_REQUIRED_STATES` with an
    automated actor is denied even though the state-machine edge exists.
    """
    next_states = allowed_next_states(from_state)
    if from_state not in LIFECYCLE_STATES:
        return TransitionResult(False, f"unknown from-state {from_state!r}", ())
    if to_state not in LIFECYCLE_STATES:
        return TransitionResult(False, f"unknown to-state {to_state!r}", tuple(next_states))
    if to_state == from_state:
        return TransitionResult(False, "state unchanged (self-transitions are rejected)", tuple(next_states))
    if to_state not in LIFECYCLE_TRANSITIONS.get(from_state, frozenset()):
        return TransitionResult(
            False,
            f"transition {from_state!r} -> {to_state!r} is not in the allowed lifecycle path",
            tuple(next_states),
        )
    if to_state in HUMAN_REQUIRED_STATES and not is_human_actor(actor):
        return TransitionResult(
            False,
            f"state {to_state!r} requires a human actor (got automated actor {actor!r})",
            tuple(next_states),
        )
    return TransitionResult(True, "ok", tuple(next_states))


def enforce_transition(from_state: str, to_state: str, actor: str = "human") -> None:
    """Validate or raise :class:`InvalidTransition` (API layer maps to 409)."""
    result = validate_transition(from_state, to_state, actor)
    if not result.allowed:
        raise InvalidTransition(from_state, to_state, result.reason, list(result.allowed_next_states))
    logger.info("lifecycle transition %s -> %s by actor=%s", from_state, to_state, actor)
