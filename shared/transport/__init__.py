"""
Abstract transport layer.
=========================
Implemented over MQTT. Designed to be interchangeable (WebSocket, AMQP, etc.)
"""
from __future__ import annotations

from shared.transport.base import TransportBase, MessageEnvelope
from shared.transport.mqtt import MQTTTransport

_transport: TransportBase | None = None


def init_transport(t: TransportBase) -> None:
    """
    Registers the global singleton transport backend instance.

    :param t: Concrete TransportBase class subclass instance.
    :type t: TransportBase
    """
    global _transport
    _transport = t


def get_transport() -> TransportBase:
    """
    Retrieves the global singleton transport backend.

    :return: The active transport instance.
    :rtype: TransportBase
    :raises RuntimeError: If transport has not been initialized.
    """
    if _transport is None:
        raise RuntimeError("Transport not initialized")
    return _transport


__all__ = ["TransportBase", "MessageEnvelope", "MQTTTransport", "init_transport", "get_transport"]
