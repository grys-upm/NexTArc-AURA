import logging
from typing import Any
import numpy as np

from aura_hw.backends.devices.camera.base import CameraBackend
from aura_hw.loader import load_component_class

logger = logging.getLogger(__name__)

class GeneralCameraBackend(CameraBackend):
    """
    General Camera library/wrapper.
    Depending on the driver selected in the config:
      - For built-in drivers ('opencv', 'libcamera', 'imx500'), delegates to the built-in backends.
      - For custom drivers, dynamically loads from hardware/sensors/camera/<driver>/library.py.
    """

    def __init__(self, component_id: str, driver: str) -> None:
        super().__init__(component_id)
        self._driver = driver
        self._delegate = None
        self._is_open = False

    @property
    def driver(self) -> str:
        return self._driver

    def open(self, params: dict) -> None:
        # All camera drivers are loaded dynamically from hardware/sensors/camera/<driver>/library.py
        driver = self._driver
        if driver in ("opencv", "libcamera", "template"):
            driver = "rpi_camera_module_3"
        logger.info(f"[GeneralCameraBackend] Dynamically loading camera driver '{driver}' (configured: '{self._driver}')")
        cls = load_component_class("sensors", "camera", driver)
        self._delegate = cls()

        # Call initialize if defined, else open
        if hasattr(self._delegate, "initialize"):
            success = self._delegate.initialize()
            if not success:
                raise OSError(f"Failed to initialize camera driver '{self._driver}'")
        elif hasattr(self._delegate, "open"):
            self._delegate.open(params)

        self._is_open = True

    def close(self) -> None:
        if self._delegate:
            if hasattr(self._delegate, "close"):
                self._delegate.close()
            self._delegate = None
        self._is_open = False

    def capture_frame(self) -> np.ndarray:
        if not self._is_open or self._delegate is None:
            raise RuntimeError(f"Camera '{self.component_id}' is not open.")

        # Try to call capture_frame, read_value, or read
        if hasattr(self._delegate, "capture_frame"):
            return self._delegate.capture_frame()
        elif hasattr(self._delegate, "read_value"):
            return self._delegate.read_value()
        elif hasattr(self._delegate, "read"):
            return self._delegate.read()
        else:
            raise AttributeError(f"Custom camera driver class has no capture/read method")

    def info(self) -> dict:
        if self._delegate and hasattr(self._delegate, "info"):
            return self._delegate.info()
            
        return {
            "component_id": self.component_id,
            "device_type": self.device_type,
            "driver": self.driver,
            "status": "open" if self._is_open else "closed",
        }
