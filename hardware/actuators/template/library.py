"""
AURA Generic Actuator Library: Template Category
================================================
Defines the generic category loader wrapper class and module-level endpoints for template category actuators.
"""
from __future__ import annotations

from typing import Any
from hardware.utils import get_active_driver, load_specific_driver


class TemplateActuator:
    """
    Template actuator proxy class delegation wrapper.
    """
    LABEL = "Template"
    
    def __init__(self, **kwargs: Any) -> None:
        """
        Initializes the template actuator by dynamically mapping the active driver.
        """
        driver, params = get_active_driver("template")
        if driver == "template":
            driver = "dummy_actuator"
        merged_params = {**params, **kwargs}
        driver_cls = load_specific_driver("actuators", "template", driver)
        try:
            self._delegate = driver_cls(**merged_params)
        except TypeError:
            self._delegate = driver_cls()

    def initialize(self) -> bool:
        """
        Invokes initialization sequence on the delegate actuator library.

        :return: True if successful, False otherwise.
        :rtype: bool
        """
        if hasattr(self._delegate, "initialize"):
            return self._delegate.initialize()
        return True

    def write_value(self, value: Any) -> None:
        """
        Dispatches a control value signal to the delegate actuator instance.

        :param value: Control payload data to write.
        :type value: Any
        :raises AttributeError: If delegate has no write_value method.
        """
        if hasattr(self._delegate, "write_value"):
            self._delegate.write_value(value)
        else:
            raise AttributeError("Template driver has no write_value method")


# Module-level convenience functions using a default global instance
_default_actuator = None


def _get_default_actuator() -> TemplateActuator:
    """
    Retrieves or lazily instantiates the default singleton actuator proxy.

    :return: The global TemplateActuator instance.
    :rtype: TemplateActuator
    """
    global _default_actuator
    if _default_actuator is None:
        _default_actuator = TemplateActuator()
        _default_actuator.initialize()
    return _default_actuator


def initialize() -> bool:
    """
    Module-level initialization callback proxying the default singleton.

    :return: True if successful, False otherwise.
    :rtype: bool
    """
    return _get_default_actuator().initialize()


def write_value(value: Any) -> None:
    """
    Module-level value dispatch callback proxying the default singleton.

    :param value: Payload value to write.
    :type value: Any
    """
    _get_default_actuator().write_value(value)
