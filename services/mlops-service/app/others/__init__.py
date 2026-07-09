"""
AURA MLOps Service Others Subpackage.
=====================================
Exposes other supported auxiliary peripheral catalog names and labels.
"""
from __future__ import annotations

from app.sensors import discover_peripherals

def get_others_data() -> dict[str, str]:
    """Returns a dictionary mapping peripheral identifiers to human-readable labels."""
    return discover_peripherals("others")

def get_others() -> list[str]:
    """Returns a list of other supported peripheral identifiers."""
    return sorted(list(get_others_data().keys()))

