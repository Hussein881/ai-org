"""Task state machine (ARCH §State machine). Pure; the API and workers call `check`."""

from enum import StrEnum


class TaskStatus(StrEnum):
    DRAFT = "draft"
    READY = "ready"
    RUNNING = "running"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    AWAITING_APPROVAL = "awaiting_approval"
    AWAITING_INFO = "awaiting_info"
    FAILED_QA = "failed_qa"
    FAILED_EXECUTION = "failed_execution"
    CANCELLED = "cancelled"


S = TaskStatus
TRANSITIONS: dict[TaskStatus, frozenset[TaskStatus]] = {
    S.DRAFT: frozenset({S.READY, S.CANCELLED}),
    S.READY: frozenset({S.RUNNING, S.BLOCKED, S.AWAITING_APPROVAL, S.CANCELLED}),
    S.RUNNING: frozenset(
        {S.VERIFYING, S.AWAITING_INFO, S.BLOCKED, S.FAILED_EXECUTION, S.READY, S.CANCELLED}
    ),
    S.VERIFYING: frozenset({S.COMPLETED, S.FAILED_QA, S.CANCELLED}),
    S.AWAITING_INFO: frozenset({S.READY, S.CANCELLED}),
    S.AWAITING_APPROVAL: frozenset({S.READY, S.CANCELLED}),
    S.BLOCKED: frozenset({S.READY, S.CANCELLED}),
    S.FAILED_QA: frozenset({S.READY, S.CANCELLED}),
    S.FAILED_EXECUTION: frozenset({S.READY, S.CANCELLED}),
    S.COMPLETED: frozenset(),
    S.CANCELLED: frozenset(),
}


class InvalidTransitionError(ValueError):
    pass


def check(current: str, target: str, *, has_check_record: bool = False) -> TaskStatus:
    """Validate a transition and return the target status, or raise InvalidTransitionError."""
    try:
        cur, tgt = TaskStatus(current), TaskStatus(target)
    except ValueError as e:
        raise InvalidTransitionError(f"unknown status: {e}") from None
    if tgt not in TRANSITIONS[cur]:
        raise InvalidTransitionError(f"cannot move a task from {cur} to {tgt}")
    if tgt is S.COMPLETED and not has_check_record:
        raise InvalidTransitionError("completion requires a QA or deterministic check record")
    return tgt
