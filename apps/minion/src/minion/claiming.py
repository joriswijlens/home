import json
import logging
from datetime import datetime, timezone

import aiomqtt

logger = logging.getLogger(__name__)


class TaskClaimer:
    def __init__(
        self, broker: str, port: int, topic_prefix: str, agent_name: str
    ) -> None:
        self._broker = broker
        self._port = port
        self._topic_prefix = topic_prefix
        self._agent_name = agent_name
        self._client: aiomqtt.Client | None = None

    def set_client(self, client: aiomqtt.Client | None) -> None:
        self._client = client

    async def try_claim(self, task_id: str) -> bool:
        if not self._client:
            logger.debug("No MQTT client — claiming locally only")
            return True

        topic = f"{self._topic_prefix}/tasks/{task_id}/claimed"
        payload = json.dumps({
            "agent": self._agent_name,
            "claimed_at": datetime.now(timezone.utc).isoformat(),
        })

        try:
            await self._client.publish(topic, payload, retain=True)
            logger.info("Claimed task %s via MQTT", task_id)
            return True
        except aiomqtt.MqttError:
            logger.exception("Failed to publish claim for task %s", task_id)
            return False

    async def release(self, task_id: str) -> None:
        if not self._client:
            return

        topic = f"{self._topic_prefix}/tasks/{task_id}/claimed"
        try:
            await self._client.publish(topic, b"", retain=True)
            logger.info("Released task %s via MQTT", task_id)
        except aiomqtt.MqttError:
            logger.exception("Failed to release task %s", task_id)
