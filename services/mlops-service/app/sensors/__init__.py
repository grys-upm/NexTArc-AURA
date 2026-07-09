"""
AURA MLOps Service Sensors Subpackage.
======================================
Exposes supported sensors catalog names and labels.
"""
from __future__ import annotations

import ast
import os
from pathlib import Path

def get_hardware_dir() -> Path:
    """Resolves the absolute path to the project's hardware directory."""
    p = Path("/app/hardware")
    if p.exists():
        return p
    return Path(__file__).parents[4] / "hardware"

def get_label_from_library_file(file_path: Path) -> str | None:
    """Statically parses a Python file to locate the value of the `LABEL` variable.
    
    Checks both module-level and class-level definitions.
    """
    try:
        tree = ast.parse(file_path.read_text(encoding="utf-8"))
        # 1. Look for module-level assignment
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "LABEL":
                        return ast.literal_eval(node.value)
        # 2. Look for class-level assignment
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                for subnode in node.body:
                    if isinstance(subnode, ast.Assign):
                        for target in subnode.targets:
                            if isinstance(target, ast.Name) and target.id == "LABEL":
                                return ast.literal_eval(subnode.value)
    except Exception:
        pass
    return None

def discover_peripherals(category: str) -> dict[str, str]:
    """Dynamically scans the hardware directory for a specific peripheral category."""
    data = {}
    hardware_dir = get_hardware_dir()
    category_dir = hardware_dir / category
    if not category_dir.exists():
        return data
    
    for subcat in category_dir.iterdir():
        if subcat.is_dir() and not subcat.name.startswith("__"):
            for driver in subcat.iterdir():
                if driver.is_dir() and not driver.name.startswith("__"):
                    lib_file = driver / "library.py"
                    if lib_file.exists():
                        identifier = f"{subcat.name}/{driver.name}"
                        label = get_label_from_library_file(lib_file) or driver.name
                        data[identifier] = label
    return data

def get_sensors_data() -> dict[str, str]:
    """Returns a dictionary mapping sensor identifiers to human-readable labels."""
    return discover_peripherals("sensors")

def get_sensors() -> list[str]:
    """Returns a sorted list of supported sensor identifiers."""
    return sorted(list(get_sensors_data().keys()))

