import asyncio
import json
import logging
from datetime import timedelta
import re

from minion.agent import AgentRunner
from minion.config import Settings
from minion.conversation import Conversation
from minion.events import Event, EventHandler
from minion.state import CLAIMED, COMPLETED, FAILED, is_claimed
from minion.store import EventStore
from minion.tools import ToolRegistry

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 50

SYSTEM_PROMPT = """\
You are an autonomous implementation agent. You have been given a GitHub issue with an approved plan.

Your job is to implement the plan exactly as described. You have access to tools for reading files, \
writing files, running shell commands, and git operations.

IMPORTANT RULES:
- Follow the plan closely. Do not deviate unless there's a clear technical reason.
- Write clean, well-structured code that matches existing patterns.
- Do NOT commit or push — that will be handled after you finish.
- Do NOT create unnecessary files or add extra features not in the plan.
"""


class ImplementHandler(EventHandler):
    event_types = ["github_implement"]

    def __init__(
        self,
        config: Settings,
        tool_registry: ToolRegistry,
        store: EventStore,
    ) -> None:
        self._runner = AgentRunner(config, tool_registry)
        self._github = config.github
        self._config = config
        self._store = store
        self._tasks = config.tasks
        self._agent_name = config.agent.name

    async def handle(self, event: Event) -> str | None:
        number = event.payload["number"]
        title = event.payload["title"]
        repo = self._github.repo
        task_id = f"github-impl-{number}"

        logger.info("Implementing issue #%d: %s", number, title)

        events = self._store.events_for(task_id)
        if is_claimed(
            events, stale_after=timedelta(minutes=self._tasks.claim_stale_minutes)
        ):
            logger.info("Task %s already claimed — skipping", task_id)
            return None

        self._store.append(task_id, CLAIMED, {"issue": number, "title": title})

        await self._update_labels(
            number,
            remove=self._github.labels["implement"],
            add=self._github.labels["implementing"],
        )

        try:
            issue_data = await self._fetch_issue(number)
            if not issue_data:
                return None

            plan, branch = self._extract_plan_and_branch(issue_data)
            if not plan or not branch:
                await self._run_gh(
                    "issue", "comment", str(number),
                    "--repo", repo,
                    "--body", "Could not find an approved plan comment with a branch. "
                    "Please ensure a plan was posted with the `## Implementation Plan` "
                    "header and `*Branch: \\`branch-name\\`*` line.",
                )
                logger.error("No plan found for issue #%d", number)
                self._store.append(
                    task_id, FAILED, {"issue": number, "reason": "no approved plan"}
                )
                return None

            repo_path = self._get_repo_path()
            await self._run_git(repo_path, "fetch", "origin")
            await self._run_git(repo_path, "checkout", branch)
            await self._run_git(repo_path, "pull", "origin", branch)

            conversation = Conversation(max_history=200)
            conversation.add_user(
                f"GitHub Issue #{number}: {title}\n\n"
                f"Approved plan:\n\n{plan}\n\n"
                f"Implement this plan now. The branch `{branch}` is already checked out."
            )

            result = await self._runner.run(SYSTEM_PROMPT, conversation, MAX_TOOL_ROUNDS, "implement")

            await self._commit_and_push(repo_path, branch, number, title)
            await self._create_pr(number, title, branch)
            await self._update_labels(
                number,
                remove=self._github.labels["implementing"],
                add=self._github.labels["done"],
            )
            await self._checkout_master(repo_path)

            self._store.append(task_id, COMPLETED, {"issue": number})
            logger.info("Implementation complete for issue #%d", number)
            return result

        except Exception:
            logger.exception("Implementation failed for issue #%d", number)
            self._store.append(task_id, FAILED, {"issue": number})
            raise

    async def _fetch_issue(self, number: int) -> dict | None:
        proc = await asyncio.create_subprocess_exec(
            "gh", "issue", "view", str(number),
            "--repo", self._github.repo,
            "--json", "title,body,comments",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            logger.error("Failed to fetch issue #%d: %s", number, stderr.decode())
            return None
        try:
            return json.loads(stdout.decode())
        except json.JSONDecodeError:
            logger.error("Failed to parse issue #%d data", number)
            return None

    def _extract_plan_and_branch(self, issue_data: dict) -> tuple[str | None, str | None]:
        comments = issue_data.get("comments", [])
        for comment in reversed(comments):
            body = comment.get("body", "")
            if "## Implementation Plan" not in body:
                continue

            branch_match = re.search(r"\*Branch: `([^`]+)`\*", body)
            if not branch_match:
                continue

            return body, branch_match.group(1)

        return None, None

    async def _commit_and_push(
        self, repo_path: str, branch: str, number: int, title: str
    ) -> None:
        await self._run_git(repo_path, "add", "-A")

        status = await self._run_git(repo_path, "status", "--porcelain")
        if not status:
            logger.info("No changes to commit for issue #%d", number)
            return

        await self._run_git(
            repo_path, "commit", "-m",
            f"#{number} {title}\n\nImplemented by minion agent.",
        )
        await self._run_git(repo_path, "push", "origin", branch)

    async def _create_pr(self, number: int, title: str, branch: str) -> None:
        await self._run_gh(
            "pr", "create",
            "--repo", self._github.repo,
            "--base", "master",
            "--head", branch,
            "--title", title,
            "--body", f"Closes #{number}\n\nImplemented by minion agent.",
        )

    async def _checkout_master(self, repo_path: str) -> None:
        await self._run_git(repo_path, "checkout", "master")

    def _get_repo_path(self) -> str:
        repos = self._config.tools.git_repos
        return repos[0] if repos else "/opt/smartworkx"

    async def _run_git(self, repo: str, *args: str) -> str:
        proc = await asyncio.create_subprocess_exec(
            "git", "-C", repo, *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            error = stderr.decode().strip()
            logger.error("git %s failed: %s", " ".join(args), error)
            raise RuntimeError(f"git {' '.join(args)} failed: {error}")
        return stdout.decode().strip()

    async def _run_gh(self, *args: str) -> str:
        proc = await asyncio.create_subprocess_exec(
            "gh", *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            error = stderr.decode().strip()
            logger.error("gh %s failed: %s", " ".join(args), error)
            raise RuntimeError(f"gh {' '.join(args)} failed: {error}")
        return stdout.decode().strip()

    async def _update_labels(self, number: int, remove: str, add: str) -> None:
        repo = self._github.repo
        await self._run_gh(
            "issue", "edit", str(number),
            "--repo", repo,
            "--remove-label", remove,
            "--add-label", add,
        )
