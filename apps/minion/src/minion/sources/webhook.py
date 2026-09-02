"""Push sources: one endpoint, one mapper per sender.

A pushing source needs no loop, no interval and no polling credentials — just a route
that turns a POST into an `Event`. Adding one (Home Assistant, Grafana, a self-hosted
Vikunja) is a mapper function, not a class.

The endpoint answers immediately. A run takes minutes and the sender must not wait for
it — Home Assistant would time out and retry, which is how one trigger becomes three.

## Security

A POST here starts an agent run: it spends money and executes shell, git and file
tools. That makes an unauthenticated endpoint a remote-code-execution hole with extra
steps, and "it's only on the LAN" is not a trust boundary — IoT devices, guest wifi and
anything already compromised sit on that same network. This is built to hold up when
the route is reachable from outside, not only from the LAN.

Every source needs its own secret, and a source without one refuses to register rather
than quietly serving an open route.

**Signature (default).** `X-Minion-Signature: sha256=<hmac>` over `timestamp.body`,
with `X-Minion-Timestamp`. The secret never travels, the body cannot be altered, and
binding the timestamp into the signature is what makes replay detectable — a captured
request stops working once it falls outside the skew window, and within that window a
seen-signature cache rejects the second use.

**Bearer (opt-in, LAN only).** `Authorization: Bearer <secret>` for senders that cannot
compute an HMAC, such as Home Assistant templates. The secret goes over the wire on
every request, so it is only as private as the link, and a captured request replays
forever. Off unless `allow_bearer=True`, and it should stay off for anything reachable
from outside.

Both are compared in constant time. Requests are rate limited per source, so a leaked
credential cannot drain the token budget in one burst. TLS is not this module's job —
put a reverse proxy in front if the route is exposed.
"""

import asyncio
import hashlib
import hmac
import logging
import time
from collections import deque
from typing import Callable

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from minion.events import Event, EventDispatcher, EventSource
from minion.store import EventStore

logger = logging.getLogger(__name__)

# A mapper turns a received payload into an event, or None to ignore it.
Mapper = Callable[[dict], Event | None]

# A trigger is a small JSON document. Anything larger is refused unread, so a big POST
# cannot exhaust memory on a 1GB Pi.
MAX_BODY_BYTES = 256 * 1024

# How far a signed timestamp may be from now. Wide enough for clock drift between
# machines, narrow enough that a captured request expires quickly.
MAX_SKEW_SECONDS = 300


class WebhookSource(EventSource):
    def __init__(
        self,
        name: str,
        mapper: Mapper,
        store: EventStore,
        secret: str,
        allow_bearer: bool = False,
        max_per_minute: int = 30,
    ) -> None:
        if not secret or len(secret) < 16:
            raise ValueError(
                f"Webhook source {name!r} needs a secret of at least 16 characters. "
                f"A POST to this route starts an agent run, so an open endpoint is "
                f"remote code execution — set webhooks.secrets.{name}."
            )
        self.name = name
        self._mapper = mapper
        self._store = store
        self._secret = secret.encode()
        self._allow_bearer = allow_bearer
        self._max_per_minute = max_per_minute
        self._recent: deque[float] = deque()
        self._seen: deque[tuple[float, str]] = deque()
        self._tasks: set[asyncio.Task] = set()

    def authenticate(
        self,
        body: bytes,
        signature: str | None,
        timestamp: str | None,
        authorization: str | None,
        now: float | None = None,
    ) -> bool:
        now = now if now is not None else time.time()

        if signature:
            if not timestamp:
                return False
            try:
                skew = abs(now - float(timestamp))
            except ValueError:
                return False
            if skew > MAX_SKEW_SECONDS:
                logger.warning("Rejected %s webhook: timestamp outside window", self.name)
                return False

            signed = f"{timestamp}.".encode() + body
            expected = hmac.new(self._secret, signed, hashlib.sha256).hexdigest()
            provided = signature.removeprefix("sha256=")
            if not hmac.compare_digest(expected, provided):
                return False

            if self._already_seen(expected, now):
                logger.warning("Rejected %s webhook: signature replayed", self.name)
                return False
            return True

        if self._allow_bearer and authorization and authorization.startswith("Bearer "):
            return hmac.compare_digest(
                self._secret, authorization.removeprefix("Bearer ").encode()
            )

        return False

    def _already_seen(self, signature: str, now: float) -> bool:
        """Reject a signature used twice inside the skew window."""
        while self._seen and now - self._seen[0][0] > MAX_SKEW_SECONDS:
            self._seen.popleft()
        if any(known == signature for _, known in self._seen):
            return True
        self._seen.append((now, signature))
        return False

    def _within_rate_limit(self, now: float | None = None) -> bool:
        """A leaked credential must not be able to drain the budget in one burst."""
        now = now if now is not None else time.time()
        while self._recent and now - self._recent[0] > 60:
            self._recent.popleft()
        if len(self._recent) >= self._max_per_minute:
            return False
        self._recent.append(now)
        return True

    def register(self, app: FastAPI, dispatcher: EventDispatcher) -> None:
        @app.post(f"/hooks/{self.name}")
        async def receive(request: Request) -> JSONResponse:
            body = await request.body()
            if len(body) > MAX_BODY_BYTES:
                return JSONResponse({"error": "payload too large"}, status_code=413)

            if not self._within_rate_limit():
                logger.warning("Rate limited %s webhook", self.name)
                return JSONResponse({"error": "too many requests"}, status_code=429)

            if not self.authenticate(
                body,
                request.headers.get("x-minion-signature"),
                request.headers.get("x-minion-timestamp"),
                request.headers.get("authorization"),
            ):
                # No detail in the response, and never the payload in the log — an
                # unauthenticated caller learns nothing about why it failed.
                logger.warning("Rejected unauthenticated %s webhook", self.name)
                return JSONResponse({"error": "unauthorized"}, status_code=401)

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
