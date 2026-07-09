"""
AURA Generic Other Library: Template Category
============================================
Defines the wrapper proxy and module-level endpoints for template other devices.
"""
from __future__ import annotations

from typing import Any
from hardware.utils import get_active_driver, load_specific_driver


class TemplateOther:
    """
    Template other device proxy class delegation wrapper.
    """
    LABEL = "Template"
    
    def __init__(self, **kwargs: Any) -> None:
        """
        Initializes the template other device by dynamically mapping the active driver.
        """
        driver, params = get_active_driver("template")
        if driver == "template":
            driver = "dummy_other"
        merged_params = {**params, **kwargs}
        driver_cls = load_specific_driver("others", "template", driver)
        try:
            self._delegate = driver_cls(**merged_params)
        except TypeError:
            self._delegate = driver_cls()

    def initialize(self) -> bool:
        """
        Invokes initialization sequence on the delegate library.

        :return: True if successful, False otherwise.
        :rtype: bool
        """
        if hasattr(self._delegate, "initialize"):
            return self._delegate.initialize()
        return True

    def run_action(self) -> None:
        """
        Dispatches a action invocation to the delegate instance.

        :raises AttributeError: If delegate has no run_action method.
        """
        if hasattr(self._delegate, "run_action"):
            self._delegate.run_action()
        else:
            raise AttributeError("Template other driver has no run_action method")


# Module-level convenience functions using a default global instance
_default_other = None


def _get_default_other() -> TemplateOther:
    """
    Retrieves or lazily instantiates the default singleton proxy.

    :return: The global TemplateOther instance.
    :rtype: TemplateOther
    """
    global _default_other
    if _default_other is None:
        _default_other = TemplateOther()
        _default_other.initialize()
    return _default_other


def initialize() -> bool:
    """
    Module-level initialization callback proxying the default singleton.

    :return: True if successful, False otherwise.
    :rtype: bool
    """
    return _get_default_other().initialize()


def run_action() -> None:
    """
    Module-level action execution callback proxying the default singleton.
    """
    _get_default_other().run_action()
