import asyncio
import logging

import httpx
import uvicorn

from minion.agent_worker import AgentWorker
from minion.agents import create_agent
from minion.api import create_app
from minion.config import load_config
from minion.events import EventDispatcher
from minion.handlers.signal import SignalHandler
from minion.flows import registry as flow_registry
from minion.providers.github import GitHubProvider
from minion.sources.grafana import grafana_mapper
from minion.sources.webhook import WebhookSource
from minion.store import EventStore, log_events
from minion.tools import create_registry
from minion.worker import Worker, reclaim_stale

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# Push sources by name: the route is `/hooks/<name>`, the secret
# `webhooks.secrets.<name>`. A source without a secret is not registered at all.
MAPPERS = {"grafana": grafana_mapper}


def build_app(config, store: EventStore, dispatcher: EventDispatcher | None = None):
    """The receiver: health plus one route per configured push source."""
    app = create_app()
    dispatcher = dispatcher or EventDispatcher()
    hooks = config.webhooks
    for name, mapper in MAPPERS.items():
        secret = hooks.secrets.get(name)
        if not secret:
            logger.info("Webhook %s disabled (no secret)", name)
            continue
        WebhookSource(
            name,
            mapper,
            store,
            secret,
            allow_bearer=name in hooks.allow_bearer,
            max_per_minute=hooks.max_per_minute,
        ).register(app, dispatcher)
        logger.info("Webhook ready at /hooks/%s", name)
    return app


async def start_handlers(
    config,
    store: EventStore,
    client: httpx.AsyncClient | None = None,
    make_agent=None,
) -> list[str]:
    """Bind the code handlers this worker runs. Each runs here and nowhere else."""
    bound = []
    signal = config.signal
    if signal.number and signal.recipients and signal.handles:
        handler = SignalHandler(signal, store, client or httpx.AsyncClient(timeout=10))
        for type in signal.handles:
            await store.handle("signal", type, handler.on_fact)
            bound.append(f"signal-{type}")
            logger.info("Handler signal-%s bound", type)
    else:
        logger.info("Signal disabled (no number, recipients or handled types)")

    if config.agents.handles:
        worker = AgentWorker(
            store, make_agent, config.agents, config.tasks, config.opencode.permission
        )
        await worker.start()
        bound += [f"{h.agent}-{type}" for type, h in config.agents.handles.items()]
    return bound


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

    store = await EventStore.connect(
        config.store.url, config.agent.name, config.store.stream
    )
    # Every fact, one JSON line each, shipped to Jupiter via the Docker Loki driver.
    # Ephemeral — losing a line there is fine, it must never be in the correctness path.
    await store.consume(None, log_events)

    tool_registry = create_registry(config.tools)
    await start_handlers(
        config, store, make_agent=lambda d: create_agent(config, tool_registry, d)
    )

    dispatcher = EventDispatcher()

    app = build_app(config, store, dispatcher)

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
        # Durable: a `labeled` fact appended while the worker was down still arrives
        # on restart, since JetStream remembers this consumer's position.
        await worker.start()

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
        await store.close()
        logger.info("Event store closed")

    logger.info("Minion agent stopped")
