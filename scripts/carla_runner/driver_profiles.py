"""Driver-profile helpers used to decouple map demos from driving backends."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class DriverMode(str, Enum):
    """Supported driving backends for demo and future app integration."""

    MANUAL = "manual"
    CARLA_AUTOPILOT = "carla_autopilot"
    BASIC_AGENT = "basic_agent"
    WAYPOINT_LOOP = "waypoint_loop"
    DUAL_LIDAR = "dual_lidar"
    EXTERNAL_MODULE = "external_module"


@dataclass(frozen=True)
class DriverProfile:
    """One application-level driving-mode profile."""

    profile_name: str
    mode: DriverMode
    external_entrypoint: str | None = None
    notes: str = ""
    runtime_options: dict[str, Any] = field(default_factory=dict)

    def describe(self) -> str:
        external = self.external_entrypoint or "none"
        return (
            f"profile={self.profile_name}, "
            f"mode={self.mode.value}, "
            f"external_entrypoint={external}"
        )


def create_manual_driver_profile(
    *,
    profile_name: str = "manual_keyboard_driver",
    notes: str = "",
    runtime_options: dict[str, Any] | None = None,
) -> DriverProfile:
    """Build a manual-driving profile for pygame keyboard control."""

    return DriverProfile(
        profile_name=profile_name,
        mode=DriverMode.MANUAL,
        notes=notes,
        runtime_options=runtime_options or {},
    )


def create_carla_autopilot_driver_profile(
    *,
    profile_name: str = "carla_builtin_autopilot",
    notes: str = "",
    runtime_options: dict[str, Any] | None = None,
) -> DriverProfile:
    """Build a CARLA built-in autopilot profile."""

    return DriverProfile(
        profile_name=profile_name,
        mode=DriverMode.CARLA_AUTOPILOT,
        notes=notes,
        runtime_options=runtime_options or {},
    )


def create_external_driver_profile(
    *,
    profile_name: str = "external_driver_module",
    external_entrypoint: str | None = None,
    notes: str = "",
    runtime_options: dict[str, Any] | None = None,
) -> DriverProfile:
    """Build a placeholder profile for user-supplied autonomous-driving code."""

    return DriverProfile(
        profile_name=profile_name,
        mode=DriverMode.EXTERNAL_MODULE,
        external_entrypoint=external_entrypoint,
        notes=notes,
        runtime_options=runtime_options or {},
    )
