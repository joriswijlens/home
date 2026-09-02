"""Where work comes from, and where the outcome goes back to.

A `TaskProvider` is an `EventSource` plus two things a plain trigger source does not
have: it can *claim* work (so a second worker leaves it alone) and it can *report* the
outcome back to the system the work came from. GitHub and Jira are providers; cron and
the HA webhook are only sources — nothing external is waiting to hear how it went.

Everything provider-shaped lives behind this: API calls, labels, branch and PR handling.
A flow never learns which system its work came from.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from minion.events import EventDispatcher, EventSource

logger = logging.getLogger(__name__)


@dataclass
class Task:
    """A unit of work, identified the same way across restarts and machines."""

    id: str
    flow: str
    ref: str
    title: str
    payload: dict = field(default_factory=dict)


class TaskProvider(EventSource, ABC):
    name: str

    @abstractmethod
    async def claim(self, task: Task) -> bool:
        """Take ownership. False means another worker got there first.

        Must be atomic against other workers, since the local event log is not shared
        between machines — the provider is the only state they both see.
        """

    @abstractmethod
    async def context(self, task: Task) -> dict | None:
        """Everything the flow needs to do the work. None if the task is not workable."""

    @abstractmethod
    async def report(self, task: Task, outcome: str, payload: dict) -> None:
        """Render the outcome back to the provider — comment, labels, PR, transition."""

    @abstractmethod
    async def release(self, task: Task) -> None:
        """Hand the task back so it can be picked up again after a failure."""


class PollingProvider(TaskProvider, ABC):
    """Base for providers that have to be asked, rather than telling us.

    Pushing is preferable — a webhook costs nothing while idle and reacts immediately.
    It needs the source to be able to reach us, which holds for anything inside the
    network (Home Assistant, a self-hosted Vikunja, a file watcher) but not for GitHub
    or Jira, since nothing here is exposed to the internet. Those get polled; the
    interface does not care either way.
    """

    poll_interval: int = 60

    def __init__(self) -> None:
        self._running = False

    @abstractmethod
    async def poll(self, dispatcher: EventDispatcher) -> None:
        """Look for work once."""

    async def start(self, dispatcher: EventDispatcher) -> None:
        self._running = True
        logger.info("%s polling every %ds", self.name, self.poll_interval)
        while self._running:
            try:
                await self.poll(dispatcher)
            except Exception:
                logger.exception("%s poll failed", self.name)
            await asyncio.sleep(self.poll_interval)

    async def stop(self) -> None:
        self._running = False
