import asyncio
import logging

import uvicorn

from minion.api import create_app
from minion.config import load_config
from minion.events import EventDispatcher
from minion.github import register_github
from minion.handlers.chat import ChatHandler
from minion.store import EventStore, log_events
from minion.tools import create_registry

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def run() -> None:
    config = load_config()
    logger.info("Starting Minion agent: %s", config.agent.name)

    store = EventStore(config.store.db_path, config.agent.name)
    # One JSON line per fact on stdout; the Docker Loki driver ships it to Jupiter.
    store.subscribe(log_events)

    tool_registry = create_registry(config.tools)
    dispatcher = EventDispatcher()

    chat_handler = ChatHandler(config, tool_registry)
    dispatcher.register(chat_handler)

    app = create_app(dispatcher)

    github_source = register_github(config, dispatcher, tool_registry, store)

    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host=config.api.host,
            port=config.api.port,
            log_level="info",
        )
    )

    tasks = [server.serve()]
    if github_source:
        tasks.append(github_source.start(dispatcher))
        logger.info("GitHub source started")
    else:
        logger.info("GitHub disabled (no repo configured)")

    try:
        await asyncio.gather(*tasks)
    finally:
        store.close()
        logger.info("Event store closed")

    logger.info("Minion agent stopped")
