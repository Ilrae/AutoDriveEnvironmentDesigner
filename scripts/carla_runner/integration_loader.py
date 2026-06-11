"""Load user-supplied vehicle configs and keyboard-driver modules."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any, Callable


def load_vehicle_integration_config(config_path: str | Path | None) -> dict[str, Any]:
    """Load one optional vehicle-integration JSON file."""

    if not config_path:
        return {}
    path = Path(config_path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"Vehicle integration config file does not exist: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Vehicle integration config must be a JSON object.")
    return payload


def load_driver_control_module(
    module_path: str | Path,
) -> tuple[ModuleType, Callable[[Any, Any, Any], Any], str]:
    """Load one user-supplied keyboard-control module from a file path."""

    path = Path(module_path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"Driver module file does not exist: {path}")

    module_name = f"aed_driver_module_{path.stem}_{abs(hash(str(path)))}"
    spec = importlib.util.spec_from_file_location(module_name, str(path))
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not import driver module from: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    for function_name in (
        "apply_keyboard_control",
        "apply_control",
        "apply_driver_control",
    ):
        candidate = getattr(module, function_name, None)
        if callable(candidate):
            hint = str(
                getattr(module, "CONTROL_HINT", getattr(module, "DRIVER_DISPLAY_NAME", path.name))
            )
            return module, candidate, hint

    raise AttributeError(
        "Driver module must define one of: apply_keyboard_control(keys, control, pygame), "
        "apply_control(keys, control, pygame), or apply_driver_control(keys, control, pygame)."
    )
