"""
Abstract transport layer for AURA cloud-to-edge communication.
==============================================================
Defines the TransportBase interface and MessageEnvelope
data class so that MQTT can be swapped for WebSocket, AMQP or any other
broker without changing business logic.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import AsyncIterator, Any


@dataclass
class MessageEnvelope:
    """
    A normalised message independent of the underlying transport.
    """
    topic: str
    payload: dict[str, Any]
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class TransportBase(ABC):
    """
    Abstract base class for pluggable transport implementations.

    Concrete implementations must override all four abstract methods.
    """

    @abstractmethod
    async def connect(self) -> None:
        """
        Establish a connection to the broker.
        """
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """
        Close the connection and release resources.
        """
        pass

    @abstractmethod
    async def publish(self, topic: str, payload: dict[str, Any]) -> None:
        """
        Publish a message to the target topic.

        :param topic: Destination topic or routing key.
        :type topic: str
        :param payload: Python dict that will be serialised to JSON.
        :type payload: dict
        """
        pass

    @abstractmethod
    async def subscribe(self, topic_filter: str) -> AsyncIterator[MessageEnvelope]:
        """
        Subscribe to a topic filter and yield incoming messages.

        :param topic_filter: Topic or wildcard filter, e.g. "device/+/events".
        :type topic_filter: str
        :yield: MessageEnvelope for each received message.
        :ytype: MessageEnvelope
        """
        pass
