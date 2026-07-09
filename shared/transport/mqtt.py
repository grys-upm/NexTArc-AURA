"""
MQTT implementation of TransportBase interface.
==============================================
Uses aiomqtt (an asyncio wrapper around paho-mqtt) to connect
to a Mosquitto broker without TLS or authentication, as required for
the AURA PoC.
"""
from __future__ import annotations

import json
import logging
from typing import AsyncIterator, Any

import aiomqtt
from shared.transport.base import TransportBase, MessageEnvelope

# Setup logging for this module
logger = logging.getLogger(__name__)


class MQTTTransport(TransportBase):
    """
    Async MQTT transport backend powered by the aiomqtt client wrapper.
    """

    def __init__(self, host: str, port: int = 1883) -> None:
        """
        Initializes the MQTTTransport connection parameters.

        :param host: MQTT broker hostname or network host IP address.
        :type host: str
        :param port: Network port of the broker. Defaults to 1883.
        :type port: int
        """
        self.host = host
        self.port = port
        self._client: aiomqtt.Client | None = None

    async def connect(self) -> None:
        """
        Establishes an active async connection to the MQTT broker.
        """
        self._client = aiomqtt.Client(hostname=self.host, port=self.port)
        await self._client.__aenter__()
        logger.info(f"MQTT connected to {self.host}:{self.port}")

    async def disconnect(self) -> None:
        """
        Closes the active connection client and releases channels.
        """
        if self._client:
            await self._client.__aexit__(None, None, None)

    async def publish(self, topic: str, payload: dict[str, Any]) -> None:
        """
        Serializes payload to JSON format and dispatches it to the topic.

        :param topic: Target MQTT routing key path or channel.
        :type topic: str
        :param payload: JSON serializable values mapping dictionary.
        :type payload: dict
        :raises RuntimeError: If connect method was not run first.
        """
        if not self._client:
            raise RuntimeError("MQTTTransport not connected. Call connect() first.")
        await self._client.publish(topic, json.dumps(payload))
        logger.debug(f"MQTT published to {topic}")

    async def subscribe(self, topic_filter: str) -> AsyncIterator[MessageEnvelope]:
        """
        Subscribes to a channel topic and yields decoded messages.

        :param topic_filter: Topic path or routing key string.
        :type topic_filter: str
        :yield: The normalized MessageEnvelope.
        :ytype: MessageEnvelope
        :raises RuntimeError: If connect method was not run first.
        """
        if not self._client:
            raise RuntimeError("MQTTTransport not connected. Call connect() first.")
        async with self._client.messages() as messages:
            await self._client.subscribe(topic_filter)
            async for msg in messages:
                try:
                    yield MessageEnvelope(
                        topic=str(msg.topic),
                        payload=json.loads(msg.payload),
                    )
                except Exception as exc:
                    logger.warning(f"Skipping malformed MQTT message on {msg.topic}: {exc}")
