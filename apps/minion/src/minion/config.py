from pathlib import Path
from typing import Any, Tuple, Type

from pydantic import BaseModel
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)



class GitHubConfig(BaseModel):
    repo: str = ""
    poll_interval: int = 60
    labels: dict[str, str] = {
        "plan": "minion:plan",
        "planning": "minion:planning",
        "planned": "minion:planned",
        "implement": "minion:implement",
        "implementing": "minion:implementing",
        "done": "minion:done",
    }


class SignalConfig(BaseModel):
    # signal-cli-rest-api on Mars. Numbers come from the environment, e.g.
    # MINION_SIGNAL__NUMBER and MINION_SIGNAL__RECIPIENTS='["+31…"]'.
    url: str = "http://mars:8081"
    number: str = ""
    recipients: list[str] = []
    # Fact types this handler sends a message for. Empty, or no number: disabled.
    handles: list[str] = []


class Ceiling(BaseModel):
    """What Minion allows an agent from a repo. The repo's agent.yml can only narrow it."""

    max_rounds: int = 40
    # Tokens per rolling 24h across runs of this handler. 0 disables the check.
    daily_token_budget: int = 0
    # Per-tool maximum; None means opencode.permission. A tool not named is denied.
    permission: dict[str, str] | None = None
    # MCP servers (by name) a repo's agent may bring. Reach a repo cannot add itself.
    mcp: list[str] = []


class AgentHandlerConfig(BaseModel):
    repo: str
    ref: str = "main"
    # Directory name under the repo's .agents/agents/.
    agent: str
    ceiling: Ceiling = Ceiling()


class AgentsConfig(BaseModel):
    checkout_dir: str = "/tmp/minion-checkouts"
    # apm installs land here, keyed by lock hash — never inside a checkout.
    apm_cache_dir: str = "/tmp/minion-apm"
    # Fact type → the repo agent that handles it, on this worker only.
    handles: dict[str, AgentHandlerConfig] = {}


class ApiConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8080


class AgentConfig(BaseModel):
    name: str = "venus"
    # `claude_api` runs the Messages API with minion's own tools; `opencode` hands the
    # run to the OpenCode CLI, where `model` is `provider/model`.
    backend: str = "opencode"
    model: str = "scaleway/qwen3-coder-30b-a3b-instruct"
    max_tokens: int = 16000
    effort: str = "medium"
    # Off only for diagnosing a cache problem; on, it is the largest cost lever there is.
    cache_prompts: bool = True
    system_prompt: str = (
        "You are a helpful home automation assistant called {name}. "
        "You help manage infrastructure, write code, and automate tasks. "
        "Be concise and practical."
    )


class OpenCodeConfig(BaseModel):
    binary: str = "opencode"
    # Passed straight through as OpenCode's `provider` block, so any OpenAI-compatible
    # endpoint works without a code change. Keys via `{env:VAR}`, never inline.
    provider: dict[str, Any] = {}
    # The same reach `tools.enabled` gives the claude_api backend — read, write and
    # shell inside the workdir — spelled out per OpenCode tool. Nothing is "ask":
    # `opencode run` has nobody to ask, so an ask would land as a rejection.
    permission: dict[str, str] = {
        "read": "allow",
        "glob": "allow",
        "grep": "allow",
        "list": "allow",
        "edit": "allow",
        "bash": "allow",
        "webfetch": "deny",
        "websearch": "deny",
        "task": "deny",
        "question": "deny",
    }
    # OpenCode's `mcp` and `skills` blocks, passed through unchanged: a Grafana MCP
    # server, a skills directory. Tools the model gets beyond bash and the editor.
    mcp: dict[str, Any] = {}
    skills: dict[str, Any] = {}
    # Extra environment for the subprocess, e.g. MINION_OPENCODE__ENV__SCALEWAY_API_KEY.
    env: dict[str, str] = {}


class ToolsConfig(BaseModel):
    enabled: list[str] = ["shell", "file_read", "file_write", "git"]
    shell_timeout: int = 30
    allowed_paths: list[str] = ["/opt/smartworkx", "/tmp"]
    git_repos: list[str] = ["/opt/smartworkx"]


class StoreConfig(BaseModel):
    # NATS with JetStream — the event store's backend. Runs as its own lightweight
    # process (~4MB idle, single ~18MB binary), not embedded, but small enough that
    # it costs nothing on the same box.
    url: str = "nats://localhost:4222"
    stream: str = "MINION_EVENTS"


class WebhooksConfig(BaseModel):
    # Per-source secrets, e.g. MINION_WEBHOOKS__SECRETS__HA=... — a source with no
    # secret refuses to register rather than serving an open route.
    secrets: dict[str, str] = {}
    # Bearer sends the secret on every request, so it is for LAN senders that cannot
    # compute an HMAC. Keep it off for anything reachable from outside.
    allow_bearer: list[str] = []
    max_per_minute: int = 30


class TasksConfig(BaseModel):
    # A claim this old with no terminal event is treated as abandoned, so a run that
    # died mid-flight doesn't leave the task silently skipped forever. Must stay
    # comfortably above run_timeout_minutes, or a task still running gets handed to a
    # second worker — the duplicate run the claim exists to prevent.
    claim_stale_minutes: int = 30
    # Bounded retries: an always-failing task would otherwise be retried on every poll,
    # and every retry is a paid model run.
    max_attempts: int = 3
    # Hard stop for a single run. A wedged agent otherwise holds its claim until the
    # staleness window expires and burns tokens the whole time.
    run_timeout_minutes: float = 20
    # Runs are the memory-hungry part; on a Pi 3 more than one at a time is an OOM.
    max_concurrent_runs: int = 1
    # Spend ceiling per rolling 24h, counted from the log. 0 disables the check.
    daily_token_budget: int = 0


class ConversationConfig(BaseModel):
    max_history: int = 50


# Build yaml_file list: only include files that exist. Later files win, so `local.yml`
# (gitignored) is where a laptop overrides the deployment's absolute paths.
_config_dir = Path(__file__).parent.parent.parent / "config"
_yaml_files: list[Path] = []
for _p in [
    _config_dir / "default.yml",
    Path("/opt/smartworkx/volumes/minion/config/default.yml"),
    _config_dir / "local.yml",
]:
    if _p.exists():
        _yaml_files.append(_p)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MINION_",
        env_nested_delimiter="__",
        yaml_file=_yaml_files or None,
    )

    anthropic_api_key: str = ""
    agent: AgentConfig = AgentConfig()
    opencode: OpenCodeConfig = OpenCodeConfig()
    api: ApiConfig = ApiConfig()
    tools: ToolsConfig = ToolsConfig()
    conversation: ConversationConfig = ConversationConfig()
    github: GitHubConfig = GitHubConfig()
    store: StoreConfig = StoreConfig()
    tasks: TasksConfig = TasksConfig()
    webhooks: WebhooksConfig = WebhooksConfig()
    signal: SignalConfig = SignalConfig()
    agents: AgentsConfig = AgentsConfig()

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: Type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
        **kwargs: Any,
    ) -> Tuple[PydanticBaseSettingsSource, ...]:
        # Priority (highest first): init > env > yaml > defaults
        sources: list[PydanticBaseSettingsSource] = [
            init_settings,
            env_settings,
        ]
        if _yaml_files:
            sources.append(
                YamlConfigSettingsSource(settings_cls)
            )
        sources.append(file_secret_settings)
        return tuple(sources)


def load_config() -> Settings:
    """Load config: defaults < YAML files < env vars."""
    return Settings()
