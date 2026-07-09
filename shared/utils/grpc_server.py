"""
gRPC server helper for AURA services.
====================================
Provides a serve coroutine that wires up an asyncio gRPC
server with server reflection enabled, making it compatible with tools
such as grpcurl and Postman.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Callable, Any

import grpc
from grpc_reflection.v1alpha import reflection

# Setup logging for this module
logger = logging.getLogger(__name__)


async def serve(
    port: int,
    add_servicer_fn: Callable[[Any, grpc.aio.Server], None],
    servicer_instance: Any,
    service_names: list[str],
) -> None:
    """
    Starts an async gRPC server with reflection.

    Creates a grpc.aio.Server, registers the given servicer,
    enables server reflection, binds to [::]:{port} and waits for
    termination.

    :param port: TCP port to listen on.
    :type port: int
    :param add_servicer_fn: The generated add_XxxServicer_to_server function.
    :type add_servicer_fn: Callable
    :param servicer_instance: An instance of the concrete servicer class.
    :type servicer_instance: Any
    :param service_names: List of fully-qualified service names used for reflection.
    :type service_names: list
    """
    server = grpc.aio.server()
    add_servicer_fn(servicer_instance, server)
    reflection.enable_server_reflection(
        service_names + [reflection.SERVICE_NAME], server
    )
    server.add_insecure_port(f"[::]:{port}")
    await server.start()
    logger.info(f"gRPC server listening on :{port}")
    await server.wait_for_termination()
