"""
Device backends for AURA HAL.

Subpackages
-----------
camera
    Backends for image sensors (USB, CSI, IMX500).
sensor
    Backends for environmental and telemetry sensors (I2C, SPI, UART).
"""
from aura_hw.backends.devices.base import DeviceBackend

__all__ = ["DeviceBackend"]
