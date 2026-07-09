"""
AURA Hardware Shared Utilities.
==============================
Common helpers for resolving device configuration and loading dynamic drivers.
"""
from __future__ import annotations

import importlib
import inspect
import logging
import os
from pathlib import Path
from typing import Any, Callable

import yaml

# Setup logging for this module
logger = logging.getLogger(__name__)


class MockDevice:
    """
    Universal mock device that responds to all method calls without crashing.

    This class serves as a safe fallback when a physical sensor, actuator,
    or camera driver fails to initialize or is missing from the environment.
    """
    
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """
        Initializes the MockDevice.
        """
        pass
        
    def initialize(self) -> bool:
        """
        Mock device initialization callback.

        :return: Always returns True.
        :rtype: bool
        """
        return True
        
    def open(self, params: dict[str, Any]) -> None:
        """
        Mock open driver interface.

        :param params: Dictionary containing configuration properties.
        :type params: dict
        """
        pass
        
    def close(self) -> None:
        """
        Mock close driver interface.
        """
        pass
        
    def read_value(self) -> dict[str, Any]:
        """
        Mock read value interface.

        :return: Status metrics dictionary.
        :rtype: dict
        """
        return {"status": "mock_active"}
        
    def measure(self) -> dict[str, Any]:
        """
        Mock sensor measure interface.

        :return: Status metrics dictionary.
        :rtype: dict
        """
        return self.read_value()
        
    def write_value(self, value: Any) -> None:
        """
        Mock actuator write value interface.

        :param value: The value payload to write.
        :type value: Any
        """
        pass
        
    def write(self, value: Any) -> None:
        """
        Mock actuator write interface.

        :param value: The value payload to write.
        :type value: Any
        """
        pass
        
    def capture_frame(self) -> Any:
        """
        Mock camera capture frame interface.

        :return: A blank 3D numpy array or list array.
        :rtype: Any
        """
        try:
            import numpy as np
            return np.zeros((640, 640, 3), dtype=np.uint8)
        except ImportError:
            return [[[0, 0, 0] for _ in range(640)] for _ in range(640)]
            
    def take_photo(self) -> Any:
        """
        Mock camera take photo interface.

        :return: A blank capture frame.
        :rtype: Any
        """
        return self.capture_frame()
        
    def __getattr__(self, name: str) -> Callable[..., Any]:
        """
        Gracefully resolves any missing methods dynamically on the mock device.

        :param name: Method name string.
        :type name: str
        :return: Callable placeholder function returning None.
        :rtype: Callable
        """
        def mock_method(*args: Any, **kwargs: Any) -> None:
            return None
        return mock_method


def get_config_path() -> Path:
    """
    Finds the components_config.yaml file path across standard setups.

    Looks up environment variable settings first, then checks pre-defined paths.

    :return: The resolved Path configuration object.
    :rtype: Path
    """
    env_path = os.environ.get("AURA_COMPONENTS_CONFIG_PATH")
    if env_path:
        p = Path(env_path)
        if p.exists():
            return p.resolve()

    p = Path("/app/config/components_config.yaml")
    if p.exists():
        return p.resolve()

    p = Path(__file__).parents[1] / "edge-runtime" / "config" / "components_config.yaml"
    if p.exists():
        return p.resolve()

    p = Path("config/components_config.yaml")
    if p.exists():
        return p.resolve()

    return Path("config/components_config.yaml").resolve()


def get_active_driver(device_type: str) -> tuple[str, dict[str, Any]]:
    """
    Finds the configured driver name and params for a given device type.

    Parses the active configuration file to locate enabled component blocks.

    :param device_type: Device classification name (e.g. 'camera', 'gps').
    :type device_type: str
    :return: A tuple of (driver_name, parameters_dict).
    :rtype: tuple
    """
    config_path = get_config_path()
    if not config_path.exists():
        logger.warning(f"components_config.yaml not found at {config_path}. Defaulting to template driver.")
        return "template", {}
    try:
        with open(config_path, encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
            components = config.get("components", [])
            for c in components:
                if c.get("type") == device_type and c.get("enabled", True):
                    return c.get("driver", "template"), c.get("params", {})
    except Exception as e:
        logger.error(f"Error loading components config: {e}")
    return "template", {}


def load_specific_driver(category: str, device_type: str, driver: str) -> type:
    """
    Dynamically loads and returns the main class of a specific device driver.

    Imports driver modules at runtime and inspects classes.

    :param category: Driver category subdirectory ('sensors', 'actuators', 'others').
    :type category: str
    :param device_type: Specific target device folder name.
    :type device_type: str
    :param driver: Target driver name.
    :type driver: str
    :return: The loaded class object type, or MockDevice fallback if loading failed.
    :rtype: type
    """
    module_name = f"hardware.{category}.{device_type}.{driver.lower()}.library"
    try:
        module = importlib.import_module(module_name)
    except ImportError:
        try:
            module = importlib.import_module(f".{driver.lower()}.library", package=f"hardware.{category}.{device_type}")
        except ImportError as e:
            logger.warning(f"Could not load specific driver library for '{driver}' under '{category}/{device_type}': {e}. Falling back to MockDevice.")
            return MockDevice
            
    classes = [obj for name, obj in inspect.getmembers(module, inspect.isclass) 
               if obj.__module__ == module_name or obj.__module__.endswith(f"{driver.lower()}.library")]
               
    if not classes:
        logger.warning(f"No class defined in driver module '{module_name}'. Falling back to MockDevice.")
        return MockDevice
        
    for cls in classes:
        cls_name = cls.__name__.lower()
        if cls_name.endswith("library") or cls_name.endswith("backend") or device_type.lower() in cls_name:
            return cls
            
    return classes[0]
