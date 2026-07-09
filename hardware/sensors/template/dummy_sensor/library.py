"""
AURA Sensor Library: Dummy Template Sensor.
==========================================
"""
from __future__ import annotations

from typing import Any

LABEL = "Template Sensor"


class TemplateSensorLibrary:
    """
    Dummy template sensor driver implementation.
    """
    
    def __init__(self, **kwargs: Any) -> None:
        """
        Initializes the dummy sensor driver with config parameters.
        """
        self.params = kwargs

    def initialize(self) -> bool:
        """
        Initializes mock sensor interfaces.

        :return: Always returns True.
        :rtype: bool
        """
        return True

    def read_value(self) -> dict[str, Any]:
        """
        Reads mock metric values.

        :return: Metric values dictionary.
        :rtype: dict
        """
        return {"value": 42}
