import asyncio
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

MAX_TOOL_ROUNDS = 30

SYSTEM_PROMPT = """\
You are an autonomous planning agent. You have been given a GitHub issue to analyze.

Your job is to:
1. Read and understand the issue
2. Explore the codebase using the available tools (file_read, git, shell)
3. Produce a detailed implementation plan

IMPORTANT RULES:
- Do NOT modify any files. Only read and explore.
- Use the tools to understand the codebase structure, read relevant files, and trace code paths.
- Be thorough — read actual code, don't guess.

When you are done exploring, write your plan in this exact format:

## Implementation Plan

### Summary
[1-2 sentence summary of what needs to be done]

### Files to modify
[List each file with what changes are needed]

### Files to create
[List each new file with its purpose, if any]

### Implementation steps
[Numbered list of concrete steps]

### Testing
[How to verify the implementation works]
"""


def _slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug[:50]


class PlanHandler(EventHandler):
    event_types = ["github_plan"]

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
        body = event.payload.get("body", "") or ""
        repo = self._github.repo
        task_id = f"github-plan-{number}"

        logger.info("Planning issue #%d: %s", number, title)

        events = self._store.events_for(task_id)
        if is_claimed(
            events, stale_after=timedelta(minutes=self._tasks.claim_stale_minutes)
        ):
            logger.info("Task %s already claimed — skipping", task_id)
            return None

        self._store.append(task_id, CLAIMED, {"issue": number, "title": title})

        await self._update_labels(
            number,
            remove=self._github.labels["plan"],
            add=self._github.labels["planning"],
        )

        try:
            conversation = Conversation(max_history=100)
            conversation.add_user(
                f"GitHub Issue #{number}: {title}\n\n{body}\n\n"
                f"Explore the codebase and create a detailed implementation plan."
            )

            plan = await self._runner.run(SYSTEM_PROMPT, conversation, MAX_TOOL_ROUNDS, "plan")

            branch = f"issue-{number}-{_slugify(title)}"
            await self._create_branch(branch)

            await self._run_gh(
                "issue", "comment", str(number),
                "--repo", repo,
                "--body", f"{plan}\n\n*Branch: `{branch}`*",
            )

            await self._update_labels(
                number,
                remove=self._github.labels["planning"],
                add=self._github.labels["planned"],
            )

            await self._checkout_master()

            self._store.append(task_id, COMPLETED, {"issue": number})
            logger.info("Plan posted for issue #%d", number)
            return plan

        except Exception:
            logger.exception("Planning failed for issue #%d", number)
            self._store.append(task_id, FAILED, {"issue": number})
            raise

    async def _create_branch(self, branch: str) -> None:
        repo_path = self._get_repo_path()
        await self._run_git(repo_path, "checkout", "master")
        await self._run_git(repo_path, "pull", "origin", "master")
        await self._run_git(repo_path, "checkout", "-b", branch)
        await self._run_git(repo_path, "push", "-u", "origin", branch)

    async def _checkout_master(self) -> None:
        repo_path = self._get_repo_path()
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
