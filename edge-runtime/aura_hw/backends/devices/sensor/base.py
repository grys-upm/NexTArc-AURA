"""
Abstract base class for all AURA sensor backends.

A sensor backend wraps a physical measurement device (temperature,
humidity, pressure, air quality, etc.) and exposes a uniform
:meth:`measure` API on top of the :class:`DeviceBackend` lifecycle.

Sensor drivers are loaded dynamically from the ``hardware/`` directory
via :class:`~aura_hw.backends.devices.sensor.general.GeneralSensorBackend`.
"""
from __future__ import annotations

from abc import abstractmethod

from aura_hw.backends.devices.base import DeviceBackend


class SensorBackend(DeviceBackend):
    """Specialised device backend for measurement sensors.

    Adds the :meth:`measure` method, which returns a dict of labelled
    readings with their physical units.
    """

    @property
    def device_type(self) -> str:
        return "sensor"

    @abstractmethod
    def measure(self) -> dict:
        """Read all measurements from the sensor.

        Returns:
            A dict mapping measurement names to values, for example::

                {
                    "temperature_c":  23.4,
                    "humidity_pct":   55.1,
                    "pressure_hpa": 1013.2,
                }

        Raises:
            RuntimeError: If the sensor has not been opened.
            IOError: If the measurement fails (e.g. I2C bus error).
        """
        ...

    def read(self) -> dict:
        """Alias for :meth:`measure` — satisfies the :class:`DeviceBackend` contract."""
        return self.measure()
