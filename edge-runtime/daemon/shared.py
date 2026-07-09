"""
Daemon shared configurations and utilities module.

This module loads global hardware configuration from environment variables and YAML files,
sets up shared logging (loggers), and provides helper functions
(such as JSON serialization of NumPy types).
"""

import logging
import os
import sys
from pathlib import Path
from typing import Any

# Setup logger for the entire hardware daemon
logger = logging.getLogger("hardware_daemon")

# Try to import Pillow (PIL) to check if graphical simulation is supported
try:
    from PIL import Image, ImageDraw
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False

#: Bytes of a minimal 1x1 black JPEG image.
#: Serves as a last resort fallback in case Pillow is missing and nothing can be simulated.
MINIMAL_JPEG = b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xff\xdb\x00C\x00\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x14\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xff\xda\x00\x08\x01\x01\x00\x00\x3f\x00\x37\xff\xd9'


def load_config() -> tuple[str, bool]:
    """
    Resolves the hardware type and whether the camera is enabled.

    Resolution priority:
    Environment variables > Configuration file (components_config.yaml) > Default values.

    :return: A tuple containing the hardware type (e.g. 'rpi', 'rpi_ai_cam', 'hailo8') and a boolean indicating if the camera is active.
    :rtype: tuple[str, bool]
    """
    import yaml
    
    # 1. Resolve hardware type from environment variable 'AURA_HARDWARE_TYPE' (defaulting to 'rpi' if not defined or set to 'auto')
    hw_type = os.environ.get("AURA_HARDWARE_TYPE")
    if not hw_type or hw_type.lower() == "auto":
        hw_type = "rpi"  # Default fallback (does not perform physical auto-probing)
    else:
        hw_type = hw_type.lower()

    # 2. Resolve if camera is enabled based on 'AURA_PERIPHERALS' or components YAML
    peripherals_env = os.environ.get("AURA_PERIPHERALS")
    active_peripherals = None
    if peripherals_env:
        try:
            import json
            # Try to parse the env variable as a JSON array or comma-separated list
            if peripherals_env.strip().startswith("["):
                active_peripherals = set(json.loads(peripherals_env))
            else:
                active_peripherals = set(p.strip() for p in peripherals_env.split(",") if p.strip())
        except Exception:
            pass

    camera_enabled = False
    
    # List of possible directories to look for components_config.yaml
    config_dirs = [
        Path(__file__).parents[1] / "config",
        Path("/app/config"),
        Path("./config"),
        Path(".")
    ]
    
    # Search each directory sequentially
    for cdir in config_dirs:
        comp_path = cdir / "components_config.yaml"
        if comp_path.exists():
            try:
                # Read components configuration YAML file
                with open(comp_path, "r", encoding="utf-8") as f:
                    comp_cfg = yaml.safe_load(f) or {}
                    components = comp_cfg.get("components", [])
                    # Search for components of type 'camera' to know if they should be active
                    for comp in components:
                        if comp.get("type") == "camera":
                            comp_id = comp.get("id")
                            # If specific active peripherals are configured in the environment, check by ID
                            if active_peripherals is not None:
                                if comp_id in active_peripherals:
                                    camera_enabled = True
                                    break
                            else:
                                # Otherwise, read the 'enabled' key (defaults to True)
                                if comp.get("enabled", True):
                                    camera_enabled = True
                                    break
            except Exception:
                pass
            break  # Stop searching once the first existing YAML file is found and processed

    return hw_type, camera_enabled


# Load global daemon constants by calling load_config when importing the module
HARDWARE_TYPE, CAMERA_ENABLED = load_config()


def _make_json_serializable(val: Any) -> Any:
    """
    Recursively converts any object or structure into JSON-compatible native types.

    This utility is especially helpful for processing NumPy arrays (for example, bounding
    boxes or sensor outputs) into standard Python lists, and converting NumPy scalar
    types (np.integer, np.floating) into their built-in equivalents.

    :param val: The value or object to serialize.
    :type val: Any
    :return: The converted object compatible with the standard JSON serializer.
    :rtype: Any
    """
    import numpy as np
    
    # Convert NumPy arrays to standard Python lists
    if isinstance(val, np.ndarray):
        return val.tolist()
        
    # Process dictionaries recursively by applying the function to keys and values
    if isinstance(val, dict):
        return {k: _make_json_serializable(v) for k, v in val.items()}
        
    # Process lists or tuples recursively
    if isinstance(val, (list, tuple)):
        return [_make_json_serializable(v) for v in val]
        
    # Convert NumPy scalar types (fixed-precision integers/floats) to native Python types (int/float)
    if isinstance(val, (np.integer, np.floating)):
        return val.item()
        
    # Return value unchanged if it is already a native serializable type
    return val
