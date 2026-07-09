"""gRPC stubs singleton for the gateway.

Manages the initialization and retrieval of asynchronous gRPC service stubs.
"""
from typing import Any
import grpc
from shared.proto_gen import (
    device_pb2_grpc, ai_pb2_grpc, script_pb2_grpc,
    compilation_pb2_grpc, deployment_pb2_grpc, monitoring_pb2_grpc,
)
from app.config import get_settings

_stubs: dict = {}
"""Private dictionary containing the active, shared gRPC service stubs."""

def init_stubs() -> None:
    """Initializes all gRPC channel connections and binds stub instances.

    Reads endpoint configuration parameters and creates asynchronous,
    insecure gRPC channels for the respective services.
    """
    s = get_settings()
    _stubs["device"]      = device_pb2_grpc.DeviceServiceStub(grpc.aio.insecure_channel(s.device_service_grpc))
    _stubs["ai"]          = ai_pb2_grpc.AIServiceStub(grpc.aio.insecure_channel(s.ai_service_grpc))
    _stubs["script"]      = script_pb2_grpc.ScriptServiceStub(grpc.aio.insecure_channel(s.script_service_grpc))
    _stubs["compilation"] = compilation_pb2_grpc.CompilationServiceStub(grpc.aio.insecure_channel(s.compilation_service_grpc))
    _stubs["deployment"]  = deployment_pb2_grpc.DeploymentServiceStub(grpc.aio.insecure_channel(s.deployment_service_grpc))
    _stubs["monitoring"]  = monitoring_pb2_grpc.MonitoringServiceStub(grpc.aio.insecure_channel(s.monitoring_service_grpc))

def get_stub(name: str) -> Any:
    """Retrieves an initialized gRPC stub by its unique key.

    Args:
        name: The key corresponding to the target service (e.g. "device", "ai").

    Returns:
        The requested asynchronous gRPC Stub object.
    """
    return _stubs[name]

