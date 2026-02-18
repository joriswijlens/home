import asyncio
import json
import logging
import re
from typing import Any

import anthropic

from minion.claiming import TaskClaimer
from minion.config import Settings
from minion.conversation import Conversation
from minion.events import Event, EventHandler
from minion.store import TaskStore
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
        store: TaskStore,
        claimer: TaskClaimer,
    ) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=config.anthropic_api_key)
        self._model = config.agent.model
        self._max_tokens = config.agent.max_tokens
        self._tools = tool_registry
        self._github = config.github
        self._config = config
        self._store = store
        self._claimer = claimer
        self._agent_name = config.agent.name

    async def handle(self, event: Event) -> str | None:
        number = event.payload["number"]
        title = event.payload["title"]
        repo = self._github.repo
        task_id = f"github-impl-{number}"

        logger.info("Implementing issue #%d: %s", number, title)

        claimed = self._store.create_task(
            task_id=task_id,
            source="github",
            external_ref=str(number),
            agent=self._agent_name,
            title=title,
        )
        if not claimed:
            logger.info("Task %s already claimed — skipping", task_id)
            return None

        await self._claimer.try_claim(task_id)

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
                self._store.update_status(task_id, "failed")
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

            result = await self._run_agent(conversation)

            await self._commit_and_push(repo_path, branch, number, title)
            await self._create_pr(number, title, branch)
            await self._update_labels(
                number,
                remove=self._github.labels["implementing"],
                add=self._github.labels["done"],
            )
            await self._checkout_master(repo_path)

            self._store.update_status(task_id, "done")
            logger.info("Implementation complete for issue #%d", number)
            return result

        except Exception:
            logger.exception("Implementation failed for issue #%d", number)
            self._store.update_status(task_id, "failed")
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

    async def _run_agent(self, conversation: Conversation) -> str:
        tools = self._tools.list_tools()

        for _ in range(MAX_TOOL_ROUNDS):
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                system=SYSTEM_PROMPT,
                messages=conversation.messages,
                tools=tools or anthropic.NOT_GIVEN,
            )

            conversation.add_assistant(response.content)

            if response.stop_reason == "end_turn":
                return self._extract_text(response.content)

            if response.stop_reason == "tool_use":
                await self._handle_tool_use(response.content, conversation)
                continue

            return self._extract_text(response.content)

        return "Implementation reached maximum tool rounds."

    async def _handle_tool_use(
        self, content: list[Any], conversation: Conversation
    ) -> None:
        results: list[tuple[str, str]] = []
        for block in content:
            if block.type == "tool_use":
                logger.info("Implement tool call: %s(%s)", block.name, block.input)
                result = await self._tools.execute(block.name, **block.input)
                results.append((block.id, result))
        if results:
            conversation.add_tool_results(results)

    def _extract_text(self, content: list[Any]) -> str:
        parts = []
        for block in content:
            if block.type == "text":
                parts.append(block.text)
        return "\n".join(parts) or "(no response)"

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
