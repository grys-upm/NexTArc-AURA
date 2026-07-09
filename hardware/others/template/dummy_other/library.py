"""
AURA Other Library: Dummy Template Other Device.
================================================
"""
from __future__ import annotations

from typing import Any


class TemplateOtherLibrary:
    """
    Dummy template other device driver.
    """
    LABEL = "Template Other Device"
    
    def __init__(self, **kwargs: Any) -> None:
        """
        Initializes the dummy other device driver with configuration parameters.
        """
        self.params = kwargs

    def initialize(self) -> bool:
        """
        Initializes the mock template other device driver interface.

        :return: Always returns True.
        :rtype: bool
        """
        return True

    def run_action(self) -> None:
        """
        Performs the mock other device action.
        """
        pass
