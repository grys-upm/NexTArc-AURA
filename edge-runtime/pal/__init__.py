"""
PAL — Hardware-Agnostic Core
=============================
Public surface of the Platform Abstraction Layer.

Exports
-------
CommunicationClient
    Async MQTT wrapper with automatic reconnection.
OTAHandler
    Download + SHA-256 verification of model and script artefacts.
Orchestrator
    Manages the inference loop and the telemetry loop.
"""

# Import the primary PAL classes to expose them directly at the package level
from pal.comm_client import CommunicationClient
from pal.ota_handler import OTAHandler
from pal.orchestrator import Orchestrator

# Define the package's public API surface
__all__ = ["CommunicationClient", "OTAHandler", "Orchestrator"]

