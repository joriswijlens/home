import asyncio
import json
import logging

from minion.events import Event, EventDispatcher, EventSource
from minion.github.config import GitHubConfig
from minion.store import TaskStore

logger = logging.getLogger(__name__)


class GitHubEventSource(EventSource):
    def __init__(self, config: GitHubConfig, store: TaskStore) -> None:
        self._config = config
        self._store = store
        self._running = False

    async def start(self, dispatcher: EventDispatcher) -> None:
        self._running = True
        logger.info(
            "GitHub source started — polling %s every %ds",
            self._config.repo,
            self._config.poll_interval,
        )

        while self._running:
            try:
                await self._poll(dispatcher)
            except Exception:
                logger.exception("GitHub poll error")
            await asyncio.sleep(self._config.poll_interval)

    async def stop(self) -> None:
        self._running = False

    async def _poll(self, dispatcher: EventDispatcher) -> None:
        for action, event_type, task_prefix in [
            ("plan", "github_plan", "github-plan-"),
            ("implement", "github_implement", "github-impl-"),
        ]:
            label = self._config.labels[action]
            issues = await self._list_issues(label)
            for issue in issues:
                number = issue["number"]
                task_id = f"{task_prefix}{number}"

                if self._store.is_known(task_id):
                    continue

                logger.info(
                    "GitHub issue #%d (%s) — dispatching %s",
                    number,
                    issue["title"],
                    event_type,
                )

                event = Event(
                    type=event_type,
                    source="github",
                    payload=issue,
                )
                await dispatcher.dispatch(event)

    async def _list_issues(self, label: str) -> list[dict]:
        proc = await asyncio.create_subprocess_exec(
            "gh", "issue", "list",
            "--repo", self._config.repo,
            "--label", label,
            "--state", "open",
            "--json", "number,title,body,labels",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            logger.error("gh issue list failed: %s", stderr.decode())
            return []

        try:
            return json.loads(stdout.decode())
        except json.JSONDecodeError:
            logger.error("Failed to parse gh output: %s", stdout.decode()[:200])
            return []
