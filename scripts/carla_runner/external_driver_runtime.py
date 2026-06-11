"""Helpers for launching user-supplied external driving stacks."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import time


def build_external_driver_environment(
    *,
    host: str,
    port: int,
    role_name: str,
    training_stage: str,
    pythonapi_path: str | None = None,
    blueprint_id: str | None = None,
    xodr_path: str | None = None,
    scenario_path: str | None = None,
    town_id: str | None = None,
    weather_preset: str | None = None,
) -> dict[str, str]:
    """Build environment variables exposed to one external driving command."""

    environment = dict(os.environ)
    environment["AED_HOST"] = str(host)
    environment["AED_PORT"] = str(port)
    environment["AED_EGO_ROLE_NAME"] = str(role_name or "hero")
    environment["AED_TRAINING_STAGE"] = str(training_stage or "track")

    if pythonapi_path:
        environment["AED_PYTHONAPI_PATH"] = str(pythonapi_path)
    if blueprint_id:
        environment["AED_EGO_BLUEPRINT_ID"] = str(blueprint_id)
    if xodr_path:
        environment["AED_XODR_PATH"] = str(xodr_path)
    if scenario_path:
        environment["AED_SCENARIO_PATH"] = str(scenario_path)
    if town_id:
        environment["AED_TOWN_ID"] = str(town_id)
    if weather_preset:
        environment["AED_WEATHER_PRESET"] = str(weather_preset)
    return environment


def launch_external_driver_process(
    command: str,
    *,
    working_dir: str | None = None,
    environment: dict[str, str] | None = None,
    startup_wait_seconds: float = 0.0,
) -> subprocess.Popen[str]:
    """Launch one external command that will control the app-owned ego vehicle."""

    normalized_command = str(command or "").strip()
    if not normalized_command:
        raise ValueError("External driver command must not be empty.")

    cwd_path: Path | None = None
    if working_dir:
        cwd_path = Path(working_dir).expanduser().resolve()
        if not cwd_path.exists():
            raise FileNotFoundError(
                f"External driver working directory does not exist: {cwd_path}"
            )

    process = subprocess.Popen(
        normalized_command,
        cwd=str(cwd_path) if cwd_path is not None else None,
        env=environment,
        shell=True,
    )
    wait_seconds = max(0.0, float(startup_wait_seconds))
    if wait_seconds > 0.0:
        time.sleep(wait_seconds)
    return process


def terminate_external_driver_process(
    process: subprocess.Popen[str] | None,
    *,
    timeout_seconds: float = 5.0,
) -> None:
    """Stop one launched external driving command and its child tree when possible."""

    if process is None or process.poll() is not None:
        return

    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            process.wait(timeout=timeout_seconds)
        except Exception:
            pass
        return

    try:
        process.terminate()
        process.wait(timeout=timeout_seconds)
    except Exception:
        try:
            process.kill()
        except Exception:
            pass
