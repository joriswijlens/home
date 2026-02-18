import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


@dataclass
class Event:
    type: str
    source: str
    payload: dict
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class EventHandler(ABC):
    event_types: list[str]

    @abstractmethod
    async def handle(self, event: Event) -> str | None: ...


class EventDispatcher:
    def __init__(self) -> None:
        self._handlers: list[EventHandler] = []

    def register(self, handler: EventHandler) -> None:
        logger.info(
            "Registered handler %s for events: %s",
            handler.__class__.__name__,
            handler.event_types,
        )
        self._handlers.append(handler)

    async def dispatch(self, event: Event) -> str | None:
        for handler in self._handlers:
            if event.type in handler.event_types:
                logger.debug(
                    "Dispatching %s event to %s",
                    event.type,
                    handler.__class__.__name__,
                )
                return await handler.handle(event)
        logger.warning("No handler for event type: %s", event.type)
        return None


class EventSource(ABC):
    @abstractmethod
    async def start(self, dispatcher: EventDispatcher) -> None: ...

    @abstractmethod
    async def stop(self) -> None: ...
