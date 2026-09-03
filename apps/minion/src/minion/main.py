import asyncio
import logging

import uvicorn

from minion.agents import create_agent
from minion.api import create_app
from minion.config import load_config
from minion.events import EventDispatcher
from minion.flows import registry as flow_registry
from minion.providers.github import GitHubProvider
from minion.store import EventStore, log_events
from minion.tools import create_registry
from minion.worker import Worker, reclaim_stale

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def _sweep_forever(store, providers, tasks) -> None:
    """Hand back tasks whose worker died, so a crash isn't a silent dead end."""
    interval = max(60, tasks.claim_stale_minutes * 60 // 2)
    while True:
        await asyncio.sleep(interval)
        try:
            await reclaim_stale(store, providers, tasks)
        except Exception:
            logger.exception("Sweep failed")


async def run() -> None:
    config = load_config()
    logger.info("Starting Minion agent: %s", config.agent.name)

    store = EventStore(config.store.db_path, config.agent.name)
    # One JSON line per fact on stdout; the Docker Loki driver ships it to Jupiter.
    store.subscribe(log_events)

    tool_registry = create_registry(config.tools)
    dispatcher = EventDispatcher()

    app = create_app()

    providers = {}
    if config.github.repo:
        providers["github"] = GitHubProvider(config, store)
    else:
        logger.info("GitHub disabled (no repo configured)")

    if providers:
        worker = Worker(
            create_agent(config, tool_registry),
            store,
            providers,
            flow_registry(),
            config.tasks,
        )
        # A provider only observes and appends `labeled`; the worker reacts to that
        # fact, alongside the Loki logger — both are plain subscribers to the same log.
        store.subscribe(worker.on_labeled)

    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host=config.api.host,
            port=config.api.port,
            log_level="info",
        )
    )

    tasks = [server.serve()]
    for name, provider in providers.items():
        tasks.append(provider.start(dispatcher))
        logger.info("Provider started: %s", name)

    if providers:
        tasks.append(_sweep_forever(store, providers, config.tasks))

    try:
        await asyncio.gather(*tasks)
    finally:
        store.close()
        logger.info("Event store closed")

    logger.info("Minion agent stopped")
