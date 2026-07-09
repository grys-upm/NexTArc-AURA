"""
Hardware daemon module.

This module initializes the `daemon` package by dynamically importing all submodules
available in this directory (except `shared`) and exposing those attributes that
end with `_manager` (hardware managers) as global singletons of the package.

This allows other components to import managers directly from `daemon`, for example:
`from daemon import camera_manager`.
"""

import importlib
import pkgutil
from pathlib import Path

# List of variables/attributes that will be exported when using `from daemon import *`
__all__ = []

# Get the directory path of the current package
package_dir = str(Path(__file__).parent)

# Iterate over all Python modules found in the package directory
for _, module_name, _ in pkgutil.iter_modules([package_dir]):
    # Exclude 'shared' module as it contains shared utilities and not managers directly
    if module_name not in ("shared",):
        # Dynamically import the module (e.g. daemon.camera, daemon.hailo, daemon.imx500)
        module = importlib.import_module(f"daemon.{module_name}")
        
        # Traverse all attributes defined within the imported module
        for attr_name in dir(module):
            # If the attribute name ends with '_manager', it is considered a singleton hardware manager
            if attr_name.endswith("_manager"):
                # Register the manager in the global namespace of the daemon package
                globals()[attr_name] = getattr(module, attr_name)
                # Add the manager name to the __all__ export list
                __all__.append(attr_name)


