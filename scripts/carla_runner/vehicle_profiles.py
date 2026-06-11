"""Vehicle-profile helpers used to decouple map demos from vehicle choices."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from scripts.carla_runner.vehicle_utils import select_vehicle_blueprint


@dataclass(frozen=True)
class VehicleProfile:
    """One application-level vehicle selection profile."""

    profile_name: str
    blueprint_filter: str = "vehicle.*"
    preferred_blueprint_id: str | None = None
    role_name: str = "hero"
    color: str | None = None
    notes: str = ""

    def describe(self) -> str:
        preferred = self.preferred_blueprint_id or "auto-select"
        return (
            f"profile={self.profile_name}, "
            f"blueprint_filter={self.blueprint_filter}, "
            f"preferred_blueprint={preferred}, "
            f"role_name={self.role_name}"
        )


def create_builtin_vehicle_profile(
    *,
    profile_name: str = "builtin_default_vehicle",
    blueprint_filter: str = "vehicle.*",
    preferred_blueprint_id: str | None = None,
    role_name: str = "hero",
    color: str | None = None,
    notes: str = "",
) -> VehicleProfile:
    """Build a profile for a CARLA built-in vehicle."""

    return VehicleProfile(
        profile_name=profile_name,
        blueprint_filter=blueprint_filter,
        preferred_blueprint_id=preferred_blueprint_id,
        role_name=role_name,
        color=color,
        notes=notes,
    )


def resolve_vehicle_blueprint_for_profile(
    world: Any,
    vehicle_profile: VehicleProfile,
    preferred_blueprint_id: str | None = None,
) -> Any:
    """Resolve and configure a blueprint from a vehicle profile."""

    blueprint_library = world.get_blueprint_library()
    selected_blueprint = None
    active_preferred_id = preferred_blueprint_id or vehicle_profile.preferred_blueprint_id

    if active_preferred_id:
        try:
            selected_blueprint = blueprint_library.find(active_preferred_id)
        except Exception:
            selected_blueprint = None

    if selected_blueprint is None:
        selected_blueprint = select_vehicle_blueprint(
            world,
            vehicle_profile.blueprint_filter,
        )

    if selected_blueprint.has_attribute("role_name"):
        selected_blueprint.set_attribute("role_name", vehicle_profile.role_name)

    if vehicle_profile.color and selected_blueprint.has_attribute("color"):
        selected_blueprint.set_attribute("color", vehicle_profile.color)

    return selected_blueprint
