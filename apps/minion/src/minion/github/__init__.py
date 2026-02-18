from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from minion.claiming import TaskClaimer
    from minion.config import Settings
    from minion.events import EventDispatcher
    from minion.github.source import GitHubEventSource
    from minion.store import TaskStore
    from minion.tools import ToolRegistry

logger = logging.getLogger(__name__)


def register_github(
    config: Settings,
    dispatcher: EventDispatcher,
    tool_registry: ToolRegistry,
    store: TaskStore,
    claimer: TaskClaimer,
) -> GitHubEventSource | None:
    from minion.github.implement import ImplementHandler
    from minion.github.plan import PlanHandler
    from minion.github.source import GitHubEventSource

    if not config.github.repo:
        logger.info("GitHub disabled (no repo configured)")
        return None

    dispatcher.register(PlanHandler(config, tool_registry, store, claimer))
    dispatcher.register(ImplementHandler(config, tool_registry, store, claimer))
    return GitHubEventSource(config.github, store)
