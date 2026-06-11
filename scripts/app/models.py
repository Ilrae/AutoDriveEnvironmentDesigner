"""Application-layer session models for the future AED UI."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from scripts.carla_runner.driver_profiles import DriverProfile
from scripts.carla_runner.input_bindings import SimulationInputBinding
from scripts.carla_runner.vehicle_profiles import VehicleProfile


@dataclass(frozen=True)
class CarlaRuntimeSpec:
    """Runtime configuration owned by the application."""

    host: str = "localhost"
    port: int = 2000
    timeout_sec: float = 30.0
    pythonapi_path: str | None = None
    spectator_mode: str = "fixed-overview"


@dataclass(frozen=True)
class MapGenerationSpec:
    """Map-generation configuration resolved by the app."""

    generator_mode: str
    generated_dir: Path
    manifest_dir: Path
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EvaluationSpec:
    """Evaluation policy resolved by the app."""

    path_tolerance_m: float = 1.5
    offroad_margin_m: float = 0.25
    finish_line_half_width_m: float = 6.0
    fail_on_collision: bool = True
    fail_on_course_departure: bool = True
    fail_on_not_finished: bool = True


@dataclass(frozen=True)
class SessionUiSpec:
    """Current UI strategy used by the application."""

    mode: str = "pygame_manual_demo"
    notes: str = ""


@dataclass(frozen=True)
class ApplicationSessionSpec:
    """Full application-level contract for one AED session."""

    session_name: str
    runtime: CarlaRuntimeSpec
    map_generation: MapGenerationSpec
    vehicle_profile: VehicleProfile
    driver_profile: DriverProfile
    input_binding: SimulationInputBinding
    evaluation: EvaluationSpec
    ui: SessionUiSpec
