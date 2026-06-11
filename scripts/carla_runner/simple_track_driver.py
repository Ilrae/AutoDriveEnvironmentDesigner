"""Minimal centerline track follower used for custom OpenDRIVE demo runs."""

from __future__ import annotations

from dataclasses import dataclass, field
import importlib
import math
import os
from pathlib import Path
import sys
from typing import Any


def _ensure_agents_path(pythonapi_path: str | None = None) -> None:
    """Add the CARLA agents package to sys.path when needed."""

    candidate_dirs: list[Path] = []
    for raw_value in (
        pythonapi_path,
        os.environ.get("CARLA_PYTHONAPI"),
        os.environ.get("CARLA_ROOT"),
    ):
        if not raw_value:
            continue

        candidate = Path(raw_value)
        possible_dirs = [
            candidate / "PythonAPI" / "carla",
            candidate / "carla",
            candidate,
        ]
        for possible_dir in possible_dirs:
            if possible_dir.exists() and (possible_dir / "agents").exists():
                candidate_dirs.append(possible_dir)

    seen_paths = set(sys.path)
    for candidate_dir in candidate_dirs:
        candidate_str = str(candidate_dir)
        if candidate_str not in seen_paths:
            sys.path.append(candidate_str)
            seen_paths.add(candidate_str)


def load_vehicle_pid_controller_class(pythonapi_path: str | None = None) -> object:
    """Import CARLA's VehiclePIDController helper."""

    _ensure_agents_path(pythonapi_path)
    controller_module = importlib.import_module("agents.navigation.controller")
    return controller_module.VehiclePIDController


@dataclass
class SimpleTrackDriverConfig:
    """Configuration for the lightweight demo track follower."""

    route_step_distance: float = 2.5
    lookahead_points: int = 6
    target_speed_kmh: float = 8.0
    min_curve_speed_kmh: float = 6.0
    curvature_speed_factor: float = 180.0
    spawn_height_offset: float = 0.6
    max_points: int = 4000
    lateral_pid: dict[str, float] = field(
        default_factory=lambda: {
            "K_P": 1.4,
            "K_D": 0.25,
            "K_I": 0.02,
            "dt": 0.05,
        }
    )
    longitudinal_pid: dict[str, float] = field(
        default_factory=lambda: {
            "K_P": 0.9,
            "K_D": 0.0,
            "K_I": 0.05,
            "dt": 0.05,
        }
    )
    max_throttle: float = 0.35
    max_brake: float = 0.35
    max_steering: float = 0.45


def _normalize_angle(angle_rad: float) -> float:
    while angle_rad > math.pi:
        angle_rad -= 2.0 * math.pi
    while angle_rad < -math.pi:
        angle_rad += 2.0 * math.pi
    return angle_rad


def find_nearest_waypoint_index(
    route: list[Any],
    vehicle_location: Any,
    start_hint: int = 0,
    search_radius: int = 40,
) -> int:
    """Return the index of the nearest route waypoint near the current progress."""

    if not route:
        raise ValueError("route must not be empty")

    route_length = len(route)
    candidate_indices = {
        (start_hint + offset) % route_length
        for offset in range(-search_radius, search_radius + 1)
    }

    nearest_index = start_hint % route_length
    nearest_distance = float("inf")
    for index in candidate_indices:
        waypoint = route[index]
        distance = waypoint.transform.location.distance(vehicle_location)
        if distance < nearest_distance:
            nearest_distance = distance
            nearest_index = index

    return nearest_index


def estimate_route_curvature(route: list[Any], index: int, stride: int = 6) -> float:
    """Estimate local curvature from centerline waypoint headings."""

    route_length = len(route)
    if route_length < 3:
        return 0.0

    heading_a = math.radians(route[index % route_length].transform.rotation.yaw)
    heading_b = math.radians(route[(index + stride) % route_length].transform.rotation.yaw)
    delta_heading = abs(_normalize_angle(heading_b - heading_a))
    distance = max(
        route[index % route_length].transform.location.distance(
            route[(index + stride) % route_length].transform.location
        ),
        1e-6,
    )
    return delta_heading / distance


def compute_target_speed(config: SimpleTrackDriverConfig, curvature: float) -> float:
    """Reduce speed in tighter turns while keeping a stable minimum."""

    scaled_speed = config.target_speed_kmh / (1.0 + (config.curvature_speed_factor * curvature))
    return max(config.min_curve_speed_kmh, min(config.target_speed_kmh, scaled_speed))


def build_centered_spawn_transform(world: Any, reference_transform: Any, z_offset: float) -> Any:
    """Project a reference transform to the center of the driving lane."""

    waypoint = world.get_map().get_waypoint(reference_transform.location)
    if waypoint is None:
        fallback_transform = reference_transform
        fallback_transform.location.z += z_offset
        return fallback_transform

    transform = waypoint.transform
    transform.location.z += z_offset
    return transform


def build_loop_waypoints(
    world: Any,
    start_location: Any,
    step_distance: float,
    max_points: int = 4000,
) -> list[Any]:
    """Sample centerline waypoints around the custom track."""

    start_waypoint = world.get_map().get_waypoint(start_location)
    if start_waypoint is None:
        raise RuntimeError("Could not project the spawn position onto a driving waypoint.")

    waypoints = [start_waypoint]
    current_waypoint = start_waypoint

    for _ in range(max_points):
        next_waypoints = current_waypoint.next(step_distance)
        if not next_waypoints:
            break

        next_waypoint = next_waypoints[0]
        if len(waypoints) > 20:
            distance_to_start = next_waypoint.transform.location.distance(
                start_waypoint.transform.location
            )
            heading_delta = abs(
                _normalize_angle(
                    math.radians(next_waypoint.transform.rotation.yaw)
                    - math.radians(start_waypoint.transform.rotation.yaw)
                )
            )
            if distance_to_start <= step_distance * 2.0 and heading_delta <= 0.35:
                break

        waypoints.append(next_waypoint)
        current_waypoint = next_waypoint

    if len(waypoints) < 20:
        raise RuntimeError("Could not build a long enough centerline route for the track.")

    return waypoints


class SimpleTrackDriver:
    """A small centerline follower for demoing generated oval tracks."""

    def __init__(
        self,
        world: Any,
        vehicle: Any,
        route: list[Any],
        controller: Any,
        config: SimpleTrackDriverConfig,
    ) -> None:
        self.world = world
        self.vehicle = vehicle
        self.route = route
        self.controller = controller
        self.config = config
        self.last_nearest_index = 0

    @classmethod
    def create(
        cls,
        world: Any,
        vehicle: Any,
        pythonapi_path: str | None,
        start_location: Any,
        config: SimpleTrackDriverConfig | None = None,
    ) -> "SimpleTrackDriver":
        active_config = config or SimpleTrackDriverConfig()
        route = build_loop_waypoints(
            world=world,
            start_location=start_location,
            step_distance=active_config.route_step_distance,
            max_points=active_config.max_points,
        )
        VehiclePIDController = load_vehicle_pid_controller_class(pythonapi_path)
        controller = VehiclePIDController(
            vehicle,
            args_lateral=active_config.lateral_pid,
            args_longitudinal=active_config.longitudinal_pid,
            max_throttle=active_config.max_throttle,
            max_brake=active_config.max_brake,
            max_steering=active_config.max_steering,
        )
        return cls(
            world=world,
            vehicle=vehicle,
            route=route,
            controller=controller,
            config=active_config,
        )

    def run_step(self) -> Any:
        """Compute one slow centerline-following control command."""

        vehicle_location = self.vehicle.get_location()
        self.last_nearest_index = find_nearest_waypoint_index(
            self.route,
            vehicle_location,
            start_hint=self.last_nearest_index,
        )
        target_index = (
            self.last_nearest_index + max(1, self.config.lookahead_points)
        ) % len(self.route)
        target_waypoint = self.route[target_index]

        curvature = estimate_route_curvature(
            self.route,
            self.last_nearest_index,
            stride=max(3, self.config.lookahead_points // 2),
        )
        target_speed = compute_target_speed(self.config, curvature)

        return self.controller.run_step(target_speed, target_waypoint)
