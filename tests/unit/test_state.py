import pytest

from app.core.state import TRANSITIONS, InvalidTransitionError, TaskStatus, check


def test_happy_path():
    assert check("draft", "ready") == TaskStatus.READY
    assert check("ready", "running") == TaskStatus.RUNNING
    assert check("running", "verifying") == TaskStatus.VERIFYING
    assert check("verifying", "completed", has_check_record=True) == TaskStatus.COMPLETED


def test_awaiting_info_round_trip():
    assert check("running", "awaiting_info") == TaskStatus.AWAITING_INFO
    assert check("awaiting_info", "ready") == TaskStatus.READY


@pytest.mark.parametrize(
    ("cur", "tgt"),
    [("draft", "running"), ("ready", "completed"), ("completed", "ready"), ("cancelled", "ready")],
)
def test_invalid_rejected(cur, tgt):
    with pytest.raises(InvalidTransitionError):
        check(cur, tgt, has_check_record=True)


def test_completion_needs_check_record():
    with pytest.raises(InvalidTransitionError, match="check record"):
        check("verifying", "completed")


def test_unknown_status():
    with pytest.raises(InvalidTransitionError):
        check("ready", "nonsense")


def test_every_status_has_a_row_and_terminals_are_closed():
    assert set(TRANSITIONS) == set(TaskStatus)
    assert not TRANSITIONS[TaskStatus.COMPLETED] and not TRANSITIONS[TaskStatus.CANCELLED]
