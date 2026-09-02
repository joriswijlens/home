"""Claim, run, report, record.

The worker is the only place that knows the order of those four things. It knows
nothing about GitHub or Anthropic — the provider handles one end, the agent the other,
and every step is written to the log as it happens.
"""

import logging

from minion.agents import Agent
from minion.events import Event, EventHandler
from minion.flows import Flow
from minion.providers import Task, TaskProvider
from minion.state import CLAIMED, COMPLETED, FAILED
from minion.store import EventStore

logger = logging.getLogger(__name__)


class Worker(EventHandler):
    event_types = ["task"]

    def __init__(
        self,
        agent: Agent,
        store: EventStore,
        providers: dict[str, TaskProvider],
        flows: dict[str, Flow],
    ) -> None:
        self._agent = agent
        self._store = store
        self._providers = providers
        self._flows = flows

    async def handle(self, event: Event) -> str | None:
        task: Task = event.payload["task"]
        provider = self._providers[event.source]
        flow = self._flows[task.flow]

        # The provider's claim is what stops a second worker, since the event log is
        # local to this machine and invisible to the others.
        if not await provider.claim(task):
            return None

        self._store.append(task.id, CLAIMED, {"ref": task.ref, "flow": task.flow})
        logger.info("Running %s for %s", task.flow, task.id)

        try:
            context = await provider.context(task)
            if context is None:
                self._store.append(
                    task.id, FAILED, {"ref": task.ref, "reason": "no workable context"}
                )
                return None

            result = await flow.run(self._agent, context)

            await provider.report(task, COMPLETED, result)
            self._store.append(task.id, COMPLETED, {"ref": task.ref})
            logger.info("Completed %s for %s", task.flow, task.id)
            return result["result"]

        except Exception as exc:
            logger.exception("%s failed for %s", task.flow, task.id)
            self._store.append(
                task.id, FAILED, {"ref": task.ref, "error": str(exc)}
            )
            # Hand it back so a retry is possible — bounded by max_attempts, which the
            # provider checks before dispatching again.
            await provider.release(task)
            raise
