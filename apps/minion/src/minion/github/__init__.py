from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from minion.config import Settings
    from minion.events import EventDispatcher
    from minion.github.source import GitHubEventSource
    from minion.store import EventStore
    from minion.tools import ToolRegistry

logger = logging.getLogger(__name__)


def register_github(
    config: Settings,
    dispatcher: EventDispatcher,
    tool_registry: ToolRegistry,
    store: EventStore,
) -> GitHubEventSource | None:
    from minion.github.implement import ImplementHandler
    from minion.github.plan import PlanHandler
    from minion.github.source import GitHubEventSource

    if not config.github.repo:
        logger.info("GitHub disabled (no repo configured)")
        return None

    dispatcher.register(PlanHandler(config, tool_registry, store))
    dispatcher.register(ImplementHandler(config, tool_registry, store))
    return GitHubEventSource(config.github, store, config.tasks)
