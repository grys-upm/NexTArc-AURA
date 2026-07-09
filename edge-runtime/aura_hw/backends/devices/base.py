"""
Abstract base class for all AURA device backends.

A *device backend* manages a single physical peripheral connected to
the edge device: a camera, an environmental sensor, a GPIO expander, etc.

Each device backend follows a simple open/read/close lifecycle and
reports its own metadata via :meth:`info`.

Subclasses
----------
* :class:`~aura_hw.backends.devices.camera.base.CameraBackend`
* :class:`~aura_hw.backends.devices.sensor.base.SensorBackend`
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class DeviceBackend(ABC):
    """Lifecycle interface for a single physical device.

    Parameters
    ----------
    component_id:
        The ``id`` field from ``components_config.yaml`` for this device
        (e.g. ``"camera_0"``, ``"env_sensor_0"``).
    """

    def __init__(self, component_id: str) -> None:
        self._component_id = component_id

    @property
    def component_id(self) -> str:
        """Unique component identifier from the config."""
        return self._component_id

    @property
    @abstractmethod
    def device_type(self) -> str:
        """Device category string.

        Returns:
            One of ``"camera"``, ``"sensor"``, ``"gpio"``.
        """
        ...

    @property
    @abstractmethod
    def driver(self) -> str:
        """Driver / backend implementation name.

        Returns:
            A short lowercase identifier such as ``"opencv"``,
            ``"libcamera"``, ``"imx500"``, ``"bme280"``.
        """
        ...

    @abstractmethod
    def open(self, params: dict) -> None:
        """Initialise the device with the given configuration parameters.

        Args:
            params: Dict from the ``params`` block in
                    ``components_config.yaml`` for this component.

        Raises:
            RuntimeError: If the required SDK/driver is not available.
            OSError: If the device cannot be opened (e.g. wrong index).
        """
        ...

    @abstractmethod
    def close(self) -> None:
        """Release all resources held by this device.

        Safe to call even if :meth:`open` has not been called (no-op).
        """
        ...

    @abstractmethod
    def read(self) -> Any:
        """Read the latest data from the device.

        Returns:
            Depends on the subclass:

            * Camera → ``numpy.ndarray`` (BGR frame)
            * Sensor → ``dict`` with measurement values + units
        """
        ...

    @abstractmethod
    def info(self) -> dict:
        """Return a dict describing this device's current state.

        Returns:
            A dict with at minimum:

            * ``component_id`` — same as :attr:`component_id`
            * ``device_type``  — same as :attr:`device_type`
            * ``driver``       — same as :attr:`driver`
            * ``status``       — ``"open"`` or ``"closed"``
        """
        ...
