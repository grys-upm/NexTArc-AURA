"""
Sensor device backends for AURA HAL.

All sensor backends are loaded dynamically from the ``hardware/``
directory via :class:`GeneralSensorBackend`.
"""
from aura_hw.backends.devices.sensor.base import SensorBackend
from aura_hw.backends.devices.sensor.general import GeneralSensorBackend

__all__ = ["SensorBackend", "GeneralSensorBackend"]
