"""State derived from the event log.

Pure functions over a list of events — no status is ever stored. Everything here
takes the events as an argument so the interesting cases (a claim gone stale, a
task that failed twice) can be tested with literal dicts and no database.
"""

from datetime import datetime, timedelta, timezone

CLAIMED = "claimed"
COMPLETED = "completed"
FAILED = "failed"
RELEASED = "released"

TERMINAL = {COMPLETED, FAILED, RELEASED}


def _parse(timestamp: str) -> datetime:
    return datetime.fromisoformat(timestamp)


def claim_state(events: list[dict], now: datetime | None = None,
                stale_after: timedelta = timedelta(minutes=30)) -> str | None:
    """Agent holding a live claim, or None.

    A claim ends when a terminal event follows it, or when it goes stale — an agent
    that dies mid-run would otherwise leave the task claimed forever, and every later
    poll would silently skip it.
    """
    now = now or datetime.now(timezone.utc)

    last_claim: dict | None = None
    for event in events:
        if event["type"] == CLAIMED:
            last_claim = event
        elif event["type"] in TERMINAL:
            last_claim = None

    if last_claim is None:
        return None
    if now - _parse(last_claim["timestamp"]) > stale_after:
        return None
    return last_claim["agent"]


def is_claimed(events: list[dict], now: datetime | None = None,
               stale_after: timedelta = timedelta(minutes=30)) -> bool:
    return claim_state(events, now, stale_after) is not None


def is_completed(events: list[dict]) -> bool:
    return any(event["type"] == COMPLETED for event in events)


def attempts(events: list[dict]) -> int:
    """Number of times a run has been started for this task."""
    return sum(1 for event in events if event["type"] == CLAIMED)


def last_attempt_failed(events: list[dict]) -> bool:
    for event in reversed(events):
        if event["type"] in TERMINAL:
            return event["type"] == FAILED
    return False


def has_event(events: list[dict], type: str) -> bool:
    return any(event["type"] == type for event in events)


def tokens_used(events: list[dict]) -> int:
    """Total tokens recorded across events — the basis for a spend ceiling."""
    total = 0
    for event in events:
        usage = event["payload"].get("usage")
        if usage:
            total += sum(int(v or 0) for v in usage.values())
    return total


def stale_claims(last_events: list[dict], now: datetime | None = None,
                 stale_after: timedelta = timedelta(minutes=30)) -> list[dict]:
    """Claims with nothing after them, old enough to count as abandoned.

    These are runs whose worker died — the label is still marked in progress while
    nothing is working on it, so it has to be handed back explicitly.
    """
    now = now or datetime.now(timezone.utc)
    return [
        event
        for event in last_events
        if event["type"] == CLAIMED
        and now - _parse(event["timestamp"]) > stale_after
    ]


def should_pick_up(events: list[dict], max_attempts: int = 3,
                   now: datetime | None = None,
                   stale_after: timedelta = timedelta(minutes=30)) -> bool:
    """Whether a trigger for this task should start a run.

    Bounded retries matter for cost as much as correctness: without them a task that
    fails every time is retried on every poll, and each retry is a paid model run.
    """
    if is_completed(events):
        return False
    if is_claimed(events, now, stale_after):
        return False
    return attempts(events) < max_attempts
