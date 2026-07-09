from __future__ import annotations

from abc import abstractmethod
from typing import Any

from aura_hw.backends.devices.base import DeviceBackend

class OtherBackend(DeviceBackend):
    """Specialised device backend for other peripherals.

    Adds the :meth:`run_action` method.
    """

    @property
    def device_type(self) -> str:
        return "other"

    @abstractmethod
    def run_action(self) -> None:
        """Trigger an action on this other peripheral.

        Raises:
            RuntimeError: If the device is not open.
            IOError: If running the action fails.
        """
        ...

    def read(self) -> Any:
        """Satisfies the DeviceBackend contract."""
        return None
