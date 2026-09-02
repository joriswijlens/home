"""Push sources: one endpoint, one mapper per sender.

A pushing source needs no loop, no interval and no polling credentials — just a route
that turns a POST into an `Event`. Adding one (Home Assistant, a self-hosted Vikunja,
anything that can do an HTTP callback) is a mapper function, not a class.

The endpoint answers immediately. A run takes minutes and the sender must not wait for
it — Home Assistant would time out and retry, which is how one trigger becomes three.
"""

import asyncio
import logging
from typing import Callable

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from minion.events import Event, EventDispatcher, EventSource
from minion.store import EventStore

logger = logging.getLogger(__name__)

# A mapper turns a received payload into an event, or None to ignore it.
Mapper = Callable[[dict], Event | None]


class WebhookSource(EventSource):
    def __init__(self, name: str, mapper: Mapper, store: EventStore) -> None:
        self.name = name
        self._mapper = mapper
        self._store = store
        self._tasks: set[asyncio.Task] = set()

    def register(self, app: FastAPI, dispatcher: EventDispatcher) -> None:
        @app.post(f"/hooks/{self.name}")
        async def receive(request: Request) -> JSONResponse:
            try:
                payload = await request.json()
            except Exception:
                return JSONResponse({"error": "expected JSON"}, status_code=400)

            event = self._mapper(payload)
            if event is None:
                logger.info("%s webhook ignored a payload", self.name)
                return JSONResponse({"accepted": False}, status_code=202)

            # Record that the request arrived: for a source with no external system
            # behind it, this is the only trace that anything was ever asked for.
            task_id = event.payload.get("task_id", f"{self.name}-{event.timestamp}")
            self._store.append(task_id, "trigger_received", {"source": self.name})

            self._spawn(dispatcher.dispatch(event))
            return JSONResponse({"accepted": True}, status_code=202)

    def _spawn(self, coro) -> None:
        task = asyncio.create_task(coro)
        # Hold a reference, or the loop may collect the task mid-run.
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def start(self, dispatcher: EventDispatcher) -> None:
        """Nothing to do — the route does the work when someone calls it."""
        logger.info("Webhook source ready at /hooks/%s", self.name)

    async def stop(self) -> None:
        for task in list(self._tasks):
            task.cancel()
