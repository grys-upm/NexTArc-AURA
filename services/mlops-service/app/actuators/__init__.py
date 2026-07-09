"""
AURA MLOps Service Actuators Subpackage.
=========================================
Exposes the supported actuators catalog names and information labels mapping.
"""
from __future__ import annotations

from app.sensors import discover_peripherals

def get_actuators_data() -> dict[str, str]:
    """Returns a dictionary mapping actuator identifiers to human-readable labels."""
    return discover_peripherals("actuators")

def get_actuators() -> list[str]:
    """Returns a list of supported actuator identifiers."""
    return sorted(list(get_actuators_data().keys()))

