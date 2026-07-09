"""
AURA Generic Sensor Library: Camera
===================================
Defines the generic proxy class and module-level convenience function shortcuts for cameras.
"""
from __future__ import annotations

from typing import Any
from hardware.utils import get_active_driver, load_specific_driver


class Camera:
    """
    Generic camera device proxy class delegation wrapper.
    """
    LABEL = "Camera"

    def __init__(self, **kwargs: Any) -> None:
        """
        Initializes the camera instance by resolving configuration and mapping drivers.
        """
        driver, params = get_active_driver("camera")
        # Map built-in drivers to rpi_camera_module_3 for local simulation/scripts
        if driver in ("opencv", "libcamera", "template"):
            driver = "rpi_camera_module_3"
        merged_params = {**params, **kwargs}
        driver_cls = load_specific_driver("sensors", "camera", driver)
        try:
            self._delegate = driver_cls(**merged_params)
        except TypeError:
            self._delegate = driver_cls()

    def initialize(self) -> bool:
        """
        Invokes initialization sequences on the delegate camera library.

        :return: True if successful, False otherwise.
        :rtype: bool
        """
        if hasattr(self._delegate, "initialize"):
            return self._delegate.initialize()
        elif hasattr(self._delegate, "open"):
            self._delegate.open({})
            return True
        return True

    def take_photo(self) -> Any:
        """
        Captures a frame or photo using the active camera driver.

        :return: Decoded frame array.
        :rtype: Any
        :raises AttributeError: If no capture methods are supported by the driver.
        """
        if hasattr(self._delegate, "read_value"):
            return self._delegate.read_value()
        elif hasattr(self._delegate, "capture_frame"):
            return self._delegate.capture_frame()
        elif hasattr(self._delegate, "read"):
            return self._delegate.read()
        raise AttributeError("Camera driver has no capture/read method")

    def read_value(self) -> Any:
        """
        Reads camera frames (alias for take_photo).

        :return: Image frame array data.
        :rtype: Any
        """
        return self.take_photo()

    def close(self) -> None:
        """
        Closes camera context resources.
        """
        if hasattr(self._delegate, "close"):
            self._delegate.close()


# Module-level convenience functions using a default global instance
_default_camera = None


def _get_default_camera() -> Camera:
    """
    Retrieves or lazily instantiates the default singleton camera proxy.

    :return: The default global Camera instance.
    :rtype: Camera
    """
    global _default_camera
    if _default_camera is None:
        _default_camera = Camera()
        _default_camera.initialize()
    return _default_camera


def initialize() -> bool:
    """
    Module-level initialization callback proxying the default singleton.

    :return: True if successful, False otherwise.
    :rtype: bool
    """
    return _get_default_camera().initialize()


def take_photo() -> Any:
    """
    Module-level capture callback proxying the default singleton.

    :return: Captured frame.
    :rtype: Any
    """
    return _get_default_camera().take_photo()


def read_value() -> Any:
    """
    Module-level read value callback proxying the default singleton.

    :return: Captured frame.
    :rtype: Any
    """
    return _get_default_camera().read_value()


def close() -> None:
    """
    Closes the global default camera singleton.
    """
    global _default_camera
    if _default_camera is not None:
        _default_camera.close()
        _default_camera = None
