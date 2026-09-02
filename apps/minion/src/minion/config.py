from pathlib import Path
from typing import Any, Tuple, Type

from pydantic import BaseModel
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

from minion.github.config import GitHubConfig


class ApiConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8080


class AgentConfig(BaseModel):
    name: str = "venus"
    provider: str = "claude_api"
    model: str = "claude-sonnet-5"
    max_tokens: int = 16000
    effort: str = "medium"
    system_prompt: str = (
        "You are a helpful home automation assistant called {name}. "
        "You help manage infrastructure, write code, and automate tasks. "
        "Be concise and practical."
    )


class ToolsConfig(BaseModel):
    enabled: list[str] = ["shell", "file_read", "file_write", "git"]
    shell_timeout: int = 30
    allowed_paths: list[str] = ["/opt/smartworkx", "/tmp"]
    git_repos: list[str] = ["/opt/smartworkx"]


class StoreConfig(BaseModel):
    db_path: str = "/data/minion.db"


class TasksConfig(BaseModel):
    # A claim this old with no terminal event is treated as abandoned, so a run that
    # died mid-flight doesn't leave the task silently skipped forever.
    claim_stale_minutes: int = 30
    # Bounded retries: an always-failing task would otherwise be retried on every poll,
    # and every retry is a paid model run.
    max_attempts: int = 3


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
    api: ApiConfig = ApiConfig()
    tools: ToolsConfig = ToolsConfig()
    conversation: ConversationConfig = ConversationConfig()
    github: GitHubConfig = GitHubConfig()
    store: StoreConfig = StoreConfig()
    tasks: TasksConfig = TasksConfig()

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
