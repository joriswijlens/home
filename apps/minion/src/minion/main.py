import asyncio
import logging

import uvicorn

from minion.api import create_app
from minion.config import load_config
from minion.events import EventDispatcher
from minion.github import register_github
from minion.handlers.chat import ChatHandler
from minion.sources.mqtt import MqttEventSource
from minion.tools import create_registry

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def run() -> None:
    config = load_config()
    logger.info("Starting Minion agent: %s", config.agent.name)

    tool_registry = create_registry(config.tools)
    dispatcher = EventDispatcher()

    chat_handler = ChatHandler(config, tool_registry)
    dispatcher.register(chat_handler)

    app = create_app(dispatcher)

    mqtt_source: MqttEventSource | None = None
    if config.mqtt.broker:
        mqtt_source = MqttEventSource(config.mqtt, config.agent.name)

    github_source = register_github(config, dispatcher, tool_registry)

    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host=config.api.host,
            port=config.api.port,
            log_level="info",
        )
    )

    tasks = [server.serve()]
    if mqtt_source:
        tasks.append(mqtt_source.start(dispatcher))
        logger.info("MQTT source started")
    else:
        logger.info("MQTT disabled (no broker configured)")

    if github_source:
        tasks.append(github_source.start(dispatcher))
        logger.info("GitHub source started")
    else:
        logger.info("GitHub disabled (no repo configured)")

    await asyncio.gather(*tasks)

    logger.info("Minion agent stopped")
