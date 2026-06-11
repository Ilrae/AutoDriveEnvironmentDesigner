"""Load an existing OpenDRIVE map, spawn a vehicle, and drive manually with pygame."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
from datetime import datetime
import json
import math
from pathlib import Path
import random
import sys
import time
from typing import Any

import pygame

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[2]))

from scripts.carla_runner.carla_utils import create_client
from scripts.carla_runner.driver_profiles import (
    create_external_driver_profile,
    create_manual_driver_profile,
)
from scripts.carla_runner.external_driver_runtime import (
    build_external_driver_environment,
    launch_external_driver_process,
    terminate_external_driver_process,
)
from scripts.carla_runner.integration_loader import (
    load_driver_control_module,
    load_vehicle_integration_config,
)
from scripts.carla_runner.finish_line_visuals import (
    draw_centerline_overlay,
    draw_finish_line_overlay,
    draw_finish_line_marker,
    spawn_finish_line_marker_props,
)
from scripts.carla_runner.input_bindings import create_split_input_binding
from scripts.carla_runner.load_xodr_in_carla import (
    create_generation_parameters,
    load_opendrive_world,
)
from scripts.carla_runner.post_run_review import (
    build_episode_result_from_overlay,
    build_result_comparison_lines,
    build_track_adaptation_lines,
    draw_review_panel,
)
from scripts.carla_runner.run_manual_track_demo import (
    create_camera_sensor,
    update_follow_vehicle_spectator,
)
from scripts.carla_runner.simple_track_driver import build_centered_spawn_transform
from scripts.carla_runner.vehicle_profiles import (
    create_builtin_vehicle_profile,
    resolve_vehicle_blueprint_for_profile,
)
from scripts.carla_runner.vehicle_utils import (
    attach_collision_sensor,
    destroy_actor,
    select_spawn_point,
)
from scripts.evaluation.path_metrics import (
    FinishLine,
    PathPoint,
    PathEvaluationSummary,
    TrajectorySample,
    evaluate_trajectory_against_paths,
    interpolate_path_point,
    project_point_to_path,
    sample_path_from_config,
)
from scripts.evaluation.scoring import compute_driving_score as compute_episode_driving_score
from scripts.evaluation.target_modes import (
    resolve_evaluation_target_mode,
    uses_road_center_target,
)
from scripts.evaluation.result_models import EpisodeResult, save_episode_result
from scripts.map_generator.level_generator import build_straight_road_config_from_level
from scripts.map_generator.opendrive_writer import (
    RoadGeometrySegment,
    StraightRoadConfig,
    build_open_course_config,
)
from scripts.map_generator.track_contract import (
    FinishLineContract,
    build_default_finish_line_contract,
)


@dataclass
class XodrEvaluationContext:
    """Runtime evaluation state for one manually driven XODR episode."""

    config: StraightRoadConfig
    finish_line_contract: FinishLineContract
    road_reference_path: list[PathPoint]
    raw_target_path: list[PathPoint]
    target_path: list[PathPoint]
    evaluation_target_mode: str
    finish_line: FinishLine
    finish_marker_actors: list[Any]
    show_centerline: bool
    collision_sensor: Any
    collision_state: dict[str, float]
    trajectory_samples: list[TrajectorySample]
    started_monotonic: float
    last_sample_time_sec: float = -1.0
    finish_crossed_override: bool = False
    finish_sample_count: int | None = None
    finish_score_overlay: "FinishScoreOverlay | None" = None


@dataclass(frozen=True)
class FinishScoreOverlay:
    """One runtime finish summary shown immediately after crossing the finish line."""

    success: bool
    failure_reason: str | None
    driving_score: float
    time_sec: float
    collision_count: int
    path_match_score: float
    path_tracking_score: float
    lane_discipline_score: float
    lane_departure_ratio: float
    opposite_lane_ratio: float
    offroad_ratio: float
    completion_ratio: float
    mean_lateral_error_m: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Load an existing .xodr map, spawn a vehicle, and drive it manually.",
    )
    parser.add_argument("--xodr-path", type=Path, required=True, help="OpenDRIVE file to load.")
    parser.add_argument(
        "--manifest-dir",
        type=Path,
        default=Path("experiments"),
        help="Directory used to look up the matching generation manifest.",
    )
    parser.add_argument("--host", default="localhost", help="CARLA server host.")
    parser.add_argument("--port", type=int, default=2000, help="CARLA server port.")
    parser.add_argument("--timeout", type=float, default=30.0, help="Connection timeout in seconds.")
    parser.add_argument(
        "--pythonapi-path",
        default=None,
        help="Path to the CARLA root, PythonAPI directory, dist directory, or .egg file.",
    )
    parser.add_argument(
        "--training-stage",
        default="track",
        help="Current AED stage label used for logs and external integration hints.",
    )
    parser.add_argument(
        "--blueprint-filter",
        default="vehicle.*",
        help="Blueprint filter for selecting a CARLA built-in vehicle.",
    )
    parser.add_argument(
        "--preferred-blueprint-id",
        default=None,
        help="Optional fixed blueprint id. If omitted, one is chosen from --blueprint-filter.",
    )
    parser.add_argument("--role-name", default=None, help="CARLA role_name attribute.")
    parser.add_argument(
        "--integration-custom-enabled",
        action="store_true",
        help="Enable one custom ego vehicle / driver integration override.",
    )
    parser.add_argument(
        "--driver-backend",
        choices=("manual", "external_module", "external_command"),
        default="manual",
        help="Driving backend used after the app spawns the ego vehicle.",
    )
    parser.add_argument(
        "--vehicle-config-path",
        default=None,
        help="Optional JSON file describing ego vehicle overrides such as blueprint id and color.",
    )
    parser.add_argument(
        "--driver-module-path",
        default=None,
        help="Optional Python file that overrides the built-in manual keyboard-control mapping.",
    )
    parser.add_argument(
        "--external-driver-command",
        default=None,
        help="Optional shell command launched after ego spawn for ROS or autonomy integration.",
    )
    parser.add_argument(
        "--external-driver-working-dir",
        default=None,
        help="Optional working directory used when launching the external driving command.",
    )
    parser.add_argument(
        "--external-driver-startup-wait",
        type=float,
        default=2.0,
        help="Seconds to wait after launching the external driving command before the drive loop begins.",
    )
    parser.add_argument("--spawn-index", type=int, default=0, help="Spawn point index on the loaded map.")
    parser.add_argument("--spawn-height-offset", type=float, default=0.6, help="Height offset for spawn centering.")
    parser.add_argument("--resolution", default="1280x720", help="Pygame camera window resolution.")
    parser.add_argument("--camera-distance", type=float, default=8.0, help="Chase camera distance in meters.")
    parser.add_argument("--camera-height", type=float, default=3.0, help="Chase camera height in meters.")
    parser.add_argument("--camera-pitch", type=float, default=-14.0, help="Chase camera pitch in degrees.")
    parser.add_argument(
        "--spectator-mode",
        choices=("fixed-overview", "follow"),
        default="fixed-overview",
        help="Server window spectator mode.",
    )
    parser.add_argument("--follow-distance", type=float, default=14.0, help="Spectator follow distance.")
    parser.add_argument("--follow-height", type=float, default=5.5, help="Spectator follow height.")
    parser.add_argument("--follow-pitch", type=float, default=-16.0, help="Spectator follow pitch.")
    parser.add_argument("--follow-smoothing", type=float, default=0.18, help="Spectator smoothing factor.")
    parser.add_argument("--overview-height", type=float, default=140.0, help="Fixed overview height.")
    parser.add_argument("--overview-pitch", type=float, default=-88.0, help="Fixed overview pitch.")
    parser.add_argument("--duration-seconds", type=float, default=0.0, help="Optional auto-exit duration.")
    parser.add_argument(
        "--result-dir",
        type=Path,
        default=Path("results/manual_sequence"),
        help="Directory where evaluation JSON files are stored.",
    )
    parser.add_argument(
        "--trajectory-sample-interval",
        type=float,
        default=0.10,
        help="Interval in seconds between recorded trajectory samples.",
    )
    parser.add_argument(
        "--path-sample-step",
        type=float,
        default=1.0,
        help="Reference path sampling step in meters.",
    )
    parser.add_argument(
        "--path-tolerance",
        type=float,
        default=1.5,
        help="Distance threshold in meters used for path match scoring.",
    )
    parser.add_argument(
        "--offroad-margin",
        type=float,
        default=0.25,
        help="Extra margin in meters added to road half-width before marking course departure.",
    )
    parser.add_argument(
        "--collision-cooldown-seconds",
        type=float,
        default=0.5,
        help="Debounce window used when counting collision sensor events.",
    )
    parser.add_argument("--keep-vehicle", action="store_true", help="Keep the spawned vehicle after exit.")
    parser.add_argument("--random-seed", type=int, default=7, help="Random seed for vehicle selection.")
    parser.add_argument("--vertex-distance", type=float, default=2.0, help="Mesh vertex distance.")
    parser.add_argument("--max-road-length", type=float, default=50.0, help="Max road mesh chunk length.")
    parser.add_argument("--wall-height", type=float, default=1.0, help="Boundary wall height.")
    parser.add_argument("--additional-width", type=float, default=0.6, help="Extra junction lane width.")
    parser.add_argument("--no-smooth-junctions", action="store_true", help="Disable junction smoothing.")
    parser.add_argument("--no-mesh-visibility", action="store_true", help="Disable visible road mesh.")
    parser.add_argument("--keep-settings", action="store_true", help="Keep current world settings.")
    return parser.parse_args()


def apply_keyboard_control(keys: Any, control: Any) -> Any:
    if keys[pygame.K_w] or keys[pygame.K_UP]:
        control.throttle = min(control.throttle + 0.04, 0.75)
    else:
        control.throttle = 0.0

    if keys[pygame.K_s] or keys[pygame.K_DOWN]:
        control.brake = min(control.brake + 0.2, 1.0)
    else:
        control.brake = 0.0

    if keys[pygame.K_a] or keys[pygame.K_LEFT]:
        control.steer = max(control.steer - 0.05, -0.7)
    elif keys[pygame.K_d] or keys[pygame.K_RIGHT]:
        control.steer = min(control.steer + 0.05, 0.7)
    else:
        control.steer *= 0.6

    control.hand_brake = bool(keys[pygame.K_SPACE])
    return control


def calculate_speed_kmh(vehicle: Any) -> float:
    velocity = vehicle.get_velocity()
    return 3.6 * math.sqrt((velocity.x ** 2) + (velocity.y ** 2) + (velocity.z ** 2))


def set_fixed_overview_from_spawn_points(carla: Any, world: Any, height: float, pitch: float) -> None:
    spawn_points = world.get_map().get_spawn_points()
    if not spawn_points:
        return
    xs = [point.location.x for point in spawn_points]
    ys = [point.location.y for point in spawn_points]
    center_x = (min(xs) + max(xs)) / 2.0
    center_y = (min(ys) + max(ys)) / 2.0
    span = max(max(xs) - min(xs), max(ys) - min(ys), 40.0)
    world.get_spectator().set_transform(
        carla.Transform(
            carla.Location(x=center_x, y=center_y, z=max(height, span * 1.8)),
            carla.Rotation(pitch=pitch, yaw=0.0, roll=0.0),
        )
    )


def load_manifest_for_xodr(xodr_path: Path, manifest_dir: Path) -> dict[str, Any] | None:
    """Load the matching manifest JSON for one generated XODR file if it exists."""

    manifest_path = manifest_dir / f"{xodr_path.stem}.json"
    if not manifest_path.exists():
        return None
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def build_spawn_transform_from_manifest(
    carla: Any,
    world: Any,
    manifest: dict[str, Any],
    z_offset: float,
) -> Any | None:
    """Build one spawn transform from resolved manifest metadata."""

    spawn_point = manifest.get("spawn_point")
    road_config = manifest.get("road_config")
    if isinstance(spawn_point, dict) and isinstance(road_config, dict):
        lane_side = str(spawn_point.get("lane_side", "right")).strip()
        lane_index = max(1, int(spawn_point.get("lane_index", 1)))
        progress_s = float(spawn_point.get("distance_along_start_m", 8.0))
        yaw_offset_deg = float(spawn_point.get("yaw_offset_deg", 0.0))
        lane_id = _lane_id_from_lane_spec(lane_side, lane_index)
        waypoint = _get_waypoint_xodr_with_fallback(
            world,
            road_id=int(road_config.get("road_id", 1)),
            lane_id=lane_id,
            progress_s=progress_s,
            total_length=float(road_config.get("total_length", road_config.get("road_length", 100.0))),
        )
        if waypoint is not None:
            transform = waypoint.transform
            return carla.Transform(
                carla.Location(
                    x=float(transform.location.x),
                    y=float(transform.location.y),
                    z=float(transform.location.z) + float(z_offset),
                ),
                carla.Rotation(
                    yaw=float(transform.rotation.yaw) + yaw_offset_deg,
                    pitch=0.0,
                    roll=0.0,
                ),
            )

    resolved_x = None
    resolved_y = None
    resolved_yaw_deg = None
    if isinstance(spawn_point, dict):
        resolved_x = spawn_point.get("resolved_x")
        resolved_y = spawn_point.get("resolved_y")
        resolved_yaw_deg = spawn_point.get("resolved_yaw_deg")

    if resolved_x is None or resolved_y is None or resolved_yaw_deg is None:
        if isinstance(road_config, dict):
            lane_width = float(road_config.get("lane_width", 4.5))
            resolved_x = 8.0
            resolved_y = 0.5 * lane_width
            resolved_yaw_deg = 0.0

    if resolved_x is None or resolved_y is None or resolved_yaw_deg is None:
        return None

    return carla.Transform(
        carla.Location(
            x=float(resolved_x),
            y=float(resolved_y),
            z=float(z_offset),
        ),
        carla.Rotation(
            yaw=float(resolved_yaw_deg),
            pitch=0.0,
            roll=0.0,
        ),
    )


def _parse_curve_direction(shape_type: str) -> str:
    if shape_type.endswith("_right"):
        return "right"
    return "left"


def _parse_open_course_variant(shape_type: str) -> str | None:
    if not shape_type.startswith("open_course_"):
        return None
    parts = shape_type.split("_")
    if len(parts) < 4:
        return None
    return "_".join(parts[2:-1])


def _build_segments_from_payload(payload: Any) -> list[RoadGeometrySegment]:
    if not isinstance(payload, list):
        return []

    segments: list[RoadGeometrySegment] = []
    for segment_payload in payload:
        if not isinstance(segment_payload, dict):
            continue
        geometry_type = str(segment_payload.get("geometry_type", "")).strip()
        if not geometry_type:
            continue
        segment = RoadGeometrySegment(
            geometry_type=geometry_type,
            length=float(segment_payload.get("length", 0.0)),
            curvature=float(segment_payload.get("curvature", 0.0)),
        )
        segment.validate()
        segments.append(segment)
    return segments


def build_config_from_manifest(
    manifest: dict[str, Any],
    xodr_path: Path,
) -> StraightRoadConfig | None:
    """Rebuild the reference road config used for path evaluation."""

    road_config = manifest.get("road_config")
    if not isinstance(road_config, dict):
        return None

    road_name = str(road_config.get("road_name") or manifest.get("map_id") or xodr_path.stem)
    road_id = int(road_config.get("road_id", 1))
    lane_width = float(road_config.get("lane_width", 4.5))
    lanes_per_direction = int(road_config.get("lanes_per_direction", 1))
    speed_limit_mps = float(road_config.get("speed_limit_mps", 10.0))
    start_x = float(road_config.get("start_x", 0.0))
    start_y = float(road_config.get("start_y", 0.0))
    heading_rad = float(road_config.get("heading_rad", 0.0))

    try:
        segments = _build_segments_from_payload(road_config.get("segments"))
    except (TypeError, ValueError):
        segments = []
    if segments:
        return build_open_course_config(
            road_name=road_name,
            road_id=road_id,
            lane_width=lane_width,
            lanes_per_direction=lanes_per_direction,
            segments=segments,
            speed_limit_mps=speed_limit_mps,
            start_x=start_x,
            start_y=start_y,
            heading_rad=heading_rad,
        )

    shape_type = str(manifest.get("shape_type", ""))
    curve_direction = _parse_curve_direction(shape_type)
    course_variant = _parse_open_course_variant(shape_type) or "adaptive"
    auto_generation = manifest.get("auto_generation")
    if isinstance(auto_generation, dict):
        resolved_direction = str(auto_generation.get("curve_direction", curve_direction)).strip()
        if resolved_direction in {"left", "right"}:
            curve_direction = resolved_direction
        resolved_variant = str(auto_generation.get("course_variant", course_variant)).strip()
        if resolved_variant:
            course_variant = resolved_variant

    level = manifest.get("level")
    if isinstance(level, (int, float)):
        try:
            config = build_straight_road_config_from_level(
                map_id=road_name,
                level=float(level),
                road_id=road_id,
                include_curve=shape_type.startswith("straight_arc_"),
                stadium_track=shape_type.startswith("stadium_track_"),
                open_course=shape_type.startswith("open_course_"),
                curve_direction=curve_direction,
                course_variant=course_variant,
                lane_width_override=lane_width,
                straight_length_override=(
                    float(road_config["road_length"])
                    if shape_type.startswith("stadium_track_") and "road_length" in road_config
                    else None
                ),
                track_radius_override=(
                    float(road_config["track_radius"])
                    if shape_type.startswith("stadium_track_") and "track_radius" in road_config
                    else None
                ),
            )
        except Exception:
            config = None
        if config is not None:
            config.start_x = start_x
            config.start_y = start_y
            config.heading_rad = heading_rad
            config.speed_limit_mps = speed_limit_mps
            config.lanes_per_direction = lanes_per_direction
            return config

    return StraightRoadConfig(
        road_name=road_name,
        road_id=road_id,
        road_length=float(road_config.get("road_length", 100.0)),
        curve_length=float(road_config.get("curve_length", 0.0)),
        curve_curvature=float(road_config.get("curve_curvature", 0.0)),
        lane_width=lane_width,
        lanes_per_direction=lanes_per_direction,
        speed_limit_mps=speed_limit_mps,
        start_x=start_x,
        start_y=start_y,
        heading_rad=heading_rad,
        track_radius=float(road_config.get("track_radius", 0.0)),
    )


def build_finish_line_contract_from_manifest(manifest: dict[str, Any]) -> FinishLineContract:
    """Resolve the finish-line contract stored alongside one generated map."""

    default_contract = build_default_finish_line_contract()
    payload = manifest.get("finish_line")
    if not isinstance(payload, dict):
        return default_contract

    lane_side = str(payload.get("lane_side", default_contract.lane_side)).strip()
    if lane_side not in {"left", "right"}:
        lane_side = default_contract.lane_side

    distance_before_end_m = float(
        payload.get("distance_before_end_m", default_contract.distance_before_end_m)
    )
    if (
        payload.get("resolved_s") is None
        and distance_before_end_m >= 12.0
        and str(manifest.get("shape_type", "")).startswith("open_course_")
    ):
        distance_before_end_m = default_contract.distance_before_end_m

    return FinishLineContract(
        distance_before_end_m=distance_before_end_m,
        lane_side=lane_side,
        lane_index=max(1, int(payload.get("lane_index", default_contract.lane_index))),
        lateral_offset_m=float(
            payload.get("lateral_offset_m", default_contract.lateral_offset_m)
        ),
        half_width_m=float(payload.get("half_width_m", default_contract.half_width_m)),
    )


def _lane_id_from_lane_spec(lane_side: str, lane_index: int) -> int:
    """Convert one lane side/index pair into the OpenDRIVE lane id used by CARLA."""

    normalized_lane_index = max(1, int(lane_index))
    if lane_side == "right":
        return -normalized_lane_index
    if lane_side == "left":
        return normalized_lane_index
    raise ValueError("lane_side must be 'left' or 'right'")


def _get_waypoint_xodr_with_fallback(
    world: Any,
    *,
    road_id: int,
    lane_id: int,
    progress_s: float,
    total_length: float,
) -> Any | None:
    """Resolve one CARLA waypoint from road/lane/s with small end-of-road fallback offsets."""

    map_object = world.get_map()
    clamped_progress_s = max(0.0, min(float(progress_s), float(total_length)))
    candidate_offsets = (0.0, -0.05, 0.05, -0.25, 0.25, -0.5, 0.5)
    tried_positions: set[float] = set()

    for offset_m in candidate_offsets:
        candidate_s = max(0.0, min(float(total_length), clamped_progress_s + offset_m))
        rounded_s = round(candidate_s, 6)
        if rounded_s in tried_positions:
            continue
        tried_positions.add(rounded_s)
        waypoint = map_object.get_waypoint_xodr(road_id, lane_id, candidate_s)
        if waypoint is not None:
            return waypoint

    return None


def _sample_lane_path_from_world(
    world: Any,
    *,
    road_id: int,
    lane_id: int,
    total_length: float,
    sample_step_m: float,
) -> list[PathPoint]:
    """Sample one lane-center path from the actually loaded CARLA map."""

    if sample_step_m <= 0:
        raise ValueError("sample_step_m must be greater than 0")

    path_points: list[PathPoint] = []
    sample_count = max(1, int(math.ceil(total_length / sample_step_m)))
    for sample_index in range(sample_count + 1):
        progress_s = min(total_length, sample_index * sample_step_m)
        waypoint = _get_waypoint_xodr_with_fallback(
            world,
            road_id=road_id,
            lane_id=lane_id,
            progress_s=progress_s,
            total_length=total_length,
        )
        if waypoint is None:
            continue
        location = waypoint.transform.location
        heading_rad = math.radians(float(waypoint.transform.rotation.yaw))
        path_points.append(
            PathPoint(
                x=float(location.x),
                y=float(location.y),
                s=float(progress_s),
                heading_rad=heading_rad,
            )
        )

    return path_points


def _sample_reference_midpoint_at_s(
    world: Any,
    *,
    road_id: int,
    total_length: float,
    progress_s: float,
) -> tuple[float, float] | None:
    """Sample one road-center midpoint between the inner left/right driving lanes."""

    left_waypoint = _get_waypoint_xodr_with_fallback(
        world,
        road_id=road_id,
        lane_id=1,
        progress_s=progress_s,
        total_length=total_length,
    )
    right_waypoint = _get_waypoint_xodr_with_fallback(
        world,
        road_id=road_id,
        lane_id=-1,
        progress_s=progress_s,
        total_length=total_length,
    )
    if left_waypoint is None and right_waypoint is None:
        return None
    if left_waypoint is None:
        left_waypoint = right_waypoint
    if right_waypoint is None:
        right_waypoint = left_waypoint
    if left_waypoint is None or right_waypoint is None:
        return None

    left_location = left_waypoint.transform.location
    right_location = right_waypoint.transform.location
    return (
        float((left_location.x + right_location.x) * 0.5),
        float((left_location.y + right_location.y) * 0.5),
    )


def _estimate_reference_heading_rad(
    world: Any,
    *,
    road_id: int,
    total_length: float,
    progress_s: float,
    current_midpoint: tuple[float, float],
) -> float:
    """Estimate the road-center tangent by differencing nearby center points."""

    current_x, current_y = current_midpoint
    sample_step_m = max(0.5, min(2.0, total_length * 0.01))
    next_progress_s = min(total_length, progress_s + sample_step_m)
    previous_progress_s = max(0.0, progress_s - sample_step_m)

    next_midpoint = None
    previous_midpoint = None
    if next_progress_s > progress_s + 1e-6:
        next_midpoint = _sample_reference_midpoint_at_s(
            world,
            road_id=road_id,
            total_length=total_length,
            progress_s=next_progress_s,
        )
    if previous_progress_s < progress_s - 1e-6:
        previous_midpoint = _sample_reference_midpoint_at_s(
            world,
            road_id=road_id,
            total_length=total_length,
            progress_s=previous_progress_s,
        )

    if next_midpoint is not None and previous_midpoint is not None:
        delta_x = next_midpoint[0] - previous_midpoint[0]
        delta_y = next_midpoint[1] - previous_midpoint[1]
    elif next_midpoint is not None:
        delta_x = next_midpoint[0] - current_x
        delta_y = next_midpoint[1] - current_y
    elif previous_midpoint is not None:
        delta_x = current_x - previous_midpoint[0]
        delta_y = current_y - previous_midpoint[1]
    else:
        waypoint = _get_waypoint_xodr_with_fallback(
            world,
            road_id=road_id,
            lane_id=-1,
            progress_s=progress_s,
            total_length=total_length,
        )
        if waypoint is None:
            waypoint = _get_waypoint_xodr_with_fallback(
                world,
                road_id=road_id,
                lane_id=1,
                progress_s=progress_s,
                total_length=total_length,
            )
        if waypoint is None:
            return 0.0
        return math.radians(float(waypoint.transform.rotation.yaw))

    if abs(delta_x) < 1e-6 and abs(delta_y) < 1e-6:
        return 0.0
    return math.atan2(delta_y, delta_x)


def _sample_reference_path_from_world(
    world: Any,
    *,
    road_id: int,
    total_length: float,
    sample_step_m: float,
) -> list[PathPoint]:
    """Sample the loaded road centerline from the inner left/right driving lanes."""

    if sample_step_m <= 0:
        raise ValueError("sample_step_m must be greater than 0")

    path_points: list[PathPoint] = []
    sample_count = max(1, int(math.ceil(total_length / sample_step_m)))
    for sample_index in range(sample_count + 1):
        progress_s = min(total_length, sample_index * sample_step_m)
        reference_point = _sample_reference_path_point_at_s(
            world,
            road_id=road_id,
            total_length=total_length,
            progress_s=progress_s,
        )
        if reference_point is None:
            continue
        path_points.append(reference_point)

    return path_points


def _sample_reference_path_point_at_s(
    world: Any,
    *,
    road_id: int,
    total_length: float,
    progress_s: float,
) -> PathPoint | None:
    """Sample one road-center point from the inner left/right driving lanes."""

    midpoint = _sample_reference_midpoint_at_s(
        world,
        road_id=road_id,
        total_length=total_length,
        progress_s=progress_s,
    )
    if midpoint is None:
        return None
    midpoint_x, midpoint_y = midpoint
    return PathPoint(
        x=midpoint_x,
        y=midpoint_y,
        s=float(progress_s),
        heading_rad=_estimate_reference_heading_rad(
            world,
            road_id=road_id,
            total_length=total_length,
            progress_s=progress_s,
            current_midpoint=midpoint,
        ),
    )


def build_finish_line_from_world(
    manifest: dict[str, Any],
    world: Any,
    config: StraightRoadConfig,
    finish_line_contract: FinishLineContract,
    *,
    use_road_center_target: bool = False,
) -> FinishLine | None:
    """Resolve the finish line from the actually loaded CARLA road end."""

    payload = manifest.get("finish_line")
    if not isinstance(payload, dict):
        payload = {}

    resolved_road_id = int(payload.get("resolved_road_id", config.road_id))
    resolved_lane_id = int(
        payload.get(
            "resolved_lane_id",
            _lane_id_from_lane_spec(
                finish_line_contract.lane_side,
                finish_line_contract.lane_index,
            ),
        )
    )
    finish_line_progress_s = float(
        payload.get(
            "resolved_s",
            max(0.0, config.total_length - finish_line_contract.distance_before_end_m),
        )
    )
    resolved_half_width_m = float(
        payload.get(
            "resolved_half_width_m",
            payload.get("half_width_m", finish_line_contract.half_width_m),
        )
    )
    if resolved_half_width_m <= 0:
        resolved_half_width_m = config.lane_width * config.lanes_per_direction

    if use_road_center_target:
        reference_point = _sample_reference_path_point_at_s(
            world,
            road_id=resolved_road_id,
            total_length=config.total_length,
            progress_s=finish_line_progress_s,
        )
        if reference_point is None:
            return None
        finish_x = reference_point.x
        finish_y = reference_point.y
        heading_rad = reference_point.heading_rad
    else:
        waypoint = _get_waypoint_xodr_with_fallback(
            world,
            road_id=resolved_road_id,
            lane_id=resolved_lane_id,
            progress_s=finish_line_progress_s,
            total_length=config.total_length,
        )
        if waypoint is None:
            return None
        location = waypoint.transform.location
        finish_x = float(location.x)
        finish_y = float(location.y)
        heading_rad = math.radians(float(waypoint.transform.rotation.yaw))

    return FinishLine(
        x=finish_x,
        y=finish_y,
        s=float(finish_line_progress_s),
        heading_rad=heading_rad,
        half_width_m=resolved_half_width_m,
    )


def build_finish_line_from_config(
    config: StraightRoadConfig,
    target_path: list[PathPoint],
    finish_line_contract: FinishLineContract,
) -> FinishLine:
    """Build one explicit finish line from the reconstructed path metadata."""

    if not target_path:
        raise ValueError("target_path must contain at least one point")

    finish_line_progress_s = max(
        0.0,
        target_path[-1].s - finish_line_contract.distance_before_end_m,
    )
    finish_path_point = interpolate_path_point(target_path, finish_line_progress_s)
    road_half_width_m = config.lane_width * config.lanes_per_direction
    finish_half_width_m = (
        finish_line_contract.half_width_m
        if finish_line_contract.half_width_m > 0
        else road_half_width_m
    )
    return FinishLine(
        x=finish_path_point.x,
        y=finish_path_point.y,
        s=finish_line_progress_s,
        heading_rad=finish_path_point.heading_rad,
        half_width_m=finish_half_width_m,
    )


def build_evaluation_context(
    *,
    manifest: dict[str, Any],
    xodr_path: Path,
    world: Any,
    vehicle: Any,
    args: argparse.Namespace,
) -> XodrEvaluationContext | None:
    """Build the path-evaluation state for one generated XODR map."""

    config = build_config_from_manifest(manifest, xodr_path)
    if config is None:
        return None

    finish_line_contract = build_finish_line_contract_from_manifest(manifest)
    training_stage = str(manifest.get("training_stage", "track")).strip().lower()
    evaluation_target_mode = str(
        manifest.get("evaluation_target_mode")
        or manifest.get("road_config", {}).get("evaluation_target_mode")
        or resolve_evaluation_target_mode(config.lanes_per_direction)
    ).strip()
    if evaluation_target_mode not in {"road_center_corridor", "lane_center_guidance"}:
        evaluation_target_mode = resolve_evaluation_target_mode(config.lanes_per_direction)
    road_reference_path = _sample_reference_path_from_world(
        world,
        road_id=config.road_id,
        total_length=config.total_length,
        sample_step_m=args.path_sample_step,
    )
    raw_target_path = _sample_lane_path_from_world(
        world,
        road_id=config.road_id,
        lane_id=_lane_id_from_lane_spec(
            finish_line_contract.lane_side,
            finish_line_contract.lane_index,
        ),
        total_length=config.total_length,
        sample_step_m=args.path_sample_step,
    )
    if len(road_reference_path) < 2:
        road_reference_path = sample_path_from_config(
            config,
            sample_step_m=args.path_sample_step,
        )
    if len(raw_target_path) < 2:
        raw_target_path = sample_path_from_config(
            config,
            sample_step_m=args.path_sample_step,
            lane_side=finish_line_contract.lane_side,
            lane_index=finish_line_contract.lane_index,
            lateral_offset_m=finish_line_contract.lateral_offset_m,
        )
    target_path = (
        list(road_reference_path)
        if uses_road_center_target(evaluation_target_mode)
        else list(raw_target_path)
    )

    finish_line = build_finish_line_from_world(
        manifest,
        world,
        config,
        finish_line_contract,
        use_road_center_target=uses_road_center_target(evaluation_target_mode),
    )
    if finish_line is None:
        finish_line = build_finish_line_from_config(
            config,
            target_path,
            finish_line_contract,
        )
    collision_sensor, collision_state = attach_collision_sensor(
        world,
        vehicle,
        cooldown_seconds=args.collision_cooldown_seconds,
    )
    return XodrEvaluationContext(
        config=config,
        finish_line_contract=finish_line_contract,
        road_reference_path=road_reference_path,
        raw_target_path=raw_target_path,
        target_path=target_path,
        evaluation_target_mode=evaluation_target_mode,
        finish_line=finish_line,
        finish_marker_actors=[],
        show_centerline=(training_stage in {"intermediate", "practical"}),
        collision_sensor=collision_sensor,
        collision_state=collision_state,
        trajectory_samples=[],
        started_monotonic=time.monotonic(),
    )


def record_trajectory_sample(
    evaluation_context: XodrEvaluationContext,
    vehicle: Any,
    *,
    force: bool = False,
    sample_interval_sec: float = 0.10,
) -> None:
    """Append one trajectory sample if enough time has passed."""

    now_monotonic = time.monotonic()
    elapsed_sec = now_monotonic - evaluation_context.started_monotonic
    if (
        not force
        and elapsed_sec - evaluation_context.last_sample_time_sec < sample_interval_sec
    ):
        return

    transform = vehicle.get_transform()
    evaluation_context.trajectory_samples.append(
        TrajectorySample(
            timestamp_sec=elapsed_sec,
            x=float(transform.location.x),
            y=float(transform.location.y),
            z=float(transform.location.z),
            speed_kmh=calculate_speed_kmh(vehicle),
        )
    )
    evaluation_context.last_sample_time_sec = elapsed_sec


def _resolve_evaluation_outcome(
    path_summary: PathEvaluationSummary,
    collision_count: int,
) -> tuple[bool, str | None]:
    """Return the success flag and failure reason for one evaluated drive."""

    if collision_count > 0:
        return False, "collision"
    if path_summary.offroad_sample_count > 0:
        return False, "course_departure"
    if path_summary.opposite_lane_ratio >= 0.35:
        return False, "wrong_lane"
    if not path_summary.crossed_finish_line:
        return False, "not_finished"
    return True, None


def _compute_driving_score_from_summary(
    path_summary: PathEvaluationSummary,
    *,
    success: bool,
    failure_reason: str | None,
    collision_count: int,
) -> float:
    """Mirror the result-driven map-generation score for live HUD feedback."""

    return compute_episode_driving_score(
        completion_ratio=path_summary.completion_ratio,
        path_tracking_score=path_summary.path_tracking_score,
        crossed_finish_line=path_summary.crossed_finish_line,
        offroad_ratio=path_summary.offroad_ratio,
        collision_count=collision_count,
        failure_reason=failure_reason,
        success=success,
        lane_discipline_score=path_summary.lane_discipline_score,
        lane_departure_ratio=path_summary.lane_departure_ratio,
        opposite_lane_ratio=path_summary.opposite_lane_ratio,
    )


def _resolve_effective_road_half_width_m(config: StraightRoadConfig) -> float:
    """Return the usable road half-width including one shoulder when available."""

    return (
        (config.lane_width * config.lanes_per_direction)
        + float(getattr(config, "shoulder_width", 0.0))
    )


def _apply_finish_cross_override(
    path_summary: PathEvaluationSummary,
    *,
    finish_crossed: bool,
) -> PathEvaluationSummary:
    """Keep HUD/save evaluation aligned once runtime finish acceptance already happened."""

    if not finish_crossed or path_summary.crossed_finish_line:
        return path_summary
    return replace(
        path_summary,
        completion_ratio=1.0,
        crossed_finish_line=True,
        finish_line_remaining_m=0.0,
    )


def build_finish_score_overlay(
    evaluation_context: XodrEvaluationContext,
    vehicle: Any,
    *,
    path_tolerance_m: float,
    offroad_margin_m: float,
) -> FinishScoreOverlay:
    """Evaluate the run at finish-cross time and return one HUD-friendly summary."""

    record_trajectory_sample(
        evaluation_context,
        vehicle,
        force=True,
        sample_interval_sec=0.0,
    )
    trajectory_samples = evaluation_context.trajectory_samples
    if evaluation_context.finish_sample_count is not None:
        trajectory_samples = trajectory_samples[: evaluation_context.finish_sample_count]
    path_summary = evaluate_trajectory_against_paths(
        trajectory_samples,
        target_path=evaluation_context.target_path,
        road_reference_path=evaluation_context.road_reference_path,
        raw_target_path=evaluation_context.raw_target_path,
        road_half_width_m=_resolve_effective_road_half_width_m(
            evaluation_context.config
        ),
        finish_line=evaluation_context.finish_line,
        path_tolerance_m=path_tolerance_m,
        offroad_margin_m=offroad_margin_m,
        lane_half_width_m=(evaluation_context.config.lane_width * 0.5),
        lane_guidance_active=(
            evaluation_context.evaluation_target_mode == "lane_center_guidance"
        ),
    )
    path_summary = _apply_finish_cross_override(
        path_summary,
        finish_crossed=evaluation_context.finish_crossed_override,
    )
    collision_count = int(evaluation_context.collision_state.get("count", 0))
    success, failure_reason = _resolve_evaluation_outcome(
        path_summary,
        collision_count,
    )
    driving_score = _compute_driving_score_from_summary(
        path_summary,
        success=success,
        failure_reason=failure_reason,
        collision_count=collision_count,
    )
    time_sec = (
        evaluation_context.trajectory_samples[-1].timestamp_sec
        if evaluation_context.trajectory_samples
        else 0.0
    )
    return FinishScoreOverlay(
        success=success,
        failure_reason=failure_reason,
        driving_score=driving_score,
        time_sec=time_sec,
        collision_count=collision_count,
        path_match_score=path_summary.path_match_score,
        path_tracking_score=path_summary.path_tracking_score,
        lane_discipline_score=path_summary.lane_discipline_score,
        lane_departure_ratio=path_summary.lane_departure_ratio,
        opposite_lane_ratio=path_summary.opposite_lane_ratio,
        offroad_ratio=path_summary.offroad_ratio,
        completion_ratio=path_summary.completion_ratio,
        mean_lateral_error_m=path_summary.mean_lateral_error_m,
    )


def draw_finish_score_overlay(
    display: Any,
    *,
    width: int,
    height: int,
    title_font: Any,
    body_font: Any,
    overlay: FinishScoreOverlay,
) -> None:
    """Draw one compact score card after the finish line is crossed."""

    panel_width = 420
    panel_height = 214
    panel = pygame.Surface((panel_width, panel_height), pygame.SRCALPHA)
    panel.fill((12, 16, 20, 210))
    panel_rect = panel.get_rect()
    panel_center_y = min(height - (panel_height // 2) - 18, int(height * 0.82))
    panel_rect.center = (width // 2, panel_center_y)
    display.blit(panel, panel_rect.topleft)

    title = "FINISH SCORE" if overlay.success else "FINISH EVALUATION"
    title_surface = title_font.render(title, True, (255, 255, 255))
    display.blit(title_surface, (panel_rect.x + 18, panel_rect.y + 14))

    outcome_text = "success" if overlay.success else str(overlay.failure_reason or "review")
    lines = [
        f"Score: {overlay.driving_score * 100.0:5.1f} / 100",
        f"Outcome: {outcome_text}",
        (
            f"Time: {overlay.time_sec:5.1f}s   "
            f"Path: {overlay.path_tracking_score * 100.0:5.1f}%"
        ),
        (
            f"Lane: {overlay.lane_discipline_score * 100.0:5.1f}%   "
            f"Raw match: {overlay.path_match_score * 100.0:5.1f}%"
        ),
        (
            f"Lane dep: {overlay.lane_departure_ratio * 100.0:4.1f}%   "
            f"Wrong lane: {overlay.opposite_lane_ratio * 100.0:4.1f}%"
        ),
        (
            f"Completion: {overlay.completion_ratio * 100.0:5.1f}%   "
            f"Offroad: {overlay.offroad_ratio * 100.0:4.1f}%"
        ),
        f"Mean err: {overlay.mean_lateral_error_m:4.2f}m   Collisions: {overlay.collision_count}",
    ]
    current_y = panel_rect.y + 52
    for line in lines:
        line_surface = body_font.render(line, True, (230, 230, 230))
        display.blit(line_surface, (panel_rect.x + 18, current_y))
        current_y += 22


def save_manual_xodr_evaluation(
    *,
    evaluation_context: XodrEvaluationContext,
    vehicle: Any,
    xodr_path: Path,
    manifest_path: Path,
    manifest: dict[str, Any],
    result_dir: Path,
    path_tolerance_m: float,
    offroad_margin_m: float,
    end_reason: str,
    vehicle_profile: Any,
    driver_profile: Any,
    input_binding: Any,
    blueprint_id: str,
) -> Path:
    """Evaluate one manually driven XODR run and save the result JSON file."""

    record_trajectory_sample(
        evaluation_context,
        vehicle,
        force=True,
        sample_interval_sec=0.0,
    )
    trajectory_samples = evaluation_context.trajectory_samples
    if evaluation_context.finish_sample_count is not None:
        trajectory_samples = trajectory_samples[: evaluation_context.finish_sample_count]
    path_summary = evaluate_trajectory_against_paths(
        trajectory_samples,
        target_path=evaluation_context.target_path,
        road_reference_path=evaluation_context.road_reference_path,
        raw_target_path=evaluation_context.raw_target_path,
        road_half_width_m=_resolve_effective_road_half_width_m(
            evaluation_context.config
        ),
        finish_line=evaluation_context.finish_line,
        path_tolerance_m=path_tolerance_m,
        offroad_margin_m=offroad_margin_m,
        lane_half_width_m=(evaluation_context.config.lane_width * 0.5),
        lane_guidance_active=(
            evaluation_context.evaluation_target_mode == "lane_center_guidance"
        ),
    )
    path_summary = _apply_finish_cross_override(
        path_summary,
        finish_crossed=evaluation_context.finish_crossed_override,
    )
    collision_count = int(evaluation_context.collision_state.get("count", 0))
    success, failure_reason = _resolve_evaluation_outcome(
        path_summary,
        collision_count,
    )

    last_timestamp = 0.0
    if evaluation_context.trajectory_samples:
        last_timestamp = evaluation_context.trajectory_samples[-1].timestamp_sec

    map_id = str(manifest.get("map_id") or xodr_path.stem)
    output_name = (
        f"{map_id}_"
        f"{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}_"
        f"{end_reason}.json"
    )
    result = EpisodeResult(
        map_id=map_id,
        success=success,
        time_sec=last_timestamp,
        collision_count=collision_count,
        offroad_ratio=path_summary.offroad_ratio,
        failure_reason=failure_reason,
        path_match_score=path_summary.path_match_score,
        path_tracking_score=path_summary.path_tracking_score,
        lane_discipline_score=path_summary.lane_discipline_score,
        lane_departure_ratio=path_summary.lane_departure_ratio,
        opposite_lane_ratio=path_summary.opposite_lane_ratio,
        mean_lateral_error_m=path_summary.mean_lateral_error_m,
        max_lateral_error_m=path_summary.max_lateral_error_m,
        completion_ratio=path_summary.completion_ratio,
        crossed_finish_line=path_summary.crossed_finish_line,
        sample_count=path_summary.sample_count,
        metadata={
            "source_xodr_path": str(xodr_path),
            "manifest_path": str(manifest_path),
            "shape_type": manifest.get("shape_type"),
            "spawn_point": manifest.get("spawn_point"),
            "finish_line": {
                "distance_before_end_m": (
                    evaluation_context.finish_line_contract.distance_before_end_m
                ),
                "lane_side": evaluation_context.finish_line_contract.lane_side,
                "lane_index": evaluation_context.finish_line_contract.lane_index,
                "lateral_offset_m": (
                    evaluation_context.finish_line_contract.lateral_offset_m
                ),
                "half_width_m": evaluation_context.finish_line_contract.half_width_m,
                "resolved_x": evaluation_context.finish_line.x,
                "resolved_y": evaluation_context.finish_line.y,
                "resolved_s": evaluation_context.finish_line.s,
                "resolved_heading_rad": evaluation_context.finish_line.heading_rad,
            },
            "path_tolerance_m": path_tolerance_m,
            "offroad_margin_m": offroad_margin_m,
            "evaluation_target_mode": evaluation_context.evaluation_target_mode,
            "raw_path_reference_mode": "lane_center_guidance",
            "lane_half_width_m": evaluation_context.config.lane_width * 0.5,
            "finish_line_half_width_m": evaluation_context.finish_line.half_width_m,
            "finish_line_remaining_m": path_summary.finish_line_remaining_m,
            "end_reason": end_reason,
            "vehicle_profile": vehicle_profile.describe(),
            "driver_profile": driver_profile.describe(),
            "input_binding": input_binding.describe(),
            "vehicle_blueprint": blueprint_id,
            "road_config": manifest.get("road_config"),
            "auto_generation": manifest.get("auto_generation"),
            "baseline_suite": manifest.get("baseline_suite"),
        },
    )
    saved_path = save_episode_result(result, result_dir / output_name)
    print(f"Saved evaluation result: {saved_path}")
    print(
        "Evaluation summary: "
        f"success={result.success}, "
        f"failure_reason={result.failure_reason}, "
        f"collisions={result.collision_count}, "
        f"offroad_ratio={result.offroad_ratio:.3f}, "
        f"path_score={result.path_tracking_score:.3f}, "
        f"lane_score={result.lane_discipline_score:.3f}, "
        f"path_match={result.path_match_score:.3f}, "
        f"lane_departure={result.lane_departure_ratio:.3f}, "
        f"wrong_lane={result.opposite_lane_ratio:.3f}, "
        f"mean_error={result.mean_lateral_error_m:.3f}m, "
        f"completion={result.completion_ratio:.3f}, "
        f"crossed_finish_line={result.crossed_finish_line}"
    )
    return saved_path


def wait_for_spawn_stabilization(
    vehicle: Any,
    target_x: float,
    target_y: float,
    timeout_sec: float = 1.5,
) -> None:
    """Wait briefly until CARLA settles the newly spawned vehicle onto the road mesh."""

    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        transform = vehicle.get_transform()
        distance_xy = math.sqrt(
            ((transform.location.x - target_x) ** 2)
            + ((transform.location.y - target_y) ** 2)
        )
        if distance_xy < 3.0 and transform.location.z < 1.0:
            return
        time.sleep(0.05)


def _vehicle_finish_trigger_offset_m(vehicle: Any) -> float:
    """Approximate the front-bumper offset so finish timing matches the visible stripe."""

    try:
        return max(0.8, float(vehicle.bounding_box.extent.x))
    except Exception:
        return 1.8


def main() -> None:
    args = parse_args()
    random.seed(args.random_seed)
    xodr_path = args.xodr_path.resolve()
    manifest_dir = args.manifest_dir.resolve()
    manifest_path = manifest_dir / f"{xodr_path.stem}.json"
    if not xodr_path.exists():
        print("The requested .xodr file does not exist.")
        print(f"Path: {xodr_path}")
        raise SystemExit(1)

    width, height = [int(value) for value in args.resolution.split("x")]
    pygame.init()
    pygame.font.init()
    display = pygame.display.set_mode((width, height))
    pygame.display.set_caption("AutoDrive Manual XODR Demo")
    font = pygame.font.SysFont("Consolas", 20)
    overlay_title_font = pygame.font.SysFont("Consolas", 28, bold=True)
    overlay_body_font = pygame.font.SysFont("Consolas", 20)

    vehicle = None
    camera = None
    camera_view = None
    evaluation_context: XodrEvaluationContext | None = None
    external_driver_process = None
    external_driver_backend = str(args.driver_backend).strip().lower() or "manual"
    if external_driver_backend == "manual":
        if str(args.driver_module_path or "").strip():
            external_driver_backend = "external_module"
        elif str(args.external_driver_command or "").strip():
            external_driver_backend = "external_command"
    external_driver_active = external_driver_backend == "external_command"
    external_module_active = external_driver_backend == "external_module"
    driver_module = None
    driver_control_override = None
    driver_control_hint = ""
    vehicle_config_overrides = load_vehicle_integration_config(args.vehicle_config_path)
    resolved_blueprint_filter = (
        str(vehicle_config_overrides.get("blueprint_filter", "")).strip()
        or args.blueprint_filter
    )
    resolved_preferred_blueprint_id = (
        args.preferred_blueprint_id
        or str(vehicle_config_overrides.get("preferred_blueprint_id", "")).strip()
        or None
    )
    resolved_role_name = (
        str(args.role_name or "").strip()
        or str(vehicle_config_overrides.get("role_name", "")).strip()
        or "hero"
    )
    resolved_color = str(vehicle_config_overrides.get("color", "")).strip() or None

    vehicle_profile = create_builtin_vehicle_profile(
        profile_name="manual_xodr_demo_vehicle",
        blueprint_filter=resolved_blueprint_filter,
        preferred_blueprint_id=resolved_preferred_blueprint_id,
        role_name=resolved_role_name,
        color=resolved_color,
        notes="Application-owned vehicle profile for existing XODR manual driving.",
    )
    if external_module_active:
        if not str(args.driver_module_path or "").strip():
            print("External module driving was enabled, but no driver module file was provided.")
            raise SystemExit(1)
        driver_module, driver_control_override, driver_control_hint = load_driver_control_module(
            str(args.driver_module_path)
        )
        driver_profile = create_external_driver_profile(
            profile_name="manual_xodr_external_module",
            external_entrypoint=args.driver_module_path,
            notes=(
                "User-supplied Python keyboard-control module loaded by the AED app "
                "for a quick manual-driving integration check."
            ),
            runtime_options={
                "backend": "external_module",
                "driver_module_path": args.driver_module_path,
            },
        )
    elif external_driver_active:
        if not str(args.external_driver_command or "").strip():
            print("External driver integration was enabled, but no launch command was provided.")
            raise SystemExit(1)
        driver_profile = create_external_driver_profile(
            profile_name="manual_xodr_external_driver",
            external_entrypoint=args.external_driver_command,
            notes=(
                "User-supplied external driving command launched after the AED app spawns "
                "the ego vehicle on the generated XODR map."
            ),
            runtime_options={
                "backend": "external_command",
                "working_dir": args.external_driver_working_dir,
                "startup_wait_seconds": args.external_driver_startup_wait,
            },
        )
    else:
        driver_profile = create_manual_driver_profile(
            notes="Manual keyboard driving backend used after loading an externally generated XODR map."
        )
    input_binding = create_split_input_binding(
        vehicle_profile=vehicle_profile,
        driver_profile=driver_profile,
        notes="Vehicle spawn is still owned by the AED app while driving stays manual.",
    )

    try:
        carla, client, _ = create_client(
            host=args.host,
            port=args.port,
            timeout=args.timeout,
            pythonapi_path=args.pythonapi_path,
        )
        generation_parameters = create_generation_parameters(carla, args)
        world = load_opendrive_world(
            client,
            xodr_path.read_text(encoding="utf-8"),
            generation_parameters,
            args.keep_settings,
        )
        manifest = load_manifest_for_xodr(xodr_path, manifest_dir)
        blueprint = resolve_vehicle_blueprint_for_profile(
            world=world,
            vehicle_profile=vehicle_profile,
            preferred_blueprint_id=resolved_preferred_blueprint_id,
        )
        spawn_transform = None
        if manifest is not None:
            spawn_transform = build_spawn_transform_from_manifest(
                carla=carla,
                world=world,
                manifest=manifest,
                z_offset=args.spawn_height_offset,
            )
        if spawn_transform is None:
            selected_spawn = select_spawn_point(world, args.spawn_index)
            spawn_transform = build_centered_spawn_transform(
                world=world,
                reference_transform=selected_spawn,
                z_offset=args.spawn_height_offset,
            )
        vehicle = world.spawn_actor(blueprint, spawn_transform)
        wait_for_spawn_stabilization(
            vehicle,
            target_x=float(spawn_transform.location.x),
            target_y=float(spawn_transform.location.y),
        )
        if external_driver_active:
            print("Launching external driving command for the app-owned XODR ego vehicle...")
            external_driver_process = launch_external_driver_process(
                str(args.external_driver_command),
                working_dir=args.external_driver_working_dir,
                environment=build_external_driver_environment(
                    host=args.host,
                    port=args.port,
                    role_name=vehicle_profile.role_name,
                    training_stage=args.training_stage,
                    pythonapi_path=args.pythonapi_path,
                    blueprint_id=blueprint.id,
                    xodr_path=str(xodr_path),
                ),
                startup_wait_seconds=float(args.external_driver_startup_wait),
            )
        camera, camera_view = create_camera_sensor(
            world=world,
            carla=carla,
            vehicle=vehicle,
            width=width,
            height=height,
            camera_distance=args.camera_distance,
            camera_height=args.camera_height,
            camera_pitch=args.camera_pitch,
        )
        if manifest is None:
            print("Evaluation disabled: matching manifest was not found.")
        else:
            try:
                evaluation_context = build_evaluation_context(
                    manifest=manifest,
                    xodr_path=xodr_path,
                    world=world,
                    vehicle=vehicle,
                    args=args,
                )
            except Exception as error:
                evaluation_context = None
                print("Evaluation disabled: manifest metadata could not be converted into a path model.")
                print(f"Reason: {error}")
            else:
                evaluation_context.finish_marker_actors = spawn_finish_line_marker_props(
                    carla=carla,
                    world=world,
                    finish_line=evaluation_context.finish_line,
                    finish_line_is_road_center=uses_road_center_target(
                        evaluation_context.evaluation_target_mode
                    ),
                )
                print(f"Evaluation enabled. Result directory: {args.result_dir.resolve()}")

        if args.spectator_mode == "fixed-overview":
            set_fixed_overview_from_spawn_points(
                carla=carla,
                world=world,
                height=args.overview_height,
                pitch=args.overview_pitch,
            )

        print("Manual XODR demo vehicle spawned successfully.")
        print(f"Loaded map: {world.get_map().name}")
        print(f"Source XODR: {xodr_path}")
        print(f"Manifest found: {manifest is not None}")
        print(f"Vehicle blueprint: {blueprint.id}")
        print(f"Vehicle profile: {vehicle_profile.describe()}")
        print(f"Driver profile: {driver_profile.describe()}")
        print(f"Input binding: {input_binding.describe()}")
        if args.vehicle_config_path:
            print(f"Vehicle config file: {args.vehicle_config_path}")
        if external_driver_active:
            print(
                "External driver command: "
                f"{args.external_driver_command} "
                f"(cwd={args.external_driver_working_dir or 'current'}, "
                f"wait={float(args.external_driver_startup_wait):.1f}s)"
            )
        if external_module_active:
            print(
                "External driver module: "
                f"{args.driver_module_path} "
                f"(hint={driver_control_hint or 'custom keyboard mapping'})"
            )
        if evaluation_context is not None:
            print(
                "Finish line: "
                f"before_end={evaluation_context.finish_line_contract.distance_before_end_m:.1f}m, "
                f"s={evaluation_context.finish_line.s:.1f}m, "
                f"x={evaluation_context.finish_line.x:.1f}, "
                f"y={evaluation_context.finish_line.y:.1f}"
            )
            print(
                "Evaluation target: "
                f"{evaluation_context.evaluation_target_mode} "
                "(raw lane-center metric retained)"
            )
        if external_driver_active:
            print("Controls: ESC exit (external driving stack owns throttle / steer / brake)")
        elif external_module_active:
            print(
                "Controls: "
                f"{driver_control_hint or 'custom keyboard mapping from external module'}"
            )
        else:
            print("Controls: WASD / Arrow keys, Space hand brake, ESC exit")

        saved_result_path: Path | None = None
        show_result_comparison = False
        show_adaptation_preview = False
        comparison_panel_top = 18
        adaptation_panel_top = 214

        def finalize_drive(end_reason: str) -> None:
            nonlocal saved_result_path
            if saved_result_path is not None:
                return
            if evaluation_context is None or manifest is None or vehicle is None:
                return
            try:
                saved_result_path = save_manual_xodr_evaluation(
                    evaluation_context=evaluation_context,
                    vehicle=vehicle,
                    xodr_path=xodr_path,
                    manifest_path=manifest_path,
                    manifest=manifest,
                    result_dir=args.result_dir.resolve(),
                    path_tolerance_m=args.path_tolerance,
                    offroad_margin_m=args.offroad_margin,
                    end_reason=end_reason,
                    vehicle_profile=vehicle_profile,
                    driver_profile=driver_profile,
                    input_binding=input_binding,
                    blueprint_id=blueprint.id,
                )
            except Exception as error:
                print("Failed to save manual XODR evaluation.")
                print(f"Reason: {error}")

        control = carla.VehicleControl()
        spectator_state = None
        clock = pygame.time.Clock()
        end_time = None if args.duration_seconds <= 0 else time.time() + args.duration_seconds

        while end_time is None or time.time() < end_time:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    finalize_drive("window_closed")
                    return
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        finalize_drive("user_exit")
                        return
                    if (
                        evaluation_context is not None
                        and evaluation_context.finish_score_overlay is not None
                        and event.key in (pygame.K_1, pygame.K_KP1)
                    ):
                        show_result_comparison = not show_result_comparison
                    if (
                        evaluation_context is not None
                        and evaluation_context.finish_score_overlay is not None
                        and event.key in (pygame.K_2, pygame.K_KP2)
                    ):
                        show_adaptation_preview = not show_adaptation_preview

            if external_driver_active:
                if external_driver_process is not None and external_driver_process.poll() is not None:
                    print("External driving command exited. Finishing the current XODR drive.")
                    finalize_drive("external_driver_exit")
                    return
            elif external_module_active:
                keys = pygame.key.get_pressed()
                control = driver_control_override(keys, control, pygame)
                vehicle.apply_control(control)
            else:
                keys = pygame.key.get_pressed()
                control = apply_keyboard_control(keys, control)
                vehicle.apply_control(control)

            if evaluation_context is not None:
                record_trajectory_sample(
                    evaluation_context,
                    vehicle,
                    force=False,
                    sample_interval_sec=args.trajectory_sample_interval,
                )
            if args.spectator_mode == "follow":
                spectator_state = update_follow_vehicle_spectator(
                    carla=carla,
                    world=world,
                    vehicle=vehicle,
                    follow_distance=args.follow_distance,
                    follow_height=args.follow_height,
                    follow_pitch=args.follow_pitch,
                    smoothing=args.follow_smoothing,
                    state=spectator_state,
                )

            if camera_view is not None and camera_view.surface is not None:
                display.blit(camera_view.surface, (0, 0))
                if evaluation_context is not None:
                    if evaluation_context.show_centerline:
                        draw_centerline_overlay(
                            display,
                            pygame=pygame,
                            carla=carla,
                            camera=camera,
                            path_points=evaluation_context.road_reference_path,
                        )
                    draw_finish_line_marker(
                        carla=carla,
                        world=world,
                        finish_line=evaluation_context.finish_line,
                        finish_line_is_road_center=uses_road_center_target(
                            evaluation_context.evaluation_target_mode
                        ),
                    )
                    draw_finish_line_overlay(
                        display,
                        pygame=pygame,
                        carla=carla,
                        world=world,
                        camera=camera,
                        finish_line=evaluation_context.finish_line,
                        finish_line_is_road_center=uses_road_center_target(
                            evaluation_context.evaluation_target_mode
                        ),
                    )
            else:
                display.fill((30, 30, 30))

            lines = [
                f"Map: {world.get_map().name}",
                f"XODR: {xodr_path.name}",
                f"Vehicle: {blueprint.id}",
                f"Speed: {calculate_speed_kmh(vehicle):5.1f} km/h",
            ]
            if evaluation_context is not None:
                transform = vehicle.get_transform()
                target_projection = project_point_to_path(
                    float(transform.location.x),
                    float(transform.location.y),
                    evaluation_context.target_path,
                )
                road_projection = project_point_to_path(
                    float(transform.location.x),
                    float(transform.location.y),
                    evaluation_context.road_reference_path,
                )
                finish_trigger_progress_s = (
                    target_projection.progress_s + _vehicle_finish_trigger_offset_m(vehicle)
                )
                finish_line_remaining_m = max(
                    0.0,
                    evaluation_context.finish_line.s - finish_trigger_progress_s,
                )
                offroad_threshold = (
                    evaluation_context.config.lane_width
                    * evaluation_context.config.lanes_per_direction
                ) + args.offroad_margin
                crossed_finish_now = (
                    evaluation_context.finish_score_overlay is None
                    and finish_trigger_progress_s >= evaluation_context.finish_line.s
                    and road_projection.distance_m <= offroad_threshold
                )
                if crossed_finish_now:
                    evaluation_context.finish_crossed_override = True
                    evaluation_context.finish_score_overlay = build_finish_score_overlay(
                        evaluation_context,
                        vehicle,
                        path_tolerance_m=args.path_tolerance,
                        offroad_margin_m=args.offroad_margin,
                    )
                    evaluation_context.finish_sample_count = len(
                        evaluation_context.trajectory_samples
                    )
                    print(
                        "Finish line crossed. "
                        f"Runtime score={evaluation_context.finish_score_overlay.driving_score * 100.0:.1f}, "
                        f"outcome={'success' if evaluation_context.finish_score_overlay.success else evaluation_context.finish_score_overlay.failure_reason}"
                    )
                lines.extend(
                    [
                        (
                            "Tracking: "
                            f"progress {target_projection.progress_ratio * 100.0:5.1f}% / "
                            f"lane error {target_projection.distance_m:4.2f}m"
                        ),
                        (
                            "Evaluation: "
                            f"collisions {int(evaluation_context.collision_state.get('count', 0))} / "
                            f"road dist {road_projection.distance_m:4.2f}m / "
                            f"limit {offroad_threshold:4.2f}m"
                        ),
                        (
                            "Finish: "
                            f"remaining {finish_line_remaining_m:5.1f}m / "
                            f"half width {evaluation_context.finish_line.half_width_m:4.1f}m"
                        ),
                        f"Eval target: {evaluation_context.evaluation_target_mode}",
                    ]
                )
                if evaluation_context.finish_score_overlay is not None:
                    lines.append(
                        f"Finish score: {evaluation_context.finish_score_overlay.driving_score * 100.0:5.1f} / 100"
                    )
                    lines.append("Review: 1 comparison / 2 next adjustment / ESC exit")
            else:
                lines.append("Evaluation: disabled (manifest metadata unavailable)")
                if external_driver_active:
                    lines.append("Controls: ESC / external driver active")
                elif external_module_active:
                    lines.append(
                        f"Controls: {driver_control_hint or 'external driver module active'}"
                    )
                else:
                    lines.append("Controls: W/A/S/D or arrows, Space, ESC")

            y = 16
            for line in lines:
                display.blit(font.render(line, True, (255, 255, 255)), (16, y))
                y += 24

            if (
                evaluation_context is not None
                and evaluation_context.finish_score_overlay is not None
            ):
                draw_finish_score_overlay(
                    display,
                    width=width,
                    height=height,
                    title_font=overlay_title_font,
                    body_font=overlay_body_font,
                    overlay=evaluation_context.finish_score_overlay,
                )
                current_result = build_episode_result_from_overlay(
                    map_id=str(manifest.get("map_id") or xodr_path.stem),
                    overlay=evaluation_context.finish_score_overlay,
                    metadata={
                        "level": manifest.get("level"),
                        "shape_type": manifest.get("shape_type"),
                    },
                )
                if show_result_comparison:
                    comparison_lines = build_result_comparison_lines(
                        current_result=current_result,
                        result_dir=args.result_dir.resolve(),
                        exclude_paths=(
                            {saved_result_path.resolve()} if saved_result_path is not None else None
                        ),
                    )
                    draw_review_panel(
                        display,
                        pygame=pygame,
                        width=width,
                        top=comparison_panel_top,
                        anchor="right",
                        title_font=overlay_title_font,
                        body_font=overlay_body_font,
                        title="RESULT COMPARISON (1)",
                        lines=comparison_lines,
                    )
                if show_adaptation_preview:
                    adaptation_lines = build_track_adaptation_lines(
                        current_result=current_result,
                        current_level=float(manifest.get("level", 0.30)),
                    )
                    draw_review_panel(
                        display,
                        pygame=pygame,
                        width=width,
                        top=adaptation_panel_top,
                        anchor="right",
                        title_font=overlay_title_font,
                        body_font=overlay_body_font,
                        title="NEXT MAP PREVIEW (2)",
                        lines=adaptation_lines,
                    )

            pygame.display.flip()
            clock.tick_busy_loop(60)

        finalize_drive("duration_timeout")
    finally:
        terminate_external_driver_process(external_driver_process)
        if evaluation_context is not None:
            for finish_marker_actor in evaluation_context.finish_marker_actors:
                destroy_actor(finish_marker_actor)
            destroy_actor(evaluation_context.collision_sensor)
        if camera is not None:
            destroy_actor(camera)
        if vehicle is not None and not args.keep_vehicle:
            destroy_actor(vehicle)
        pygame.quit()


if __name__ == "__main__":
    main()
