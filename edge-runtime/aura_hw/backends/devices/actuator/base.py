from __future__ import annotations

from abc import abstractmethod
from typing import Any

from aura_hw.backends.devices.base import DeviceBackend

class ActuatorBackend(DeviceBackend):
    """Specialised device backend for actuator peripherals.

    Adds the :meth:`write` method, which sets the state/action of the actuator.
    """

    @property
    def device_type(self) -> str:
        return "actuator"

    @abstractmethod
    def write(self, value: Any) -> None:
        """Set or trigger the actuator state/action.

        Args:
            value: The state/command value (e.g. RGB color tuple for LED, bool for relay/buzzer).

        Raises:
            RuntimeError: If the actuator is not open.
            IOError: If writing to the actuator fails.
        """
        ...

    def read(self) -> Any:
        """Satisfies the DeviceBackend contract."""
        return None
