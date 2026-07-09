"""
AURA GPS Sensor Library: Simulated GPS.
=======================================
Generates dummy GPS coordinates with coordinates loading from configuration and small random drift simulation.
"""
from __future__ import annotations

import random
from pathlib import Path
from typing import Any

import yaml


class GPSSimulated:
    """
    Simulated GPS sensor implementation.
    """
    LABEL = "Simulated GPS"

    def __init__(self, **kwargs: Any) -> None:
        """
        Initializes the simulated GPS driver.
        """
        self.coords = [-3.6294, 40.3897]  # Default fallback
        self.load_initial_coordinates()

    def load_initial_coordinates(self) -> None:
        """
        Looks up configuration settings to set initial coordinate values.
        """
        config_dirs = [
            Path("/app/config"),
            Path(__file__).parents[4] / "edge-runtime" / "config",
            Path("config"),
            Path(".")
        ]
        for cdir in config_dirs:
            device_path = cdir / "device_config.yaml"
            if device_path.exists():
                try:
                    with open(device_path, "r", encoding="utf-8") as f:
                        cfg = yaml.safe_load(f) or {}
                        coords = cfg.get("coordinates")
                        if coords and isinstance(coords, list) and len(coords) == 2:
                            self.coords = [float(coords[0]), float(coords[1])]
                            break
                except Exception:
                    pass

    def initialize(self) -> bool:
        """
        Initializes the simulated sensor.

        :return: Always returns True.
        :rtype: bool
        """
        return True

    def read_value(self) -> list[float]:
        """
        Collects active coordinate values and updates internally with small movement drifts.

        :return: A list containing [longitude, latitude].
        :rtype: list
        """
        current = list(self.coords)
        # Add a small random drift to simulate movement (approx 1-10 meters, very small delta)
        # 0.0001 degrees is roughly 11 meters
        delta_lon = random.uniform(-0.0001, 0.0001)
        delta_lat = random.uniform(-0.0001, 0.0001)
        self.coords[0] = round(self.coords[0] + delta_lon, 6)
        self.coords[1] = round(self.coords[1] + delta_lat, 6)
        return current

    def close(self) -> None:
        """
        Releases driver interfaces.
        """
        pass
