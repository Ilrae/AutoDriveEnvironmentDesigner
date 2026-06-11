"""Runtime helpers for source and frozen AED execution."""

from __future__ import annotations

import importlib
import os
from pathlib import Path
import sys
from typing import Iterable


APP_RUNTIME_DIRNAME = "AutoDriveEnvironmentDesignerRuntime"


def is_frozen_app() -> bool:
    """Return True when running from a packaged executable."""

    return bool(getattr(sys, "frozen", False))


def get_runtime_workspace_root(source_file: str | Path | None = None) -> Path:
    """Return the writable AED workspace root for the current runtime."""

    if is_frozen_app():
        documents_dir = Path.home() / "Documents"
        workspace_root = documents_dir / APP_RUNTIME_DIRNAME
        return workspace_root.resolve()

    if source_file is None:
        raise ValueError("source_file is required when not running from a frozen build.")
    return Path(source_file).resolve().parents[2]


def ensure_runtime_workspace(root: Path) -> Path:
    """Create the writable AED runtime folders if they do not exist yet."""

    root.mkdir(parents=True, exist_ok=True)
    required_dirs = (
        "docs",
        "experiments",
        "experiments/practical",
        "logs",
        "maps",
        "maps/generated",
        "output",
        "output/doc",
        "output/pdf",
        "results",
        "results/manual_sequence",
        "results/practical",
        "scenarios",
        "scenarios/practical",
    )
    for rel_dir in required_dirs:
        (root / rel_dir).mkdir(parents=True, exist_ok=True)
    return root


def configure_runtime_workspace(source_file: str | Path | None = None) -> Path:
    """Resolve and prepare the writable AED workspace, updating cwd when frozen."""

    workspace_root = ensure_runtime_workspace(get_runtime_workspace_root(source_file))
    if is_frozen_app():
        os.chdir(str(workspace_root))
    return workspace_root


def build_launcher_subprocess_command(launcher_path: Path, extra_args: Iterable[str]) -> list[str]:
    """Build the subprocess command used by the GUI to launch AED tasks."""

    if is_frozen_app():
        return [sys.executable, *list(extra_args)]
    return [sys.executable, "-u", str(launcher_path), *list(extra_args)]


def run_module_main(module_name: str, extra_args: Iterable[str]) -> int:
    """Import one AED module and execute its main() entrypoint with argv."""

    old_argv = sys.argv[:]
    try:
        sys.argv = [module_name, *list(extra_args)]
        module = importlib.import_module(module_name)
        entrypoint = getattr(module, "main", None)
        if entrypoint is None:
            raise RuntimeError(f"Module '{module_name}' does not define main().")
        try:
            entrypoint()
            return 0
        except SystemExit as exc:
            code = exc.code
            if code is None:
                return 0
            if isinstance(code, int):
                return code
            return 1
    finally:
        sys.argv = old_argv
