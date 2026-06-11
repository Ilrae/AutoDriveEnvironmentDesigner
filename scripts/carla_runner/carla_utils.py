"""Helpers for importing CARLA and connecting to a running simulator."""

from __future__ import annotations

import importlib
import os
from pathlib import Path
import sys
from typing import Any


def _append_sys_path(candidate: Path, seen_paths: set[str]) -> None:
    candidate_str = str(candidate)
    if candidate_str not in seen_paths and candidate.exists():
        sys.path.append(candidate_str)
        seen_paths.add(candidate_str)


def _iter_pythonapi_candidates(explicit_path: str | None = None) -> list[Path]:
    raw_candidates: list[str] = []

    for raw_value in (
        explicit_path,
        os.environ.get("CARLA_PYTHONAPI"),
        os.environ.get("CARLA_ROOT"),
        r"D:\CARLA",
        r"C:\CARLA",
    ):
        if raw_value:
            raw_candidates.append(raw_value)

    egg_candidates: list[Path] = []
    directory_candidates: list[Path] = []
    seen_eggs: set[str] = set()
    seen_dirs: set[str] = set()

    for raw_candidate in raw_candidates:
        candidate = Path(raw_candidate)
        candidate_str = str(candidate)

        if candidate.suffix == ".egg" and candidate.exists():
            if candidate_str not in seen_eggs:
                egg_candidates.append(candidate)
                seen_eggs.add(candidate_str)
            continue

        dist_dir = candidate / "PythonAPI" / "carla" / "dist"
        if dist_dir.exists():
            for egg_path in sorted(dist_dir.glob("*.egg")):
                egg_str = str(egg_path)
                if egg_str not in seen_eggs:
                    egg_candidates.append(egg_path)
                    seen_eggs.add(egg_str)

        python_api_dir = candidate / "PythonAPI"
        if python_api_dir.exists():
            python_api_str = str(python_api_dir)
            if python_api_str not in seen_dirs:
                directory_candidates.append(python_api_dir)
                seen_dirs.add(python_api_str)
            agents_dir = python_api_dir / "carla"
            agents_dir_str = str(agents_dir)
            if agents_dir.exists() and agents_dir_str not in seen_dirs:
                directory_candidates.append(agents_dir)
                seen_dirs.add(agents_dir_str)

    # The CARLA .egg contains the real API. Importing PythonAPI/carla first can
    # create a namespace package without Client/OpendriveGenerationParameters,
    # so we always try eggs before plain directories.
    return egg_candidates + directory_candidates


def load_carla_module(pythonapi_path: str | None = None) -> Any:
    """Import the CARLA Python API after trying common install paths."""

    seen_paths = set(sys.path)
    for candidate in _iter_pythonapi_candidates(pythonapi_path):
        _append_sys_path(candidate, seen_paths)

    try:
        return importlib.import_module("carla")
    except ImportError as first_error:
        last_error = first_error
    try:
        return importlib.import_module("carla")
    except ImportError as import_error:
        last_error = import_error

    raise RuntimeError(
        "Could not import the CARLA Python API. Install the CARLA package in your "
        "virtual environment or set CARLA_ROOT/CARLA_PYTHONAPI to the CARLA install path."
    ) from last_error


def create_client(
    host: str = "localhost",
    port: int = 2000,
    timeout: float = 10.0,
    pythonapi_path: str | None = None,
) -> tuple[Any, Any, Any]:
    """Create a CARLA client and return the module, client, and world."""

    carla = load_carla_module(pythonapi_path)
    client = carla.Client(host, port)
    client.set_timeout(timeout)
    world = client.get_world()
    return carla, client, world
