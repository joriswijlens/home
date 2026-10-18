"""Agent backed by the OpenCode CLI.

One `opencode run` per flow run, in the task's working directory. OpenCode brings its
own tool loop — bash, edit, read, grep — so nothing from `minion.tools` is involved;
what minion controls is the agent definition it hands over: system prompt, model,
step limit and permissions, plus any MCP servers and skills from config — all passed
inline through `OPENCODE_CONFIG_CONTENT`, so no file is written into the repo being
worked on.

Output is read as `--format json`: one event per line, `text` for the answer,
`step_finish` for what each round cost, `error` when the provider or the run fails.
The last text part is the result; token counts are summed across steps.

Which model answers is a provider concern — `agent.model` is `provider/model`, and the
provider itself (an OpenAI-compatible endpoint, its key) is config OpenCode reads, so
swapping to a cheaper open-weight model is a config change, never a code one.
"""

import asyncio
import json
import logging
import os

from minion.agent_definition import AgentDefinition
from minion.agents import RunResult
from minion.config import Settings

logger = logging.getLogger(__name__)

AGENT_NAME = "minion"


class OpenCodeError(RuntimeError):
    pass


class OpenCodeAgent:
    def __init__(self, config: Settings, definition: AgentDefinition | None = None) -> None:
        # An agent definition, when given, wins over the deployment's defaults.
        definition = definition or AgentDefinition()
        self._binary = config.opencode.binary
        self._model = definition.model or config.agent.model
        self._max_rounds = definition.max_rounds
        self._provider = config.opencode.provider
        self._permission = definition.permission or config.opencode.permission
        self._mcp = {**config.opencode.mcp, **definition.mcp}
        self._skills = (
            {"paths": [str(definition.skills_dir)]}
            if definition.skills_dir
            else config.opencode.skills
        )
        self._env = config.opencode.env

    def _config(self, system_prompt: str, max_rounds: int) -> dict:
        config: dict = {
            "agent": {
                AGENT_NAME: {
                    "mode": "primary",
                    "prompt": system_prompt,
                    "model": self._model,
                    "steps": max_rounds,
                    "permission": self._permission,
                }
            }
        }
        for key, block in (
            ("provider", self._provider),
            ("mcp", self._mcp),
            ("skills", self._skills),
        ):
            if block:
                config[key] = block
        return config

    async def run(
        self,
        system_prompt: str,
        prompt: str,
        max_rounds: int,
        label: str = "agent",
        workdir: str | None = None,
    ) -> RunResult:
        max_rounds = self._max_rounds or max_rounds
        env = {
            **os.environ,
            **self._env,
            "OPENCODE_CONFIG_CONTENT": json.dumps(self._config(system_prompt, max_rounds)),
        }
        args = [
            self._binary, "run",
            "--format", "json",
            "--pure",
            "--agent", AGENT_NAME,
            "--model", self._model,
        ]
        if workdir:
            args += ["--dir", workdir]
        args += ["--", prompt]

        proc = await asyncio.create_subprocess_exec(
            *args,
            env=env,
            cwd=workdir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await proc.communicate()
        except asyncio.CancelledError:
            # The worker's timeout lands here; a child left running keeps spending.
            proc.kill()
            await proc.wait()
            raise

        result, errors = _parse(stdout.decode())
        if errors:
            raise OpenCodeError("; ".join(errors))
        if proc.returncode != 0:
            raise OpenCodeError(
                f"{label}: opencode exited {proc.returncode}: {stderr.decode().strip()[-500:]}"
            )
        logger.info("%s: %d tokens across opencode run", label, result.total_tokens)
        return result


def _parse(output: str) -> tuple[RunResult, list[str]]:
    """Fold the event lines into a result and the errors seen along the way."""
    result = RunResult(text="")
    errors: list[str] = []
    for line in output.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        kind = event.get("type")
        if kind == "text":
            text = event["part"].get("text", "").strip()
            if text:
                result.text = text
        elif kind == "step_finish":
            tokens = event["part"].get("tokens", {})
            cache = tokens.get("cache", {})
            result.input_tokens += tokens.get("input", 0)
            result.output_tokens += tokens.get("output", 0) + tokens.get("reasoning", 0)
            result.cache_read_tokens += cache.get("read", 0)
            result.cache_write_tokens += cache.get("write", 0)
        elif kind == "error":
            errors.append(_describe(event.get("error")))
    return result, errors


def _describe(error) -> str:
    if isinstance(error, dict):
        data = error.get("data") or {}
        return str(data.get("message") or error.get("name") or error)
    return str(error)
