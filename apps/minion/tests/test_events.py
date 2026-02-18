import pytest

from minion.events import Event, EventDispatcher, EventHandler


class FakeHandler(EventHandler):
    event_types = ["test_event"]

    def __init__(self) -> None:
        self.called_with: Event | None = None

    async def handle(self, event: Event) -> str | None:
        self.called_with = event
        return "handled"


async def test_dispatch_to_matching_handler() -> None:
    dispatcher = EventDispatcher()
    handler = FakeHandler()
    dispatcher.register(handler)

    event = Event(type="test_event", source="test", payload={"key": "value"})
    result = await dispatcher.dispatch(event)

    assert result == "handled"
    assert handler.called_with is event


async def test_dispatch_no_matching_handler() -> None:
    dispatcher = EventDispatcher()
    handler = FakeHandler()
    dispatcher.register(handler)

    event = Event(type="unknown_event", source="test", payload={})
    result = await dispatcher.dispatch(event)

    assert result is None
    assert handler.called_with is None
