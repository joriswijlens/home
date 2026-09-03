from datetime import datetime, timedelta, timezone

from minion.state import (
    attempts,
    claim_state,
    is_claimed,
    is_completed,
    is_labeled,
    last_attempt_failed,
    should_pick_up,
)

NOW = datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc)


def event(type, minutes_ago=0, agent="venus"):
    return {
        "task_id": "task-1",
        "agent": agent,
        "type": type,
        "payload": {},
        "timestamp": (NOW - timedelta(minutes=minutes_ago)).isoformat(),
    }


def test_no_events_means_unclaimed():
    assert not is_claimed([], now=NOW)
    assert claim_state([], now=NOW) is None


def test_fresh_claim_is_held():
    assert claim_state([event("claimed", minutes_ago=5)], now=NOW) == "venus"


def test_claim_released_by_completion():
    events = [event("claimed", 10), event("completed", 2)]
    assert not is_claimed(events, now=NOW)


def test_claim_released_by_failure():
    events = [event("claimed", 10), event("failed", 2)]
    assert not is_claimed(events, now=NOW)


def test_stale_claim_is_not_held():
    """An agent that died mid-run must not leave the task claimed forever."""
    events = [event("claimed", minutes_ago=45)]
    assert not is_claimed(events, now=NOW, stale_after=timedelta(minutes=30))


def test_reclaim_after_failure_is_held_again():
    events = [event("claimed", 60), event("failed", 55), event("claimed", 1)]
    assert claim_state(events, now=NOW) == "venus"


def test_claim_state_reports_the_holding_agent():
    events = [event("claimed", 1, agent="jupiter")]
    assert claim_state(events, now=NOW) == "jupiter"


def test_attempts_counts_claims():
    events = [event("claimed", 60), event("failed", 58), event("claimed", 30)]
    assert attempts(events) == 2


def test_last_attempt_failed():
    assert last_attempt_failed([event("claimed", 10), event("failed", 5)])
    assert not last_attempt_failed([event("claimed", 10), event("completed", 5)])
    assert not last_attempt_failed([event("claimed", 10)])


def test_is_completed():
    assert is_completed([event("claimed", 10), event("completed", 5)])
    assert not is_completed([event("claimed", 10)])


def test_should_pick_up_fresh_task():
    assert should_pick_up([], now=NOW)


def test_should_not_pick_up_completed_task():
    events = [event("claimed", 10), event("completed", 5)]
    assert not should_pick_up(events, now=NOW)


def test_should_not_pick_up_claimed_task():
    assert not should_pick_up([event("claimed", 1)], now=NOW)


def test_should_pick_up_after_a_stale_claim():
    events = [event("claimed", 90)]
    assert should_pick_up(events, now=NOW, stale_after=timedelta(minutes=30))


def test_retries_are_bounded():
    """Without a cap, an always-failing task is retried on every poll — each one paid for."""
    events = []
    for i in range(3):
        events += [event("claimed", 60 - i * 10), event("failed", 59 - i * 10)]

    assert not should_pick_up(events, max_attempts=3, now=NOW)
    assert should_pick_up(events, max_attempts=4, now=NOW)


def test_not_labeled_with_no_events():
    assert not is_labeled([])


def test_labeled_once_stays_labeled():
    assert is_labeled([event("labeled", 5)])


def test_labeled_gate_closes_on_completion():
    """The poller must not observe it again while nothing has ended."""
    events = [event("labeled", 10), event("claimed", 8), event("completed", 2)]
    assert not is_labeled(events)


def test_labeled_gate_reopens_after_failure():
    """A retry-eligible task must be observable as labeled again."""
    events = [event("labeled", 30), event("claimed", 28), event("failed", 20)]
    assert not is_labeled(events)
