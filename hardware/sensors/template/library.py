"""
AURA Generic Sensor Library: Template Category
==============================================
Defines the generic proxy class wrapper and module convenience endpoints for template sensors.
"""
from __future__ import annotations

from typing import Any
from hardware.utils import get_active_driver, load_specific_driver


class TemplateSensor:
    """
    Template sensor device proxy delegation wrapper class.
    """
    
    def __init__(self, **kwargs: Any) -> None:
        """
        Initializes the template sensor by resolving active configuration.
        """
        driver, params = get_active_driver("template")
        # Fallback to dummy_sensor if default driver is specified
        if driver == "template":
            driver = "dummy_sensor"
        merged_params = {**params, **kwargs}
        driver_cls = load_specific_driver("sensors", "template", driver)
        try:
            self._delegate = driver_cls(**merged_params)
        except TypeError:
            self._delegate = driver_cls()

    def initialize(self) -> bool:
        """
        Invokes initialization sequence on the delegate sensor library.

        :return: True if successful, False otherwise.
        :rtype: bool
        """
        if hasattr(self._delegate, "initialize"):
            return self._delegate.initialize()
        return True

    def read_value(self) -> Any:
        """
        Reads values from the active sensor delegate.

        :return: Collected sensor values data.
        :rtype: Any
        :raises AttributeError: If driver has no read_value method.
        """
        if hasattr(self._delegate, "read_value"):
            return self._delegate.read_value()
        raise AttributeError("Template driver has no read_value method")


# Module-level convenience functions using a default global instance
_default_sensor = None


def _get_default_sensor() -> TemplateSensor:
    """
    Retrieves or lazily instantiates the default singleton proxy.

    :return: The global TemplateSensor instance.
    :rtype: TemplateSensor
    """
    global _default_sensor
    if _default_sensor is None:
        _default_sensor = TemplateSensor()
        _default_sensor.initialize()
    return _default_sensor


def initialize() -> bool:
    """
    Module-level initialization callback proxying the default singleton.

    :return: True if successful, False otherwise.
    :rtype: bool
    """
    return _get_default_sensor().initialize()


def read_value() -> Any:
    """
    Module-level value collection callback proxying the default singleton.

    :return: Collected values.
    :rtype: Any
    """
    return _get_default_sensor().read_value()
