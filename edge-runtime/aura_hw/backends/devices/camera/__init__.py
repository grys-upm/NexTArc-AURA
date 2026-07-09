"""
Camera device backends for AURA HAL.

All camera backends are loaded dynamically from the ``hardware/``
directory via :class:`GeneralCameraBackend`.
"""
from aura_hw.backends.devices.camera.base import CameraBackend
from aura_hw.backends.devices.camera.general import GeneralCameraBackend

__all__ = [
    "CameraBackend",
    "GeneralCameraBackend",
]
