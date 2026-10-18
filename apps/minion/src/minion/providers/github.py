"""GitHub as a task provider: issues in, labels and PRs out.

The only module that shells out to `gh`. Labels are the shared state between workers —
they are how a task is handed in, claimed, and reported on. What actually happened is
recorded in the event log, not in the labels.
"""

import json
import logging
import re
from minion.config import Settings
from minion.events import EventDispatcher
from minion.providers import PollingProvider, Task
from minion.providers.process import git, run, try_run
from minion.state import LABELED, is_labeled
from minion.store import EventStore

logger = logging.getLogger(__name__)

# Which label hands work in, and which one marks it as being worked on.
FLOWS = {
    "plan": ("plan", "planning", "planned"),
    "implement": ("implement", "implementing", "done"),
}

PLAN_HEADER = "## Implementation Plan"
BRANCH_PATTERN = r"\*Branch: `([^`]+)`\*"


def slugify(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:50]


class GitHubProvider(PollingProvider):
    name = "github"

    def __init__(self, config: Settings, store: EventStore) -> None:
        super().__init__()
        self._config = config.github
        self._repo_path = (
            config.tools.git_repos[0] if config.tools.git_repos else "/opt/smartworkx"
        )
        self._store = store
        self.poll_interval = config.github.poll_interval

    # -- EventSource (polled: GitHub cannot reach in to push) ------------------

    async def poll(self, dispatcher: EventDispatcher) -> None:
        """Observe which issues are ready for pickup — nothing more.

        Retry eligibility, budget and staleness are the worker's job, evaluated when
        it reacts to `labeled`. The poller only records that the label was seen, once,
        so the log does not fill with the same observation every cycle.
        """
        for flow, (ready_label, _, _) in FLOWS.items():
            for issue in await self._list_issues(self._config.labels[ready_label]):
                task = Task(
                    id=f"github-{flow}-{issue['number']}",
                    flow=flow,
                    ref=str(issue["number"]),
                    title=issue["title"],
                    payload=issue,
                )

                if is_labeled(await self._store.events_for(task.id)):
                    continue

                logger.info("Issue #%s (%s) labeled for %s", task.ref, task.title, flow)
                await self._store.append(
                    task.id,
                    LABELED,
                    {
                        "provider": self.name,
                        "flow": task.flow,
                        "ref": task.ref,
                        "title": task.title,
                    },
                )

    # -- TaskProvider ---------------------------------------------------------

    async def claim(self, task: Task) -> bool:
        """Claim by *removing* the ready label.

        Removal is the primitive that can fail: adding a label succeeds for both
        workers racing for the same issue, so both would believe they won. The loser
        of a removal gets an error and backs off.
        """
        ready, working, _ = FLOWS[task.flow]

        won = await try_run(
            "gh", "issue", "edit", task.ref,
            "--repo", self._config.repo,
            "--remove-label", self._config.labels[ready],
        )
        if not won:
            logger.info("Issue #%s already claimed by another worker", task.ref)
            return False

        await run(
            "gh", "issue", "edit", task.ref,
            "--repo", self._config.repo,
            "--add-label", self._config.labels[working],
        )
        return True

    async def context(self, task: Task) -> dict | None:
        if task.flow == "plan":
            return {
                "title": task.title,
                "body": task.payload.get("body", "") or "",
                "ref": task.ref,
                "workdir": self._repo_path,
            }

        issue = await self._fetch_issue(task.ref)
        if not issue:
            return None

        plan, branch = self._extract_plan_and_branch(issue)
        if not plan or not branch:
            await self._comment(
                task.ref,
                "Could not find an approved plan comment with a branch. Please ensure "
                f"a plan was posted with the `{PLAN_HEADER}` header and a "
                "`*Branch: `branch-name`*` line.",
            )
            logger.error("No plan found for issue #%s", task.ref)
            return None

        await git(self._repo_path, "fetch", "origin")
        await git(self._repo_path, "checkout", branch)
        await git(self._repo_path, "pull", "origin", branch)

        return {
            "title": task.title,
            "plan": plan,
            "branch": branch,
            "ref": task.ref,
            "workdir": self._repo_path,
        }

    async def report(self, task: Task, outcome: str, payload: dict) -> None:
        _, working, done = FLOWS[task.flow]

        if task.flow == "plan":
            branch = f"issue-{task.ref}-{slugify(task.title)}"
            await self._create_branch(branch)
            await self._comment(
                task.ref, f"{payload['result']}\n\n*Branch: `{branch}`*"
            )
        else:
            branch = payload["branch"]
            await self._commit_and_push(branch, task.ref, task.title)
            await self._create_pr(task.ref, task.title, branch)

        await run(
            "gh", "issue", "edit", task.ref,
            "--repo", self._config.repo,
            "--remove-label", self._config.labels[working],
            "--add-label", self._config.labels[done],
        )
        await git(self._repo_path, "checkout", "master")

    async def release(self, task: Task) -> None:
        """Put the task back so a later poll — or another worker — can retry it."""
        ready, working, _ = FLOWS[task.flow]
        await try_run(
            "gh", "issue", "edit", task.ref,
            "--repo", self._config.repo,
            "--remove-label", self._config.labels[working],
            "--add-label", self._config.labels[ready],
        )

    # -- gh / git -------------------------------------------------------------

    async def _list_issues(self, label: str) -> list[dict]:
        try:
            out = await run(
                "gh", "issue", "list",
                "--repo", self._config.repo,
                "--label", label,
                "--state", "open",
                "--json", "number,title,body,labels",
            )
            return json.loads(out)
        except (RuntimeError, json.JSONDecodeError):
            logger.exception("Failed to list issues for label %s", label)
            return []

    async def _fetch_issue(self, ref: str) -> dict | None:
        try:
            out = await run(
                "gh", "issue", "view", ref,
                "--repo", self._config.repo,
                "--json", "title,body,comments",
            )
            return json.loads(out)
        except (RuntimeError, json.JSONDecodeError):
            logger.exception("Failed to fetch issue #%s", ref)
            return None

    @staticmethod
    def _extract_plan_and_branch(issue: dict) -> tuple[str | None, str | None]:
        for comment in reversed(issue.get("comments", [])):
            body = comment.get("body", "")
            if PLAN_HEADER not in body:
                continue
            match = re.search(BRANCH_PATTERN, body)
            if match:
                return body, match.group(1)
        return None, None

    async def _comment(self, ref: str, body: str) -> None:
        await run(
            "gh", "issue", "comment", ref, "--repo", self._config.repo, "--body", body
        )

    async def _create_branch(self, branch: str) -> None:
        await git(self._repo_path, "checkout", "master")
        await git(self._repo_path, "pull", "origin", "master")
        await git(self._repo_path, "checkout", "-b", branch)
        await git(self._repo_path, "push", "-u", "origin", branch)

    async def _commit_and_push(self, branch: str, ref: str, title: str) -> None:
        await git(self._repo_path, "add", "-A")
        if not await git(self._repo_path, "status", "--porcelain"):
            logger.info("No changes to commit for issue #%s", ref)
            return
        await git(
            self._repo_path, "commit", "-m",
            f"#{ref} {title}\n\nImplemented by minion agent.",
        )
        await git(self._repo_path, "push", "origin", branch)

    async def _create_pr(self, ref: str, title: str, branch: str) -> None:
        await run(
            "gh", "pr", "create",
            "--repo", self._config.repo,
            "--base", "master",
            "--head", branch,
            "--title", title,
            "--body", f"Closes #{ref}\n\nImplemented by minion agent.",
        )
