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


class MqttConfig(BaseModel):
    broker: str = "mars.local"
    port: int = 1883
    topic_prefix: str = "minion"


class ApiConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8080


class AgentConfig(BaseModel):
    name: str = "venus"
    model: str = "claude-sonnet-4-5-20250929"
    max_tokens: int = 4096
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


class ConversationConfig(BaseModel):
    max_history: int = 50


# Build yaml_file list: only include files that exist
_yaml_files: list[Path] = []
for _p in [
    Path(__file__).parent.parent.parent / "config" / "default.yml",
    Path("/opt/smartworkx/volumes/minion/config/default.yml"),
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
    mqtt: MqttConfig = MqttConfig()
    api: ApiConfig = ApiConfig()
    tools: ToolsConfig = ToolsConfig()
    conversation: ConversationConfig = ConversationConfig()
    github: GitHubConfig = GitHubConfig()

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
