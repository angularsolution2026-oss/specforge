from __future__ import annotations

from dataclasses import dataclass

TASK_STATES = {
    "pending",
    "planned",
    "prompted",
    "running",
    "blocked",
    "failed",
    "passed",
    "reconciled",
}

VALID_TRANSITIONS = {
    "pending": {"planned"},
    "planned": {"prompted"},
    "prompted": {"running"},
    "running": {"passed", "failed", "blocked"},
    "passed": {"reconciled"},
    "blocked": {"planned"},
    "failed": {"planned"},
    "reconciled": set(),
}


@dataclass(frozen=True)
class FsmValidation:
    valid: bool
    from_state: str
    to_state: str
    message: str


def validate_transition(from_state: str, to_state: str) -> FsmValidation:
    if from_state not in TASK_STATES:
        return FsmValidation(False, from_state, to_state, f"Unknown source state: {from_state}")
    if to_state not in TASK_STATES:
        return FsmValidation(False, from_state, to_state, f"Unknown destination state: {to_state}")
    if to_state not in VALID_TRANSITIONS.get(from_state, set()):
        return FsmValidation(False, from_state, to_state, f"Invalid transition: {from_state} -> {to_state}")
    return FsmValidation(True, from_state, to_state, "ok")

