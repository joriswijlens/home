"""Claim, run, report, record.

The worker is the only place that knows the order of those four things. It knows
nothing about GitHub or Anthropic — the provider handles one end, the agent the other,
and every step is written to the log as it happens.

It is also where the bounds live, because unattended runs fail expensively rather than
loudly: one run at a time, a hard timeout, and a spend ceiling checked before starting.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from minion.agents import Agent
from minion.config import TasksConfig
from minion.events import Event, EventHandler
from minion.flows import Flow
from minion.providers import Task, TaskProvider
from minion.state import CLAIMED, COMPLETED, FAILED, tokens_used
from minion.store import EventStore

logger = logging.getLogger(__name__)

BUDGET_EXCEEDED = "budget_exceeded"
TIMED_OUT = "timed_out"


class Worker(EventHandler):
    event_types = ["task"]

    def __init__(
        self,
        agent: Agent,
        store: EventStore,
        providers: dict[str, TaskProvider],
        flows: dict[str, Flow],
        tasks: TasksConfig | None = None,
    ) -> None:
        self._agent = agent
        self._store = store
        self._providers = providers
        self._flows = flows
        self._tasks = tasks or TasksConfig()
        # Runs are the memory-hungry part. Everything else queues behind this.
        self._slots = asyncio.Semaphore(self._tasks.max_concurrent_runs)

    async def handle(self, event: Event) -> str | None:
        task: Task = event.payload["task"]
        provider = self._providers[event.source]
        flow = self._flows[task.flow]

        if self._over_budget():
            self._store.append(
                task.id, BUDGET_EXCEEDED, {"ref": task.ref, "flow": task.flow}
            )
            logger.warning(
                "Daily token budget reached — not starting %s", task.id
            )
            return None

        # The provider's claim is what stops a second worker, since the event log is
        # local to this machine and invisible to the others.
        if not await provider.claim(task):
            return None

        self._store.append(task.id, CLAIMED, {"ref": task.ref, "flow": task.flow})

        async with self._slots:
            return await self._run(task, provider, flow)

    async def _run(self, task: Task, provider: TaskProvider, flow: Flow) -> str | None:
        logger.info("Running %s for %s", task.flow, task.id)
        timeout = self._tasks.run_timeout_minutes * 60

        try:
            context = await provider.context(task)
            if context is None:
                self._store.append(
                    task.id, FAILED, {"ref": task.ref, "reason": "no workable context"}
                )
                return None

            report, run = await asyncio.wait_for(
                flow.run(self._agent, context), timeout=timeout
            )

            await provider.report(task, COMPLETED, report)
            self._store.append(
                task.id, COMPLETED, {"ref": task.ref, "usage": run.usage()}
            )
            logger.info(
                "Completed %s for %s (%d tokens)",
                task.flow,
                task.id,
                run.total_tokens,
            )
            return report["result"]

        except asyncio.TimeoutError:
            logger.error(
                "%s timed out after %d minutes for %s",
                task.flow,
                self._tasks.run_timeout_minutes,
                task.id,
            )
            self._store.append(
                task.id,
                TIMED_OUT,
                {"ref": task.ref, "minutes": self._tasks.run_timeout_minutes},
            )
            await provider.release(task)
            return None

        except Exception as exc:
            logger.exception("%s failed for %s", task.flow, task.id)
            self._store.append(task.id, FAILED, {"ref": task.ref, "error": str(exc)})
            # Hand it back so a retry is possible — bounded by max_attempts, which the
            # provider checks before dispatching again.
            await provider.release(task)
            raise

    def _over_budget(self) -> bool:
        budget = self._tasks.daily_token_budget
        if not budget:
            return False

        since = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        return tokens_used(self._store.since(since)) >= budget


async def reclaim_stale(
    store: EventStore, providers: dict[str, TaskProvider], tasks: TasksConfig
) -> int:
    """Hand back tasks whose worker died mid-run.

    Without this a crashed run leaves the task marked in progress at the provider while
    nothing is working on it, and every later poll skips it — silently, forever.
    """
    from minion.state import stale_claims

    stale = stale_claims(
        store.last_events(),
        stale_after=timedelta(minutes=tasks.claim_stale_minutes),
    )

    reclaimed = 0
    for event in stale:
        payload = event["payload"]
        provider = providers.get(payload.get("provider") or _provider_of(event))
        if provider is None:
            continue

        task = Task(
            id=event["task_id"],
            flow=payload.get("flow", ""),
            ref=payload.get("ref", ""),
            title="",
        )
        try:
            await provider.release(task)
            store.append(event["task_id"], "released", {"reason": "stale claim"})
            reclaimed += 1
            logger.info("Reclaimed stale task %s", event["task_id"])
        except Exception:
            logger.exception("Failed to reclaim %s", event["task_id"])

    return reclaimed


def _provider_of(event: dict) -> str:
    """Task ids are `<provider>-<flow>-<ref>`, so the provider is recoverable."""
    return event["task_id"].split("-", 1)[0]
