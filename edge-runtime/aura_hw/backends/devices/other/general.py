import logging
from typing import Any

from aura_hw.backends.devices.other.base import OtherBackend
from aura_hw.loader import load_component_class

logger = logging.getLogger(__name__)

class GeneralOtherBackend(OtherBackend):
    """
    General Other library/wrapper.
    Dynamically loads custom other from hardware/others/<device_type>/<driver>/library.py.
    """

    def __init__(self, component_id: str, device_type: str, driver: str) -> None:
        super().__init__(component_id)
        self._device_type = device_type
        self._driver = driver
        self._delegate = None
        self._is_open = False

    @property
    def device_type(self) -> str:
        return self._device_type

    @property
    def driver(self) -> str:
        return self._driver

    def open(self, params: dict) -> None:
        logger.info(f"[GeneralOtherBackend] Dynamically loading custom {self._device_type} driver '{self._driver}'")
        cls = load_component_class("others", self._device_type, self._driver)

        try:
            self._delegate = cls(**params)
        except TypeError:
            self._delegate = cls()

        if hasattr(self._delegate, "initialize"):
            success = self._delegate.initialize()
            if not success:
                raise OSError(f"Failed to initialize custom {self._device_type} driver '{self._driver}'")
        elif hasattr(self._delegate, "open"):
            self._delegate.open(params)

        self._is_open = True

    def close(self) -> None:
        if self._delegate:
            if hasattr(self._delegate, "close"):
                self._delegate.close()
            self._delegate = None
        self._is_open = False

    def run_action(self) -> None:
        if not self._is_open or self._delegate is None:
            raise RuntimeError(f"Other device '{self.component_id}' is not open.")

        if hasattr(self._delegate, "run_action"):
            self._delegate.run_action()
        elif hasattr(self._delegate, "write_value"):
            self._delegate.write_value(None)
        else:
            raise AttributeError(f"Custom {self._device_type} driver class has no run_action/write_value method")

    def info(self) -> dict:
        if self._delegate and hasattr(self._delegate, "info"):
            return self._delegate.info()

        return {
            "component_id": self.component_id,
            "device_type": self.device_type,
            "driver": self.driver,
            "status": "open" if self._is_open else "closed",
        }
