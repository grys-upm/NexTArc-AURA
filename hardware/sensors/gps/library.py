"""
AURA Generic Sensor Library: GPS
================================
Defines the generic proxy wrapper class for GPS sensors.
"""
from __future__ import annotations

from typing import Any
from hardware.utils import get_active_driver, load_specific_driver


class GPSSensor:
    """
    Generic GPS sensor proxy class delegation wrapper.
    """
    LABEL = "GPS"

    def __init__(self, **kwargs: Any) -> None:
        """
        Initializes the GPS sensor by resolving configuration and mapping drivers.
        """
        driver, params = get_active_driver("gps")
        if driver == "gps":
            driver = "gps_simulated"
        merged_params = {**params, **kwargs}
        driver_cls = load_specific_driver("sensors", "gps", driver)
        try:
            self._delegate = driver_cls(**merged_params)
        except TypeError:
            self._delegate = driver_cls()

    def initialize(self) -> bool:
        """
        Invokes initialization sequence on the delegate GPS driver library.

        :return: True if successful, False otherwise.
        :rtype: bool
        """
        if hasattr(self._delegate, "initialize"):
            return self._delegate.initialize()
        return True

    def read_value(self) -> list[float]:
        """
        Reads coordinates from the active GPS driver.

        :return: A list of float coordinates [longitude, latitude].
        :rtype: list
        :raises AttributeError: If driver has no read_value method.
        """
        if hasattr(self._delegate, "read_value"):
            return self._delegate.read_value()
        raise AttributeError("GPS driver has no read_value method")
