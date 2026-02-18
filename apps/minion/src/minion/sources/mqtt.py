from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING

import aiomqtt

from minion.config import MqttConfig
from minion.events import Event, EventDispatcher, EventSource

if TYPE_CHECKING:
    from minion.claiming import TaskClaimer

logger = logging.getLogger(__name__)

RECONNECT_DELAY = 5


class MqttEventSource(EventSource):
    def __init__(
        self, config: MqttConfig, agent_name: str, claimer: TaskClaimer | None = None
    ) -> None:
        self._broker = config.broker
        self._port = config.port
        self._inbox = f"{config.topic_prefix}/{agent_name}/inbox"
        self._outbox = f"{config.topic_prefix}/{agent_name}/outbox"
        self._client: aiomqtt.Client | None = None
        self._claimer = claimer
        self._running = False

    async def start(self, dispatcher: EventDispatcher) -> None:
        self._running = True
        while self._running:
            try:
                async with aiomqtt.Client(self._broker, self._port) as client:
                    self._client = client
                    if self._claimer:
                        self._claimer.set_client(client)
                    logger.info("MQTT connected to %s:%d", self._broker, self._port)
                    await client.subscribe(self._inbox)
                    logger.info("Subscribed to %s", self._inbox)

                    async for message in client.messages:
                        await self._handle_message(message, dispatcher)
            except aiomqtt.MqttError as e:
                if not self._running:
                    break
                logger.warning("MQTT connection lost: %s. Reconnecting in %ds...", e, RECONNECT_DELAY)
                await asyncio.sleep(RECONNECT_DELAY)
            finally:
                self._client = None
                if self._claimer:
                    self._claimer.set_client(None)

    async def stop(self) -> None:
        self._running = False

    async def publish(self, message: str) -> None:
        if self._client:
            await self._client.publish(self._outbox, message)

    async def _handle_message(
        self, message: aiomqtt.Message, dispatcher: EventDispatcher
    ) -> None:
        try:
            payload = json.loads(message.payload.decode())
        except (json.JSONDecodeError, UnicodeDecodeError):
            logger.warning("Invalid MQTT message: %s", message.payload)
            return

        event = Event(
            type="chat",
            source="mqtt",
            payload=payload,
        )

        response = await dispatcher.dispatch(event)
        if response:
            await self.publish(
                json.dumps({"content": response, "sender": "agent"})
            )
