"""Application-facing input binding models for vehicle and driver integration."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from scripts.carla_runner.driver_profiles import DriverProfile
from scripts.carla_runner.vehicle_profiles import VehicleProfile


class InputBindingMode(str, Enum):
    """How the app receives driving-stack inputs."""

    SPLIT = "split"
    BUNDLED = "bundled"


@dataclass(frozen=True)
class SimulationInputBinding:
    """One resolved integration contract between the app and a driving stack."""

    binding_mode: InputBindingMode
    driver_profile: DriverProfile
    vehicle_profile: VehicleProfile | None = None
    notes: str = ""

    def describe(self) -> str:
        vehicle_name = self.vehicle_profile.profile_name if self.vehicle_profile else "driver-owned"
        return (
            f"binding_mode={self.binding_mode.value}, "
            f"vehicle_profile={vehicle_name}, "
            f"driver_profile={self.driver_profile.profile_name}"
        )


def create_split_input_binding(
    *,
    vehicle_profile: VehicleProfile,
    driver_profile: DriverProfile,
    notes: str = "",
) -> SimulationInputBinding:
    """Use separate application inputs for vehicle selection and driving backend."""

    return SimulationInputBinding(
        binding_mode=InputBindingMode.SPLIT,
        vehicle_profile=vehicle_profile,
        driver_profile=driver_profile,
        notes=notes,
    )


def create_bundled_input_binding(
    *,
    vehicle_profile: VehicleProfile,
    driver_profile: DriverProfile,
    notes: str = "",
) -> SimulationInputBinding:
    """Use one external package input, while keeping vehicle spawn in the app."""

    return SimulationInputBinding(
        binding_mode=InputBindingMode.BUNDLED,
        vehicle_profile=vehicle_profile,
        driver_profile=driver_profile,
        notes=notes,
    )
