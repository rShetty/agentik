"""Agent lifecycle state machine.

Valid transitions
-----------------
idle     → running   (start)
running  → paused    (pause)
running  → stopped   (stop)
paused   → running   (resume)
paused   → stopped   (stop)
stopped  → idle      (reset — admin only)

Any other transition raises ``InvalidTransitionError``.
"""
from __future__ import annotations

from typing import Final

from app.runtime.exceptions import InvalidTransitionError

# State constants
IDLE: Final = "idle"
RUNNING: Final = "running"
PAUSED: Final = "paused"
STOPPED: Final = "stopped"
DEACTIVATED: Final = "deactivated"

# (from_state, action) → to_state
_TRANSITIONS: dict[tuple[str, str], str] = {
    (IDLE, "start"): RUNNING,
    (RUNNING, "pause"): PAUSED,
    (RUNNING, "stop"): STOPPED,
    (PAUSED, "resume"): RUNNING,
    (PAUSED, "stop"): STOPPED,
    (STOPPED, "reset"): IDLE,
}


def next_state(current: str, action: str) -> str:
    """Return the next lifecycle state for *action* from *current*.

    Raises :class:`InvalidTransitionError` for illegal transitions.
    """
    key = (current, action)
    if key not in _TRANSITIONS:
        valid = [act for (st, act) in _TRANSITIONS if st == current]
        raise InvalidTransitionError(
            f"Cannot '{action}' from state '{current}'. "
            f"Valid actions from '{current}': {valid or ['none']}"
        )
    return _TRANSITIONS[key]


def can_start(current: str) -> bool:
    """Return True if the agent may accept a new run in its current state."""
    return current == IDLE


def is_accepting_runs(current: str) -> bool:
    """Return True if scheduled runs should be dispatched."""
    return current not in (PAUSED, STOPPED, DEACTIVATED)
